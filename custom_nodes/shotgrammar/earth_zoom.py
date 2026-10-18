"""Earth Zoom path: a continuous 2D pull-back from an inner stage image to an outer one.

inner_rect = where the inner image sits inside the outer image (normalised x0, y0, x1, y1, same
aspect as the frame). Frame t shows the outer image cropped to a view rectangle that grows
geometrically from inner_rect to the full frame; the inner image is pasted over its footprint
through a HARD mask (a few px of feather) that shrinks to nothing by fade_end, so every pixel of
every frame comes from exactly one plate: no frame is a double exposure for LTX to copy.
Pure numpy/cv2, no ComfyUI imports.
"""
from __future__ import annotations

import cv2
import numpy as np

try:
    from .reproject import EASES
except ImportError:  # loaded as a plain module (tests, scripts)
    from reproject import EASES


def view_rects(inner_rect, n_frames: int, ease: str = "linear") -> np.ndarray:
    """(n, 4) view rectangles in outer-normalised coords, inner_rect -> (0, 0, 1, 1).

    Zoom is linear in log scale (constant perceived speed); the rect shrinks around the
    point that is fixed under the similarity between inner_rect and the full frame.
    """
    x0, y0, x1, y1 = inner_rect
    s = x1 - x0  # inner width as a fraction of the outer width (= height fraction)
    t = EASES[ease](np.linspace(0.0, 1.0, n_frames)) if n_frames > 1 else np.zeros(1)
    size = s ** (1.0 - t)  # s -> 1
    # fixed point f of the map frame -> inner_rect: f = r0 + s * f  =>  f = r0 / (1 - s)
    fx, fy = (x0 / (1 - s), y0 / (1 - s)) if s < 1 else (0.0, 0.0)
    vx0 = fx - size * fx
    vy0 = fy - size * fy
    return np.stack([vx0, vy0, vx0 + size, vy0 + size], axis=1)


def _rect_mask(h: int, w: int, rect, feather_px: float) -> np.ndarray:
    """Float mask of an axis-aligned pixel rect (x0, y0, x1, y1): 1 inside, 0 outside, a linear
    ramp feather_px wide just inside the edge (0 = binary)."""
    x0, y0, x1, y1 = rect
    xs, ys = np.arange(w) + 0.5, np.arange(h) + 0.5
    dx = np.minimum(xs - x0, x1 - xs)
    dy = np.minimum(ys - y0, y1 - ys)
    d = np.minimum(dy[:, None], dx[None, :]).astype(np.float32)
    if feather_px <= 0:
        return (d >= 0).astype(np.float32)
    return np.clip(d / feather_px, 0.0, 1.0)


