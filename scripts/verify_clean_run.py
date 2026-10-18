"""Verify the OPEN SAUCE build is API-free and (optionally) renders every shipped preset.

  python scripts/verify_clean_run.py                       # static audit, prints PASS/FAIL table
  python scripts/verify_clean_run.py --render [--err-log <comfy-install>/opensauce.err.log]

Static audit (no GPU):
  1. every class_type in workflows/*.api.json against an API/partner-node denylist and against
     /object_info python_module (comfy_api_nodes.* is always a partner node);
  2. class_type -> custom_nodes pack map;
  3. outbound-network call scan of custom_nodes/shotgrammar, app/ and scripts/;
  4. best-effort scan of the third-party packs the graphs use for download code (informational).

--render drives scripts/run_workflow.py once per shipped preset at its golden-1 seed and reports
wall time, output path, and any download-looking lines that appeared in the server error log
while rendering. Exit code 1 when the audit or any render fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DENY = re.compile(
    r"Api|API|Partner|Router|Cloud|Openai|OpenAI|Gemini|Kling|Runway|Minimax|MiniMax|Luma|Pika|Veo|"
    r"Ideogram|Recraft|Stability|BFL|Sora|Moonvalley|Pixverse|Vidu|Tripo|Rodin|Hunyuan3D.*Api"
)
NET_CALL = re.compile(
    r"\b(requests\.(get|post|put|head|request|Session)|httpx\.|urllib\.request|urlopen\(|http\.client|"
    r"aiohttp|websocket\.|socket\.(socket|create_connection)|hf_hub_download|snapshot_download|"
    r"wget|curl\b|git clone|pip install)"
)
URL = re.compile(r"https?://[^\s\"'`)>\]]+")
LOCAL = re.compile(r"https?://(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])")
DL_WORDS = re.compile(r"download|huggingface|https?://|hf_hub|connection (error|refused)|urlopen", re.I)

# default golden-1 render recipe per shipped preset (seeds from examples/<preset>/goldens.json)
EARTH_PROMPT = (
    "The flat grey bands around the photo are empty canvas. Paint over every grey area so the picture fills "
    "the whole frame edge to edge, a seamless wider view of the same scene from twice as far away. Above: open "
    "sky and distant red sandstone cliffs. Below and around: sandy canyon floor and rock. The man stays small "
    "in the middle, unchanged. Same warm soft daylight, same colors, photoreal. No grey, no border, no frame, "
    "no text."
)


def http_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def pack_of(module: str | None) -> str:
    if not module:
        return "UNKNOWN"
    if module.startswith("custom_nodes."):
        return module.split(".")[1]
    if module.startswith("comfy_api_nodes"):
        return "API-PARTNER"
    return "core"


def static_audit(server: str, object_info: Path | None):
    if object_info:
        info = json.loads(object_info.read_text(encoding="utf-8"))
    else:
        info = http_json(f"{server}/object_info")
    classes: dict[str, set[str]] = {}
    for wf in sorted((ROOT / "workflows").glob("*.api.json")):
        for node in json.loads(wf.read_text(encoding="utf-8")).values():
            classes.setdefault(node["class_type"], set()).add(wf.name)

    rows, api_hits, unresolved = [], [], []
    packs: dict[str, set[str]] = {}
    for ct in sorted(classes):
        mod = (info.get(ct) or {}).get("python_module")
        pack = pack_of(mod)
        packs.setdefault(pack, set()).add(ct)
        if mod is None:
            unresolved.append(ct)
        name_hit = bool(DENY.search(ct))
        if pack == "API-PARTNER" or (name_hit and pack in ("UNKNOWN",)):
            api_hits.append(ct)
        rows.append((ct, pack, "name-pattern match, local module" if name_hit and pack not in ("API-PARTNER", "UNKNOWN") else ""))

    # outbound-network scan of our own code
    own = [*sorted((ROOT / "custom_nodes" / "shotgrammar").rglob("*.py")),
           *sorted((ROOT / "app").rglob("*.py")),
           *sorted((ROOT / "scripts").glob("*.py"))]
    net = []
    for f in own:
        if "tests" in f.parts or f.name == Path(__file__).name:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            urls = URL.findall(line)
            remote = [u for u in urls if not LOCAL.match(u)]
            if NET_CALL.search(line) or remote:
                net.append((f.relative_to(ROOT).as_posix(), i, s[:140], bool(remote), bool(NET_CALL.search(line))))

    # third-party packs used by the graphs: informational download-code count
    third = {}
    for pack in sorted(p for p in packs if p not in ("core", "UNKNOWN", "API-PARTNER")):
        d = None
        for base in (ROOT / "custom_nodes", Path(os.environ.get("COMFY_DIR", ROOT.parent / "comfy-opensauce-install")) / "custom_nodes"):
            if (base / pack).is_dir():
                d = base / pack
                break
        if d is None or pack == "shotgrammar":
            continue
        n = 0
        for f in d.rglob("*.py"):
            try:
                n += len(re.findall(r"hf_hub_download|snapshot_download|urlopen|requests\.get|download_file|torch\.hub", f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
        third[pack] = n
    return classes, rows, packs, api_hits, unresolved, net, third


def print_audit(res) -> bool:
    classes, rows, packs, api_hits, unresolved, net, third = res
    print(f"\n== Static audit: {len(classes)} distinct class_types in workflows/*.api.json\n")
    print(f"{'class_type':42} {'pack':26} note")
    for ct, pack, note in rows:
        print(f"{ct:42} {pack:26} {note}")
    print("\n-- custom_nodes packs the graphs depend on")
    for p, cts in sorted(packs.items()):
        if p != "core":
            print(f"  {p}: {', '.join(sorted(cts))}")
    print(f"  core ComfyUI: {len(packs.get('core', []))} classes")
    print("\n-- outbound-network scan (shotgrammar, app, scripts)")
    remote_lines = [n for n in net if n[3]]
    for f, i, s, remote, call in net:
        tag = "REMOTE-URL" if remote else "net-call/local"
        print(f"  [{tag}] {f}:{i}: {s}")
    print("\n-- third-party packs used: download-code references (informational; only reached when a model file is missing)")
    for p, n in third.items():
        print(f"  {p}: {n}")
    ok_api = not api_hits and not unresolved
    print("\n== Result")
    print(f"{'check':58} result")
    print(f"{'no API/partner node classes in any workflow':58} {'PASS' if ok_api else 'FAIL ' + str(api_hits + unresolved)}")
    print(f"{'no comfy_api_nodes.* python_module':58} {'PASS' if 'API-PARTNER' not in packs else 'FAIL'}")
    print(f"{'remote URLs in own code (text only is OK, review above)':58} {len(remote_lines)} line(s)")
    return ok_api


def run(cmd: list[str]):
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return p, time.time() - t0


def last_json(stdout: str):
    i = stdout.rfind("{\n")
    return json.loads(stdout[i:]) if i >= 0 else {}


def render_all(server: str, out: Path, err_log: Path | None):
    from app.opensauce import fill_prompt, intensity_phrase, load_preset

    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    rw = [py, str(ROOT / "scripts" / "run_workflow.py"), "--server", server, "--out"]
    ex = ROOT / "examples"
    results = []
    err0 = err_log.stat().st_size if err_log and err_log.exists() else 0

    def step(label, args, outdir):
        p, wall = run([*rw, str(outdir), *args])
        js = last_json(p.stdout)
        ok = p.returncode == 0 and bool(js.get("outputs"))
        if not ok:
            print(f"[{label}] FAILED\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
        return ok, wall, js.get("outputs", [])

    def finish(preset, ok, wall, outs):
        mp4 = next((o for o in outs if o.endswith(".mp4")), "")
        results.append((preset, ok and bool(mp4), wall, mp4))

    # levitate: base workflow + prompt from preset
    lev = load_preset("levitate")
    g = json.loads((ex / "levitate" / "goldens.json").read_text(encoding="utf-8"))
    prompt, neg = fill_prompt(lev, g["prompt_fill"])
    prompt = f"{prompt}, {intensity_phrase(lev, lev['defaults']['intensity'])}"
    ok, wall, outs = step("levitate", [
        str(ROOT / lev["base_workflow"]), "--image", str(ex / "levitate" / "input_01.jpg"), "--prompt", prompt,
        "--negative", neg, "--seed", str(g["goldens"][0]["seed"]), "--prefix", "opensauce/verify_levitate"], out / "levitate")
    finish("levitate", ok, wall, outs)

    # crash_zoom / vertigo: single graph, default prompt in the graph is the golden-1 prompt
    for name in ("crash_zoom", "vertigo"):
        seed = json.loads((ex / name / "goldens.json").read_text(encoding="utf-8"))["goldens"][0]["seed"]
        ok, wall, outs = step(name, [str(ROOT / "workflows" / f"{name}.api.json"), "--image",
                                     str(ex / name / "input_01.jpg"), "--seed", str(seed),
                                     "--prefix", f"opensauce/verify_{name}"], out / name)
        finish(name, ok, wall, outs)

    # petrify: stage (Qwen + BiRefNet) then video
    seed = json.loads((ex / "petrify" / "goldens.json").read_text(encoding="utf-8"))["goldens"][0]["seed"]
    ok1, w1, o1 = step("petrify-stage", [str(ROOT / "workflows" / "_stage_petrify_qwen.api.json"), "--image",
                                         str(ex / "petrify" / "input_01.jpg")], out / "petrify_stage")
    still = next((o for o in o1 if "petrify_stone" in o), "")
    if ok1 and still:
        ok2, w2, o2 = step("petrify", [str(ROOT / "workflows" / "petrify.api.json"), "--image",
                                       str(ex / "petrify" / "input_01.jpg"), "--end-image", still, "--seed", str(seed),
                                       "--prefix", "opensauce/verify_petrify"], out / "petrify")
        finish("petrify", ok2, w1 + w2, o2)
    else:
        finish("petrify", False, w1, [])

    # pull_back: Qwen zoom-out stage then earth_zoom graph
    seed = json.loads((ex / "earth_zoom" / "goldens.json").read_text(encoding="utf-8"))["goldens"][0]["seed"]
    ok1, w1, o1 = step("pull_back-stage", [str(ROOT / "workflows" / "_stage_earth_zoom_outpaint.api.json"), "--image",
                                           str(ex / "earth_zoom" / "input_01.jpg"), "--set",
                                           f"OS:edit_prompt.prompt={json.dumps(EARTH_PROMPT)}"], out / "pull_back_stage")
    still = next((o for o in o1 if "earth_zoom_stage" in o), "")
    if ok1 and still:
        ok2, w2, o2 = step("pull_back", [str(ROOT / "workflows" / "earth_zoom.api.json"), "--image",
                                         str(ex / "earth_zoom" / "input_01.jpg"), "--end-image", still, "--seed", str(seed),
                                         "--prefix", "opensauce/verify_pull_back"], out / "pull_back")
        finish("pull_back", ok2, w1 + w2, [o for o in o2 if "clean" not in Path(o).name] or o2)
    else:
        finish("pull_back", False, w1, [])

    dl = []
    if err_log and err_log.exists():
        with err_log.open("rb") as f:
            f.seek(err0)
            dl = [ln for ln in f.read().decode("utf-8", "replace").splitlines() if DL_WORDS.search(ln)]
    return results, dl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8189")
    ap.add_argument("--object-info", type=Path, help="saved /object_info JSON instead of fetching")
    ap.add_argument("--render", action="store_true", help="also render every shipped preset at golden-1 seed")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp" / "verify_clean_run")
    ap.add_argument("--err-log", type=Path, help="server stderr log to scan for download/http lines during --render")
    a = ap.parse_args()

    ok = print_audit(static_audit(a.server, a.object_info))
    if a.render:
        results, dl = render_all(a.server, a.out, a.err_log)
        print("\n== Render (golden-1 seed, 704x1280 draft)\n")
        print(f"{'preset':12} {'result':7} {'wall s':>8}  output")
        for name, rok, wall, mp4 in results:
            print(f"{name:12} {'PASS' if rok else 'FAIL':7} {wall:8.1f}  {mp4}")
            ok = ok and rok
        print(f"\nserver log lines mentioning download/http during renders: {len(dl)}")
        for ln in dl[:20]:
            print("  ", ln[:200])
    print("\nOVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
