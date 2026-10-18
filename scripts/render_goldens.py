"""Render every passing golden of every shipped preset at its locked seed.

  python scripts/render_goldens.py [--preset X] [--golden N] [--size final|draft] [--server URL] [--no-trailer]

For each presets/<name>.json with examples/<name>/goldens.json, every golden with pass == true is rendered
through its stage chain at the chosen size:
  final = 1088x1920 (9:16) or 1920x1088 (16:9); draft = the size recorded in goldens.json (704x1280 / 1280x704).
  levitate    base workflow, prompt = template + goldens prompt_fill + intensity phrase
  crash_zoom  workflows/crash_zoom.api.json, SGReprojectMove bbox = golden target_bbox (normalised)
  vertigo     workflows/vertigo.api.json, SGReprojectMove bbox = golden subject_bbox (normalised)
  petrify     Qwen stone stage at the target size (stage seed 8) -> workflows/petrify.api.json
  disintegrate Qwen clean-plate stage at the target size (cached by content hash, STAGE_SALT) ->
              workflows/disintegrate.api.json (SGDisintegrate guide keys), prompt = template + golden prompt_fill
  earth_zoom  "Pull Back": the shipped graph from the golden's recipe (prompt, inner_rect) with the shipped
              Qwen S1 still (examples/earth_zoom/ladder_NN_S1.png, resized). The still is NOT regenerated:
              inner_rect was measured on that exact still, a new Qwen still would need a new measurement.
              Forward + reverse via scripts/earth_zoom_assemble.py.
Output: examples/<preset>/expected/<input-stem>_seed<seed>_<size>.mp4 (recipe in MP4 tags, sidecar in recipes/),
one line per clip in examples/RENDER-LOG.md. The trailer preset is assembled from the others at the end.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.opensauce import (  # noqa: E402
    by_title,
    ensure_recipe_node,
    fill_prompt,
    intensity_phrase,
    load_preset,
    stamp_recipe,
)

EX = ROOT / "examples"
LOG = EX / "RENDER-LOG.md"
TMP = ROOT / "tmp" / "render_goldens"
FINAL = {"portrait": (1088, 1920), "landscape": (1920, 1088)}
SHIPPED = ("levitate", "crash_zoom", "vertigo", "petrify", "disintegrate", "earth_zoom")
STAGE_SALT = "disintegrate-plate-v2"  # bump to invalidate cached stage stills


def _set(g: dict, title: str, **kv) -> None:
    for nid in by_title(g, title):
        g[nid]["inputs"].update(kv)


def size_of(golden: dict, size: str) -> tuple[int, int]:
    w, h = golden["size"]
    if size == "draft":
        return w, h
    return FINAL["portrait" if h > w else "landscape"]


def patch_size(g: dict, w: int, h: int) -> None:
    for t in ("OS:resize", "OS:depth_resize", "OS:resize_end"):
        _set(g, t, **{"resize_type.width": w, "resize_type.height": h})
    _set(g, "OS:latent", width=w // 2, height=h // 2)  # two-stage base graph: stage 1 at half size
    _set(g, "OS:latent_full", width=w, height=h)


def patch_seed(g: dict, preset: str, seed: int, image: Path) -> None:
    _set(g, "OS:seed", noise_seed=seed)
    ensure_recipe_node(g, preset, seed)
    for nid in by_title(g, "OS:recipe"):
        inp = g[nid]["inputs"]
        extra = json.loads(inp.get("extra_json") or "{}")
        extra["inputs"] = [{"name": image.name, "sha256": sha(image)}]
        inp.update(preset=preset, seed=seed, extra_json=json.dumps(extra), burn_qr=False)


def set_bbox(g: dict, box: list[float]) -> None:
    x0, y0, x1, y1 = box
    _set(g, "OS:reproject", bbox_x0=x0, bbox_y0=y0, bbox_x1=x1, bbox_y1=y1)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(server: str, graph: dict, out: Path, prefix: str, image: Path | None = None,
        end_image: Path | None = None, extra: list[str] | None = None) -> tuple[list[str], float]:
    """Submit via scripts/run_workflow.py (upload, poll, download from the ComfyUI output dir)."""
    out.mkdir(parents=True, exist_ok=True)
    wf = out / f"{prefix.replace('/', '_')}.api.json"
    wf.write_text(json.dumps(graph), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "scripts" / "run_workflow.py"), str(wf), "--server", server,
           "--out", str(out), "--prefix", prefix]
    if image:
        cmd += ["--image", str(image)]
    if end_image:
        cmd += ["--end-image", str(end_image)]
    t0 = time.time()
    p = subprocess.run([*cmd, *(extra or [])], capture_output=True, text=True, cwd=ROOT)
    wall = time.time() - t0
    i = p.stdout.rfind("{\n")
    outs = json.loads(p.stdout[i:]).get("outputs", []) if p.returncode == 0 and i >= 0 else []
    if not outs:
        raise RuntimeError(f"{prefix} failed\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return outs, wall


def load(name: str) -> dict:
    return json.loads((ROOT / "workflows" / f"{name}.api.json").read_text(encoding="utf-8"))


def build(preset: str, golden: dict, w: int, h: int, server: str, work: Path, tag: str):
    """Return (video graph, image, end_image, stage wall s)."""
    img = EX / preset / golden["input"]
    if preset == "levitate":
        pre = load_preset("levitate")
        gs = json.loads((EX / "levitate" / "goldens.json").read_text(encoding="utf-8"))
        prompt, neg = fill_prompt(pre, gs["prompt_fill"])
        prompt = f"{prompt}, {intensity_phrase(pre, pre['defaults']['intensity'])}"
        g = json.loads((ROOT / pre["base_workflow"]).read_text(encoding="utf-8"))
        _set(g, "OS:prompt", text=prompt)
        _set(g, "OS:negative", text=neg)
        return g, img, None, 0.0
    if preset in ("crash_zoom", "vertigo"):
        g = load(preset)
        set_bbox(g, golden["target_bbox" if preset == "crash_zoom" else "subject_bbox"])
        return g, img, None, 0.0
    if preset == "petrify":
        st = load("_stage_petrify_qwen")
        patch_size(st, w, h)
        outs, sw = run(server, st, work, f"opensauce/golden_stage_{tag}", image=img)
        still = next(o for o in outs if "petrify_stone" in Path(o).name)
        return load("petrify"), img, Path(still), sw
    if preset == "disintegrate":
        st = load("_stage_disintegrate_plate")
        patch_size(st, w, h)
        for k, v in (golden.get("stage_set") or {}).items():  # e.g. a per-input plate prompt
            title, key = k.split(".", 1)
            _set(st, title, **{key: v})
        plate, sw = cached_stage(server, st, img, work, f"opensauce/golden_stage_{tag}", "disintegrate_plate_0")
        pre = load_preset("disintegrate")
        prompt, neg = fill_prompt(pre, golden.get("prompt_fill"))
        g = load("disintegrate")
        _set(g, "OS:prompt", text=prompt)
        _set(g, "OS:negative", text=neg)
        return g, img, plate, sw
    if preset == "earth_zoom":
        rid = re.search(r"recipe ([0-9a-f]{10})", golden["pull_back"]["render"]).group(1)
        g = json.loads((ROOT / "recipes" / f"{rid}.json").read_text(encoding="utf-8"))["api_workflow"]
        nn = Path(golden["input"]).stem.split("_")[-1]
        return g, img, EX / "earth_zoom" / f"ladder_{nn}_S1.png", 0.0
    raise SystemExit(f"no render chain for preset {preset}")


def cached_stage(server: str, graph: dict, image: Path, work: Path, prefix: str, pick: str) -> tuple[Path, float]:
    """Run a still stage once per (salt, graph minus the upload name, input bytes); reuse the PNG after that."""
    g = copy.deepcopy(graph)
    for nid in by_title(g, "OS:image"):
        g[nid]["inputs"].pop("image", None)
    key = hashlib.sha256((STAGE_SALT + json.dumps(g, sort_keys=True) + sha(image)).encode()).hexdigest()[:16]
    hit = TMP / "_stage_cache" / f"{key}.png"
    if hit.exists():
        print(f"stage cache hit {hit.name}", flush=True)
        return hit, 0.0
    outs, wall = run(server, graph, work, prefix, image=image)
    still = next(o for o in outs if pick in Path(o).name)
    hit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(still, hit)
    return hit, wall


def passing(preset: str, golden: dict) -> bool:
    return golden.get("pull_back", {}).get("pass") is True if preset == "earth_zoom" else golden.get("pass") is True


def render_one(preset: str, gi: int, golden: dict, size: str, server: str) -> dict:
    w, h = size_of(golden, size)
    stem, seed = Path(golden["input"]).stem, golden["seed"]
    name = f"{stem}_seed{seed}_{size}"
    tag = f"{preset}_{name}"
    work = TMP / preset / name
    exp = EX / preset / "expected"
    exp.mkdir(parents=True, exist_ok=True)
    dst = exp / f"{name}.mp4"

    g, img, end, stage_wall = build(preset, golden, w, h, server, work, tag)
    g = copy.deepcopy(g)
    patch_size(g, w, h)
    patch_seed(g, preset, seed, img)
    outs, wall = run(server, g, work, f"opensauce/golden_{tag}", image=img, end_image=end)
    mp4s = [Path(o) for o in outs if o.endswith(".mp4")]
    main = next(p for p in mp4s if "_clean" not in p.name)
    for nid in by_title(g, "OS:image"):
        g[nid]["inputs"]["image"] = img.name
    st = stamp_recipe(main, g, preset, seed, img, server)
    extra_files = []
    if preset == "earth_zoom":
        clean = next(p for p in mp4s if "_clean" in p.name)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "earth_zoom_assemble.py"), "--clean", str(clean),
                        "--recipe", str(st["sidecar"]), "--out", str(exp / name)], check=True, cwd=ROOT)
        extra_files.append(exp / f"{name}_reverse.mp4")
    else:
        shutil.copyfile(st["video"], dst)
    total = stage_wall + wall
    digest = sha(dst)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    if not LOG.exists():
        LOG.write_text("# Golden render log\n\nWritten by scripts/render_goldens.py. One line per clip.\n\n"
                       "| time | preset | golden | seed | size | wall s | recipe | sha256 | file |\n"
                       "|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        for p in [dst, *extra_files]:
            f.write(f"| {stamp} | {preset} | g{gi + 1:02d} | {seed} | {w}x{h} | {total:.1f} | {st['id']} | "
                    f"{sha(p) if p != dst else digest} | {p.relative_to(ROOT).as_posix()} |\n")
    print(f"[{preset} g{gi + 1:02d}] {w}x{h} seed {seed} wall {total:.1f}s (stage {stage_wall:.1f}s) -> {dst} "
          f"recipe {st['id']} ({st['source']})", flush=True)
    return {"preset": preset, "golden": gi + 1, "size": f"{w}x{h}", "wall": round(total, 1), "file": str(dst),
            "recipe": st["id"], "sha256": digest}


def trailer(size: str) -> None:
    """Point the trailer's reuse globs at copies of the finished clips (names the globs expect)."""
    reuse = TMP / "trailer_reuse"
    src = {"vertigo_g01_v3_final.mp4": EX / "vertigo" / "expected" / f"input_01_seed11_{size}.mp4",
           "crash_zoom_g01_v2_final.mp4": EX / "crash_zoom" / "expected" / f"input_01_seed11_{size}.mp4",
           "levitate25v3_g01.mp4": EX / "levitate" / "expected" / f"input_01_seed11_{size}.mp4",
           "pull_back_g01_final.mp4": EX / "earth_zoom" / "expected" / f"input_01_seed11_{size}.mp4"}
    missing = [str(p) for p in src.values() if not p.exists()]
    if missing:
        print("trailer skipped, missing:", *missing, sep="\n  ")
        return
    for n, p in src.items():
        (reuse / n).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, reuse / n)
    out = EX / "trailer" / "expected" / f"trailer_g01_{size}.mp4"
    cmd = [sys.executable, "-m", "app", "trailer", "--image", str(EX / "levitate" / "input_01.jpg"),
           "--reuse-dir", str(reuse), "--out", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", choices=SHIPPED)
    ap.add_argument("--golden", type=int, help="1-based golden index in goldens.json")
    ap.add_argument("--size", choices=("final", "draft"), default="final")
    ap.add_argument("--server", default="http://127.0.0.1:8189")
    ap.add_argument("--no-trailer", action="store_true")
    a = ap.parse_args()

    done, failed = [], []
    for preset in [a.preset] if a.preset else SHIPPED:
        goldens = json.loads((EX / preset / "goldens.json").read_text(encoding="utf-8"))["goldens"]
        for gi, golden in enumerate(goldens):
            if (a.golden and gi + 1 != a.golden) or not passing(preset, golden):
                continue
            try:
                done.append(render_one(preset, gi, golden, a.size, a.server))
            except Exception as e:  # keep going: one failed golden should not block the rest
                print(f"[{preset} g{gi + 1:02d}] FAILED: {e}", flush=True)
                failed.append(f"{preset} g{gi + 1:02d}")
    print(f"\n{'preset':12} {'golden':6} {'size':10} {'wall s':>7}  file")
    for r in done:
        print(f"{r['preset']:12} g{r['golden']:02d}    {r['size']:10} {r['wall']:7.1f}  {r['file']}")
    if failed:
        print("FAILED:", ", ".join(failed))
    if not a.preset and not a.golden and not a.no_trailer and not failed:
        trailer(a.size)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