def subject_plates(inner: np.ndarray, outer: np.ndarray, inner_rect, inner_mask: np.ndarray,
                   outer_mask: np.ndarray, feather_px: float = 3.0, grow_px: int = 12):
    """Make the two plates agree everywhere so the path never mixes two different scenes.

    A free re-render (Qwen zoom-out) keeps the subject but invents a new background, so inner
    and outer disagree inside the footprint. Returns (inner', outer'): outer' = outer with its own
    subject inpainted away inside the footprint (outer_mask grown by grow_px) and the inner subject
    pasted at inner_rect;
    inner' = the inner subject over outer' upscaled to full frame. Masks are float [0, 1] subject
    mattes at each plate's size; they are binarised (feather_px edge), never alpha-blended wide.
    """
    h, w = outer.shape[:2]
    inner = cv2.resize(inner, (w, h), interpolation=cv2.INTER_AREA) if inner.shape[:2] != (h, w) else inner
    im = cv2.resize(inner_mask.astype(np.float32), (w, h)) > 0.5
    om = cv2.resize(outer_mask.astype(np.float32), (w, h)) > 0.5
    k = 2 * grow_px + 1
    x0, y0, x1, y1 = inner_rect
    hole = cv2.dilate(om.astype(np.uint8), np.ones((k, k), np.uint8))
    foot = np.zeros_like(hole)
    foot[int(y0 * h):int(np.ceil(y1 * h)), int(x0 * w):int(np.ceil(x1 * w))] = 1
    hole *= foot  # only inside the footprint: parts of the outer subject the inner crop lacks stay
    clean = cv2.inpaint(outer, hole, 5, cv2.INPAINT_TELEA)
    m = np.array([[x1 - x0, 0, x0 * w], [0, y1 - y0, y0 * h]], np.float64)  # inner frame -> outer px
    f = int(round(feather_px))
    soft = cv2.blur(im.astype(np.float32), (f, f)) if f > 1 else im.astype(np.float32)
    small = cv2.warpAffine(inner, m, (w, h), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    a = cv2.warpAffine(soft, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]
    outer2 = np.clip(small * a + clean * (1 - a) + 0.5, 0, 255).astype(np.uint8)
    bg = cv2.warpAffine(outer2, cv2.invertAffineTransform(m), (w, h), flags=cv2.INTER_LANCZOS4,
                        borderMode=cv2.BORDER_REFLECT)
    a = soft[..., None]
    inner2 = np.clip(inner * a + bg * (1 - a) + 0.5, 0, 255).astype(np.uint8)
    return inner2, outer2


def zoom_path(inner: np.ndarray, outer: np.ndarray, inner_rect, n_frames: int, ease: str = "linear",
              feather: float = 3.0, fade_end: float = 0.5) -> np.ndarray:
    """uint8 (n, H, W, 3) frames; frame 0 == inner, frame n-1 == outer (both at outer's size).

    The inner image shows through a hard rect mask centred on its footprint that shrinks to zero
    by fade_end (fraction of the clip); feather is the mask edge ramp in output pixels.
    """
    h, w = outer.shape[:2]
    inner = cv2.resize(inner, (w, h), interpolation=cv2.INTER_AREA) if inner.shape[:2] != (h, w) else inner
    x0, y0, x1, y1 = inner_rect
    out = np.empty((n_frames, h, w, 3), np.uint8)
    for i, (vx0, vy0, vx1, vy1) in enumerate(view_rects(inner_rect, n_frames, ease)):
        sx, sy = w / ((vx1 - vx0) * w), h / ((vy1 - vy0) * h)
        m = np.array([[sx, 0, -vx0 * w * sx], [0, sy, -vy0 * h * sy]], np.float64)
        frame = cv2.warpAffine(outer, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        if i == 0:
            out[i] = inner
            continue
        # inner footprint inside this view, in output pixels
        ix0, iy0 = (x0 - vx0) * w * sx, (y0 - vy0) * h * sy
        iw, ih = (x1 - x0) * w * sx, (y1 - y0) * h * sy
        mi = np.array([[iw / w, 0, ix0], [0, ih / h, iy0]], np.float64)
        interp = cv2.INTER_AREA if iw < w else cv2.INTER_CUBIC
        warped = cv2.warpAffine(inner, mi, (w, h), flags=interp, borderMode=cv2.BORDER_REPLICATE)
        u = min(i / max(n_frames - 1, 1) / fade_end, 1.0)
        k = 1.0 - u * u * (3 - 2 * u)  # mask size as a fraction of the footprint
        cx, cy = ix0 + iw / 2, iy0 + ih / 2
        a = _rect_mask(h, w, (cx - k * iw / 2, cy - k * ih / 2, cx + k * iw / 2, cy + k * ih / 2), feather)
        a = a[..., None]
        out[i] = np.clip(warped * a + frame * (1 - a) + 0.5, 0, 255).astype(np.uint8)
    out[-1] = outer
    return out


def measure_inner_rect(input_img: np.ndarray, outpainted_img: np.ndarray, scale_hint=(0.2, 0.55),
                       mask: np.ndarray | None = None, coarse_steps: int = 13):
    """Find where the (shrunk) input landed inside the outpainted still.

    Multi-scale normalised cross-correlation of the downscaled input against the still, on
    grayscale blurred intensity plus gradient magnitude (robust to Qwen's colour drift), coarse
    scale sweep over scale_hint (inner width as a fraction of the still width) then a fine sweep.
    Both images are the same frame size. mask (float [0, 1] subject matte of the input) restricts the
    match to the subject: Qwen re-renders the background freely, only the subject survives. coarse_steps = samples of the
    coarse scale sweep (raise it with a wide scale_hint: Qwen may shrink a pasted inset far below the pasted size).
    Returns ((x0, y0, x1, y1) normalised, confidence 0..1).
    """
    h, w = outpainted_img.shape[:2]
    if input_img.shape[:2] != (h, w):
        input_img = cv2.resize(input_img, (w, h), interpolation=cv2.INTER_AREA)
    if isinstance(scale_hint, (int, float)):
        scale_hint = (scale_hint * 0.7, min(scale_hint * 1.4, 0.98))

    def feats(img):
        g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1.0)
        gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
        return g, cv2.magnitude(gx, gy)

    og, oe = feats(outpainted_img)

    tm = None
    if mask is not None:
        tm = (cv2.resize(mask.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8) * 255

    def match(s):
        tw, th = int(round(w * s)), int(round(h * s))
        if tw < 8 or th < 8 or tw >= w or th >= h:
            return -1.0, (0, 0), (tw, th)
        res = None
        small = cv2.resize(input_img, (tw, th), interpolation=cv2.INTER_AREA)
        for src, t in zip((og, oe), feats(small)):
            if tm is not None:
                m = cv2.resize(tm, (tw, th), interpolation=cv2.INTER_NEAREST)
                if m.sum() < 255 * 16:
                    return -1.0, (0, 0), (tw, th)
                r = cv2.matchTemplate(src, t, cv2.TM_CCOEFF_NORMED, mask=(m > 0).astype(np.float32))
                r = np.clip(np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0), -1.0, 1.0)
            else:
                r = cv2.matchTemplate(src, t, cv2.TM_CCOEFF_NORMED)
            res = r if res is None else res + r
        res /= 2.0
        _, mv, _, ml = cv2.minMaxLoc(res)
        return float(mv), ml, (tw, th)

    lo, hi = scale_hint
    coarse = [(match(s), s) for s in np.linspace(lo, hi, coarse_steps)]
    (_, _, _), s0 = max(coarse, key=lambda c: c[0][0])
    step = (hi - lo) / (coarse_steps - 1)
    fine = [(match(s), s) for s in np.linspace(max(s0 - step, 0.05), min(s0 + step, 0.98), 13)]
    (conf, (px, py), (tw, th)), _ = max(fine, key=lambda c: c[0][0])
    return (px / w, py / h, (px + tw) / w, (py + th) / h), max(conf, 0.0)


# ----------------------------------------------------------------------------- N-plate pyramid
# plates[0] = the input photo, plates[k] = an outpaint generated FROM plates[k-1]; rects[k-1] = where plates[k-1]
# sits inside plates[k] (normalised x0, y0, x1, y1, same aspect). The zoom is one continuous similarity through
# the whole stack: constant log-scale rate after a short ease-in, each frame drawn coarse -> fine with the finer
# plate replacing the centre through a hard mask (<= feather px ramp). No dissolves, no end-image blends.

def ease_in_param(n_frames: int, ease_in: float = 0.15) -> np.ndarray:
    """tau(t) in [0, 1]: speed ramps linearly from 0 over the first ease_in of the clip, then constant.
    Continuous position and velocity; tau(0) = 0, tau(1) = 1."""
    t = np.linspace(0.0, 1.0, n_frames) if n_frames > 1 else np.zeros(1)
    a = float(np.clip(ease_in, 0.0, 1.0))
    if a <= 0:
        return t
    norm = 1.0 - a / 2.0
    return np.where(t < a, t * t / (2.0 * a), a / 2.0 + (t - a)) / norm


def compose_rects(rects) -> list:
    """Footprint of every plate inside the top (coarsest) plate, normalised. len(rects) = N gives N + 1 entries;
    the last is (0, 0, 1, 1)."""
    out = [(0.0, 0.0, 1.0, 1.0)]
    for x0, y0, x1, y1 in reversed(list(rects)):  # map coarse -> fine
        prev = out[-1]  # rect of plate k inside top; plate k-1 sits at (x0..x1) inside plate k
        pw, ph = prev[2] - prev[0], prev[3] - prev[1]
        out.append((prev[0] + x0 * pw, prev[1] + y0 * ph, prev[0] + x1 * pw, prev[1] + y1 * ph))
    return out[::-1]


def _view_at(rect, u: float):
    """View rectangle (in the outer plate's coords) at local progress u: rect (u=0) -> full frame (u=1),
    geometric in size around the fixed point of the inner->outer similarity (same law as view_rects)."""
    x0, y0, x1, y1 = rect
    s = x1 - x0
    size = s ** (1.0 - u)
    fx, fy = (x0 / (1 - s), y0 / (1 - s)) if s < 1 else (0.0, 0.0)
    vx0, vy0 = fx - size * fx, fy - size * fy
    return (vx0, vy0, vx0 + size, vy0 + size)


def pyramid_views(rects, n_frames: int, ease_in: float = 0.15):
    """Per frame: (view rect in TOP-plate coords, segment index k (plate k is the one filling the frame, its
    finer neighbour k-1 shrinking inside), local progress u in [0, 1]). Log-scale rate is constant across all
    segments after the ease-in, so a 4x step and a 2.5x step take time proportional to log(4) and log(2.5)."""
    rects = [tuple(map(float, r)) for r in rects]
    comp = compose_rects(rects)
    logs = np.array([-np.log(r[2] - r[0]) for r in rects])
    cum = np.concatenate([[0.0], np.cumsum(logs)])
    tau = ease_in_param(n_frames, ease_in) * cum[-1]
    views, segs, us = [], [], []
    for z in tau:
        k = int(np.clip(np.searchsorted(cum, z, side="right") - 1, 0, len(rects) - 1))
        u = float(np.clip((z - cum[k]) / logs[k], 0.0, 1.0)) if logs[k] > 0 else 1.0
        v = _view_at(rects[k], u)  # in plate k+1 coords
        ox0, oy0, ox1, oy1 = comp[k + 1]  # plate k+1 inside top
        ow, oh = ox1 - ox0, oy1 - oy0
        views.append((ox0 + v[0] * ow, oy0 + v[1] * oh, ox0 + v[2] * ow, oy0 + v[3] * oh))
        segs.append(k + 1)
        us.append(u)
    return np.array(views), np.array(segs), np.array(us)


def segment_switch_frames(rects, n_frames: int, ease_in: float = 0.15) -> list:
    """Frames at which the plate filling the frame changes (plate-switch markers for the diff plot)."""
    _, segs, _ = pyramid_views(rects, n_frames, ease_in)
    return [int(i) for i in np.where(np.diff(segs) != 0)[0] + 1]


def nest_plates(plates, rects, feather_px: float = 3.0) -> list:
    """Return plates where every plate has its finer neighbour pasted (INTER_AREA downscale) at its rect through
    a hard mask (feather_px edge ramp), bottom-up. After this all plates agree inside the nested footprints, so the
    zoom only ever trades resolution, never content, when a finer plate takes over the centre."""
    out = [plates[0]]
    for k, (x0, y0, x1, y1) in enumerate(rects, start=1):
        outer = plates[k]
        h, w = outer.shape[:2]
        inner = out[-1]
        if inner.shape[:2] != (h, w):
            inner = cv2.resize(inner, (w, h), interpolation=cv2.INTER_AREA)
        m = np.array([[x1 - x0, 0, x0 * w], [0, y1 - y0, y0 * h]], np.float64)
        small = cv2.warpAffine(inner, m, (w, h), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
        a = _rect_mask(h, w, (x0 * w, y0 * h, x1 * w, y1 * h), feather_px)[..., None]
        out.append(np.clip(small * a + outer * (1 - a) + 0.5, 0, 255).astype(np.uint8))
    return out


def zoom_pyramid(plates, rects, n_frames: int, ease_in: float = 0.15, feather: float = 3.0, nest: bool = True,
                 min_overlay_px: int = 8, return_map: bool = False, only=None):
    """uint8 (n, H, W, 3) frames of one continuous zoom from plates[0] (frame 0, full frame) out to plates[-1]
    (last frame, full frame). Every pixel of every frame is sampled from exactly one plate, except a <= feather px
    band at a plate edge. With return_map, also returns an int8 (n, H, W) map of the plate index each pixel came
    from (-1 inside the feather band) for the honesty check."""
    plates = list(plates)
    h, w = plates[-1].shape[:2]
    plates = [p if p.shape[:2] == (h, w) else cv2.resize(p, (w, h), interpolation=cv2.INTER_AREA) for p in plates]
    if nest:
        plates = nest_plates(plates, rects, feather)
    comp = compose_rects(rects)
    views, segs, _ = pyramid_views(rects, n_frames, ease_in)
    idx = list(range(n_frames)) if only is None else [int(i) for i in only]  # only: render just these frames, in order
    out = np.empty((len(idx), h, w, 3), np.uint8)
    pmap = np.empty((len(idx), h, w), np.int8) if return_map else None
    for o, i in enumerate(idx):
        v, k = views[i], segs[i]
        vw, vh = v[2] - v[0], v[3] - v[1]
        frame, fmap = None, None
        for j in range(k, -1, -1):  # coarse (plate k fills the view) -> fine
            r = comp[j]
            ax, ay = (r[2] - r[0]) / vw, (r[3] - r[1]) / vh  # output px per plate px
            px0, py0 = (r[0] - v[0]) / vw * w, (r[1] - v[1]) / vh * h
            fw_, fh_ = ax * w, ay * h
            if j < k and (fw_ < min_overlay_px or fh_ < min_overlay_px):
                break
            m = np.array([[ax, 0, px0], [0, ay, py0]], np.float64)
            interp = cv2.INTER_AREA if ax < 1 else cv2.INTER_CUBIC
            warped = cv2.warpAffine(plates[j], m, (w, h), flags=interp, borderMode=cv2.BORDER_REFLECT)
            if frame is None:
                frame = warped.astype(np.float32)
                if return_map:
                    fmap = np.full((h, w), j, np.int8)
                continue
            # feather only where a plate edge lies inside the frame; an edge beyond the frame border is no edge
            e = [px0, py0, px0 + fw_, py0 + fh_]
            e = [-1e9 if e[0] <= 0.5 else e[0], -1e9 if e[1] <= 0.5 else e[1],
                 1e9 if e[2] >= w - 0.5 else e[2], 1e9 if e[3] >= h - 0.5 else e[3]]
            a = _rect_mask(h, w, e, feather)
            if a.max() <= 0:
                continue
            frame = warped * a[..., None] + frame * (1 - a[..., None])
            if return_map:
                fmap[a >= 1.0] = j
                fmap[(a > 0.0) & (a < 1.0)] = -1
        out[o] = np.clip(frame + 0.5, 0, 255).astype(np.uint8)
        if return_map:
            pmap[o] = fmap
        if i == 0:
            out[o] = plates[0]
            if return_map:
                pmap[o] = 0
        elif i == n_frames - 1:
            out[o] = plates[-1]
            if return_map:
                pmap[o] = len(plates) - 1
    return (out, pmap) if return_map else out


def honesty_check(pmap: np.ndarray, feather: float = 3.0) -> dict:
    """Assert no frame is a blend of two plates: pixels marked -1 (inside a feather ramp) must form a band no
    wider than `feather` px along plate edges. Per frame: band width = mixed pixels / band length (half the
    mixed/non-mixed boundary), and the mixed area may not exceed one feather band around the frame perimeter per
    nested plate edge visible in that frame. Returns {ok, worst_frame, worst_band_px, mixed_fraction_max, ...}."""
    h, w = pmap.shape[1:]
    edge = 2.0 * (w + h) * (feather + 1.0) / (w * h)  # one rect edge of at most frame perimeter, feather px wide
    worst, worst_frame, frac_max, over = 0.0, -1, 0.0, []
    for i, fm in enumerate(pmap):
        mixed = fm < 0
        n = int(mixed.sum())
        if n == 0:
            continue
        frac = n / mixed.size
        frac_max = max(frac_max, frac)
        edges = max(len(np.unique(fm[fm >= 0])) - 1, 1)  # nested overlays visible in this frame
        if frac > edges * edge:
            over.append(i)
        bx = int(np.count_nonzero(mixed[:, 1:] != mixed[:, :-1]))
        by = int(np.count_nonzero(mixed[1:, :] != mixed[:-1, :]))
        width = n / max((bx + by) / 2.0, 1.0)  # the band has two sides
        if width > worst:
            worst, worst_frame = width, i
    ok = worst <= feather + 0.5 and not over
    return {"ok": bool(ok), "worst_frame": worst_frame, "worst_band_px": round(float(worst), 2),
            "mixed_fraction_max": round(float(frac_max), 5), "mixed_fraction_bound_per_edge": round(float(edge), 5),
            "frames_over_bound": over[:10], "feather_px": feather}


def edge_score(plate: np.ndarray, rect, band_px: int = 6) -> float:
    """How much of the pasted-canvas border survives as a straight edge in an outpaint: mean gradient magnitude
    along the four sides of rect (normalised) relative to the mean gradient in a ring band_px further out.
    ~1 = no edge, > 2 = a visible straight edge (reject and re-roll)."""
    h, w = plate.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(plate, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1.0)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    x0, y0, x1, y1 = int(rect[0] * w), int(rect[1] * h), int(rect[2] * w), int(rect[3] * h)

    def lines(off):
        vals = []
        for x in (x0 - off, x1 + off):
            if 0 <= x < w:
                vals.append(np.abs(gx[y0:y1, x]).mean())
        for y in (y0 - off, y1 + off):
            if 0 <= y < h:
                vals.append(np.abs(gy[y, x0:x1]).mean())
        return float(np.mean(vals)) if vals else 0.0

    on = max(lines(o) for o in (-1, 0, 1))
    far = np.mean([lines(o) for o in range(band_px, 3 * band_px)]) + 1e-6
    return float(on / far)


def match_tone(inner: np.ndarray, outer: np.ndarray, rect, sigma_frac: float = 0.15,
               clip=(0.6, 1.6)) -> np.ndarray:
    """Grade `inner` so its low frequencies match the outer plate's own (re-rendered) version of it at `rect`:
    a smooth per-channel gain field, blur(outer @ rect) / blur(inner shrunk to rect), upsampled to inner's size.
    Not a blend: every pixel stays inner's pixel times a slowly varying gain. Removes the tone step that makes a
    nested plate read as a lighter/darker rectangle; detail (sharpness) differences are left as they are."""
    h, w = outer.shape[:2]
    x0, y0, x1, y1 = int(round(rect[0] * w)), int(round(rect[1] * h)), int(round(rect[2] * w)), int(round(rect[3] * h))
    rw, rh = max(x1 - x0, 2), max(y1 - y0, 2)
    q = outer[y0:y0 + rh, x0:x0 + rw].astype(np.float32)
    d = cv2.resize(inner, (rw, rh), interpolation=cv2.INTER_AREA).astype(np.float32)
    s = max(sigma_frac * rw, 1.0)
    g = (cv2.GaussianBlur(q, (0, 0), s) + 4.0) / (cv2.GaussianBlur(d, (0, 0), s) + 4.0)
    g = cv2.resize(np.clip(g, *clip), (inner.shape[1], inner.shape[0]), interpolation=cv2.INTER_CUBIC)
    return np.clip(inner.astype(np.float32) * g + 0.5, 0, 255).astype(np.uint8)
