"""Fork This Shot: recipe build, MP4 metadata, sidecar, card, end-frame QR. Pure functions."""

import base64
import datetime
import gzip
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import qrcode
from mutagen.mp4 import MP4
from PIL import Image, ImageDraw, ImageFilter

try:
    from . import fonts
except ImportError:  # loaded as a plain module (tests, scripts)
    import fonts

SCHEMA = "opensauce.recipe/1"
DEFAULT_BASE = "https://github.com/lightbrushproject/opensauce/blob/main/recipes/"
GZ_LIMIT = 60_000
QR_SIZE_FRAC = 0.14
QUIET_MODULES = 2


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_recipe(preset, seed, inputs, models, api_workflow, extra=None):
    body = {
        "preset": preset,
        "seed": int(seed),
        "inputs": list(inputs),
        "models": list(models),
        "extra": extra or {},
        "api_workflow": api_workflow,
    }
    rid = hashlib.sha256(_canon({"schema": SCHEMA, **body}).encode("utf-8")).hexdigest()[:10]
    created = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return {"schema": SCHEMA, "id": rid, "created": created, **body}


def recipe_url(recipe, base=DEFAULT_BASE):
    return f"{base}{recipe['id']}.json"


def write_sidecar(recipe, recipes_dir):
    d = Path(recipes_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{recipe['id']}.json"
    p.write_text(json.dumps(recipe, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _ffmpeg():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _pack(recipe):
    s = _canon(recipe)
    if len(s) > GZ_LIMIT:
        s = "gz:" + base64.b64encode(gzip.compress(s.encode("utf-8"))).decode("ascii")
    return s


def _unpack(s):
    if s.startswith("gz:"):
        s = gzip.decompress(base64.b64decode(s[3:])).decode("utf-8")
    return json.loads(s)


def _ffmeta_escape(v):
    for ch in ("\\", "=", ";", "#", "\n"):
        v = v.replace(ch, "\\" + ch)
    return v


def embed_mp4_metadata(mp4_path, recipe):
    """Copy the MP4 with the recipe in its tags. Returns the new path (<stem>_recipe.mp4).

    Tags go through an ffmetadata file, not argv, to dodge the Windows command-line limit.
    """
    src = Path(mp4_path)
    out = src.with_name(src.stem + "_recipe.mp4")
    packed = _pack(recipe)
    tags = {
        "title": f"OPEN SAUCE {recipe['preset']} {recipe['id']}",
        "comment": packed,
        "opensauce_recipe": packed,
    }
    meta = ";FFMETADATA1\n" + "".join(f"{k}={_ffmeta_escape(v)}\n" for k, v in tags.items())
    with tempfile.TemporaryDirectory() as td:
        mf = Path(td) / "meta.txt"
        mf.write_text(meta, encoding="utf-8")
        cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(src), "-i", str(mf), "-map", "0",
               "-map_metadata", "1", "-c", "copy", "-movflags", "use_metadata_tags", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()}")
    if read_recipe_from_mp4(out, sidecar_dir=None).get("id") != recipe["id"]:
        raise RuntimeError("recipe metadata did not round-trip")
    return out


def _ffmeta_unescape(v):
    out, i = [], 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            i += 1
        out.append(v[i])
        i += 1
    return "".join(out)


def _read_tags(mp4_path):
    """Global tags as {key: text}. ffmpeg reads mdta keys (custom names); mutagen covers plain iTunes atoms."""
    tags = {}
    r = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(mp4_path), "-f", "ffmetadata", "-"],
                       capture_output=True)
    if r.returncode == 0:
        for line in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
            k, sep, v = line.partition("=")
            if sep and not line.startswith("["):
                tags.setdefault(k.lower(), _ffmeta_unescape(v))
    for key, name in (("©cmt", "comment"), ("©nam", "title")):
        v = (MP4(str(mp4_path)).tags or {}).get(key)
        if v:
            tags.setdefault(name, str(v[0]))
    return tags


