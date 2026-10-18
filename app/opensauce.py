"""OPEN SAUCE: render a preset through the official Comfy SDK, then stamp the Fork This Shot recipe.

  python -m app menu
  python -m app render levitate --image photo.jpg [--seed 11 --intensity 0.6 --prompt "..."] [--out dir]
  python -m app fork outputs/levitate/levitate_11_recipe.mp4
  python -m app trailer --image photo.jpg [--title "OPEN SAUCE" --subtitle "..." --reuse-dir outputs] [--tag g01]

Target: COMFY_BASE_URL (default the local comfy-api-proxy, http://127.0.0.1:8190), COMFY_API_KEY (default "local").
The same code runs against a Comfy API deployment by changing those two variables.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_nodes" / "shotgrammar"))

DEFAULT_BASE_URL = "http://127.0.0.1:8190"
DEFAULT_COMFY_URL = "http://127.0.0.1:8189"  # only used to fetch the recipe sidecar the SG node wrote server-side

# (preset file stem, tile name, fallback one_line when the preset file does not exist yet)
TILES = [
    ("vertigo", "Vertigo", "The subject stays locked while the world rushes toward you."),
    ("crash_zoom", "Crash Zoom", "A violent push from wide to detail in under a second."),
    ("disintegrate", "Disintegrate", "The subject chars and crumbles into ash and embers that blow away."),
    ("petrify", "Petrify", "Turn one photo into a statue reveal."),
    ("levitate", "Levitate", "The subject rises; hair and clothes know it."),
    ("trailer", "Main Character Trailer", "One photo becomes a three-shot trailer with a title card."),
]


# ---------------------------------------------------------------- presets and prompt

def load_preset(name: str) -> dict:
    name = ALIASES.get(name, name)
    p = ROOT / "presets" / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"preset '{name}' not found ({p}). Run `python -m app menu`.")
    return json.loads(p.read_text(encoding="utf-8"))


def fill_prompt(preset: dict, fill: dict | None = None) -> tuple[str, str]:
    """Return (prompt, negative) from the preset's prompt_module. Unknown placeholders stay as written."""
    pm = preset["prompt_module"]
    values = {**pm.get("defaults", {}), **(fill or {})}
    prompt = re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), pm["template"])
    return prompt, pm.get("negative", "")


def intensity_phrase(preset: dict, intensity: float) -> str:
    """Nearest intensity_map phrase; used only by presets with no geometry move (the phrase is prompt text)."""
    imap = preset["prompt_module"].get("intensity_map") or {}
    if not imap:
        return ""
    return imap[min(imap, key=lambda k: abs(float(k) - intensity))]


def workflow_path(preset: dict) -> Path:
    own = ROOT / "workflows" / f"{preset['preset']}.api.json"
    return own if own.exists() else ROOT / preset["base_workflow"]


# ---------------------------------------------------------------- graph patching

def by_title(graph: dict, title: str) -> list[str]:
    return [nid for nid, n in graph.items() if n.get("_meta", {}).get("title") == title]


def _set(graph: dict, title: str, **kv) -> None:
    for nid in by_title(graph, title):
        graph[nid]["inputs"].update(kv)


def ensure_recipe_node(graph: dict, preset: str, seed: int, inputs: list | None = None) -> None:
    """Base workflows have no Fork This Shot node: splice SGRecipeEmbed between the decode and CreateVideo."""
    if by_title(graph, "OS:recipe"):
        return
    create = by_title(graph, "OS:create")[0]
    new_id = str(max(int(k) for k in graph) + 1)
    graph[new_id] = {
        "class_type": "SGRecipeEmbed",
        "inputs": {"images": graph[create]["inputs"]["images"], "preset": preset, "seed": seed,
                   "recipe_base_url": "https://github.com/lightbrushproject/opensauce/blob/main/recipes/",
                   "models": "\n".join(_models_of(graph)),
                   "extra_json": json.dumps({"inputs": inputs or []})},
        "_meta": {"title": "OS:recipe"},
    }
    graph[create]["inputs"]["images"] = [new_id, 0]


