"""Build the README / Hub brand assets from the committed example renders (CPU only, no ComfyUI).

usage: python scripts/build_brand_assets.py [--out docs/img]
Writes hero.jpg (1920x1080), menu.jpg (one tile per preset), poster.jpg (2:3 trailer poster) and
thumbnail.mp4 (1080x1350 hard-cut loop of the five presets, no fades, ends luminous).
Lightbrush tokens: cyan #14d7f2 / bright #06fbfc, void #020408, panel #060d18, text #e2e8f0, muted #94a3b8.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_nodes" / "shotgrammar"))
import fonts  # noqa: E402
import recipe as R  # noqa: E402
import title_card as TC  # noqa: E402
import trailer  # noqa: E402

CYAN, BRIGHT, VOID, SPACE, PANEL, TEXT, MUTED = (20, 215, 242), (6, 251, 252), (2, 4, 8), (5, 8, 16), (6, 13, 24), (226, 232, 240), (148, 163, 184)
EX = "examples/{}/expected/input_01_seed11_final.mp4"
# (menu name, source, frame for the still, crop-centre y fraction of the 9:16 frame, loop range for the thumbnail or None)
PRESETS = [
    ("Vertigo", EX.format("vertigo"), 84, 0.50, (24, 58)),
    ("Crash Zoom", EX.format("crash_zoom"), 40, 0.30, (0, 34)),
    ("Disintegrate", EX.format("disintegrate"), 44, 0.50, (14, 70)),
    ("Petrify", EX.format("petrify"), 45, 0.50, (20, 54)),
    ("Levitate", EX.format("levitate"), 90, 0.45, (40, 74)),
    ("Main Character Trailer", "examples/trailer/expected/trailer_g01_final.mp4", 258, 0.50, None),
]
LOOP_ORDER = ["Crash Zoom", "Vertigo", "Disintegrate", "Petrify", "Levitate"]


def frames_of(src: str) -> np.ndarray:
    return trailer.read_frames(ROOT / src)


def crop_to(img: np.ndarray, w: int, h: int, cy: float) -> np.ndarray:
    """Scale to cover w x h, then crop with the window centred at fraction cy of the scaled height."""
    s = max(w / img.shape[1], h / img.shape[0])
    big = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    y0 = int(np.clip(cy * big.shape[0] - h / 2, 0, big.shape[0] - h))
    x0 = (big.shape[1] - w) // 2
    return big[y0:y0 + h, x0:x0 + w]


def over(base: np.ndarray, layer: Image.Image) -> np.ndarray:
    a = np.asarray(layer).astype(np.float32) / 255.0
    out = base.astype(np.float32) / 255.0 * (1 - a[..., 3:4]) + a[..., :3] * a[..., 3:4]
    return np.rint(out * 255).astype(np.uint8)


def glow_text(im: Image.Image, xy, text, font, track, fill=TEXT, big=None):
    """Rajdhani title with the Lightbrush bloom (outer #14d7f2, bright #06fbfc core)."""
    m = Image.new("L", im.size, 0)
    TC._draw_tracked(ImageDraw.Draw(m), xy, text, font, track, 255)
    s = big or font.size
    for blur, gain, rgb in ((s * 0.30, 1.4, CYAN), (s * 0.09, 1.8, CYAN), (s * 0.025, 2.0, BRIGHT)):
        im.alpha_composite(TC._tint(m, rgb, gain, blur))
    im.alpha_composite(TC._tint(m, fill))


def wrap(text, font, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and font.getlength(t) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur]


def glass(im, box, radius, alpha=0.78):
    ss = 3
    lay = Image.new("RGBA", (im.width * ss, im.height * ss), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle([v * ss for v in box], radius=radius * ss, fill=PANEL + (int(alpha * 255),),
                                          outline=CYAN + (70,), width=ss)
    im.alpha_composite(lay.resize(im.size, Image.LANCZOS))


def hero(out: Path) -> None:
    W, H = 1920, 1080
    src = frames_of(PRESETS[1][1])[40]
    bg = crop_to(src, W, H, 0.30)
    bg = cv2.GaussianBlur(bg, (0, 0), 38)
    bg = np.rint(bg.astype(np.float32) * 0.45 + np.array(SPACE, np.float32) * 0.55).astype(np.uint8)
    pw = round(H * src.shape[1] / src.shape[0])
    px = W - pw - 110
    bg[:, px:px + pw] = cv2.resize(src, (pw, H), interpolation=cv2.INTER_AREA)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([px - 2, 0, px + pw + 1, H], outline=CYAN + (255,), width=2)
    glass(im, (90, 150, px - 70, H - 150), 26)
    x = 150
    d = ImageDraw.Draw(im)
    d.text((x, 205), "OPEN SOURCE  ·  MIT  ·  OPEN WEIGHTS", font=fonts.brand_font("mono-500", 26), fill=CYAN)
    tf = fonts.brand_font("rajdhani-700", 172)
    glow_text(im, (x - 5, 275), "OPEN SAUCE", tf, 172 * 0.03)
    d = ImageDraw.Draw(im)
    d.rectangle([x, 480, x + 260, 483], fill=BRIGHT)
    pf = fonts.brand_font("grotesk-500", 45)
    y = 530
    for ln in wrap("Cinematic camera moves, rebuilt as free, open, forkable ComfyUI presets. Every video carries its own recipe.",
                   pf, px - 70 - x - 60):
        d.text((x, y), ln, font=pf, fill=TEXT)
        y += 62
    wm = fonts.wordmark(250)
    wy = H - 150 - 40 - wm.height
    im.alpha_composite(wm, (x - 10, wy))
    d.text((x + 270, wy + wm.height // 2), "ANIMATING WITH AI SINCE 2021", font=fonts.brand_font("mono-400", 21), fill=MUTED, anchor="lm")
    Image.fromarray(over(bg, im)).convert("RGB").save(out / "hero.jpg", quality=93, subsampling=0)


def menu(out: Path) -> None:
    W, tw, gap, mx = 1920, 580, 30, 60
    th, head = 700, 150
    H = head + 2 * th + gap + mx
    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[:] = VOID
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    nf, lf = fonts.brand_font("rajdhani-700", 46), fonts.brand_font("mono-500", 24)
    for i, (name, src, fi, cy, _) in enumerate(PRESETS):
        col, row = i % 3, i // 3
        x, y = mx + col * (tw + gap), head + row * (th + gap)
        canvas[y:y + th, x:x + tw] = crop_to(frames_of(src)[fi], tw, th, cy)
    d.text((mx, 62), "OPEN SAUCE", font=fonts.brand_font("rajdhani-700", 62), fill=TEXT, anchor="lm")
    d.text((W - mx, 62), "THE MENU  ·  6 PRESETS  ·  ONE LTX-2.5 PIPELINE", font=lf, fill=CYAN, anchor="rm")
    d.rectangle([mx, 112, W - mx, 113], fill=CYAN + (110,))
    for i, (name, *_r) in enumerate(PRESETS):
        col, row = i % 3, i // 3
        x, y = mx + col * (tw + gap), head + row * (th + gap)
        d.rectangle([x, y + th - 96, x + tw, y + th], fill=SPACE + (153,))  # glass band, flat
        d.rectangle([x, y + th - 96, x + tw, y + th - 95], fill=CYAN + (230,))
        d.text((x + 24, y + th - 48), f"{i + 1:02d}", font=lf, fill=CYAN, anchor="lm")
        nm = name.upper()
        f = nf if nf.getlength(nm) < tw - 120 else fonts.brand_font("rajdhani-700", 36)
        d.text((x + 80, y + th - 48), nm, font=f, fill=TEXT, anchor="lm")
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=CYAN + (60,), width=1)
    Image.fromarray(over(canvas, im)).convert("RGB").save(out / "menu.jpg", quality=92, subsampling=0)


def poster(out: Path) -> None:
    p = ROOT / "examples/trailer/expected/trailer_g01_final_poster.png"
    Image.open(p).convert("RGB").save(out / "poster.jpg", quality=94, subsampling=0)


def thumbnail(out: Path) -> None:
    W, H, fps = 1080, 1350, 24
    byname = {p[0]: p for p in PRESETS}
    cmd = [R._ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "thumbnail.mp4")]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nf, lf = fonts.brand_font("rajdhani-700", 78), fonts.brand_font("mono-500", 28)
    wm = fonts.wordmark(240)
    total = 0
    for k, name in enumerate(LOOP_ORDER):
        _, src, _, cy, (a, b) = byname[name]
        clip = frames_of(src)[a:b]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, H - 250, W, H], fill=SPACE + (153,))
        d.rectangle([0, H - 250, W, H - 249], fill=CYAN + (230,))
        d.text((60, H - 195), f"{k + 1:02d} / 05", font=lf, fill=CYAN, anchor="lm")
        d.text((60, H - 120), name.upper(), font=nf, fill=TEXT, anchor="lm")
        d.text((W - 60, H - 195), "OPEN SAUCE", font=lf, fill=TEXT, anchor="rm")
        im.alpha_composite(wm, (W - 60 - wm.width, H - 150))
        for f in clip:
            pr.stdin.write(np.ascontiguousarray(over(crop_to(f, W, H, cy), im)).tobytes())
            total += 1
    pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    print(f"thumbnail.mp4: {total} frames, {total / fps:.1f}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/img")
    a = ap.parse_args()
    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    for fn in (hero, menu, poster, thumbnail):
        fn(out)
        print("built", fn.__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