def read_recipe_from_mp4(mp4_path, sidecar_dir="recipes"):
    """Recipe dict from MP4 tags; falls back to <sidecar_dir>/<id>.json when tags are stripped."""
    tags = _read_tags(mp4_path)
    for key in ("opensauce_recipe", "comment"):
        if tags.get(key):
            try:
                return _unpack(tags[key])
            except (ValueError, OSError):
                continue
    title = tags.get("title", "")
    if sidecar_dir is not None and title.startswith("OPEN SAUCE "):
        p = Path(sidecar_dir) / f"{title.split()[-1]}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise ValueError(f"no OPEN SAUCE recipe found in {mp4_path}")


def _qr_image(url):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=1)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


CYAN, CYAN_BRIGHT, VOID, PANEL, TEXT, MUTED = (20, 215, 242), (6, 251, 252), (2, 4, 8), (6, 13, 24), (226, 232, 240), (148, 163, 184)
OUTLINE_PX = 2


def _qr_tile(qr, mpx, quiet):
    """Brand QR tile: black modules on white (maximally scannable; a cyan-on-dark QR does not decode with
    cv2) in a rounded white tile with a 2 px cyan outline drawn OUTSIDE the quiet zone, so module size and
    quiet zone are exactly those of a plain tile. Returns (RGB uint8 array, alpha 0..1 array), side + 2*OUTLINE_PX."""
    modules = qr.width
    side = (modules + 2 * quiet) * mpx
    t = side + 2 * OUTLINE_PX
    ss, r = 4, max(2, int(mpx * 1.5))  # corner radius stays inside the quiet zone
    big = Image.new("RGB", (t * ss, t * ss), (0, 0, 0))
    mask = Image.new("L", (t * ss, t * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, t * ss - 1, t * ss - 1], radius=(r + OUTLINE_PX) * ss, fill=255)
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, t * ss - 1, t * ss - 1], radius=(r + OUTLINE_PX) * ss, fill=CYAN)
    o = OUTLINE_PX * ss
    d.rounded_rectangle([o, o, t * ss - 1 - o, t * ss - 1 - o], radius=r * ss, fill=(255, 255, 255))
    tile = big.resize((t, t), Image.LANCZOS)
    tile.paste(qr.resize((modules * mpx, modules * mpx), Image.NEAREST),
               (OUTLINE_PX + quiet * mpx, OUTLINE_PX + quiet * mpx))
    return np.asarray(tile), np.asarray(mask.resize((t, t), Image.LANCZOS), dtype=np.float32)[..., None] / 255.0


def _rounded_panel(img, box, radius, fill, outline):
    ss = 3
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (img.width * ss, img.height * ss), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([v * ss for v in box], radius=radius * ss, fill=fill + (255,),
                                            outline=outline, width=ss)
    img.alpha_composite(layer.resize(img.size, Image.LANCZOS))


def _glow(img, draw_fn, rgb, blur, gain):
    m = Image.new("L", img.size, 0)
    draw_fn(ImageDraw.Draw(m))
    a = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * gain)))
    g = Image.new("RGBA", img.size, rgb + (0,))
    g.putalpha(a)
    img.alpha_composite(g)


