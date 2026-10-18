import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import camera_move as cm  # noqa: E402
import nodes_camera_move as ncm  # noqa: E402
import speed_ramp as sr  # noqa: E402

BANNED = ["tripod", "wide shot", "camera follows", "camera tracks"]
EXPECTED = {
    "static_hold", "levitate", "jib_up", "dolly_zoom_out", "dolly_zoom_in",
    "crash_zoom", "push_in", "pull_back", "earth_zoom", "petrify",
}


def test_registry_loads_all_moves():
    assert set(cm.load_registry()) == EXPECTED


@pytest.mark.parametrize("move", sorted(EXPECTED))
def test_directive_clean(move):
    d = cm.directive(move, 0.5, "man")
    assert d["prompt"].strip() and d["negative"].strip()
    assert "{" not in d["prompt"] and "man" in d["prompt"]
    for b in BANNED:
        assert b not in d["prompt"].lower()
        assert b not in d["negative"].lower()
    assert d["ramp"]["curve"] in sr.CURVES
    assert d["lane"] in {"motion-led", "geometry-led", "material-led"}
    assert d["seconds"] > 0


def test_reproject_presence_matches_registry():
    for name, m in cm.load_registry().items():
        assert (cm.directive(name)["reproject"] is None) == (m["reproject"] is None)
    assert cm.directive("jib_up")["validate"]


@pytest.mark.parametrize("move", ["dolly_zoom_out", "dolly_zoom_in", "crash_zoom", "push_in", "pull_back"])
def test_intensity_monotonic(move):
    vals = [cm.directive(move, i / 10)["reproject"]["intensity"] for i in range(11)]
    assert vals == sorted(vals) and vals[0] < vals[-1]
    assert all(0.0 <= v <= 1.0 for v in vals)


def test_levitate_intensity_changes_prompt():
    assert cm.directive("levitate", 0.2)["prompt"] != cm.directive("levitate", 0.9)["prompt"]


def test_extras():
    d = cm.directive(
        "crash_zoom", 0.5, extras={"prompt": "his two eyes glowing bright gold", "seconds": 2.0, "bbox": [0.4, 0.4, 0.6, 0.5]}
    )
    assert "glowing bright gold" in d["prompt"] and d["seconds"] == 2.0
    assert d["reproject"]["bbox"] == [0.4, 0.4, 0.6, 0.5]


def test_stack_splits_seconds():
    s = cm.stack("dolly_zoom_out", "crash_zoom", split=0.25, total_seconds=8.0)
    assert s["seconds_a"] == 2.0 and s["seconds_b"] == 6.0
    assert s["seconds_a"] + s["seconds_b"] == s["seconds"] == 8.0
    assert ". Then " in s["prompt"]
    assert s["reproject_a"]["move"] == "dolly_zoom_out" and s["reproject_b"]["move"] == "crash_zoom"
    assert s["ramp_a"]["curve"] == "linear" and s["ramp_b"]["curve"] == "impact"
    assert s["lane"] == "geometry-led"


def test_stack_default_total_and_warning():
    s = cm.stack("levitate", "push_in")
    assert s["seconds"] == 4.0 and s["seconds_a"] == 2.0
    assert s["reproject"]["move"] == "push_in" and s["warnings"]
    assert s["lane"] == "mixed"


def test_unknown_and_bad_args_raise():
    with pytest.raises(ValueError):
        cm.directive("barrel_roll")
    with pytest.raises(ValueError):
        cm.stack("push_in", "nope")
    with pytest.raises(ValueError):
        cm.stack("push_in", "pull_back", split=1.5)
    with pytest.raises(ValueError):
        cm.directive("push_in", intensity=2)


def test_node_wrapper():
    out = ncm.SGCameraMove().run("crash_zoom", 0.5, "man", "none", 0.5)
    assert out[4] == "crash_zoom" and out[5] == "impact" and out[6] == 0.22 and out[3] == pytest.approx(0.5625)
    assert out[7:] == ("crash_zoom", "impact", 0.42, 0.40, 0.58, 0.50, 6)
    out = ncm.SGCameraMove().run("static_hold", 0.5, "man", "none", 0.5)
    assert out[3] == 0.0 and out[4] == "none"
    assert out[7] == "static_hold" and out[8] == "linear" and out[13] == 12
    assert "none" in ncm.SGCameraMove.INPUT_TYPES()["required"]["second_move"][0]


def test_app_move_names_subset():
    import camera_move as cm
    names = cm.app_move_names()
    assert set(names) == {"levitate", "crash_zoom", "dolly_zoom_out", "push_in", "pull_back"}
    assert set(names) <= set(cm.move_names())
