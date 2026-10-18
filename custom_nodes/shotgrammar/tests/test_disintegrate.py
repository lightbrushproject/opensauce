import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import disintegrate as di  # noqa: E402


def scene(h=96, w=64):
    photo = np.full((h, w, 3), 0.2, np.float32)
    photo[20:80, 22:42] = [0.1, 0.1, 0.6]  # the subject
    plate = np.full((h, w, 3), 0.3, np.float32)
    matte = np.zeros((h, w), np.float32)
    matte[20:80, 22:42] = 1.0
    return photo, plate, matte


def test_shape_first_frame_and_end_state():
    photo, plate, matte = scene()
    fr = di.disintegrate(photo, plate, matte, n_frames=17, start=0.1, end=0.8, density=0.0)
    assert fr.shape == (17, 96, 64, 3) and fr.dtype == np.float32
    assert np.array_equal(fr[0], photo)
    inside = matte > 0
    assert np.allclose(fr[-1][inside], plate[inside])  # body fully gone: the plate shows through, opaque


def test_gone_pixels_are_pure_plate_never_a_mix():
    photo, plate, matte = scene()
    t = di.death_time(matte)
    fr = di.disintegrate(photo, plate, matte, n_frames=17, density=0.0)
    for i in range(1, 17):
        gone = (t >= 0) & (t <= di.progress(i / 16, 0.10, 0.85))
        assert np.allclose(fr[i][gone], plate[gone])


def test_body_loses_area_monotonically_and_head_goes_last():
    _, _, matte = scene()
    t = di.death_time(matte, seed=3)
    fr = [di.body_fraction(t, u, 0.1, 0.85) for u in np.linspace(0, 1, 11)]
    assert fr[0] == 1.0 and fr[-1] == 0.0 and all(a >= b for a, b in zip(fr, fr[1:]))
    assert t[20:30, 22:42].mean() > t[70:80, 22:42].mean()
    assert (t[matte == 0] == -1).all()


def test_world_outside_subject_is_the_plate_from_frame_1():
    """Outside the body every frame after 0 is the plate (equal to the photo outside the plate's own matte)."""
    photo, plate, matte = scene()
    fr = di.disintegrate(photo, plate, matte, n_frames=9, density=0.0)
    outside = matte == 0
    assert np.allclose(fr[1:, outside], plate[outside])


def test_key_weights_pin_gone_and_world_free_body():
    photo, plate, matte = scene()
    fr, wts = di.guide_sequence(photo, plate, matte, n_frames=17, density=0.0, body_base=0.5, pin=0.85)
    assert wts.shape == (17, 96, 64) and np.all(wts[0] == 1.0)
    t = di.death_time(matte)
    p = di.progress(8 / 16, 0.10, 0.85)
    assert np.allclose(wts[8][t > p], wts[8][t > p][0]) and wts[8][t > p][0] < 0.85
    assert np.allclose(wts[8][(t >= 0) & (t <= p)], 0.85) and np.allclose(wts[8][matte == 0], 0.85)


def test_body_strength_rises_late_and_with_size():
    assert di.body_strength(0.2, 0.1) == 0.5
    assert di.body_strength(0.7, 0.1) > di.body_strength(0.2, 0.1)
    assert di.body_strength(0.2, 0.45) > di.body_strength(0.2, 0.1)


def test_removal_mask_grows_and_covers_the_floor():
    _, _, matte = scene()
    rm = di.removal_mask(matte, grow_frac=0.05, below_frac=0.12)
    assert rm[matte > 0].min() == 1.0
    assert rm[85, 32] == 1.0  # ground under the feet
    assert rm[5, 2] == 0.0
