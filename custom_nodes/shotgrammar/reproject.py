"""Depth-based camera reprojection: pure numpy/cv2, no ComfyUI imports.

Approach: forward splat. Every source pixel is unprojected to 3D using its
metric-ish depth, moved into the target camera, projected, and splatted with a
k x k footprint (k = ceil of the local magnification) in far-to-near order so the
nearest surface wins (z-buffer). Unwritten pixels are the disocclusion hole mask.

Cameras are axis-aligned dicts: {"pos": (x, y, z), "focal_px": f, "cx": .., "cy": ..}
(cx/cy optional, default image centre). +z points into the scene; moving the
camera forward means pos z increases.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

NEAR = 1.0  # metric-ish z of inverse-depth 1.0
FAR = 10.0  # metric-ish z of inverse-depth 0.0
DEFAULT_FOV_DEG = 60.0


# ---------------------------------------------------------------- easing
def linear(t):
    return np.asarray(t, dtype=np.float64)


def ease_in_out(t):
    t = np.asarray(t, dtype=np.float64)
    return t * t * (3.0 - 2.0 * t)


def impact(t):
    """Fast start, hard settle."""
    t = np.asarray(t, dtype=np.float64)
    return 1.0 - (1.0 - t) ** 5


def slowmo_settle(t):
    """Slow start, then a long soft landing (smootherstep)."""
    t = np.asarray(t, dtype=np.float64)
    return t * t * t * (t * (6.0 * t - 15.0) + 10.0)


EASES = {"linear": linear, "ease_in_out": ease_in_out, "impact": impact, "slowmo_settle": slowmo_settle}


def _progress(n_frames: int, ease: str) -> np.ndarray:
    if n_frames == 1:
        return np.zeros(1)
    return EASES[ease](np.linspace(0.0, 1.0, n_frames))


# ---------------------------------------------------------------- geometry
def focal_from_fov(width: int, fov_deg: float = DEFAULT_FOV_DEG) -> float:
    return 0.5 * width / math.tan(math.radians(fov_deg) / 2.0)


def inverse_depth_to_z(depth: np.ndarray, near: float = NEAR, far: float = FAR) -> np.ndarray:
    """Relative inverse depth (1 = near) -> metric-ish z in [near, far]."""
    d = np.clip(np.asarray(depth, dtype=np.float32), 0.0, 1.0)
    return 1.0 / (d * (1.0 / near - 1.0 / far) + 1.0 / far)


def depth_to_points(depth, fov_deg: float = DEFAULT_FOV_DEG, near: float = NEAR, far: float = FAR):
    """Depth [H,W] (0..1, near=1) -> camera-space points [H,W,3] (x right, y down, z forward)."""
    h, w = depth.shape
    z = inverse_depth_to_z(depth, near, far)
    f = focal_from_fov(w, fov_deg)
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return np.stack([(u - (w - 1) / 2) * z / f, (v - (h - 1) / 2) * z / f, z], axis=-1)


def reproject_frame(image, depth, cam_from, cam_to, out_size=None, near=NEAR, far=FAR):
    """Forward-splat `image` from cam_from into cam_to.

    Focal lengths are in source-pixel units and are scaled if out_size (w, h) differs.
    Returns (frame uint8 [h,w,3], hole_mask uint8 [h,w], 255 = hole).
    """
    H, W = image.shape[:2]
    ow, oh = out_size if out_size is not None else (W, H)
    if depth.shape != (H, W):
        depth = cv2.resize(depth.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    z = inverse_depth_to_z(depth, near, far).reshape(-1)
    uu, vv = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))

    f0 = cam_from["focal_px"]
    cx0, cy0 = cam_from.get("cx", (W - 1) / 2), cam_from.get("cy", (H - 1) / 2)
    f1 = cam_to["focal_px"]
    cx1, cy1 = cam_to.get("cx", (W - 1) / 2), cam_to.get("cy", (H - 1) / 2)
    s = ow / W
    d = np.array(cam_from.get("pos", (0, 0, 0)), dtype=np.float32) - np.array(
        cam_to.get("pos", (0, 0, 0)), dtype=np.float32
    )

    x = (uu.reshape(-1) - cx0) * z / f0 + d[0]
    y = (vv.reshape(-1) - cy0) * z / f0 + d[1]
    zc = z + d[2]
    front = zc > 0.05
    safe = np.where(front, zc, 1.0)
    pu = (f1 * x / safe + cx1) * s
    pv = (f1 * y / safe + cy1) * s

    # Local magnification of the source pixel grid (1 = identity) sets the footprint.
    mag = float(np.percentile((f1 * s / safe) * (z / f0), 99)) if front.any() else 1.0
    k = int(min(4, max(1, math.ceil(mag - 1e-3))))

    shift = 0.5 - (k - 1) / 2.0
    bu, bv = np.floor(pu + shift).astype(np.int32), np.floor(pv + shift).astype(np.int32)
    src = np.arange(z.size)
    idxs, zs, srcs = [], [], []
    for dy in range(k):
        for dx in range(k):
            tu, tv = bu + dx, bv + dy
            ok = front & (tu >= 0) & (tu < ow) & (tv >= 0) & (tv < oh)
            idxs.append(tv[ok] * ow + tu[ok])
            zs.append(zc[ok])
            srcs.append(src[ok])
    idx, zz, sr = np.concatenate(idxs), np.concatenate(zs), np.concatenate(srcs)
    order = np.argsort(-zz, kind="stable")  # far first; nearest is written last and wins
    idx, sr = idx[order], sr[order]

    out = np.zeros((oh * ow, 3), dtype=np.uint8)
    filled = np.zeros(oh * ow, dtype=bool)
    out[idx] = image.reshape(-1, 3)[sr]
    filled[idx] = True
    hole = np.where(filled, 0, 255).astype(np.uint8)
    return out.reshape(oh, ow, 3), hole.reshape(oh, ow)


# ---------------------------------------------------------------- moves
def _bbox_z(depth, bbox) -> float:
    x0, y0, x1, y1 = (int(v) for v in bbox)
    patch = depth[max(0, y0):max(1, y1), max(0, x0):max(1, x1)]
    return float(np.median(inverse_depth_to_z(patch)))


def _cam0(image):
    return {"pos": (0.0, 0.0, 0.0), "focal_px": focal_from_fov(image.shape[1])}


def fill_holes(frame: np.ndarray, hole: np.ndarray, radius: int = 3) -> np.ndarray:
    """Fill disocclusion holes (hole==255) with neighbouring content so LTX guides carry
    no black regions. Thin holes: Telea inpaint. Wide holes: inpaint a downscaled copy and
    upsample the fill, which keeps the cost bounded for dolly-out plates."""
    if not hole.any():
        return frame
    if hole.mean() < 255 * 0.08:
        return cv2.inpaint(frame, hole, radius, cv2.INPAINT_TELEA)
    h, w = hole.shape
    small = cv2.resize(frame, (max(w // 4, 8), max(h // 4, 8)), interpolation=cv2.INTER_AREA)
    small_hole = cv2.resize(hole, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(small, small_hole, radius, cv2.INPAINT_TELEA)
    up = cv2.resize(filled, (w, h), interpolation=cv2.INTER_LINEAR)
    m = (hole > 0)[..., None]
    return np.where(m, up, frame).astype(np.uint8)


def fit_depth(depth: np.ndarray, image: np.ndarray) -> np.ndarray:
    """Depth estimators return maps at their own size; resize to the image before use."""
    h, w = image.shape[:2]
    if depth.shape[:2] == (h, w):
        return depth
    return cv2.resize(depth.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


def _run(image, depth, cam0, cams_to):
    frames, masks = zip(*(reproject_frame(image, depth, cam0, c) for c in cams_to))
    return np.stack(frames), np.stack(masks)


def move_dolly_zoom(image, depth, n_frames, subject_bbox, dolly_distance=0.4, direction="in", ease="ease_in_out"):
    """Vertigo. dolly_distance is a fraction of the subject's z; the focal length
    follows focal_t = focal_0 * (z_s - dolly_t) / z_s so the subject keeps its size.
    bbox is in pixels (x0, y0, x1, y1)."""
    cam0 = _cam0(image)
    zs = _bbox_z(depth, subject_bbox)
    sign = 1.0 if direction == "in" else -1.0
    cams = []
    for p in _progress(n_frames, ease):
        t = sign * dolly_distance * zs * float(p)
        cams.append({"pos": (0.0, 0.0, t), "focal_px": cam0["focal_px"] * (zs - t) / zs})
    return _run(image, depth, cam0, cams)


def move_crash_zoom(image, depth, n_frames, target_bbox, zoom_factor=3.0, ease="impact", parallax=0.15):
    """Fast push onto target_bbox (pixels); the last frame has the target centred at zoom_factor x."""
    cam0 = _cam0(image)
    h, w = image.shape[:2]
    c0x, c0y = (w - 1) / 2, (h - 1) / 2
    tx, ty = (target_bbox[0] + target_bbox[2]) / 2, (target_bbox[1] + target_bbox[3]) / 2
    zt = _bbox_z(depth, target_bbox)
    cams = []
    for p in _progress(n_frames, ease):
        p = float(p)
        scale = 1.0 + (zoom_factor - 1.0) * p
        dz = parallax * zt * p
        cams.append(
            {
                "pos": (0.0, 0.0, dz),
                "focal_px": cam0["focal_px"] * scale * (zt - dz) / zt,
                # target pixel travels linearly from its place to frame centre
                "cx": tx + p * (c0x - tx) - scale * (tx - c0x),
                "cy": ty + p * (c0y - ty) - scale * (ty - c0y),
            }
        )
    return _run(image, depth, cam0, cams)


def move_push(image, depth, n_frames, distance=0.3, ease="ease_in_out"):
    """Dolly with fixed focal and parallax. distance is a fraction of the median
    scene z; negative pulls out."""
    cam0 = _cam0(image)
    zmed = float(np.median(inverse_depth_to_z(depth)))
    cams = [
        {"pos": (0.0, 0.0, distance * zmed * float(p)), "focal_px": cam0["focal_px"]}
        for p in _progress(n_frames, ease)
    ]
    return _run(image, depth, cam0, cams)


# ---------------------------------------------------------------- measurement
def _best_scale(gray, tmpl, scales):
    best, best_s = -2.0, 1.0
    for s in scales:
        t = cv2.resize(tmpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if min(t.shape) < 8 or t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
            continue
        score = float(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED).max())
        if score > best:
            best, best_s = score, float(s)
    return best_s


def measure_bbox_scale(frames, template_bbox):
    """Per-frame scale of the region template_bbox (x0,y0,x1,y1 in frame-0 pixels),
    by multi-scale template matching against each frame. Returns float array [N]."""
    gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    x0, y0, x1, y1 = (int(round(v)) for v in template_bbox)
    tmpl = gray[0][y0:y1, x0:x1]
    coarse = np.exp(np.linspace(math.log(0.4), math.log(8.0), 90))
    out = []
    for g in gray:
        s = _best_scale(g, tmpl, coarse)
        out.append(_best_scale(g, tmpl, s * np.linspace(0.95, 1.05, 21)))
    return np.array(out)
