"""Title card: text over a held frame + 2:3 poster. PIL + numpy, no ComfyUI imports.

The text fades in over the image; the image itself is never faded (LAW-7).
Default style "lightbrush": Rajdhani 700 caps with a cyan glow, Space Grotesk subtitle, thin cyan rule, mono
credit, wordmark bottom-left (OFL font files in assets/fonts/, see fonts.py). The older styles use system
fonts and fall back to PIL's default font.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    from . import fonts
except ImportError:  # loaded as a plain module (tests, scripts)
    import fonts

STYLES = ["lightbrush", "trailer_bold", "minimal", "stencil"]
POSITIONS = ["center", "lower_third"]

_FONTS = {
    "trailer_bold": ["impact.ttf", "ariblk.ttf", "seguibl.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "minimal": ["segoeuil.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    "stencil": ["STENCIL.TTF", "impact.ttf", "ariblk.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
}
_SUB_FONTS = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
# (title height as fraction of image height, title tracking em, uppercase, colour)
_STYLE = {
    "trailer_bold": (0.13, 0.04, True, (255, 255, 255)),
    "minimal": (0.07, 0.02, False, (245, 245, 240)),
    "stencil": (0.11, 0.06, True, (255, 214, 150)),
    "lightbrush": (0.085, 0.03, True, (226, 232, 240)),
}

CYAN, CYAN_BRIGHT, MUTED = (20, 215, 242), (6, 251, 252), (148, 163, 184)
CREDIT = "Lightbrush · animating with AI since 2021"


def load_font(names: list[str], size: int):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # old Pillow
        return ImageFont.load_default()


def _text_width(font, text: str, track: float) -> float:
    return sum(font.getlength(c) + track for c in text) - track if text else 0.0


def _draw_tracked(draw, xy, text, font, track, fill):
    x, y = xy
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += font.getlength(c) + track


def _tint(mask: Image.Image, rgb, gain: float = 1.0, blur: float = 0.0, off: int = 0) -> Image.Image:
    a = mask.filter(ImageFilter.GaussianBlur(blur)) if blur else mask
    a = a.point(lambda v: min(255, int(v * gain)))
    if off:
        a = ImageChops.offset(a, off, off)
    im = Image.new("RGBA", mask.size, tuple(rgb) + (0,))
    im.putalpha(a)
    return im


def _lightbrush_layers(w: int, h: int, title: str, subtitle: str, position: str, wordmark: bool = True,
                       credit: str = CREDIT):
    """(text layer, mark layer) as PIL RGBA. The text slams in; the wordmark stays put."""
    size = max(8, int(h * _STYLE["lightbrush"][0]))
    track_em = _STYLE["lightbrush"][1]
    t, s, c = title.upper(), subtitle.upper(), credit.upper()
    while True:
        tf = fonts.brand_font("rajdhani-700", size)
        if _text_width(tf, t, size * track_em) <= w * 0.84 or size <= 10:
            break
        size = int(size * 0.92)
    sf = fonts.brand_font("grotesk-500", max(10, int(size * 0.30)))
    cf = fonts.brand_font("mono-400", max(10, int(size * 0.19)))
    s_track, c_track = sf.size * 0.14, cf.size * 0.06
    tw, sw, cw = _text_width(tf, t, size * track_em), _text_width(sf, s, s_track), _text_width(cf, c, c_track)
    unit = max(1, round(h / 960))
    gap = int(size * 0.20)
    rule_h = max(2, 2 * unit)
    below = bool(s or c)
    block_h = (size if t else 0) + (gap + rule_h if t and below else 0) + ((gap + sf.size) if s else 0) \
        + ((int(gap * 0.9) + cf.size) if c else 0)
    cy = h * 0.5 if position == "center" else h * 0.80
    y = int(min(max(cy - block_h / 2, h * 0.03), h * 0.97 - block_h))

    title_m, rule_m, ink_s, ink_c = (Image.new("L", (w, h), 0) for _ in range(4))
    if t:
        _draw_tracked(ImageDraw.Draw(title_m), ((w - tw) / 2, y - size * 0.16), t, tf, size * track_em, 255)
        y += size
    if t and below:
        y += gap
        rl = int(min(w * 0.30, max(tw * 0.34, w * 0.14)))
        ImageDraw.Draw(rule_m).rectangle([(w - rl) // 2, y, (w + rl) // 2, y + rule_h - 1], fill=255)
        y += rule_h
    if s:
        y += gap
        _draw_tracked(ImageDraw.Draw(ink_s), ((w - sw) / 2, y - sf.size * 0.12), s, sf, s_track, 255)
        y += sf.size
    if c:
        y += int(gap * 0.9)
        _draw_tracked(ImageDraw.Draw(ink_c), ((w - cw) / 2, y - cf.size * 0.12), c, cf, c_track, 255)
    glow = ImageChops.lighter(title_m, rule_m)
    allink = ImageChops.lighter(glow, ImageChops.lighter(ink_s, ink_c))

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    soft = ImageChops.lighter(ink_s, ink_c)
    for im in (_tint(allink, (2, 4, 8), 1.7, size * 0.09, max(2, int(size * 0.035))),  # legibility shadow
               _tint(soft, (2, 4, 8), 3.0, size * 0.10),                              # keeps muted text legible on pale plates
               _tint(soft, (2, 4, 8), 3.0, size * 0.04),
               _tint(glow, CYAN, 1.5, size * 0.30),                                  # outer bloom
               _tint(glow, CYAN, 1.8, size * 0.09),
               _tint(glow, CYAN_BRIGHT, 2.0, size * 0.025)):                         # bright core
        layer = Image.alpha_composite(layer, im)
    layer = Image.alpha_composite(layer, _tint(title_m, _STYLE["lightbrush"][3]))
    layer = Image.alpha_composite(layer, _tint(rule_m, CYAN_BRIGHT))
    layer = Image.alpha_composite(layer, _tint(ink_s, MUTED))
    layer = Image.alpha_composite(layer, _tint(ink_c, MUTED))

    mark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    wm = fonts.wordmark(max(int(w * 0.14), min(130, int(w * 0.2)))) if wordmark else None
    if wm is not None:
        mx = int(w * 0.04)
        my = h - wm.height - int(h * 0.04)
        halo = Image.new("L", (w, h), 0)
        halo.paste(wm.split()[3], (mx, my))
        mark = Image.alpha_composite(mark, _tint(halo, CYAN, 0.55, max(2, wm.height * 0.12)))
        mark.alpha_composite(wm, (mx, my))
    return layer, mark


def render_text_layer(w: int, h: int, title: str, subtitle: str, style: str, position: str) -> np.ndarray:
    """RGBA float layer (h,w,4) in 0..1 with drop shadow baked in (straight alpha)."""
    if style == "lightbrush":
        text, mark = _lightbrush_layers(w, h, title, subtitle, position)
        return np.asarray(Image.alpha_composite(text, mark)).astype(np.float32) / 255.0
    frac, track_em, upper, color = _STYLE[style]
    size = max(8, int(h * frac))
    t = title.upper() if upper else title
    s = subtitle.upper() if upper else subtitle
    max_w = w * 0.84
    while True:  # shrink to fit width
        tf = load_font(_FONTS[style], size)
        if _text_width(tf, t, size * track_em) <= max_w or size <= 10:
            break
        size = int(size * 0.92)
    sf = load_font(_SUB_FONTS if style != "minimal" else _FONTS["minimal"], max(8, int(size * 0.34)))
    s_track = sf.size * 0.18 if hasattr(sf, "size") else 2
    tw, sw = _text_width(tf, t, size * track_em), _text_width(sf, s, s_track)
    th, sh = size, (sf.size if hasattr(sf, "size") else 12)
    gap = int(size * 0.25) if s else 0
    block_h = (th if t else 0) + (gap + sh if s else 0)
    cy = h * 0.5 if position == "center" else h * 0.80
    top = int(min(max(cy - block_h / 2, h * 0.03), h * 0.97 - block_h))

    def paint(fill_t, fill_s):
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if t:
            _draw_tracked(d, ((w - tw) / 2, top - size * 0.12), t, tf, size * track_em, fill_t)
        if s:
            _draw_tracked(d, ((w - sw) / 2, top + th + gap), s, sf, s_track, fill_s)
        return im

    blur = max(2, int(size * 0.07))
    off = max(2, int(size * 0.04))
    shadow = paint((0, 0, 0, 255), (0, 0, 0, 255))
    a = shadow.split()[3].filter(ImageFilter.GaussianBlur(blur))
    a = a.point(lambda v: min(255, int(v * 1.6) * 3 // 4))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(a)
    shadow = Image.fromarray(np.roll(np.asarray(shadow), (off, off), axis=(0, 1)))
    layer = Image.alpha_composite(shadow, paint(color + (255,), color + (230,)))
    return np.asarray(layer).astype(np.float32) / 255.0


def composite(img: np.ndarray, layer: np.ndarray, alpha: float) -> np.ndarray:
    a = layer[..., 3:4] * alpha
    return img * (1.0 - a) + layer[..., :3] * a


def title_card(image: np.ndarray, title: str, subtitle: str = "", style: str = "lightbrush",
               position: str = "lower_third", hold_frames: int = 24, fade_in_frames: int = 8):
    """image (H,W,3) float 0..1 -> (frames (hold,H,W,3), poster (H',W',3)), float32."""
    img = np.clip(image[..., :3].astype(np.float32), 0.0, 1.0)
    h, w = img.shape[:2]
    layer = render_text_layer(w, h, title, subtitle, style, position)
    n = max(1, int(hold_frames))
    fade = max(0, int(fade_in_frames))
    alphas = [1.0 if fade == 0 else min(1.0, i / fade) for i in range(n)]
    frames = np.stack([composite(img, layer, a) for a in alphas]).astype(np.float32)
    pw = min(w, int(round(h * 2 / 3)))
    ph = min(h, int(round(pw * 1.5)))
    x0, y0 = (w - pw) // 2, (h - ph) // 2
    crop = img[y0:y0 + ph, x0:x0 + pw]
    poster = composite(crop, render_text_layer(pw, ph, title, subtitle, style, position), 1.0)
    return frames, poster.astype(np.float32)


def _scale_layer(layer: np.ndarray, s: float) -> np.ndarray:
    """Scale an RGBA layer about its centre, keeping the canvas size."""
    if abs(s - 1.0) < 1e-3:
        return layer
    h, w = layer.shape[:2]
    im = Image.fromarray(np.rint(layer * 255).astype(np.uint8), "RGBA")
    sw, sh = max(1, round(w * s)), max(1, round(h * s))
    im = im.resize((sw, sh), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(im, ((w - sw) // 2, (h - sh) // 2))
    return np.asarray(canvas).astype(np.float32) / 255.0


def title_arrive(frames: np.ndarray, title: str, subtitle: str = "", style: str = "lightbrush",
                 position: str = "center", scale_frames: int = 6, scale_from: float = 1.35):
    """Title over MOVING frames (N,H,W,3) float 0..1: fully opaque from its first frame (never faded), the
    letters slam in from scale_from x to 1.0 over scale_frames (ease-out). Returns (frames, poster)."""
    imgs = np.clip(frames[..., :3].astype(np.float32), 0.0, 1.0)
    h, w = imgs.shape[1:3]
    mark = None
    if style == "lightbrush":  # the text slams in; the wordmark is already there
        text, mark_im = _lightbrush_layers(w, h, title, subtitle, position)
        layer = np.asarray(text).astype(np.float32) / 255.0
        mark = np.asarray(mark_im).astype(np.float32) / 255.0
    else:
        layer = render_text_layer(w, h, title, subtitle, style, position)
    out = []
    for i, img in enumerate(imgs):
        u = min(1.0, i / max(1, scale_frames))
        s = 1.0 + (scale_from - 1.0) * (1.0 - u) ** 3
        f = composite(img, _scale_layer(layer, s), 1.0)
        out.append(composite(f, mark, 1.0) if mark is not None else f)
    _, poster = title_card(imgs[-1], title, subtitle, style, position, 1, 0)
    return np.stack(out).astype(np.float32), poster
