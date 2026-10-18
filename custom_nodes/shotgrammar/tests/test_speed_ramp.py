import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import speed_ramp as sr  # noqa: E402


def clip(n=25):
    f = np.zeros((n, 4, 4, 3), np.float32)
    f += (np.arange(n, dtype=np.float32) / (n - 1))[:, None, None, None]
    return f


def test_linear_identity():
    f = clip()
    assert np.allclose(sr.speed_ramp(f, "linear"), f, atol=1e-6)


def test_count_and_dtype():
    f = clip()
    for c in sr.CURVES:
        out = sr.speed_ramp(f, c)
        assert out.shape == f.shape and out.dtype == f.dtype
    out = sr.speed_ramp(f, "speed_up", out_frames=13)
    assert out.shape[0] == 13 and out.dtype == np.float32


def test_monotonic_and_endpoints():
    for c in sr.CURVES:
        pos = sr.source_positions(49, 49, c, 0.6)
        assert np.all(np.diff(pos) >= -1e-9)
        assert pos[0] == 0 and abs(pos[-1] - 48) < 1e-9


def test_impact_front_loaded_then_holds():
    pos = sr.source_positions(49, 49, "impact", 0.6)
    before = pos[: int(0.6 * 49)]
    assert np.all(before <= 0.41 * 48)  # approach stays in the early source
    hold = pos[(np.arange(49) / 48 >= 0.6) & (np.arange(49) / 48 < 0.66)]
    assert len(hold) >= 2 and np.ptp(hold) < 1e-9


def test_shapes_of_other_curves():
    mid = len(clip()) // 2
    assert sr.speed_ramp(clip(), "slow_mo_settle")[mid, 0, 0, 0] > 0.5
    assert sr.speed_ramp(clip(), "speed_up")[mid, 0, 0, 0] < 0.5


def test_nearest_vs_blend():
    f = clip(5)
    nn = sr.speed_ramp(f, "linear", out_frames=9, blend=False)
    assert set(np.unique(nn[..., 0])) <= set(np.unique(f[..., 0]))
    bl = sr.speed_ramp(f, "linear", out_frames=9, blend=True)
    assert np.allclose(bl[1, 0, 0, 0], 0.125)
