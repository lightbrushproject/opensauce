"""Procedural disintegration guide: the subject breaks into ash and embers from the edges inward.

Pure numpy/cv2. Every frame is the photo where the body is still intact, the clean plate where it has gone,
a grey ash crust + ember rim on the advancing front, and opaque flakes carried off on the wind. Nothing is ever
alpha-blended over the plate, so no guide frame can show a translucent subject. The result is a guide for LTX,
which re-renders it as real ash (sparse keys at ~0.5); it is not meant to be shown as is.
"""
from __future__ import annotations

import cv2
import numpy as np

EMBER = np.array([1.0, 0.48, 0.12], np.float32)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def fbm(h: int, w: int, rng: np.random.Generator, cells=(3, 6, 12, 24, 48)) -> np.ndarray:
    """Smooth multi-scale noise in [0, 1]."""
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for c in cells:
        g = rng.random((max(2, round(c * h / w)), c)).astype(np.float32)
        acc += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
        tot += amp
        amp *= 0.6
    acc /= tot
    return (acc - acc.min()) / max(float(acc.max() - acc.min()), 1e-6)


def death_time(matte: np.ndarray, seed: int = 0, w_core: float = 0.40, w_noise: float = 0.45,
               w_head: float = 0.30, head_frac: float = 0.24, w_side: float = 0.30,
               w_height: float = 0.25) -> np.ndarray:
    """Per-pixel time in [0, 1] at which the body pixel crumbles; -1 outside the subject.

    Thin extremities (hands, fingers, outline) go first via local body density, outstretched hands and arms
    first of all via the lateral distance from the body's centre line; head and neck go last via a
    lateness bonus on the top `head_frac` of the silhouette; coarse fbm noise makes the front ragged in chunks
    (fine noise perforates the body and LTX reads a perforated body as translucent).
    Rank-normalised so the body loses area at a constant rate.
    """
    m = (matte > 0.5).astype(np.uint8)
    h, w = m.shape
    t = np.full((h, w), -1.0, np.float32)
    if not m.any():
        return t
    rng = np.random.default_rng(seed)
    # local body density, not distance to the edge: arms and fingers are sparse and go early, while a thin neck
    # between head and shoulders is dense and is not cut before the chest (no floating head)
    dens = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.05 * min(h, w))
    dn = dens / max(float(dens[m > 0].max()), 1e-6)
    ys = np.nonzero(m)[0]
    y0, y1 = ys.min(), ys.max()
    yrel = np.clip((np.arange(h, dtype=np.float32)[:, None] - y0) / max(y1 - y0, 1), 0, 1)
    head = np.clip((head_frac * 1.5 - yrel) / head_frac, 0, 1)  # 1 on head and neck, fades out over the chest
    xs = np.nonzero(m)[1]
    cx, half = float(np.median(xs)), max(float(np.abs(xs - np.median(xs)).max()), 1.0)
    side = 1.0 - np.clip(np.abs(np.arange(w, dtype=np.float32)[None, :] - cx) / half, 0, 1)  # 1 on the centre line
    # height term: the body crumbles bottom-up overall, so the neck never goes before the chest (no floating head)
    raw = (w_core * dn + w_noise * fbm(h, w, rng, (4, 8, 16, 32)) + w_head * head + w_side * side
           + w_height * (1.0 - yrel))
    inside = m.astype(bool)
    order = raw[inside].argsort().argsort().astype(np.float32)
    t[inside] = (order + 1) / len(order)  # in (0, 1]: nothing is gone at progress 0
    return t


def progress(u: float, start: float, end: float) -> float:
    """Fraction of the body gone at clip time u in [0, 1] (smoothstep between start and end)."""
    x = float(np.clip((u - start) / max(end - start, 1e-6), 0.0, 1.0))
    return x * x * (3 - 2 * x)


def body_fraction(t: np.ndarray, u: float, start: float, end: float) -> float:
    """Fraction of the subject still intact at clip time u (death_time map t)."""
    inside = t >= 0
    return float((t[inside] > progress(u, start, end)).mean()) if inside.any() else 0.0