def patch_graph(graph: dict, preset: dict, *, prompt: str, negative: str, seed: int, intensity: float | None,
                prefix: str, inputs: list | None = None) -> dict:
    """Patch every OS:* node from the preset defaults and the user's choices. Returns a patched copy.

    The OS:image node is left alone: the SDK asset is attached at submit time.
    """
    g = copy.deepcopy(graph)
    d = preset["defaults"]
    w, h, frames, fps = d["width"], d["height"], d["frames"], d["fps"]
    ensure_recipe_node(g, preset["preset"], seed, inputs)
    _set(g, "OS:prompt", text=prompt)
    _set(g, "OS:negative", text=negative)
    _set(g, "OS:seed", noise_seed=seed)
    _set(g, "OS:resize", **{"resize_type.width": w, "resize_type.height": h})
    _set(g, "OS:depth_resize", **{"resize_type.width": w, "resize_type.height": h})
    _set(g, "OS:latent", width=w // 2, height=h // 2, length=frames)  # stage 1 runs at half size
    _set(g, "OS:latent_full", width=w, height=h, length=frames)
    _set(g, "OS:audio_latent", frames_number=frames, frame_rate=fps)
    _set(g, "OS:fps_cond", frame_rate=float(fps))
    _set(g, "OS:create", fps=float(fps))
    _set(g, "OS:reproject", n_frames=frames)
    if intensity is not None:
        _set(g, "OS:reproject", intensity=intensity)
    _set(g, "OS:recipe", preset=preset["preset"], seed=seed)
    _set(g, "OS:save", filename_prefix=prefix)
    return g


# ---------------------------------------------------------------- recipe helpers

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _models_of(graph: dict) -> list[str]:
    for nid in by_title(graph, "OS:recipe"):
        m = [x.strip() for x in str(graph[nid]["inputs"].get("models", "")).splitlines() if x.strip()]
        if m:
            return m
    out = set()
    for n in graph.values():
        for k, v in n["inputs"].items():
            if k.endswith("_name") and isinstance(v, str) and v.endswith((".safetensors", ".gguf", ".pth", ".ckpt")):
                out.add(v)
    return sorted(out)


def qr_url_from_video(mp4: Path) -> str | None:
    """Decode the QR burned into the last frames (Fork This Shot) and return its URL."""
    import cv2

    cap = cv2.VideoCapture(str(mp4))
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        det = cv2.QRCodeDetector()
        for idx in (n - 2, n - 6, n - 10):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(idx, 0))
            ok, frame = cap.read()
            if ok:
                text, _, _ = det.detectAndDecode(frame)
                if text:
                    return text
    finally:
        cap.release()
    return None


