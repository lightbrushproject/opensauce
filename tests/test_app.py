"""No-network tests for the app: prompt fill and OS:* graph patching."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import opensauce as A  # noqa: E402


def test_fill_prompt_defaults_and_override():
    p = A.load_preset("levitate")
    text, neg = A.fill_prompt(p)
    assert "{" not in text and "person" in text
    assert neg.startswith("pc game")
    text2, _ = A.fill_prompt(p, {"subject": "woman", "particles": ""})
    assert "woman" in text2 and "person" not in text2


def test_fill_prompt_unknown_slot_kept():
    text, _ = A.fill_prompt({"prompt_module": {"template": "a {x} and {y}", "defaults": {"x": "cat"}}})
    assert text == "a cat and {y}"


def test_intensity_phrase_nearest():
    p = A.load_preset("levitate")
    assert A.intensity_phrase(p, 0.55) == p["prompt_module"]["intensity_map"]["0.6"]


def test_patch_levitate_base_graph():
    p = A.load_preset("levitate")
    base = json.loads(A.workflow_path(p).read_text(encoding="utf-8"))
    assert A.workflow_path(p).name == "_base_ltx25_i2v.api.json"
    g = A.patch_graph(base, p, prompt="P", negative="N", seed=7, intensity=None, prefix="opensauce/x")
    t = lambda title: g[A.by_title(g, title)[0]]["inputs"]  # noqa: E731
    assert t("OS:prompt")["text"] == "P" and t("OS:negative")["text"] == "N"
    assert t("OS:seed")["noise_seed"] == 7
    assert t("OS:resize")["resize_type.width"] == 704 and t("OS:resize")["resize_type.height"] == 1280
    assert (t("OS:latent")["width"], t("OS:latent")["height"], t("OS:latent")["length"]) == (352, 640, 97)
    assert t("OS:audio_latent")["frames_number"] == 97
    assert t("OS:save")["filename_prefix"] == "opensauce/x"
    # recipe node spliced between decode and CreateVideo
    rid = A.by_title(g, "OS:recipe")[0]
    assert g[rid]["class_type"] == "SGRecipeEmbed" and g[rid]["inputs"]["seed"] == 7
    assert t("OS:create")["images"] == [rid, 0]
    assert "ltx-2.5-22b-distilled" in g[rid]["inputs"]["models"]
    assert A.by_title(base, "OS:recipe") == []  # input graph untouched


def test_patch_crash_zoom_intensity():
    p = A.load_preset("crash_zoom")
    base = json.loads(A.workflow_path(p).read_text(encoding="utf-8"))
    g = A.patch_graph(base, p, prompt="P", negative="N", seed=3, intensity=0.75, prefix="opensauce/c")
    rp = g[A.by_title(g, "OS:reproject")[0]]["inputs"]
    assert rp["intensity"] == 0.75 and rp["n_frames"] == 97
    assert g[A.by_title(g, "OS:latent_full")[0]]["inputs"]["width"] == 704
    assert len(A.by_title(g, "OS:recipe")) == 1  # not duplicated


def test_menu_has_six_tiles(capsys):
    A.cmd_menu(None)
    out = capsys.readouterr().out
    assert out.count("shipped") == 6 and out.count("coming") == 0


def test_two_step_chain_with_fake_runner(tmp_path, monkeypatch):
    """petrify: stage still feeds OS:image_end of the video step; recipe extra lists the stage recipe id."""
    img = tmp_path / "in.jpg"
    img.write_bytes(b"photo")
    calls = []

    def fake(graph, assets, out, prefix, timeout):
        calls.append((prefix, {t: p.name for t, p in assets.items()}, graph))
        out.mkdir(parents=True, exist_ok=True)
        f = out / (Path(prefix).name + ("_00001_.png" if prefix.endswith("_stone") else "_00001_.mp4"))
        f.write_bytes(b"x")
        return [f, out / "unrelated_00001_.png"]

    seen = {}
    monkeypatch.setattr(A, "stamp_recipe", lambda mp4, g, preset, seed, image, url: seen.update(
        graph=g, preset=preset) or {"id": "abc", "url": "u", "video": mp4, "sidecar": "s", "source": "fake"})
    monkeypatch.setattr(A, "ROOT", tmp_path)  # stage recipe sidecars go to tmp, not the repo
    for d in ("workflows", "presets"):
        (tmp_path / d).mkdir()
    real = Path(__file__).resolve().parent.parent
    for w in ("_stage_petrify_qwen", "petrify"):
        (tmp_path / "workflows" / f"{w}.api.json").write_bytes((real / "workflows" / f"{w}.api.json").read_bytes())
    (tmp_path / "presets" / "petrify.json").write_bytes((real / "presets" / "petrify.json").read_bytes())

    r = A.render("petrify", img, seed=5, out=tmp_path / "o", runner=fake)

    assert [c[0] for c in calls] == ["opensauce/petrify_5_stone", "opensauce/petrify_5"]
    assert calls[0][1] == {"OS:image": "in.jpg"}
    assert calls[1][1] == {"OS:image": "in.jpg", "OS:image_end": "petrify_5_stone_00001_.png"}
    assert r["raw"].name == "petrify_5_00001_.mp4" and len(r["stages"]) == 1
    rec = seen["graph"][A.by_title(seen["graph"], "OS:recipe")[0]]["inputs"]
    assert json.loads(rec["extra_json"])["stages"][0]["recipe"] == r["stages"][0]["recipe"]
    assert seen["graph"][A.by_title(seen["graph"], "OS:image_end")[0]]["inputs"]["image"] == "petrify_5_stone_00001_.png"
    assert calls[1][2][A.by_title(calls[1][2], "OS:seed")[0]]["inputs"]["noise_seed"] == 5


def test_pull_back_alias_and_steps():
    p = A.load_preset("pull_back")
    assert p["preset"] == "earth_zoom"
    assert [s["name"] for s in p["run_steps"]] == ["zoom_out", "video"]
    assert p["run_steps"][1]["images"]["OS:image_end"] == "zoom_out"


def test_pick_output_skips_clean_and_other_prefixes(tmp_path):
    fs = [tmp_path / n for n in ("x_5_00001_.mp4", "x_5_clean_00001_.mp4", "y_00001_.mp4")]
    assert A.pick_output(fs, "opensauce/x_5", "video").name == "x_5_00001_.mp4"


def test_disintegrate_chain_plate_feeds_guide_node(tmp_path, monkeypatch):
    """disintegrate: the plate stage still feeds OS:image_end, which SGDisintegrate uses as its plate."""
    img = tmp_path / "in.jpg"
    img.write_bytes(b"photo")
    calls = []

    def fake(graph, assets, out, prefix, timeout):
        calls.append((prefix, {t: p.name for t, p in assets.items()}, graph))
        out.mkdir(parents=True, exist_ok=True)
        f = out / (Path(prefix).name + ("_00001_.png" if prefix.endswith("_plate") else "_00001_.mp4"))
        f.write_bytes(b"x")
        return [f]

    monkeypatch.setattr(A, "stamp_recipe", lambda mp4, g, preset, seed, image, url: {
        "id": "abc", "url": "u", "video": mp4, "sidecar": "s", "source": "fake"})
    monkeypatch.setattr(A, "ROOT", tmp_path)
    for d in ("workflows", "presets"):
        (tmp_path / d).mkdir()
    real = Path(__file__).resolve().parent.parent
    for w in ("_stage_disintegrate_plate", "disintegrate"):
        (tmp_path / "workflows" / f"{w}.api.json").write_bytes((real / "workflows" / f"{w}.api.json").read_bytes())
    (tmp_path / "presets" / "disintegrate.json").write_bytes((real / "presets" / "disintegrate.json").read_bytes())

    A.render("disintegrate", img, seed=7, out=tmp_path / "o", runner=fake)

    assert [c[0] for c in calls] == ["opensauce/disintegrate_7_plate", "opensauce/disintegrate_7"]
    assert calls[1][1] == {"OS:image": "in.jpg", "OS:image_end": "disintegrate_7_plate_00001_.png"}
    g = calls[1][2]
    node = g[A.by_title(g, "OS:disintegrate")[0]]
    end = A.by_title(g, "OS:resize_end")[0]
    assert node["inputs"]["plate"] == [end, 0]
    assert node["inputs"]["n_frames"] == g[A.by_title(g, "OS:latent_full")[0]]["inputs"]["length"]
    assert len(A.by_title(g, "OS:guide")) == 9