def make_particles(photo: np.ndarray, t: np.ndarray, seed: int, density: float) -> dict:
    """Flakes sampled from the body: ash grey from the pixel's own luminance, ~40% glowing embers."""
    rng = np.random.default_rng(seed + 1)
    ys, xs = np.nonzero(t >= 0)
    # flake count follows the frame, not the subject: a subject filling the frame must not snow it over
    keep = rng.random(len(ys)) < min(density, density * 0.1 * t.size / max(len(ys), 1))
    ys, xs = ys[keep], xs[keep]
    n = len(ys)
    luma = photo[ys, xs].astype(np.float32) @ LUMA
    ash = (0.35 + 0.45 * luma)[:, None] * np.array([0.92, 0.9, 0.88], np.float32)
    ember = rng.random(n) < 0.4
    col = np.where(ember[:, None], EMBER[None, :] * rng.uniform(0.8, 1.15, (n, 1)), ash).astype(np.float32)
    return {
        "x": xs.astype(np.float32), "y": ys.astype(np.float32), "t": t[ys, xs], "col": np.clip(col, 0, 1),
        "speed": rng.uniform(0.5, 1.4, n).astype(np.float32),
        "life": np.where(ember, rng.uniform(0.3, 0.7, n), rng.uniform(0.18, 0.5, n)).astype(np.float32),
        "phase": rng.uniform(0, 2 * np.pi, n).astype(np.float32),
        "size": 1 + (rng.random(n) < 0.45).astype(np.int32) + (rng.random(n) < 0.15).astype(np.int32),
    }


def render_frame(photo, plate, t, parts, grit, fleck, crack, u, start, end, wind, band=0.035,
                 ash_band=0.55) -> tuple[np.ndarray, np.ndarray]:
    """One guide frame at clip time u and the 0/1 map of pixels covered by flying flakes.

    photo/plate float32 HxWx3 in [0, 1]; grit = crust texture; fleck / crack = 0/1 pale ash specks / crack lines."""
    h, w = t.shape
    scale = max(1, round(min(h, w) / 704))  # flake sizes are tuned on a 704 px short side
    p = progress(u, start, end)
    alive = t > p
    # everything not still body is the plate: the plate equals the photo outside its own feathered matte, so the
    # only seam is that soft feather, never the hard body outline (a hard photo/plate edge reads as a ghost)
    out = np.where(alive[..., None], photo, plate)
    # ash crust: the body greys and cracks ahead of the crumble line; embers glow right at it
    ahead = t - p
    on = alive & (p > 0)
    ash_k = (np.clip(1.8 * (1.0 - ahead / ash_band), 0, 1) * on)[..., None] * 0.97
    # charred crust: dark charcoal with pale ash flecks, low contrast so printed graphics char over instead of
    # floating on as a decal, and dark enough never to be read as a see-through patch of a grey background
    # keep the photo's own shading (folds, face) in the crust so LTX reads burnt material, not a flat cut-out
    shade = cv2.GaussianBlur(photo @ LUMA, (0, 0), max(2.0, min(h, w) / 60))  # broad shading only: no print
    ash_col = (0.07 + 0.13 * shade + 0.06 * grit)[..., None] * np.array([0.95, 0.92, 0.9], np.float32)
    ash_col = np.where((fleck > 0.5)[..., None], np.float32(0.40), ash_col)
    out = out * (1 - ash_k) + ash_col * ash_k
    # glowing cracks run through the charred crust
    out = out + (crack * (ash_k[..., 0] > 0.5))[..., None] * EMBER * 0.35
    # ember glow only on part of the crumbling edge (grit-gated): an even glowing outline reads as a cut-out
    rim = np.clip(1.0 - ahead / band, 0, 1) * on * (grit > 0.55)
    out = out + (rim ** 1.5)[..., None] * EMBER * 0.9
    # flakes: born when their pixel crumbles, carried off on the wind, rising and swirling
    cover = np.zeros((h, w), np.float32)
    age = (u - start) - parts["t"] * (end - start)
    born = (parts["t"] <= p) & (age >= 0) & (age < parts["life"])
    if born.any():
        a = age[born] * parts["speed"][born]
        ph = parts["phase"][born]
        dx = wind[0] * a * w * 1.1 + 0.015 * w * np.sin(ph + a * 18)
        dy = wind[1] * a * h * 0.6 - 0.25 * a * a * h + 0.01 * h * np.cos(ph + a * 14)
        x = (parts["x"][born] + dx).astype(np.int32)
        y = (parts["y"][born] + dy).astype(np.int32)
        col = parts["col"][born]
        size = parts["size"][born] * scale
        for s in range(1, 3 * scale + 1):
            sel = size >= s
            xs, ys, cs = x[sel], y[sel], col[sel]
            for o in range(s):  # grow each flake by one row and one column per size step
                for xx, yy in ((xs + s - 1, ys + o), (xs + o, ys + s - 1)):
                    ok = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
                    out[yy[ok], xx[ok]] = cs[ok]
                    cover[yy[ok], xx[ok]] = 1.0
    return np.clip(out, 0, 1).astype(np.float32), cover


