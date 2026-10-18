import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import title_card as tc  # noqa: E402

IMG = np.tile(np.linspace(0.2, 0.8, 320, dtype=np.float32)[None, :, None], (180, 1, 3))


def run(**kw):
    args = dict(title="OPEN SAUCE", subtitle="Fork this shot", style="trailer_bold", position="lower_third",
                hold_frames=12, fade_in_frames=6)
    args.update(kw)
    return tc.title_card(IMG, **args)


def test_shapes():
    frames, poster = run()
    assert frames.shape == (12, 180, 320, 3) and frames.dtype == np.float32
    assert poster.shape[2] == 3 and abs(poster.shape[0] / poster.shape[1] - 1.5) < 0.02
    assert 0.0 <= frames.min() and frames.max() <= 1.0


def test_text_region_differs_and_rest_untouched():
    frames, _ = run()
    d = np.abs(frames[-1] - IMG).sum(-1)
    assert d[int(180 * 0.7):].max() > 0.3  # lower third changed
    assert d[:int(180 * 0.15)].max() < 1e-6  # top untouched


def test_fade_text_only():
    frames, _ = run()
    d = [np.abs(f - IMG).mean() for f in frames]
    assert d[0] < d[-1] and d[0] < 1e-6
    assert all(b >= a - 1e-6 for a, b in zip(d, d[1:]))
    assert d[-1] > 0  # image is never darkened wholesale: untouched pixels equal the source
    assert np.array_equal(frames[-1][:10], IMG[:10])


def test_all_styles_and_positions():
    for s in tc.STYLES:
        for p in tc.POSITIONS:
            f, _ = run(style=s, position=p, hold_frames=1, fade_in_frames=0)
            assert np.abs(f[0] - IMG).max() > 0.1
