"""Observation helper: extract first/25/50/75/last frames from an MP4 into a labelled strip PNG.

usage: python scripts/observe_video.py out.mp4 [--out tmp/obs/name] [--n 5]
Prints the strip path and the per-frame mean brightness (black-frame check).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default=None)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        print("could not read", args.video)
        return 1
    idxs = [round(i * (total - 1) / (args.n - 1)) for i in range(args.n)]
    frames = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            continue
        s = args.height / f.shape[0]
        f = cv2.resize(f, (int(f.shape[1] * s), args.height))
        cv2.putText(f, f"f{i}", (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(f, f"f{i}", (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        frames.append(f)
    cap.release()
    out_dir = Path(args.out or Path("tmp/obs") / Path(args.video).stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    strip = np.hstack(frames)
    path = out_dir / "strip.png"
    cv2.imwrite(str(path), strip)
    means = [round(float(f.mean()), 1) for f in frames]
    print(f"{path}  frames={total} sampled={idxs} mean_brightness={means}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