def render_recipe_card(recipe, out_png, size=(1080, 1350)):
    """Brand card: #060d18 panel on #020408 void, Rajdhani title, JetBrains Mono fields, QR tile, wordmark, footer."""
    w, h = size
    img = Image.new("RGBA", size, VOID + (255,))
    pm = 48
    _rounded_panel(img, (pm, pm, w - pm, h - pm), 28, PANEL, (20, 215, 242, 64))
    d = ImageDraw.Draw(img)
    m = pm + 56
    d.text((m, m), "OPEN SAUCE  /  RECIPE", font=fonts.brand_font("mono-500", 26), fill=CYAN)
    title_font = fonts.brand_font("rajdhani-700", 132)
    ty = m + 44
    _glow(img, lambda g: g.text((m, ty), "FORK THIS SHOT", font=title_font, fill=255), CYAN, 22, 1.1)
    d = ImageDraw.Draw(img)
    d.text((m, ty), "FORK THIS SHOT", font=title_font, fill=TEXT)
    ry = ty + 156
    d.rectangle([m, ry, m + 220, ry + 3], fill=CYAN_BRIGHT)
    extra = recipe.get("extra", {})
    lab, val = fonts.brand_font("mono-400", 24), fonts.brand_font("mono-500", 32)
    y = ry + 44
    for k, v in (("PRESET", recipe["preset"]), ("SEED", str(recipe["seed"])), ("RECIPE ID", recipe["id"])):
        d.text((m, y), k, font=lab, fill=MUTED)
        d.text((m + 250, y - 4), v, font=val, fill=TEXT)
        y += 58
    d.text((m, y), "MODELS", font=lab, fill=MUTED)
    mf = fonts.brand_font("mono-400", 25)
    for mdl in recipe["models"][:5]:
        d.text((m + 250, y - 1), mdl[:38] + ("..." if len(mdl) > 38 else ""), font=mf, fill=TEXT)
        y += 38
    prompt = str(extra.get("prompt", ""))
    if prompt:
        y += 22
        d.text((m, y), "PROMPT", font=lab, fill=MUTED)
        d.text((m + 250, y - 1), (prompt[:60] + "...") if len(prompt) > 60 else prompt, font=mf, fill=TEXT)
    qr = _qr_image(recipe_url(recipe, extra.get("base_url", DEFAULT_BASE)))
    quiet = QUIET_MODULES
    mpx = max(1, 400 // (qr.width + 2 * quiet))
    tile, alpha = _qr_tile(qr, mpx, quiet)
    tx, tyq = (w - tile.shape[1]) // 2, h - tile.shape[0] - 190
    reg = np.asarray(img.convert("RGB"), dtype=np.float32)
    reg[tyq:tyq + tile.shape[0], tx:tx + tile.shape[1]] = (
        reg[tyq:tyq + tile.shape[0], tx:tx + tile.shape[1]] * (1 - alpha) + tile * alpha)
    img = Image.fromarray(np.rint(reg).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((w // 2, tyq - 30), "SCAN TO OPEN THE RECIPE", font=fonts.brand_font("mono-500", 22), fill=MUTED, anchor="mm")
    wm = fonts.wordmark(190)
    if wm is not None:
        img.alpha_composite(wm, (m, h - pm - 36 - wm.height))
    d.text((w - m, h - pm - 56), "OPEN SAUCE · Lightbrush", font=fonts.brand_font("rajdhani-600", 36),
           fill=TEXT, anchor="rm")
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    return out


def burn_endframe_qr(frames, recipe_url, n_frames=12, corner="br", size_frac=QR_SIZE_FRAC, quiet_zone=True):
    """Composite a QR over the last n_frames.

    Sized by modules: at least size_frac of min(H, W), and at least 4 px per module after a
    downscale to 720 px on the short side (survives social recompression). Quiet zone included.
    """
    arr = np.asarray(frames)
    is_float = arr.dtype != np.uint8
    out = arr.copy()
    n, h, w, _ = out.shape
    short = min(h, w)
    qr = _qr_image(recipe_url)
    modules = qr.width
    quiet = QUIET_MODULES if quiet_zone else 0
    total = modules + 2 * quiet
    mpx = max(-(-int(round(size_frac * short)) // total), -(-4 * short // 720), 1)
    tile, alpha = _qr_tile(qr, mpx, quiet)  # rounded white tile + 2 px cyan outline outside the quiet zone
    side = tile.shape[0]
    tile = tile.astype(np.float32) / 255.0 if is_float else tile
    margin = max(int(short * 0.03), 4)
    y0 = margin if corner[0] == "t" else h - side - margin
    x0 = margin if corner[1] == "l" else w - side - margin
    lo = max(n - n_frames, 0)
    reg = out[lo:, y0:y0 + side, x0:x0 + side, :3].astype(np.float32)
    mixed = reg * (1 - alpha) + tile.astype(np.float32) * alpha
    out[lo:, y0:y0 + side, x0:x0 + side, :3] = mixed if is_float else np.rint(mixed).astype(np.uint8)
    return out
