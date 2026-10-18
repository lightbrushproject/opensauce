"""Trailer: cut_plan math and assemble on tiny synthetic clips (needs only ffmpeg via imageio_ffmpeg)."""
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_nodes" / "shotgrammar"))
import recipe as R  # noqa: E402
import speed_ramp as SR  # noqa: E402
import trailer as T  # noqa: E402

SHOTS = [{**s, "src_frames": 97} for s in T.DEFAULT_SHOTS]


def test_cut_plan_default_durations():
    p = T.cut_plan(SHOTS)
    assert [s["out_frames"] for s in p["shots"]] == [60, 72, 84]
    assert p["title"]["out_frames"] == 60
    assert p["total_frames"] == 276 and p["total_s"] <= 12.0
    t = 0
    for s in p["shots"]:
        assert s["out_start"] == t and s["in_end"] == 84  # 97 - 12 QR frames
        t = s["out_end"] + 1
    assert p["title"]["out_start"] == t


def test_cut_plan_scales_to_ceiling():
    p = T.cut_plan(SHOTS, total_s=6.0)
    assert p["total_s"] <= 6.0 + 1 / 24


@pytest.mark.parametrize("s", SHOTS)
def test_ramps_monotonic(s):
    p = T.cut_plan([s])["shots"][0]
    pos = SR.source_positions(p["src_frames"], p["out_frames"], p["ramp"], p["hit_at"])
    assert np.all(np.diff(pos) >= 0) and pos[0] == 0 and pos[-1] == p["src_frames"] - 1


def _clip(path, color, n=30, size=(96, 64)):
    w, h = size
    cmd = [R._ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r=24:d={n / 24}",
           "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)


def test_assemble_synthetic(tmp_path):
    cols = ["0x805030", "0x308050", "0x503080"]
    shots = []
    for i, (spec, c) in enumerate(zip(T.DEFAULT_SHOTS, cols)):
        p = tmp_path / f"s{i}.mp4"
        _clip(p, c, n=30, size=(704, 1280))  # real size: the QR needs it to decode
        shots.append({**spec, "path": str(p)})
    rec = R.build_recipe("trailer", 1, ["x.jpg"], ["m"], {"t": 1}, {})
    plan = T.cut_plan([{**s, "src_frames": 30} for s in shots], strip=12)
    out = tmp_path / "t.mp4"
    res = T.assemble(shots, "TITLE", "SUB", "warm_film", out, rec, tmp_path / "recipes", plan, burn_qr=True)
    cap = cv2.VideoCapture(str(out))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == plan["total_frames"]
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    assert frames[-1].mean() > 60  # luminous end, not black
    assert min(f.mean() for f in frames) > 30  # no fade to black anywhere
    # hard cut: first frame of shot 2 is already the new colour
    b = plan["shots"][1]["out_start"]
    assert np.abs(frames[b].astype(int) - frames[b - 1].astype(int)).mean() > 15
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(frames[-1])
    assert text == R.recipe_url(rec)
    assert R.read_recipe_from_mp4(out, sidecar_dir=None)["id"] == rec["id"]
    assert res["poster"].exists() and res["sidecar"].exists()


import bridge as B  # noqa: E402


def _solid(v, shape=(64, 48, 3)):
    return np.full(shape, v, np.uint8)


def test_plan_bridges_match_vs_bridge():
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (64, 48, 3), dtype=np.uint8)
    near = np.clip(base.astype(int) + 3, 0, 255).astype(np.uint8)  # same framing, tiny drift
    far = 255 - base  # different framing
    shots = [{"name": "a", "first": base, "last": base},
             {"name": "b", "first": near, "last": near},
             {"name": "c", "first": far, "last": far, "bridge_in": {"frames": 25, "prompt": "p"}}]
    a_b, b_c = B.plan_bridges(shots)
    assert a_b["kind"] == "match" and a_b["frames"] == 0 and a_b["key"] is None
    assert b_c["kind"] == "bridge" and b_c["frames"] == 25 and b_c["prompt"] == "p" and len(b_c["key"]) == 10
    assert B.plan_bridges(shots)[1]["key"] == b_c["key"]  # cache key is deterministic
    with pytest.raises(ValueError):
        B.plan_bridges([shots[0], {**shots[2], "bridge_in": {"frames": 30}}])


