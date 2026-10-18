"""SG Bridge: generated first-to-last-frame transitions so a multi-shot piece plays as one take (LAW-9).

plan_bridges() is pure numpy: per shot boundary it compares shot A's last frame with shot B's first frame.
Nearly identical framing (mean abs diff < threshold) -> "match" (the hard cut is invisible); anything
else -> "bridge": N frames rendered by workflows/bridge.api.json (LTX-2.5, A's last frame guided at f0
strength 1.0, B's first frame at the last frame strength 1.0). render_bridge() drives that workflow through
scripts/run_workflow.py and caches the MP4 by a hash of both frames + settings. No ComfyUI imports.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MATCH_THRESHOLD = 8.0  # mean abs diff (0..255): no larger than the re-render seam at a bridge's own ends (~7-8)
DEFAULT_FRAMES = 33
IDENTITY = ("a man with long dark wavy hair under a black baseball cap, his two eyes glowing bright gold, glowing "
            "translucent circuit-lit forearms and hands, wearing a black t-shirt printed with the bold words DEITCH "
            "BEATS DON'T QUIT between two red mushrooms and gold circuit lines, in a red sandstone canyon with "
            "floating golden sparks")
PROMPT = ("The shot continues in one unbroken take, the framing changes smoothly and naturally from the first frame to "
          "the last, same man, same canyon, same light, no cut. The camera glides continuously; " + IDENTITY +
          ". Both eyes stay brightly lit, face sharp and unchanged, shirt text crisp and legible, photoreal, "
          "cinematic, fine detail")


def frame_diff(a: np.ndarray, b: np.ndarray, step: int = 4) -> float:
    """Mean abs difference of two uint8 frames (subsampled), 0..255."""
    if a.shape != b.shape:
        return 255.0
    return float(np.abs(a[::step, ::step].astype(np.int16) - b[::step, ::step].astype(np.int16)).mean())


def bridge_key(a: np.ndarray, b: np.ndarray, frames: int, prompt: str, seed: int) -> str:
    h = hashlib.sha256()
    for x in (a, b):
        h.update(np.ascontiguousarray(x).tobytes())
    h.update(json.dumps([frames, prompt, seed]).encode())
    return h.hexdigest()[:10]


def plan_bridges(shots: list[dict], threshold: float = MATCH_THRESHOLD, frames: int = DEFAULT_FRAMES) -> list[dict]:
    """shots: dicts with name, first, last (uint8 frames) and optional bridge_in {frames, prompt, seed}
    describing the bridge INTO that shot. Returns one dict per boundary."""
    out = []
    for a, b in zip(shots, shots[1:]):
        d = frame_diff(a["last"], b["first"])
        cfg = b.get("bridge_in") or {}
        kind = "match" if d < threshold else "bridge"
        if cfg.get("mode") == "whip":  # deterministic zoom whip instead of an LTX bridge
            kind = "whip"
        n = int(cfg.get("frames", frames))
        if kind == "whip":
            out.append({"a": a["name"], "b": b["name"], "kind": kind, "diff": round(d, 2), "frames": n,
                        "prompt": None, "seed": None, "key": None})
            continue
        if kind == "bridge" and (n - 1) % 8:
            raise ValueError(f"bridge into {b['name']!r}: frames must be 8k+1, got {n}")
        prompt, seed = cfg.get("prompt", PROMPT), int(cfg.get("seed", 11))
        out.append({"a": a["name"], "b": b["name"], "kind": kind, "diff": round(d, 2),
                    "frames": n if kind == "bridge" else 0, "prompt": prompt, "seed": seed,
                    "key": bridge_key(a["last"], b["first"], n, prompt, seed) if kind == "bridge" else None})
    return out


def _save_png(frame: np.ndarray, path: Path) -> None:
    from PIL import Image

    Image.fromarray(frame).save(path)


def render_bridge(a: np.ndarray, b: np.ndarray, frames: int = DEFAULT_FRAMES, prompt: str = PROMPT, seed: int = 11,
                  cache_dir=None, server: str = "http://127.0.0.1:8189", workflow=None) -> Path:
    """Render (or reuse) the bridge from frame a to frame b; returns the cached MP4 path.

    The output size is the frames' size (multiples of 64 expected, e.g. 1088x1920)."""
    cache_dir = Path(cache_dir or ROOT / "outputs" / "trailer" / "bridges")
    key = bridge_key(a, b, frames, prompt, seed)
    dst = cache_dir / f"bridge_{key}.mp4"
    if dst.exists():
        return dst
    work = cache_dir / f"work_{key}"
    work.mkdir(parents=True, exist_ok=True)
    _save_png(a, work / f"bridge_{key}_a.png")
    _save_png(b, work / f"bridge_{key}_b.png")
    h, w = a.shape[:2]
    cmd = [sys.executable, str(ROOT / "scripts" / "run_workflow.py"),
           str(workflow or ROOT / "workflows" / "bridge.api.json"), "--server", server,
           "--image", str(work / f"bridge_{key}_a.png"), "--end-image", str(work / f"bridge_{key}_b.png"),
           "--prompt", prompt, "--seed", str(seed), "--prefix", f"opensauce/bridge_{key}", "--out", str(work),
           "--set", f"OS:latent_full.length={frames}", "--set", f"OS:audio_latent.frames_number={frames}",
           "--set", f"OS:resize.resize_type.width={w}", "--set", f"OS:resize.resize_type.height={h}",
           "--set", f"OS:resize_end.resize_type.width={w}", "--set", f"OS:resize_end.resize_type.height={h}",
           "--set", f"OS:latent_full.width={w}", "--set", f"OS:latent_full.height={h}"]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    mp4s = sorted(work.glob(f"bridge_{key}*.mp4"))
    if p.returncode or not mp4s:
        raise RuntimeError(f"bridge {key} failed\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    shutil.move(str(mp4s[-1]), dst)
    (cache_dir / f"bridge_{key}.json").write_text(json.dumps(
        {"key": key, "frames": frames, "prompt": prompt, "seed": seed, "size": [w, h],
         "workflow": "workflows/bridge.api.json", "a": f"work_{key}/bridge_{key}_a.png",
         "b": f"work_{key}/bridge_{key}_b.png"}, indent=1), encoding="utf-8")
    return dst


def whip_tilt(a: np.ndarray, b: np.ndarray, n: int = 8, blur: float = 0.45, feather: float = 0.25) -> np.ndarray:
    """Deterministic whip-tilt (camera tilts down fast: A slides up and out, B rises in from below) with
    vertical motion blur proportional to speed. For hand-offs LTX cannot bridge (eye-level -> aerial):
    a camera move, not a dissolve: A and B only mix inside a moving, blurred seam band (feather * H).
    Returns n frames strictly between a and b (uint8)."""
    import cv2

    h = a.shape[0]
    f = int(feather * h)
    r = np.linspace(0.0, 1.0, f, dtype=np.float32)[:, None, None]
    seam = a[h - f:].astype(np.float32) * (1 - r) + b[:f].astype(np.float32) * r
    strip = np.concatenate([a[:h - f], seam, b[f:]]).astype(np.float32)  # A above B; window slides by h - f
    h_move = h - f
    t = np.arange(1, n + 1) / (n + 1)
    pos = (1 - np.cos(np.pi * t)) / 2  # ease in-out
    vel = np.pi / 2 * np.sin(np.pi * t)  # d pos / d t (peak pi/2 mid-whip)
    out = []
    for p, v in zip(pos, vel):
        y = int(round(p * h_move))
        k = max(1, int(blur * h_move * v / (n + 1)) | 1)  # blur length = distance travelled per frame
        win = strip[max(0, y - k):y + h + k]
        win = cv2.blur(win, (1, k))
        top = y - max(0, y - k)
        out.append(np.clip(win[top:top + h], 0, 255).astype(np.uint8))
    return np.stack(out)


def trim_static_opening(frames: np.ndarray, threshold: float = 10.0, keep: int = 2) -> np.ndarray:
    """LTX bridges hold their first frame for ~0.5 s before the move starts. Drop the leading
    frames that are still near-identical to frame 0 (diff below `threshold`; LTX hold noise is ~5-7), keeping `keep`
    of them so the whip still has a visible start. A cut, not a retime (LAW-9)."""
    n = len(frames)
    if n <= keep + 2:
        return frames
    first_moving = n - 1
    for i in range(1, n):
        if frame_diff(frames[0], frames[i]) > threshold:
            first_moving = i
            break
    start = max(0, first_moving - keep)
    return frames[start:]


JUMP_THRESHOLD = 40.0


def whip_zoom(a: np.ndarray, b: np.ndarray, n: int = 3, blur: float = 0.06) -> np.ndarray:
    """Deterministic zoom whip for a bridge whose own first move is a one-frame jump (wide -> medium):
    A punches in toward B's framing with radial-ish motion blur while B takes over only in the last
    blurred frame. n frames strictly between a and b (uint8). A camera move, not a dissolve."""
    import cv2

    h, w = a.shape[:2]
    out = []
    t = np.arange(1, n + 1) / (n + 1)
    for p in t:
        s = 1.0 + 0.8 * p  # push in up to 1.8x
        m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
        za = cv2.warpAffine(a, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        k = max(3, int(blur * h * p) | 1)
        za = cv2.blur(za, (k, k))
        wb = p ** 3  # B only shows through at the very end of the whip
        f = za.astype(np.float32) * (1 - wb) + cv2.blur(b, (k, k)).astype(np.float32) * wb
        out.append(np.clip(f, 0, 255).astype(np.uint8))
    return np.stack(out)


def match_color(frames: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Grade a rendered bridge onto its anchors: per-channel mean/std transfer that maps the bridge's first frame
    onto a and its last onto b, interpolated linearly across the bridge (LTX renders drift ~8/255 in level, which
    would read as a pop at both ends). A grade, never a blend of images."""
    def stats(x):
        x = x[::4, ::4].reshape(-1, 3).astype(np.float32)
        return x.mean(0), x.std(0) + 1e-3

    (m0, s0), (ma, sa) = stats(frames[0]), stats(a)
    (m1, s1), (mb, sb) = stats(frames[-1]), stats(b)
    out = np.empty_like(frames)
    n = len(frames)
    for i, f in enumerate(frames):
        w = i / max(1, n - 1)
        gain = (1 - w) * sa / s0 + w * sb / s1
        src_m, dst_m = (1 - w) * m0 + w * m1, (1 - w) * ma + w * mb
        out[i] = np.clip((f.astype(np.float32) - src_m) * gain + dst_m, 0, 255).astype(np.uint8)
    return out
