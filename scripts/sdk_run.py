"""Run an OPEN SAUCE workflow through the official Comfy SDK.

Default target is our own ComfyUI behind comfy-api-proxy (scripts/start_proxy.ps1):
    COMFY_BASE_URL=http://127.0.0.1:8190  COMFY_API_KEY=local
Point COMFY_BASE_URL at a Comfy API deployment and the same code runs in the cloud.

usage:
  python scripts/sdk_run.py workflows/levitate.api.json --image examples/levitate/input_01.png \
      --set 7.text="the subject slowly rises" --set 9.seed=11 --out outputs/levitate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from comfy_sdk import Comfy

IMAGE_FIELDS = ("image",)


def parse_set(items: list[str]) -> list[tuple[str, str, object]]:
    out = []
    for item in items:
        key, _, raw = item.partition("=")
        node_id, _, field = key.partition(".")
        try:
            val: object = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        out.append((node_id, field, val))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--image", help="input image; replaces every LoadImage node's image")
    ap.add_argument("--set", action="append", default=[], metavar="NODE.FIELD=VALUE")
    ap.add_argument("--out", default="outputs/sdk")
    ap.add_argument("--timeout", type=float, default=1800)
    args = ap.parse_args()

    os.environ.setdefault("COMFY_BASE_URL", "http://127.0.0.1:8190")
    os.environ.setdefault("COMFY_API_KEY", "local")
    client = Comfy()

    graph = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    wf = client.workflows.from_json(graph)

    if args.image:
        asset = client.assets.from_file(args.image)
        for nid, node in graph.items():
            if node.get("class_type") == "LoadImage":
                wf.set_input(nid, "image", asset)
    for nid, field, val in parse_set(args.set):
        wf.set_input(nid, field, val)

    print(f"submitting via Comfy SDK -> {os.environ['COMFY_BASE_URL']}")
    job = client.run(wf, timeout=args.timeout)
    print(f"job {job.id if hasattr(job, 'id') else ''} done")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for nid, node in graph.items():
        if not node.get("class_type", "").startswith(("Save", "VHS_VideoCombine")):
            continue
        try:
            for i, output in enumerate(job.get_outputs(nid)):
                name = getattr(output, "filename", None) or f"{nid}_{i}.bin"
                saved.append(output.to_file(out_dir / name))
        except Exception as exc:  # node produced nothing or proxy lacks the route
            print(f"  node {nid}: no outputs ({exc})")
    for p in saved:
        print("saved", p)
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
