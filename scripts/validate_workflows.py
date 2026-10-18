"""Gate: every workflows/*.api.json parses, every node class resolves on the
OpenSauce ComfyUI server, and every referenced model file exists on disk.

usage: python scripts/validate_workflows.py [--server http://127.0.0.1:8189] [--no-server]
exit code 0 = all good, 1 = a workflow failed, 2 = nothing to validate yet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
MODEL_EXT = (".safetensors", ".gguf", ".pth", ".pt", ".ckpt", ".bin", ".onnx")
# OS:* titles the app / golden renderer patch, per workflow file (a missing one fails the gate)
REQUIRED_TITLES = {
    "_stage_disintegrate_plate.api.json": ["OS:image", "OS:resize", "OS:matte", "OS:edit_prompt", "OS:edit_sampler",
                                           "OS:plate_noise_mask", "OS:composite", "OS:save_still"],
    "disintegrate.api.json": ["OS:image", "OS:resize", "OS:image_end", "OS:resize_end", "OS:matte", "OS:disintegrate",
                              "OS:prompt", "OS:negative", "OS:seed", "OS:latent_full", "OS:audio_latent",
                              "OS:guide_first", "OS:guide", "OS:fps_cond", "OS:create", "OS:ramp", "OS:grade",
                              "OS:recipe", "OS:save"],
}


def model_roots() -> list[Path]:
    roots = []
    env = os.environ.get("OPENSAUCE_MODELS")
    if env:
        roots.append(Path(env))
    comfy = Path(os.environ.get("COMFY_DIR", ROOT.parent / "comfy-opensauce-install"))
    for cand in (
        comfy / "models",
        comfy / "custom_nodes" / "comfyui_controlnet_aux" / "ckpts",
    ):
        if cand.exists():
            roots.append(cand)
    return roots


def file_index(roots: list[Path]) -> set[str]:
    names: set[str] = set()
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(MODEL_EXT):
                    names.add(f)
                    rel = Path(dirpath, f).relative_to(root).as_posix()
                    names.add(rel)
                    names.add(rel.split("/", 1)[-1])
    return names


def fetch_object_info(server: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{server}/object_info", timeout=5) as r:
            return json.load(r)
    except Exception as exc:  # server down is reported, not fatal
        print(f"  ! server {server} unreachable ({exc}); skipping node check")
        return None


def validate(path: Path, object_info: dict | None, known_files: set[str]) -> list[str]:
    errors: list[str] = []
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"json parse failed: {exc}"]
    if not isinstance(graph, dict) or not graph:
        return ["not an API-format graph (expected dict of node_id -> node)"]
    titles = {n.get("_meta", {}).get("title") for n in graph.values() if isinstance(n, dict)}
    for t in REQUIRED_TITLES.get(path.name, []):
        if t not in titles:
            errors.append(f"missing node titled {t}")
    for nid, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node:
            errors.append(f"node {nid}: missing class_type (is this UI format, not API format?)")
            continue
        ct = node["class_type"]
        if object_info is not None and ct not in object_info:
            errors.append(f"node {nid}: class_type {ct!r} not installed on server")
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, str) and "\n" in val:
                continue  # free-text lists (e.g. SGRecipeEmbed.models) are not file inputs
            if isinstance(val, str) and val.lower().endswith(MODEL_EXT):
                if known_files and val not in known_files and Path(val).name not in known_files:
                    errors.append(f"node {nid}.{key}: model file {val!r} not found under model roots")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8189")
    ap.add_argument("--no-server", action="store_true")
    args = ap.parse_args()

    files = sorted(WORKFLOWS.glob("*.api.json"))
    if not files:
        print("no workflows/*.api.json yet")
        return 2
    object_info = None if args.no_server else fetch_object_info(args.server)
    known = file_index(model_roots())
    failed = 0
    for f in files:
        errs = validate(f, object_info, known)
        status = "OK " if not errs else "FAIL"
        print(f"[{status}] {f.relative_to(ROOT)}")
        for e in errs:
            print(f"      - {e}")
        failed += bool(errs)
    print(f"{len(files) - failed}/{len(files)} workflows valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