def removal_mask(matte: np.ndarray, grow_frac: float = 0.05, below_frac: float = 0.12) -> np.ndarray:
    """What the clean plate must repaint: the subject grown by `grow_frac` of the short side (glow halos), plus a
    soft floor patch under the feet (contact shadows, light the subject casts on the ground). Float [0, 1]."""
    m = (matte > 0.5).astype(np.uint8)
    h, w = m.shape
    if not m.any():
        return np.zeros((h, w), np.float32)
    r = max(1, round(grow_frac * min(h, w)))
    out = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    ys, xs = np.nonzero(m)
    y1 = int(ys.max())
    if y1 < h - 2 and below_frac > 0:  # feet in frame: cover the ground around and below them
        low = ys > y1 - 0.15 * (y1 - ys.min())
        x0, x1 = xs[low].min(), xs[low].max()
        pad = 0.6 * (x1 - x0) + r
        cx, cy = (x0 + x1) / 2, y1
        ax, ay = (x1 - x0) / 2 + pad, below_frac * h + r
        yy, xx = np.mgrid[0:h, 0:w]
        floor = (((xx - cx) / ax) ** 2 + ((yy - cy) / ay) ** 2 <= 1) & (yy > y1 - 0.05 * h)
        out = out | floor.astype(np.uint8)
    return out.astype(np.float32)


def key_weights(t: np.ndarray, cover: np.ndarray, u: float, start: float, end: float, body: float,
                pin: float = 0.85, wake: float = 0.4) -> np.ndarray:
    """Per-pixel guide strength for one key frame (multiplies the LTXVAddGuide strength via attention_mask).

    The live body gets `body` (LTX re-renders it as real ash); everything already gone and the world get `pin`, so
    LTX has to show the plate there and cannot leave a translucent body behind; pixels under flying flakes, and a
    small margin round them, get `wake` so LTX makes its own flakes instead of copying the guide's dots."""
    p = progress(u, start, end)
    wts = np.full(t.shape, pin, np.float32)
    k = max(3, round(0.006 * min(t.shape)) * 2 + 1)
    wake_px = cv2.dilate(cover.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)
    wts[wake_px] = wake
    wts[t > p] = body
    return wts


def body_strength(u: float, area_frac: float, base: float = 0.5, late: float = 0.12, area_gain: float = 0.2) -> float:
    """Body key strength: higher late in the clip (f48+) and for subjects that fill more of the frame."""
    ramp = float(np.clip((u - 0.42) / 0.12, 0, 1))
    size = float(np.clip((area_frac - 0.12) / 0.3, 0, 1))
    return base + late * ramp + area_gain * size


def disintegrate(photo: np.ndarray, plate: np.ndarray, matte: np.ndarray, n_frames: int = 97,
                 start: float = 0.10, end: float = 0.85, wind_x: float = -1.0, wind_y: float = -0.3,
                 density: float = 0.22, seed: int = 0) -> np.ndarray:
    """Guide sequence (n_frames, H, W, 3) float32. Frame 0 is the photo; by `end` the body is gone."""
    return guide_sequence(photo, plate, matte, n_frames, start, end, wind_x, wind_y, density, seed)[0]


def guide_sequence(photo: np.ndarray, plate: np.ndarray, matte: np.ndarray, n_frames: int = 97,
                   start: float = 0.10, end: float = 0.85, wind_x: float = -1.0, wind_y: float = -0.3,
                   density: float = 0.22, seed: int = 0, body_base: float = 0.5, pin: float = 0.85,
                   wake: float = 0.4) -> tuple[np.ndarray, np.ndarray]:
    """(frames (N, H, W, 3), key weights (N, H, W)) float32; frame 0 is the photo with weight 1."""
    photo = photo.astype(np.float32)
    h, w = photo.shape[:2]
    plate = cv2.resize(plate.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
    matte = cv2.resize(matte.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    t = death_time(matte, seed)
    parts = make_particles(photo, t, seed, density)
    grit = fbm(h, w, np.random.default_rng(seed + 2), (40, 80, 160, 320))
    cn = fbm(h, w, np.random.default_rng(seed + 3), (12, 24, 48))
    crack = (np.abs(cn - 0.5) < 0.007).astype(np.float32)
    rng = np.random.default_rng(seed + 4)
    fleck = (cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (3, 3), 0) > 0.66).astype(np.float32)
    area = float((t >= 0).mean())
    frames, weights = [photo], [np.ones((h, w), np.float32)]
    for i in range(1, n_frames):
        u = i / max(n_frames - 1, 1)
        f, cover = render_frame(photo, plate, t, parts, grit, fleck, crack, u, start, end, (wind_x, wind_y))
        frames.append(f)
        weights.append(key_weights(t, cover, u, start, end, body_strength(u, area, body_base), pin, wake))
    return np.stack(frames), np.stack(weights)