def fetch_server_recipe(recipe_id: str, comfy_url: str) -> dict | None:
    """Raw ComfyUI /view fetch of the sidecar SGRecipeEmbed wrote server-side (the SDK has no route for it)."""
    q = urllib.parse.urlencode({"filename": f"{recipe_id}.json", "subfolder": "opensauce/recipes", "type": "output"})
    try:
        with urllib.request.urlopen(f"{comfy_url}/view?{q}", timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None


def stamp_recipe(mp4: Path, graph: dict, preset: str, seed: int, image: Path, comfy_url: str) -> dict:
    """Embed the recipe in the MP4 tags and recipes/ sidecar. Prefer the server's recipe so QR id == tag id."""
    import recipe as R

    rec = None
    url = qr_url_from_video(mp4)
    if url:
        m = re.search(r"([0-9a-f]{10})\.json", url)
        if m:
            rec = fetch_server_recipe(m.group(1), comfy_url)
    source = "server sidecar, matches the burned QR"
    if rec is None:
        source = "built locally, id may differ from the burned QR"
        rec = R.build_recipe(preset, seed, [{"name": image.name, "sha256": _sha(image)}], _models_of(graph), graph)
    side = R.write_sidecar(rec, ROOT / "recipes")
    out = R.embed_mp4_metadata(mp4, rec)
    return {"id": rec["id"], "url": url or R.recipe_url(rec), "video": out, "sidecar": side, "source": source}


# ---------------------------------------------------------------- render (official Comfy SDK)

ALIASES = {"pull_back": "earth_zoom"}  # menu name -> preset file


def sdk_runner(graph: dict, assets: dict, out: Path, prefix: str, timeout: float) -> list[Path]:
    """Run one graph through the official Comfy SDK. assets: {OS: title -> local image file}. Returns saved files."""
    from comfy_sdk import Comfy

    os.environ.setdefault("COMFY_BASE_URL", DEFAULT_BASE_URL)
    os.environ.setdefault("COMFY_API_KEY", "local")
    client = Comfy()
    wf = client.workflows.from_json(copy.deepcopy(graph))  # the SDK mutates what it is given
    for title, path in assets.items():
        asset = client.assets.from_file(path)
        for nid in by_title(graph, title):
            wf.set_input(nid, "image", asset)
    print(f"submitting '{prefix}' via Comfy SDK -> {os.environ['COMFY_BASE_URL']}", flush=True)
    job = client.run(wf, timeout=timeout)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for nid in [*by_title(graph, "OS:save"), *by_title(graph, "OS:save_still")]:
        for o in job.get_outputs(nid):  # the SDK output carries no filename: name it from the prefix + content type
            ext = mimetypes.guess_extension((getattr(o, "content_type", "") or "").split(";")[0]) or ".bin"
            saved.append(Path(o.to_file(out / (getattr(o, "filename", None) or f"{Path(prefix).name}_{nid}{ext}"))))
    return saved


def http_runner(graph: dict, assets: dict, out: Path, prefix: str, timeout: float) -> list[Path]:
    """Raw HTTP fallback: scripts/run_workflow.py straight against ComfyUI (:8189), no proxy needed."""
    out.mkdir(parents=True, exist_ok=True)
    wf = out / f"{Path(prefix).name}.api.json"
    wf.write_text(json.dumps(graph), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "scripts" / "run_workflow.py"), str(wf),
           "--server", os.environ.get("COMFYUI_URL", DEFAULT_COMFY_URL), "--out", str(out), "--timeout", str(int(timeout))]
    for title, path in assets.items():
        cmd += ["--load", f"{title}={path}"]
    print(f"submitting '{prefix}' via raw HTTP run_workflow.py", flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    i = p.stdout.rfind("{\n")
    outs = json.loads(p.stdout[i:]).get("outputs", []) if p.returncode == 0 and i >= 0 else []
    if not outs:
        raise SystemExit(f"raw run failed\n{p.stdout[-1200:]}\n{p.stderr[-1200:]}")
    return [Path(o) for o in outs]


def auto_runner(graph, assets, out, prefix, timeout):
    """SDK first; if the SDK/proxy path fails (proxy down, upload route missing), say so and use raw HTTP."""
    try:
        return sdk_runner(graph, assets, out, prefix, timeout)
    except Exception as e:  # noqa: BLE001 - any SDK/proxy failure falls back
        print(f"SDK path failed ({type(e).__name__}: {e}); falling back to raw HTTP", flush=True)
        return http_runner(graph, assets, out, prefix, timeout)


def pick_output(files: list[Path], prefix: str, kind: str) -> Path:
    """The step's result among everything the run saved: by media kind and filename prefix, never *_clean."""
    stem = Path(prefix).name
    exts = (".mp4",) if kind == "video" else (".png", ".jpg", ".jpeg", ".webp")
    hits = [f for f in files if f.suffix.lower() in exts and f.name.startswith(stem) and "_clean" not in f.name]
    if not hits:
        raise SystemExit(f"step '{prefix}' produced no {kind} output (got {[f.name for f in files]})")
    return sorted(hits)[-1]


def run_stage(step: dict, preset: dict, image: Path, produced: dict, name: str, seed: int, out: Path,
              runner, timeout: float) -> tuple[Path, str]:
    """Run one non-final step (an image-producing stage workflow). Returns (its still, stage recipe id)."""
    import recipe as R

    g = json.loads((ROOT / step["workflow"]).read_text(encoding="utf-8"))
    d = preset["defaults"]
    _set(g, "OS:resize", **{"resize_type.width": d["width"], "resize_type.height": d["height"]})
    prefix = f"opensauce/{name}_{seed}_{step['name']}"
    _set(g, "OS:save_still", filename_prefix=prefix)
    for k, v in (step.get("set") or {}).items():
        title, key = k.split(".", 1)
        _set(g, title, **{key: v})
    assets = {t: (image if src == "input" else produced[src]) for t, src in step["images"].items()}
    files = runner(g, assets, out, prefix, timeout)
    still = pick_output(files, prefix, "image")
    rec = R.build_recipe(f"{preset['preset']}:{step['name']}", seed,
                         [{"name": p.name, "sha256": _sha(p)} for p in assets.values()], _models_of(g), g)
    R.write_sidecar(rec, ROOT / "recipes")
    return still, rec["id"]


def render(preset_name: str, image: Path, *, seed: int = 11, intensity: float | None = None,
           prompt: str | None = None, fill: dict | None = None, out: Path | None = None,
           timeout: float = 3600, runner=None, qr: bool = False) -> dict:
    """Render a preset. A preset with `run_steps` is a chain: every step but the last is an image stage whose
    saved still feeds a named OS:* LoadImage of the next step; the last step's MP4 is stamped with the recipe."""
    runner = runner or auto_runner
    preset = load_preset(preset_name)
    steps = preset.get("run_steps") or []
    final = steps[-1] if steps else {}
    graph = json.loads(workflow_path(preset).read_text(encoding="utf-8"))
    if by_title(graph, "OS:image_end") and not steps:
        raise SystemExit(f"'{preset_name}' needs its Qwen stage still but declares no run_steps.")
    text, negative = fill_prompt(preset, fill)
    if "{" in text and not prompt:  # unfilled slots: keep the workflow's own tuned prompt
        text = graph[by_title(graph, "OS:prompt")[0]]["inputs"]["text"]
    has_move = bool(by_title(graph, "OS:reproject"))
    if prompt:
        text = prompt
    elif intensity is not None and not has_move:
        phrase = intensity_phrase(preset, intensity)
        text = f"{text}, {phrase}" if phrase else text
    effective = intensity if intensity is not None else preset["defaults"].get("intensity")
    out = Path(out or ROOT / "outputs" / preset_name)

    produced: dict[str, Path] = {}
    stage_ids: list[dict] = []
    for step in steps[:-1]:
        t0 = time.time()
        produced[step["name"]], rid = run_stage(step, preset, image, produced, preset_name, seed, out / "stages",
                                                runner, timeout)
        stage_ids.append({"step": step["name"], "recipe": rid, "still": produced[step["name"]].name})
        print(f"step '{step['name']}': {produced[step['name']]} recipe {rid} ({time.time() - t0:.0f}s)", flush=True)

    patched = patch_graph(graph, preset, prompt=text, negative=negative, seed=seed,
                          intensity=effective if has_move else None,
                          prefix=f"opensauce/{preset_name}_{seed}",
                          inputs=[{"name": image.name, "sha256": _sha(image)}])
    for nid in by_title(patched, "OS:recipe"):
        patched[nid]["inputs"]["burn_qr"] = qr  # opt-in; the recipe is always in the MP4 tags + sidecar
    if stage_ids:
        for nid in by_title(patched, "OS:recipe"):
            inp = patched[nid]["inputs"]
            extra = json.loads(inp.get("extra_json") or "{}")
            extra["stages"] = stage_ids
            inp["extra_json"] = json.dumps(extra)
    assets = {"OS:image": image, **{t: (image if src == "input" else produced[src])
                                     for t, src in (final.get("images") or {}).items()}}
    api_graph = copy.deepcopy(patched)  # keep a clean copy for the recipe
    files = runner(patched, assets, out, f"opensauce/{preset_name}_{seed}", timeout)
    if steps:
        video = pick_output(files, f"opensauce/{preset_name}_{seed}", "video")
    else:
        video = next((p for p in files if p.suffix == ".mp4"), None)
        if video is None:
            raise SystemExit("job finished but the SaveVideo node returned no output")

    for title, path in assets.items():
        for nid in by_title(api_graph, title):
            api_graph[nid]["inputs"]["image"] = path.name
    stamp = stamp_recipe(video, api_graph, preset["preset"], seed, image,
                         os.environ.get("COMFYUI_URL", DEFAULT_COMFY_URL))
    return {"raw": video, "stages": stage_ids, **stamp}


# ---------------------------------------------------------------- trailer (3 shots + title card)

def find_reuse(reuse_dir: Path, shot: dict, tag: str) -> Path | None:
    for pat in shot.get("reuse_glob", []):
        hits = sorted(reuse_dir.glob(pat.format(tag=tag)))
        if hits:
            return hits[-1]
    return None


def trailer(image: Path, *, title: str | None = None, subtitle: str | None = None, reuse_dir: Path | None = None,
            tag: str = "g01", seed: int = 11, grade: str | None = None, out: Path | None = None,
            server: str = DEFAULT_COMFY_URL, qr: bool = False) -> dict:
    """Render (or reuse) the shots, then join them as one take with shotgrammar.trailer.assemble (bridges
    rendered through workflows/bridge.api.json on this server and cached under outputs/trailer/bridges/)."""
    import bridge as B
    import recipe as R
    import trailer as T

    preset = load_preset("trailer")
    tc = preset["title_card"]
    title, subtitle = title or tc["title"], subtitle or tc["subtitle"]
    grade = grade or preset["grade_chip"]
    shots = []
    for sh in preset["shots"]:
        path = find_reuse(reuse_dir, sh, tag) if reuse_dir else None
        if path is None and sh.get("needs_qwen_stage"):
            raise SystemExit(f"'{sh['label']}' needs the Qwen-Image-Edit zoom-out stage, which the app runner cannot "
                             f"drive from one graph. Render it with the earth_zoom steps in presets/earth_zoom.json "
                             f"and pass --reuse-dir (looked for {sh['reuse_glob']}).")
        if path is None:
            path = render(sh["preset"], image, seed=seed)["video"]
        print(f"shot {sh['name']}: {path}", flush=True)
        shots.append({**sh, "path": str(path)})

    sub_ids = {}
    for sh in shots:
        try:
            sub_ids[sh["name"]] = R.read_recipe_from_mp4(sh["path"], sidecar_dir=ROOT / "recipes")["id"]
        except Exception:
            sub_ids[sh["name"]] = None  # reused file without tags
    out = Path(out or ROOT / "outputs" / "trailer" / f"trailer_{tag}.mp4")
    import cv2

    counts = []
    for sh in shots:
        cap = cv2.VideoCapture(sh["path"])
        counts.append(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        cap.release()
    plan = T.cut_plan([{**s, "src_frames": n} for s, n in zip(shots, counts)],
                      preset["defaults"]["total_s_ceiling"], title_hold_s=tc["hold_s"],
                      title_fade_frames=tc["scale_in_frames"], title_mode=tc.get("mode", "hold"))
    bcfg = preset.get("bridges", {})
    bridges_on = bcfg.get("enabled", False)
    rec = R.build_recipe("trailer", seed, [{"name": image.name, "sha256": _sha(image)}],
                         [preset["model"]], {"plan": plan, "grade_chip": grade, "bridges": {
                             "enabled": bridges_on, "workflow": bcfg.get("workflow"),
                             "match_threshold": bcfg.get("match_threshold", B.MATCH_THRESHOLD),
                             "bridge_in": {s["name"]: s.get("bridge_in") for s in shots if s.get("bridge_in")}}},
                         {"shots": [{"name": s["name"], "file": Path(s["path"]).name, "recipe": sub_ids[s["name"]]}
                                    for s in shots], "title": title, "subtitle": subtitle})

    def provider(a, b, bnd):
        t0 = time.time()
        path = B.render_bridge(a, b, bnd["frames"], bnd["prompt"], bnd["seed"], server=server)
        print(f"bridge {bnd['a']} -> {bnd['b']}: {bnd['frames']} f, {path.name} ({time.time() - t0:.1f}s)", flush=True)
        bnd["file"] = path.name
        return T.read_frames(path)

    res = T.assemble(shots, title, subtitle, grade, out, rec, ROOT / "recipes", plan, tc["style"], tc["position"],
                     provider if bridges_on else None, bcfg.get("match_threshold", B.MATCH_THRESHOLD),
                     burn_qr=qr)
    for b in res["plan"]["bridges"]:
        print(f"boundary {b['a']} -> {b['b']}: {b['kind']} (diff {b['diff']}"
              + (f", {b['used_frames']} f)" if b["kind"] == "bridge" else ")"), flush=True)
    return {**res, "id": rec["id"], "url": R.recipe_url(rec)}


# ---------------------------------------------------------------- CLI

def cmd_menu(_args) -> int:
    print(f"{'#':<3}{'Preset':<26}{'Status':<9}One line")
    for i, (stem, name, fallback) in enumerate(TILES, 1):
        p = ROOT / "presets" / f"{stem}.json"
        if p.exists():
            line, status = json.loads(p.read_text(encoding="utf-8")).get("one_line", fallback), "shipped"
        else:
            line, status = fallback, "coming"
        print(f"{i:<3}{name:<26}{status:<9}{line}")
    return 0


def cmd_render(a) -> int:
    fill = dict(kv.split("=", 1) for kv in a.fill)
    r = render(a.preset, Path(a.image), seed=a.seed, intensity=a.intensity, prompt=a.prompt, fill=fill,
               out=Path(a.out) if a.out else None, timeout=a.timeout, qr=a.qr)
    for st in r["stages"]:
        print(f"stage:   {st['step']} -> {st['still']}  recipe {st['recipe']}")
    print(f"video:   {r['video']}")
    print(f"sidecar: {r['sidecar']}")
    print(f"FORK THIS SHOT  recipe {r['id']}  {r['url']}  [{r['source']}]" + ("  (QR burned in)" if a.qr else ""))
    print(f"Restore the graph: python -m app fork {r['video']}")
    return 0


def cmd_trailer(a) -> int:
    r = trailer(Path(a.image), title=a.title, subtitle=a.subtitle, reuse_dir=Path(a.reuse_dir) if a.reuse_dir else None,
                tag=a.tag, seed=a.seed, grade=a.grade, out=Path(a.out) if a.out else None, qr=a.qr)
    print(f"video:   {r['video']}  ({r['plan']['total_frames']} frames, {r['plan']['total_s']:.1f}s)")
    print(f"poster:  {r['poster']}")
    print(f"sidecar: {r['sidecar']}")
    print(f"FORK THIS SHOT  recipe {r['id']}  {r['url']}" + ("  (QR burned in)" if a.qr else ""))
    return 0


def cmd_fork(a) -> int:
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "fork_this_shot.py"), a.video])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("menu", help="list the six tiles").set_defaults(fn=cmd_menu)
    r = sub.add_parser("render", help="render one preset from one photo")
    r.add_argument("preset")
    r.add_argument("--image", required=True)
    r.add_argument("--seed", type=int, default=11)
    r.add_argument("--intensity", type=float)
    r.add_argument("--prompt", help="replace the preset prompt entirely")
    r.add_argument("--fill", action="append", default=[], metavar="KEY=VALUE",
                   help="fill a prompt-template slot (subject=woman); repeatable")
    r.add_argument("--out")
    r.add_argument("--qr", action="store_true", help="also burn the recipe QR into the last frames (off by default)")
    r.add_argument("--timeout", type=float, default=3600)
    r.set_defaults(fn=cmd_render)
    t = sub.add_parser("trailer", help="one photo -> 3-shot trailer with title card and poster")
    t.add_argument("--image", required=True)
    t.add_argument("--title")
    t.add_argument("--subtitle")
    t.add_argument("--reuse-dir", help="reuse finished shot renders found here (required for Pull Back)")
    t.add_argument("--tag", default="g01", help="golden/input tag used to find reusable renders")
    t.add_argument("--seed", type=int, default=11)
    t.add_argument("--grade", help="grade chip (default: preset's warm_film)")
    t.add_argument("--out")
    t.add_argument("--qr", action="store_true", help="also burn the recipe QR into the last frames (off by default)")
    t.set_defaults(fn=cmd_trailer)
    f = sub.add_parser("fork", help="restore the recipe and API workflow from an OPEN SAUCE video")
    f.add_argument("video")
    f.set_defaults(fn=cmd_fork)
    a = ap.parse_args(argv)
    return a.fn(a)
