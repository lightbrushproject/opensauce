"""Lightbrush brand fonts (all OFL, shipped in assets/fonts/) + the wordmark. Falls back to system fonts."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFont

ASSETS = Path(__file__).resolve().parents[2] / "assets"
FONT_DIR = ASSETS / "fonts"
LOGO = ASSETS / "brand" / "lightbrush-logo.png"

# role -> (file, variable-axis weight or None, system fallbacks)
_ROLES = {
    "rajdhani-400": ("Rajdhani-Regular.ttf", None, ["bahnschrift.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]),
    "rajdhani-600": ("Rajdhani-SemiBold.ttf", None, ["bahnschrift.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]),
    "rajdhani-700": ("Rajdhani-Bold.ttf", None, ["bahnschrift.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]),
    "grotesk-400": ("SpaceGrotesk-VF.ttf", 400, ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]),
    "grotesk-500": ("SpaceGrotesk-VF.ttf", 500, ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]),
    "grotesk-700": ("SpaceGrotesk-VF.ttf", 700, ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]),
    "mono-400": ("JetBrainsMono-VF.ttf", 400, ["consola.ttf", "DejaVuSansMono.ttf"]),
    "mono-500": ("JetBrainsMono-VF.ttf", 500, ["consolab.ttf", "DejaVuSansMono-Bold.ttf", "consola.ttf"]),
}


def brand_font(role: str, size: int):
    """PIL font for a role like 'rajdhani-700'; system fallback, then PIL's default, if the TTF is missing."""
    fname, weight, fallbacks = _ROLES[role]
    path = FONT_DIR / fname
    if path.exists():
        try:
            f = ImageFont.truetype(str(path), size)
            if weight is not None:
                f.set_variation_by_axes([weight])
            return f
        except (OSError, AttributeError):
            pass
    for n in fallbacks:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # old Pillow
        return ImageFont.load_default()


def have_brand_fonts() -> bool:
    return all((FONT_DIR / f).exists() for f in {v[0] for v in _ROLES.values()})


def wordmark(width: int) -> Image.Image | None:
    """Lightbrush script wordmark (RGBA) at `width` px, capped at its native width (never upscaled). None if absent."""
    if not LOGO.exists():
        return None
    im = Image.open(LOGO).convert("RGBA")
    width = max(1, min(int(width), im.width))
    if width == im.width:
        return im
    return im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
