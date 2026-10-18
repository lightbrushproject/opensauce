import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reproject as rp  # noqa: E402

SIZE = 512
SQ = (192, 192, 320, 320)  # subject box
BG_PATCH = (40, 40, 140, 140)


def make_scene():
    rng = np.random.default_rng(3)
    cells = rng.integers(40, 200, (32, 32), dtype=np.uint8)  # non-periodic blocky checker
    bg = cv2.resize(cells, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    grad = np.linspace(0, 55, SIZE, dtype=np.uint8)[None, :]
    bg = np.clip(bg.astype(int) + grad, 0, 255).astype(np.uint8)
    img = np.stack([bg, bg, bg], -1)
    x0, y0, x1, y1 = SQ
    img[y0:y1, x0:x1] = (235, 235, 235)
    cv2.rectangle(img, (x0 + 20, y0 + 20), (x0 + 60, y0 + 50), (200, 40, 40), -1)
    cv2.line(img, (x0, y1 - 1), (x1 - 1, y0), (20, 20, 120), 5)
    cv2.circle(img, (x0 + 85, y0 + 85), 18, (30, 120, 40), -1)
    depth = np.full((SIZE, SIZE), 0.2, np.float32)
    depth[y0:y1, x0:x1] = 0.9
    return img, depth


def test_dolly_zoom_locks_subject_and_moves_background():
    img, depth = make_scene()
    frames, masks = rp.move_dolly_zoom(img, depth, 25, SQ, dolly_distance=0.5, direction="in")
    assert frames.shape == (25, SIZE, SIZE, 3) and frames.dtype == np.uint8
    assert masks.shape == (25, SIZE, SIZE) and masks.dtype == np.uint8
    subj = rp.measure_bbox_scale(frames, SQ)
    assert np.all(np.abs(subj - 1.0) < 0.03), subj
    bg = rp.measure_bbox_scale(frames, BG_PATCH)
    assert abs(bg[-1] - 1.0) >= 0.30, bg
    assert masks[-1].any()


def test_dolly_zoom_out_has_holes():
    img, depth = make_scene()
    frames, masks = rp.move_dolly_zoom(img, depth, 9, SQ, dolly_distance=0.5, direction="out")
    subj = rp.measure_bbox_scale(frames, SQ)
    assert np.all(np.abs(subj - 1.0) < 0.03), subj
    assert masks[-1].any()


def test_crash_zoom_final_scale():
    img, depth = make_scene()
    target = (216, 216, 296, 296)  # inside the subject; flat-depth so scale is exact
    frames, masks = rp.move_crash_zoom(img, depth, 12, target, zoom_factor=3.0)
    scale = rp.measure_bbox_scale(frames, target)
    assert abs(scale[-1] - 3.0) / 3.0 < 0.10, scale
    assert abs(scale[0] - 1.0) < 0.03
    # target centre lands at frame centre
    ys, xs = np.nonzero(frames[-1][..., 0] > 200)
    assert abs(xs.mean() - SIZE / 2) < 0.1 * SIZE and abs(ys.mean() - SIZE / 2) < 0.1 * SIZE


def test_identity_single_frame():
    img, depth = make_scene()
    for frames, masks in (
        rp.move_dolly_zoom(img, depth, 1, SQ),
        rp.move_push(img, depth, 1),
        rp.move_crash_zoom(img, depth, 1, SQ),
    ):
        assert frames.shape == (1, SIZE, SIZE, 3)
        assert masks.max() == 0
        assert np.array_equal(frames[0], img)


def test_push_has_parallax_and_shapes():
    img, depth = make_scene()
    frames, masks = rp.move_push(img, depth, 5, distance=0.5)
    assert frames.dtype == np.uint8 and masks.dtype == np.uint8
    assert not np.array_equal(frames[-1], img)


def test_easing_endpoints():
    for name, fn in rp.EASES.items():
        assert abs(float(fn(0.0))) < 1e-9 and abs(float(fn(1.0)) - 1.0) < 1e-9, name
    assert rp.impact(0.2) > rp.linear(0.2)


def test_fill_holes_and_fit_depth():
    import cv2
    import numpy as np
    from shotgrammar import reproject as rp

    img = np.full((64, 64, 3), 120, np.uint8)
    img[:, 32:] = 200
    hole = np.zeros((64, 64), np.uint8)
    hole[20:30, 28:36] = 255  # thin hole across the edge
    out = rp.fill_holes(img, hole)
    assert out.shape == img.shape and out.dtype == np.uint8
    assert (out[20:30, 28:36] > 0).all()  # nothing left black
    big = np.zeros((64, 64), np.uint8)
    big[:, :40] = 255  # wide hole -> downscaled path
    out2 = rp.fill_holes(img, big)
    assert out2.shape == img.shape and (out2[:, :40] > 0).all()
    assert rp.fill_holes(img, np.zeros((64, 64), np.uint8)) is img
    d = cv2.resize(np.linspace(0, 1, 32 * 48, dtype=np.float32).reshape(48, 32), (32, 48))
    assert rp.fit_depth(d, img).shape == (64, 64)
