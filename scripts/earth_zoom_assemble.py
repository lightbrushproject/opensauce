"""Assemble Pull Back segments into forward + reverse MP4s (video only).

  python scripts/earth_zoom_assemble.py --clean A_clean.mp4 B_clean.mp4 C_clean.mp4 \
      --recipe recipes/<id>.json --out outputs/earth_zoom/final/earth_zoom_g01

Forward = clean segments joined (first frame of each later segment dropped: it repeats the
previous segment's landing frame), QR burned into the last 12 frames. Reverse = the same
clean frames reversed (wide -> face), QR burned into its own last 12 frames. Both get the
recipe embedded in MP4 metadata.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_nodes" / "shotgrammar"))
import recipe as R  # noqa: E402


def read(path):
    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, f = cap.read()
        if not ok:
            return out
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))


def write(frames, path, fps):
    h, w = frames[0].shape[:2]
    cmd = [R._ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, input=np.ascontiguousarray(np.stack(frames)).tobytes(), check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", nargs="+", required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--out", required=True, help="output stem; writes <stem>.mp4 and <stem>_reverse.mp4")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--qr", action="store_true", help="burn the recipe QR into the last frames (opt-in)")
    a = ap.parse_args()

    frames = []
    for i, p in enumerate(a.clean):
        seg = read(p)
        frames += seg if i == 0 else seg[1:]
    rec = json.loads(Path(a.recipe).read_text(encoding="utf-8"))
    url = R.recipe_url(rec, rec.get("extra", {}).get("base_url", R.DEFAULT_BASE))
    stem = Path(a.out)
    stem.parent.mkdir(parents=True, exist_ok=True)
    for name, seq in ((f"{stem}.mp4", frames), (f"{stem}_reverse.mp4", frames[::-1])):
        burned = R.burn_endframe_qr(np.stack(seq), url) if a.qr else np.stack(seq)
        write(list(burned), name, a.fps)
        os.replace(R.embed_mp4_metadata(name, rec), name)
        print(name, len(seq), "frames")


if __name__ == "__main__":
    main()
