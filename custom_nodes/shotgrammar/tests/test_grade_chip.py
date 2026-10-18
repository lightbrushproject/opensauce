import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import grade_chip as gc  # noqa: E402

rng = np.random.default_rng(1)
IMG = rng.uniform(0.15, 0.85, (2, 32, 48, 3)).astype(np.float32)
RAMP = np.tile(np.linspace(0, 1, 64, dtype=np.float32)[None, None, :, None], (1, 16, 1, 3))


def mean(x):
    return x.reshape(-1, 3).mean(0)


def sat(x):
    return np.abs(x - x.mean(-1, keepdims=True)).mean()


def test_none_identity():
    assert np.array_equal(gc.apply_chip(IMG, "none"), IMG)
    assert np.array_equal(gc.apply_chip(IMG, "none", 0.5, 3), IMG)


def test_deterministic_and_seed_matters():
    for c in gc.CHIP_NAMES:
        a = gc.apply_chip(IMG, c, 0.4, 7)
        assert np.array_equal(a, gc.apply_chip(IMG, c, 0.4, 7))
    assert not np.array_equal(gc.apply_chip(IMG, "warm_film", 0.4, 1), gc.apply_chip(IMG, "warm_film", 0.4, 2))


def test_range_and_shape():
    for c in gc.CHIP_NAMES:
        out = gc.apply_chip(IMG, c, 1.0, 0)
        assert out.shape == IMG.shape and out.dtype == np.float32
        assert out.min() >= 0.0 and out.max() <= 1.0


def test_colour_directions():
    m0 = mean(IMG)
    w = mean(gc.apply_chip(IMG, "warm_film"))
    assert w[0] - w[2] > m0[0] - m0[2] + 0.05
    c = mean(gc.apply_chip(IMG, "cool_steel"))
    assert c[2] - c[0] > m0[2] - m0[0] + 0.05
    assert sat(gc.apply_chip(IMG, "bleach_bypass")) < sat(IMG) * 0.75
    s8 = mean(gc.apply_chip(IMG, "super8"))
    assert s8[0] - s8[2] > m0[0] - m0[2] + 0.05


def test_teal_orange_split():
    out = gc.apply_chip(RAMP, "teal_orange")[0, 0]
    assert out[4, 2] > out[4, 0]  # shadows lean teal (blue > red)
    assert out[-5, 0] > out[-5, 2]  # highlights lean orange


def test_vignette_and_vhs():
    flat = np.full((1, 40, 60, 3), 0.6, np.float32)
    s8 = gc.apply_chip(flat, "super8")[0]
    assert s8[0, 0].mean() < s8[20, 30].mean() - 0.05
    v = gc.apply_chip(flat, "vhs")[0]
    assert abs(v[0].mean() - v[1].mean()) > 0.02  # scanlines
