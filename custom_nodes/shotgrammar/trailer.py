"""Main Character Trailer: bounded multi-shot sequencer. No ComfyUI imports.

cut_plan() is pure arithmetic. assemble() decodes finished shot MP4s, strips each shot's burned
end-frame QR (LAW-4: only the trailer's own last frames carry one), remaps timing with
speed_ramp, joins shots as one take (LAW-9: per boundary a match cut when the framing is identical,
otherwise a generated bridge from shotgrammar.bridge, inserted unretimed), grades everything with one
chip, slams the title in over the final frames (title_mode "overlay") or a held last frame ("hold"),
burns the trailer QR into the last 12 frames, encodes H.264 and embeds the recipe. Nothing fades or
dissolves, nothing fades to black (LAW-7).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np

try:
    from . import bridge as B
    from . import grade_chip, speed_ramp, title_card
    from . import recipe as R
except ImportError:  # loaded as a plain module (tests, scripts)
    import bridge as B
    import grade_chip
    import recipe as R
    import speed_ramp
    import title_card

FPS = 24
QR_FRAMES = 12
TITLE_HOLD_S = 2.5
TITLE_FADE_FRAMES = 12
DEFAULT_SHOTS = [
    {"name": "crash_zoom", "ramp": "impact", "hit_at": 0.22, "seconds": 2.5},
    {"name": "vertigo", "ramp": "linear", "seconds": 3.0},
    {"name": "pull_back", "ramp": "slow_mo_settle", "seconds": 3.5},
]


def cut_plan(shots: list[dict], total_s: float = 12.0, fps: int = FPS, title_hold_s: float = TITLE_HOLD_S,
             strip: int = QR_FRAMES, title_fade_frames: int = TITLE_FADE_FRAMES, title_mode: str = "hold") -> dict:
    """Per-shot source range, timeline range and ramp, plus the title hold.

    shots: dicts with name, ramp, seconds and src_frames (frames in the file, QR frames included;
    default 97). The last `strip` source frames are dropped. Durations are authoritative: if
    shots + title exceed total_s they are scaled down together; if they fall short, total_s is
    only a ceiling (the default plan is 9.0 + 2.5 = 11.5 s). src_in == src_out holds one frame.
    title_mode "overlay": the title rides the last title_hold_s of the final shot (no held frame) and
    adds no time. Bridges are not in this plan; assemble() inserts them and re-times the plan.
    """
    overlay = title_mode == "overlay"
    scale = min(1.0, total_s / (sum(s["seconds"] for s in shots) + (0 if overlay else title_hold_s)))
    out, t = [], 0
    for s in shots:
        n_src = int(s.get("src_frames", 97)) - strip
        if n_src < 2:
            raise ValueError(f"shot {s['name']!r} has no usable frames after stripping {strip}")
        # optional trim: src_in/src_out select the peak section of the source clip
        in_start = max(0, min(int(s.get("src_in", 0)), n_src - 2))
        in_end = max(in_start, min(int(s.get("src_out", n_src - 1)), n_src - 1))
        n_out = max(2, round(s["seconds"] * scale * fps))
        out.append({"name": s["name"], "ramp": s["ramp"], "hit_at": s.get("hit_at", 0.6),
                    "in_start": in_start, "in_end": in_end, "src_frames": in_end - in_start + 1,
                    "out_start": t, "out_end": t + n_out - 1, "out_frames": n_out})
        t += n_out
    hold = max(1, round(title_hold_s * scale * fps))
    if overlay:
        hold = min(hold, out[-1]["out_frames"])
        title, total = {"mode": "overlay", "out_start": t - hold, "out_end": t - 1, "out_frames": hold}, t
    else:
        title = {"mode": "hold", "out_start": t, "out_end": t + hold - 1, "out_frames": hold}
        total = t + hold
    title["scale_in_frames"] = min(title_fade_frames, hold)  # letters slam in; never an opacity fade
    return {"fps": fps, "shots": out, "title": title, "total_frames": total, "total_s": total / fps,
            "qr_frames": QR_FRAMES}


def read_frames(path) -> np.ndarray:
    """(N,H,W,3) uint8 RGB."""
    import cv2

    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    if not out:
        raise ValueError(f"no frames decoded from {path}")
    return np.stack(out)


def grade(frames: np.ndarray, chip: str, batch: int = 16) -> np.ndarray:
    """Apply a chip in batches (bounded memory); uint8 in, uint8 out."""
    if chip == "none":
        return frames
    parts = []
    for i in range(0, len(frames), batch):
        g = grade_chip.apply_chip(frames[i:i + batch].astype(np.float32) / 255.0, chip)
        parts.append(np.rint(g * 255.0).astype(np.uint8))
    return np.concatenate(parts)


def _cut_shot(frames: np.ndarray, spec: dict) -> np.ndarray:
    seg = frames[spec["in_start"]:spec["in_end"] + 1]
    if len(seg) == 1:
        return np.repeat(seg, spec["out_frames"], axis=0)
    return speed_ramp.speed_ramp(seg, spec["ramp"], spec["out_frames"], spec["hit_at"], blend=spec["ramp"] != "impact")


def _encode(frames: np.ndarray, out: Path, fps: int) -> None:
    n, h, w, _ = frames.shape
    dur = n / fps
    cmd = [R._ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={dur:.3f}",
           "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
           "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, input=np.ascontiguousarray(frames).tobytes(), check=True)


def join_shots(cut: list[np.ndarray], shots: list[dict], bridge_provider=None,
               threshold: float = B.MATCH_THRESHOLD) -> tuple[list[np.ndarray], list[dict]]:
    """Cut shots -> pieces in timeline order. Per boundary (shotgrammar.bridge.plan_bridges): "match" = hard
    cut on identical framing; "bridge" = bridge_provider(a_last, b_first, boundary) -> (N,H,W,3) uint8 whose
    first/last frames re-render the two boundary frames and are dropped; the rest plays unretimed, colour-matched
    to both boundary frames (bridge.match_color).
    Without a provider a needed bridge degrades to a plain "cut" (recorded in the boundary dict)."""
    bounds = B.plan_bridges([{"name": s["name"], "first": c[0], "last": c[-1], "bridge_in": s.get("bridge_in")}
                             for s, c in zip(shots, cut)], threshold)
    pieces = [cut[0]]
    for i, b in enumerate(bounds):
        if b["kind"] == "bridge" and bridge_provider is None:
            b["kind"] = "cut"
        if b["kind"] == "whip":
            fr = B.whip_zoom(cut[i][-1], cut[i + 1][0], n=max(2, int(b["frames"])))
            b["used_frames"] = len(fr)
            pieces.append(fr)
            pieces.append(cut[i + 1])
            continue
        if b["kind"] == "bridge":
            fr = B.match_color(np.asarray(bridge_provider(cut[i][-1], cut[i + 1][0], b)), cut[i][-1], cut[i + 1][0])[1:-1]
            fr = B.trim_static_opening(fr)
            # (LTX whips carry their own motion blur; do not splice synthetic whips inside a bridge)
            # the exit junction: drop a frozen tail, then whip if the bridge never quite reached shot B
            fr = B.trim_static_opening(fr[::-1])[::-1]
            if B.frame_diff(fr[-1], cut[i + 1][0]) > B.JUMP_THRESHOLD:
                fr = np.concatenate([fr, B.whip_zoom(fr[-1], cut[i + 1][0])])
                b["whip_zoom_exit"] = True
            if fr.shape[1:] != cut[i].shape[1:]:
                raise ValueError(f"bridge {b['a']}->{b['b']} is {fr.shape[1:]}, shots are {cut[i].shape[1:]}")
            b["used_frames"] = len(fr)
            pieces.append(fr)
        pieces.append(cut[i + 1])
    return pieces, bounds


def assemble(shots: list[dict], title: str, subtitle: str, grade_chip_name: str, out_mp4, recipe: dict,
             recipes_dir=None, plan: dict | None = None, title_style: str = "lightbrush",
             title_position: str = "lower_third", bridge_provider=None,
             match_threshold: float = B.MATCH_THRESHOLD, burn_qr: bool = False) -> dict:
    """shots: dicts with name, path, ramp, seconds (+ hit_at, bridge_in). Returns paths and the plan
    (plan["bridges"] = one dict per boundary; plan["timeline"] = every piece's output range).

    `recipe` is a finished recipe dict (recipe.build_recipe); its id drives the QR URL and sidecar.
    """
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    srcs = [read_frames(s["path"]) for s in shots]
    plan = plan or cut_plan([{**s, "src_frames": len(f)} for s, f in zip(shots, srcs)])
    cut = [_cut_shot(f, spec) for f, spec in zip(srcs, plan["shots"])]
    del srcs
    h, w = cut[0].shape[1:3]
    if any(c.shape[1:3] != (h, w) for c in cut):
        raise ValueError("all shots must share one resolution")
    pieces, bounds = join_shots(cut, shots, bridge_provider, match_threshold)
    del cut
    names = [p for s in shots for p in (s["name"], None)][:-1]  # shot, boundary, shot, ...
    timeline, t, bi = [], 0, iter(bounds)
    for n in names:
        if n is None:
            b = next(bi)
            if b["kind"] not in ("bridge", "whip"):
                continue
            n = f"{b['kind']}:{b['a']}->{b['b']}"
        timeline.append({"piece": n, "out_start": t, "out_end": t + len(pieces[len(timeline)]) - 1})
        t = timeline[-1]["out_end"] + 1
    frames = np.concatenate([grade(p, grade_chip_name) for p in pieces])
    del pieces

    ti = plan["title"]
    if ti.get("mode") == "overlay":
        base = frames[-ti["out_frames"]:]
    else:
        base = np.repeat(frames[-1:], ti["out_frames"], axis=0)  # held last frame (graded, no QR)
    card, poster = title_card.title_arrive(base.astype(np.float32) / 255.0, title, subtitle, title_style,
                                           title_position, ti.get("scale_in_frames", 6))
    card = np.rint(card * 255.0).astype(np.uint8)
    frames = np.concatenate([frames[:-ti["out_frames"]], card]) if ti.get("mode") == "overlay"         else np.concatenate([frames, card])
    ti.update(out_start=len(frames) - ti["out_frames"], out_end=len(frames) - 1)
    plan.update(bridges=bounds, timeline=timeline, total_frames=len(frames), total_s=len(frames) / plan["fps"])
    if burn_qr:
        frames = R.burn_endframe_qr(frames, R.recipe_url(recipe), plan["qr_frames"])

    _encode(frames, out_mp4, plan["fps"])
    tagged = R.embed_mp4_metadata(out_mp4, recipe)
    os.replace(tagged, out_mp4)
    from PIL import Image

    poster_png = out_mp4.with_name(out_mp4.stem + "_poster.png")
    Image.fromarray(np.rint(poster * 255.0).astype(np.uint8)).save(poster_png)
    card_png = R.render_recipe_card(recipe, out_mp4.with_name(out_mp4.stem + "_card.png"))
    sidecar = R.write_sidecar(recipe, recipes_dir or Path(__file__).resolve().parents[2] / "recipes")
    return {"video": out_mp4, "poster": poster_png, "card": card_png, "sidecar": sidecar, "plan": plan}
