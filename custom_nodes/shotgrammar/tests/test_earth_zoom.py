import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import earth_zoom as ez  # noqa: E402

H, W = 128, 72
RECT = (0.375, 0.5, 0.625, 0.75)  # inner sits 4x smaller, below centre


def test_view_rects_endpoints_and_constant_log_speed():
    v = ez.view_rects(RECT, 9)
    assert np.allclose(v[0], RECT)
    assert np.allclose(v[-1], (0, 0, 1, 1))
    sizes = v[:, 2] - v[:, 0]
    ratios = sizes[1:] / sizes[:-1]
    assert np.allclose(ratios, ratios[0])  # geometric zoom
    assert sizes[-1] / sizes[0] >= 4.0 - 1e-9


def test_zoom_path_starts_on_inner_ends_on_outer():
    rng = np.random.default_rng(0)
    inner = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    outer = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    fr = ez.zoom_path(inner, outer, RECT, 17)
    assert fr.shape == (17, H, W, 3) and fr.dtype == np.uint8
    assert np.abs(fr[0].astype(int) - inner).mean() < 3
    assert np.array_equal(fr[-1], outer)


def test_inner_fades_out_by_fade_end():
    inner = np.full((H, W, 3), 250, np.uint8)
    outer = np.full((H, W, 3), 10, np.uint8)
    fr = ez.zoom_path(inner, outer, RECT, 21, fade_end=0.5)
    assert fr[10].max() <= 12  # by the midpoint only the outer image is left
    assert fr[3][H // 2 + 16, W // 2, 0] > 150  # early on the inner image dominates its own centre


def test_hard_mask_never_double_exposes():
    inner = np.full((H, W, 3), 250, np.uint8)
    outer = np.full((H, W, 3), 10, np.uint8)
    fr = ez.zoom_path(inner, outer, RECT, 21, feather=0.0, fade_end=0.5)
    assert set(np.unique(fr).tolist()) <= {10, 250}  # every pixel from exactly one plate
    lit = [(f == 250).mean() for f in fr[:11]]
    assert all(b <= a for a, b in zip(lit, lit[1:]))  # the mask only shrinks



def test_subject_plates_agree_and_drop_outer_subject():
    inner = np.full((H, W, 3), 100, np.uint8)
    inner[40:90, 26:46] = 250  # inner subject
    outer = np.full((H, W, 3), 30, np.uint8)
    outer[70:100, 30:42] = 200  # outer's own (re-rendered) subject, slightly off
    im = (inner[..., 0] == 250).astype(np.float32)
    om = (outer[..., 0] == 200).astype(np.float32)
    i2, o2 = ez.subject_plates(inner, outer, RECT, im, om, feather_px=0)
    x0, y0 = int(RECT[0] * W), int(RECT[1] * H)
    y1 = int(RECT[3] * H)
    assert (o2[y0:y1] == 200).sum() == 0  # outer subject inpainted away inside the footprint
    assert (o2[y1 + 1:] == 200).any()  # the part the inner crop lacks (below it) is kept
    assert i2[60, 36, 0] == 250 and i2[5, 5, 0] < 60  # inner subject over outer's background
    assert o2[y0 + 16, x0 + 9, 0] > 200  # inner subject pasted into outer at inner_rect


def _textured(h, w, seed):
    import cv2

    n = np.random.default_rng(seed).integers(0, 255, (h, w, 3), dtype=np.uint8)
    return cv2.GaussianBlur(n, (0, 0), 2.0)


def _padded(mask_only):
    import cv2

    h, w = 320, 180
    inp = _textured(h, w, 1)
    s = 0.3
    tw, th = round(w * s), round(h * s)  # 54 x 96
    x0, y0 = 70, 150
    still = _textured(h, w, 2)  # unrelated "re-rendered" background
    small = cv2.resize(inp, (tw, th), interpolation=cv2.INTER_AREA)
    mask = np.zeros((h, w), np.float32)
    mask[h // 5:4 * h // 5, w // 4:3 * w // 4] = 1  # subject = centre block
    if mask_only:
        sm = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST) > 0.5
        still[y0:y0 + th, x0:x0 + tw][sm] = small[sm]
    else:
        still[y0:y0 + th, x0:x0 + tw] = small
    return inp, still, mask, (x0, y0, x0 + tw, y0 + th), (w, h)


def test_measure_inner_rect_recovers_known_pad():
    inp, still, _, (x0, y0, x1, y1), (w, h) = _padded(False)
    (rx0, ry0, rx1, ry1), conf = ez.measure_inner_rect(inp, still)
    for got, want in ((rx0 * w, x0), (ry0 * h, y0), (rx1 * w, x1), (ry1 * h, y1)):
        assert abs(got - want) <= 2
    assert conf > 0.8


def test_measure_inner_rect_subject_mask_ignores_rerendered_background():
    inp, still, mask, (x0, y0, x1, y1), (w, h) = _padded(True)
    (rx0, ry0, rx1, ry1), conf = ez.measure_inner_rect(inp, still, mask=mask)
    for got, want in ((rx0 * w, x0), (ry0 * h, y0), (rx1 * w, x1), (ry1 * h, y1)):
        assert abs(got - want) <= 2
    assert conf > 0.8


# ----------------------------------------------------------------------------- N-plate pyramid
RECTS3 = [RECT, (0.3, 0.3, 0.7, 0.7), (0.35, 0.35, 0.65, 0.65)]


def test_ease_in_param_endpoints_and_monotone():
    tau = ez.ease_in_param(50, 0.2)
    assert tau[0] == 0 and abs(tau[-1] - 1) < 1e-12
    assert np.all(np.diff(tau) > 0)
    d = np.diff(tau)
    assert d[0] < d[-1] * 0.3  # starts slow
    assert np.allclose(d[20:], d[-1])  # constant speed after the ease-in


def test_compose_rects_nests():
    comp = ez.compose_rects(RECTS3)
    assert comp[-1] == (0.0, 0.0, 1.0, 1.0)
    assert comp[-2] == RECTS3[-1]
    widths = [c[2] - c[0] for c in comp]
    assert all(a < b for a, b in zip(widths, widths[1:]))
    assert abs(widths[0] - 0.25 * 0.4 * 0.3) < 1e-12


def test_pyramid_views_constant_log_rate_and_switches():
    views, segs, _ = ez.pyramid_views(RECTS3, 41, ease_in=0.0)
    comp = ez.compose_rects(RECTS3)
    assert np.allclose(views[0], comp[0]) and np.allclose(views[-1], (0, 0, 1, 1))
    sizes = views[:, 2] - views[:, 0]
    ratios = sizes[1:] / sizes[:-1]
    assert np.allclose(ratios, ratios[0])  # one geometric zoom across every plate boundary
    assert segs[0] == 1 and segs[-1] == 3 and np.all(np.diff(segs) >= 0)
    sw = ez.segment_switch_frames(RECTS3, 41, ease_in=0.0)
    assert len(sw) == 2 and all(segs[i] != segs[i - 1] for i in sw)


def test_pyramid_two_plates_matches_view_rects():
    v2 = ez.view_rects(RECT, 17)
    v, _, _ = ez.pyramid_views([RECT], 17, ease_in=0.0)
    assert np.allclose(v, v2)


def test_zoom_pyramid_endpoints_and_single_plate_pixels():
    vals = [40, 90, 140, 190]
    plates = [np.full((H, W, 3), v, np.uint8) for v in vals]
    fr, pm = ez.zoom_pyramid(plates, RECTS3, 31, feather=0.0, return_map=True)
    assert fr.shape == (31, H, W, 3)
    assert np.array_equal(fr[0], plates[0])
    assert np.array_equal(fr[-1], ez.nest_plates(plates, RECTS3, 0.0)[-1])  # top plate with the finer ones nested
    assert fr[-1][2, 2, 0] == 190 and fr[-1][H // 2, W // 2, 0] == 40  # ... centre = the photo, edge = the top plate
    pure = np.isin(fr, vals).mean()  # the rest is cubic resampling across a nested seam (1-2 px), not a blend
    assert pure > 0.9, pure  # 72 px wide test frames: the resampled seam rows are a large share
    assert (pm >= 0).all()  # no feather band at all with feather 0
    rep = ez.honesty_check(pm, 0.0)
    assert rep["ok"] and rep["worst_band_px"] == 0


def test_zoom_pyramid_feather_band_stays_thin():
    rng = np.random.default_rng(3)
    plates = [rng.integers(0, 255, (H, W, 3), dtype=np.uint8) for _ in range(4)]
    _, pm = ez.zoom_pyramid(plates, RECTS3, 25, feather=2.0, return_map=True)
    rep = ez.honesty_check(pm, 2.0)
    assert rep["ok"], rep
    assert rep["worst_band_px"] <= 2.5


def test_nest_plates_agree_inside_footprint():
    inner = np.full((H, W, 3), 200, np.uint8)
    outer = np.full((H, W, 3), 20, np.uint8)
    nested = ez.nest_plates([inner, outer], [RECT], feather_px=0)
    x0, y0, x1, y1 = int(RECT[0] * W), int(RECT[1] * H), int(RECT[2] * W), int(RECT[3] * H)
    assert (nested[1][y0 + 1:y1 - 1, x0 + 1:x1 - 1] == 200).all()
    assert nested[1][5, 5, 0] == 20 and nested[0] is inner


def test_edge_score_flags_a_pasted_border():
    import cv2

    base = cv2.GaussianBlur(np.random.default_rng(5).integers(0, 255, (H, W, 3), dtype=np.uint8), (0, 0), 1.5)
    clean = base.copy()
    boxed = base.copy()
    x0, y0, x1, y1 = int(RECT[0] * W), int(RECT[1] * H), int(RECT[2] * W), int(RECT[3] * H)
    cv2.rectangle(boxed, (x0, y0), (x1, y1), (255, 255, 255), 1)
    assert ez.edge_score(boxed, RECT) > 2.0 > ez.edge_score(clean, RECT)


def test_match_tone_removes_a_tone_step_but_keeps_detail():
    rng = np.random.default_rng(7)
    inner = np.clip(100 + rng.normal(0, 20, (H, W, 3)), 0, 255).astype(np.uint8)
    outer = np.full((H, W, 3), 60, np.uint8)
    x0, y0, x1, y1 = int(RECT[0] * W), int(RECT[1] * H), int(RECT[2] * W), int(RECT[3] * H)
    outer[y0:y1, x0:x1] = 150  # the outer plate's own (soft, brighter) re-render of inner
    graded = ez.match_tone(inner, outer, RECT)
    assert abs(graded.astype(float).mean() - 150) < 8  # tone now matches the outer's version
    assert graded.std() > inner.std() * 1.2  # detail kept (scaled with the gain), not replaced by outer pixels


def test_zoom_pyramid_only_frames_matches_full_render():
    rng = np.random.default_rng(11)
    plates = [rng.integers(0, 255, (H, W, 3), dtype=np.uint8) for _ in range(4)]
    full = ez.zoom_pyramid(plates, RECTS3, 25)
    keys = [0, 8, 16, 24]
    sub = ez.zoom_pyramid(plates, RECTS3, 25, only=keys)
    assert sub.shape[0] == 4 and all(np.array_equal(sub[j], full[k]) for j, k in enumerate(keys))
