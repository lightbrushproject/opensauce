"""Grade chips: deterministic per-pixel looks + seeded grain. Pure numpy, no ComfyUI imports.

Frames are float arrays (N,H,W,3) in 0..1. Per chip: gain/lift per channel, gamma, contrast,
saturation, vignette, plus VHS-style chroma shift / softness / scanlines.
"""
from __future__ import annotations

import numpy as np

# gain/lift/gamma are per-channel RGB; gamma > 1 brightens mids.
CHIPS: dict[str, dict] = {
    "none": {},
    "warm_film": dict(gain=(1.06, 1.0, 0.90), lift=(0.02, 0.01, 0.0), gamma=(1.0, 1.0, 0.95), sat=1.05, contrast=1.05),
    "cool_steel": dict(gain=(0.92, 1.0, 1.08), lift=(0.0, 0.01, 0.025), sat=0.8, contrast=1.1),
    "bleach_bypass": dict(sat=0.45, contrast=1.35),
    "teal_orange": dict(gain=(1.12, 1.0, 0.88), lift=(-0.01, 0.03, 0.06), sat=1.15, contrast=1.1),
    "vhs": dict(sat=0.85, contrast=0.92, lift=(0.04, 0.04, 0.05), soft=1.2, chroma_shift=3, scanline=0.12),
    "super8": dict(gain=(1.1, 1.02, 0.84), lift=(0.03, 0.02, 0.0), sat=0.9, contrast=0.95, vignette=0.45, soft=0.6),
}
CHIP_NAMES = list(CHIPS)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _box(img: np.ndarray, sigma: float) -> np.ndarray:
    import cv2

    return cv2.GaussianBlur(img, (0, 0), sigma)


def _vignette(h: int, w: int, strength: float) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2
    return (1.0 - strength * np.clip(r2 / 2.0, 0, 1) ** 1.2)[..., None].astype(np.float32)


def apply_chip(frames: np.ndarray, chip: str, grain_amount: float = 0.0, seed: int = 0) -> np.ndarray:
    """Return graded frames (float32, clipped 0..1). chip == 'none' returns the input unchanged."""
    if chip not in CHIPS:
        raise ValueError(f"unknown chip {chip!r}")
    if chip == "none":
        return frames
    p = CHIPS[chip]
    x = np.clip(frames.astype(np.float32), 0.0, 1.0)
    n, h, w, _ = x.shape
    if p.get("soft"):
        x = np.stack([_box(f, p["soft"]) for f in x])
    if p.get("chroma_shift"):  # red right, blue left
        s = int(p["chroma_shift"])
        x = x.copy()
        x[..., 0] = np.roll(x[..., 0], s, axis=2)
        x[..., 2] = np.roll(x[..., 2], -s, axis=2)
    x = x * np.array(p.get("gain", (1, 1, 1)), np.float32) + np.array(p.get("lift", (0, 0, 0)), np.float32)
    x = np.clip(x, 0.0, 1.0)
    x = x ** (1.0 / np.array(p.get("gamma", (1, 1, 1)), np.float32))
    c = p.get("contrast", 1.0)
    x = np.clip((x - 0.5) * c + 0.5, 0.0, 1.0)
    luma = (x * LUMA).sum(-1, keepdims=True)
    x = np.clip(luma + (x - luma) * p.get("sat", 1.0), 0.0, 1.0)
    if p.get("vignette"):
        x = x * _vignette(h, w, p["vignette"])
    if p.get("scanline"):
        lines = np.where(np.arange(h) % 2 == 0, 1.0, 1.0 - p["scanline"]).astype(np.float32)
        x = x * lines[None, :, None, None]
    if grain_amount > 0:
        for i in range(n):  # per-frame grain, seeded by (seed, frame) so reruns match
            g = np.random.default_rng([int(seed), i]).standard_normal((h, w, 1)).astype(np.float32)
            x[i] += g * grain_amount * 0.1 * (1.0 - np.abs(x[i] - 0.5))  # strongest in mids
    return np.clip(x, 0.0, 1.0).astype(np.float32)
