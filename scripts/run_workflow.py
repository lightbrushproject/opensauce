"""Run an OpenSauce API-format workflow against a local ComfyUI.

Patches nodes by their OS:* _meta titles (image, prompt, seed, size, frames, fps),
POSTs to /prompt, polls /history, downloads outputs.

  python run_workflow.py workflows/_base_ltx_i2v.api.json --image in.png \
      --prompt "..." --seed 7 --width 704 --height 1280 --frames 97 --fps 24
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req) as r:
        return r.read()


def upload_image(server, path):
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + open(path, "rb").read() + \
           f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    r = json.loads(http(f"{server}/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
    return (r.get("subfolder") + "/" if r.get("subfolder") else "") + r["name"]


def by_title(wf, title):
    return [n for n in wf.values() if n.get("_meta", {}).get("title") == title]


def patch(wf, title, **kv):
    nodes = by_title(wf, title)
    for node in nodes:
        node["inputs"].update(kv)
    return bool(nodes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--server", default="http://127.0.0.1:8189")
    ap.add_argument("--image")
    ap.add_argument("--end-image", help="second LoadImage titled OS:image_end (e.g. petrify stone still)")
    ap.add_argument("--prompt")
    ap.add_argument("--negative")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--width", type=int, help="final width (multiple of 64 for the two-stage pipeline)")
    ap.add_argument("--height", type=int, help="final height (multiple of 64)")
    ap.add_argument("--frames", type=int, help="8k+1, e.g. 97 or 121")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--prefix", help="SaveVideo filename_prefix")
    ap.add_argument("--set", action="append", default=[], metavar="TITLE.key=VALUE",
                    help="patch any titled node input; VALUE parsed as JSON when possible (repeatable)")
    ap.add_argument("--load", action="append", default=[], metavar="TITLE=PATH",
                    help="upload PATH into the LoadImage titled TITLE (repeatable)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "outputs"))
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()

    wf = json.load(open(a.workflow))
    if a.image:
        patch(wf, "OS:image", image=upload_image(a.server, a.image))
    if a.end_image:
        patch(wf, "OS:image_end", image=upload_image(a.server, a.end_image))
    if a.prompt is not None:
        patch(wf, "OS:prompt", text=a.prompt)
    if a.negative is not None:
        patch(wf, "OS:negative", text=a.negative)
    if a.seed is not None:
        patch(wf, "OS:seed", noise_seed=a.seed)
    if a.width or a.height:
        for w, h in [(a.width, a.height)]:
            if (w and w % 64) or (h and h % 64):
                sys.exit("width/height must be multiples of 64 (stage 1 runs at half size, latent stride 32)")
        r = by_title(wf, "OS:resize")[0]["inputs"]
        w, h = a.width or r["resize_type.width"], a.height or r["resize_type.height"]
        patch(wf, "OS:resize", **{"resize_type.width": w, "resize_type.height": h})
        patch(wf, "OS:latent", width=w // 2, height=h // 2)
    if a.frames:
        if (a.frames - 1) % 8:
            sys.exit("frames must be 8k+1")
        patch(wf, "OS:latent", length=a.frames)
        patch(wf, "OS:audio_latent", frames_number=a.frames)
    if a.fps:
        patch(wf, "OS:audio_latent", frame_rate=a.fps)
        patch(wf, "OS:fps_cond", frame_rate=float(a.fps))
        patch(wf, "OS:create", fps=float(a.fps))
    if a.prefix:
        patch(wf, "OS:save", filename_prefix=a.prefix)
    for item in a.load:
        title, path = item.split("=", 1)
        if not patch(wf, title, image=upload_image(a.server, path)):
            sys.exit(f"--load: no node titled {title}")
    for item in a.set:
        lhs, val = item.split("=", 1)
        title, key = lhs.split(".", 1)  # titles have no dots; keys may (resize_type.width)
        try:
            val = json.loads(val)
        except json.JSONDecodeError:
            pass
        if not patch(wf, title, **{key: val}):
            sys.exit(f"--set: no node titled {title}")

    client_id = uuid.uuid4().hex
    t0 = time.time()
    try:
        resp = json.loads(http(f"{a.server}/prompt", json.dumps({"prompt": wf, "client_id": client_id}).encode(),
                               {"Content-Type": "application/json"}))
    except urllib.error.HTTPError as e:
        sys.exit(f"/prompt rejected: {e.read().decode()}")
    if resp.get("node_errors"):
        sys.exit(f"/prompt node_errors (those outputs would be skipped): {json.dumps(resp['node_errors'])}")
    pid = resp["prompt_id"]
    print("queued", pid, flush=True)

    while True:
        if time.time() - t0 > a.timeout:
            sys.exit("timeout")
        try:
            h = json.loads(http(f"{a.server}/history/{pid}"))
        except (urllib.error.URLError, TimeoutError, ConnectionError):  # a busy server may drop one poll; the job runs on
            time.sleep(10)
            continue
        if pid in h:
            entry = h[pid]
            break
        time.sleep(3)
    wall = time.time() - t0
    status = entry.get("status", {})
    if status.get("status_str") != "success":
        print(json.dumps(status, indent=1))
        sys.exit("FAILED")

    os.makedirs(a.out, exist_ok=True)
    saved = []
    for node_out in entry["outputs"].values():
        for key in ("images", "videos", "gifs", "audio"):
            for f in node_out.get(key, []):
                q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
                dst = os.path.join(a.out, f["filename"])
                open(dst, "wb").write(http(f"{a.server}/view?{q}"))
                saved.append(os.path.abspath(dst))
    print(json.dumps({"prompt_id": pid, "wall_seconds": round(wall, 1), "outputs": saved}, indent=1))


if __name__ == "__main__":
    main()
