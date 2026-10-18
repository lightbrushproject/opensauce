"""Speed ramp: frame-timing remap. Pure numpy, no ComfyUI imports.

A curve maps normalised output time t in [0, 1] to normalised source time u in [0, 1]
(monotonic non-decreasing, u(0)=0, u(1)=1). Output frame i samples source position
u(i/(n_out-1)) * (n_in-1), blending the two neighbouring frames (or nearest).
"""
from __future__ import annotations

import numpy as np

CURVES = ["linear", "slow_mo_settle", "speed_up", "impact", "accelerate"]
HIT_SOURCE = 0.4  # fraction of the source consumed by the slow approach in `impact`
HOLD = 0.06  # output-time fraction held on the hit


def time_curve(name: str, t: np.ndarray, hit_at: float = 0.6) -> np.ndarray:
    t = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    if name == "linear":
        return t
    if name == "slow_mo_settle":  # fast start, long slow tail
        return 1.0 - (1.0 - t) ** 3
    if name == "speed_up":
        return t**2
    if name == "accelerate":  # speed_up that starts at hit_at x the average speed (no stall after a cut)
        s0 = float(np.clip(hit_at, 0.0, 1.0))
        return s0 * t + (1.0 - s0) * t**2
    if name == "impact":
        hit = float(np.clip(hit_at, 0.05, 0.9))
        end_hold = min(hit + HOLD, 0.97)
        u = np.empty_like(t)
        a = t < hit
        u[a] = HIT_SOURCE * (t[a] / hit) ** 1.5  # slow approach
        h = (t >= hit) & (t < end_hold)
        u[h] = HIT_SOURCE  # brief hold on the hit
        r = t >= end_hold
        s = (t[r] - end_hold) / (1.0 - end_hold)
        u[r] = HIT_SOURCE + (1.0 - HIT_SOURCE) * (1.0 - (1.0 - s) ** 3)  # hard release
        return u
    raise ValueError(f"unknown curve {name!r}")


def source_positions(n_in: int, n_out: int, curve: str, hit_at: float = 0.6) -> np.ndarray:
    """Fractional source frame index for each output frame."""
    t = np.linspace(0.0, 1.0, n_out) if n_out > 1 else np.zeros(1)
    return time_curve(curve, t, hit_at) * (n_in - 1)


def speed_ramp(frames: np.ndarray, curve: str = "linear", out_frames: int | None = None,
               hit_at: float = 0.6, blend: bool = True) -> np.ndarray:
    """frames: (N,H,W,C) float array. Returns (out_frames or N, H, W, C) same dtype."""
    n_in = len(frames)
    n_out = n_in if not out_frames else int(out_frames)
    pos = source_positions(n_in, n_out, curve, hit_at)
    if not blend:
        return frames[np.rint(pos).astype(int)].copy()
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, n_in - 1)
    w = (pos - lo).astype(np.float32).reshape(-1, 1, 1, 1)
    out = frames[lo].astype(np.float32) * (1.0 - w) + frames[hi].astype(np.float32) * w
    return out.astype(frames.dtype)