def test_whip_tilt_is_motion_not_dissolve():
    a, b = _solid(40), _solid(200)
    w = B.whip_tilt(a, b, 8)
    assert w.shape == (8, 64, 48, 3)
    # top rows go from A to B monotonically as the frame slides (a tilt), never a global mix at frame 0
    assert w[0, :20].mean() < 60 and w[-1, -20:].mean() > 180


def test_assemble_with_fake_bridges(tmp_path):
    cols = ["0x805030", "0x308050", "0x308050"]  # shot 2 -> 3 share framing: match cut, no bridge
    specs = [{"name": "s0", "ramp": "linear", "seconds": 1.0}, {"name": "s1", "ramp": "linear", "seconds": 1.0},
             {"name": "s2", "ramp": "linear", "seconds": 1.0, "bridge_in": {"frames": 9}}]
    shots = []
    for i, (spec, c) in enumerate(zip(specs, cols)):
        p = tmp_path / f"s{i}.mp4"
        _clip(p, c, n=40, size=(704, 1280))
        shots.append({**spec, "path": str(p)})
    calls = []

    def fake(a, b, bnd):  # linear ramp from a to b, like a generated camera move (no GPU)
        calls.append(bnd)
        t = np.linspace(0, 1, bnd["frames"])[:, None, None, None]
        return np.rint(a[None] * (1 - t) + b[None] * t).astype(np.uint8)

    rec = R.build_recipe("trailer", 1, ["x.jpg"], ["m"], {"t": 1}, {})
    plan = T.cut_plan([{**s, "src_frames": 40} for s in shots], title_hold_s=0.5, title_mode="overlay")
    out = tmp_path / "t.mp4"
    res = T.assemble(shots, "TITLE", "SUB", "none", out, rec, tmp_path / "recipes", plan, bridge_provider=fake)
    kinds = [b["kind"] for b in res["plan"]["bridges"]]
    assert kinds == ["bridge", "match"] and len(calls) == 1
    used = res["plan"]["bridges"][0]["used_frames"]
    assert 2 <= used <= 33 - 2 + 6  # ends dropped, frozen lead/tail trimmed, up to two 3-frame whips added
    assert [p["piece"] for p in res["plan"]["timeline"]] == ["s0", "bridge:s0->s1", "s1", "s2"]
    cap = cv2.VideoCapture(str(out))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    assert n == res["plan"]["total_frames"] == 3 * 24 + used  # overlay title adds no frames
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f.astype(int))
    steps = [np.abs(frames[i + 1] - frames[i]).mean() for i in range(23, 23 + 32)]
    assert max(steps) < 15  # the bridge carries shot 0 into shot 1 without a jump
    ti = res["plan"]["title"]
    assert ti["mode"] == "overlay" and ti["out_end"] == n - 1
    # title is fully on from its first frame: no opacity fade
    first, prev = frames[ti["out_start"]], frames[ti["out_start"] - 1]
    assert np.abs(first - prev).max() > 150


def test_trim_static_opening_drops_frozen_lead():
    import bridge as B
    import numpy as np

    h, w = 32, 32
    still = np.full((h, w, 3), 100, np.uint8)
    frames = [still.copy() for _ in range(10)]
    for k in range(1, 9):
        f = still.copy()
        f[:, : k * 4] = 200  # moving edge
        frames.append(f)
    arr = np.stack(frames)
    out = B.trim_static_opening(arr, threshold=10.0, keep=2)
    assert len(out) == len(arr) - 8  # 10 frozen -> keep 2
    assert np.array_equal(out[-1], arr[-1])
    assert B.trim_static_opening(arr[:3]).shape == arr[:3].shape
