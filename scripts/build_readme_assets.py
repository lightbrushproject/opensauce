# ruff: noqa: E702  (generator script written in a compact one-liner style)
import base64
import io
import os
import random

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "readme")
F = os.path.join(ROOT, "assets", "fonts")

CY, BR, IN = "#14d7f2", "#06fbfc", "#6366f1"
VOID, SPACE, PANEL, ELEV = "#020408", "#050810", "#060d18", "#0c1a2e"
TXT, MUT = "#e2e8f0", "#94a3b8"

_cache = {}
def font(name, wght=None):
    k = (name, wght)
    if k not in _cache:
        t = TTFont(os.path.join(F, name))
        if wght:
            t = instancer.instantiateVariableFont(t, {"wght": wght})
        _cache[k] = t
    return _cache[k]

def RAJ():
    return font("Rajdhani-Bold.ttf")
def SG(w=500):
    return font("SpaceGrotesk-VF.ttf", w)
def JB(w=500):
    return font("JetBrainsMono-VF.ttf", w)

def r(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s

def text(f, s, size, x=0, y=0, track=0.0):
    """Return (path d, advance width). track in em. Baseline at y, left at x."""
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    sc = size / upm
    pen = SVGPathPen(gs, ntos=lambda v: r(v))
    cx = x
    for i, ch in enumerate(s):
        gn = cmap.get(ord(ch))
        if gn is None:
            continue
        tp = TransformPen(pen, (sc, 0, 0, -sc, cx, y))
        gs[gn].draw(tp)
        cx += f["hmtx"][gn][0] * sc + track * size
    return pen.getCommands(), cx - x - track * size

def tpath(f, s, size, x, y, track=0.0, fill=TXT, extra=""):
    d, w = text(f, s, size, x, y, track)
    return f'<path d="{d}" fill="{fill}" {extra}/>', w

def logo_png(width, colors=None):
    im = Image.open(os.path.join(ROOT, "assets", "brand", "lightbrush-logo.png")).convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    h = round(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    if colors:
        im = im.quantize(colors, method=Image.FASTOCTREE, dither=Image.NONE)
    b = io.BytesIO(); im.save(b, "PNG", optimize=True)
    return b.getvalue(), width, h

def write(name, s):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)
    print(name, os.path.getsize(p))

RM = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
EASE = "cubic-bezier(0,0,.2,1)"

# ---------------------------------------------------------------- header
def header():
    W, H = 1920, 600
    rnd = random.Random(21)
    parts = []
    # particles
    for i in range(70):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        rad = rnd.choice([1.2, 1.6, 2.0, 2.6, 3.4])
        op = rnd.choice([.15, .25, .35, .5])
        col = BR if rnd.random() < .25 else (IN if rnd.random() < .15 else CY)
        cls = rnd.choice(["d1", "d2", "d3"])
        dl = -rnd.uniform(0, 50)
        parts.append(f'<g class="p {cls}" style="animation-delay:{dl:.1f}s"><circle cx="{r(x)}" cy="{r(y)}" r="{rad}" fill="{col}" fill-opacity="{op}"/></g>')
    eb, _ = tpath(JB(500), "OPEN SOURCE  \u00b7  MIT  \u00b7  OPEN WEIGHTS", 22, 120, 104, .2, CY)
    wm_d, wm_w = text(RAJ(), "OPEN SAUCE", 214, 120, 300, .1)
    p1, _ = tpath(SG(500), "Cinematic camera moves, rebuilt as free, open, forkable ComfyUI presets.", 38, 120, 428, 0, TXT)
    p2, _ = tpath(SG(400), "Every output video carries its own recipe.", 28, 120, 474, 0, MUT)
    lg, lw, lh = logo_png(270, 160)
    b64 = base64.b64encode(lg).decode()
    disp_h = 64; disp_w = round(lw * disp_h / lh)
    tg, _ = tpath(JB(500), "ANIMATING WITH AI SINCE 2021", 20, 120 + disp_w + 32, 556, .2, MUT)
    ring = f'''<g class="ring" fill="none" stroke="{CY}" stroke-linecap="round">
<circle cx="1620" cy="250" r="150" stroke-opacity=".30" stroke-width="1.5" stroke-dasharray="320 622"/>
<circle cx="1620" cy="250" r="214" stroke-opacity=".16" stroke-width="1" stroke-dasharray="40 14"/>
</g>
<g class="ring2" fill="none" stroke="{BR}" stroke-linecap="round"><circle cx="1620" cy="250" r="182" stroke-opacity=".34" stroke-width="2" stroke-dasharray="90 1053"/></g>'''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">OPEN SAUCE. Cinematic camera moves, rebuilt as free, open, forkable ComfyUI presets. Every output video carries its own recipe. Lightbrush, animating with AI since 2021.</title>
<defs>
<radialGradient id="bg" cx="78%" cy="40%" r="75%"><stop offset="0" stop-color="{ELEV}"/><stop offset=".45" stop-color="{SPACE}"/><stop offset="1" stop-color="{VOID}"/></radialGradient>
<linearGradient id="rule" gradientUnits="userSpaceOnUse" x1="120" x2="1800" y1="0" y2="0"><stop offset="0" stop-color="{CY}"/><stop offset=".7" stop-color="{CY}" stop-opacity=".55"/><stop offset="1" stop-color="{IN}" stop-opacity=".35"/></linearGradient>
<filter id="b1" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="22"/></filter>
<filter id="b2" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="7"/></filter>
<filter id="gl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>
</defs>
<style>
.p{{animation:drift linear infinite}}
.d1{{animation-duration:34s}}.d2{{animation-duration:48s}}.d3{{animation-duration:64s}}
@keyframes drift{{0%{{transform:translate(0,0);opacity:0}}12%{{opacity:1}}88%{{opacity:1}}100%{{transform:translate(46px,-230px);opacity:0}}}}
.bloom1,.bloom2{{opacity:.5}}
.bloom1{{animation:breathe 7s ease-in-out infinite alternate}}
.bloom2{{animation:breathe 7s ease-in-out -2.5s infinite alternate}}
@keyframes breathe{{0%{{opacity:.28}}100%{{opacity:.8}}}}
.in{{animation:up .8s {EASE} both}}
.in2{{animation:up .8s {EASE} .25s both}}
.in3{{animation:up .8s {EASE} .5s both}}
.in4{{animation:up .8s {EASE} 1.4s both}}
@keyframes up{{from{{transform:translateY(26px);opacity:0}}to{{transform:translateY(0);opacity:1}}}}
.draw{{stroke-dasharray:1;stroke-dashoffset:0;animation:draw 1.8s {EASE} .3s both}}
@keyframes draw{{from{{stroke-dashoffset:1}}to{{stroke-dashoffset:0}}}}
.pulse{{stroke-dasharray:.05 2;stroke-dashoffset:.05;opacity:0;animation:trav 6.5s linear 2.4s infinite backwards}}
@keyframes trav{{from{{stroke-dashoffset:.05;opacity:1}}to{{stroke-dashoffset:-1;opacity:1}}}}
.ring{{transform-box:fill-box;transform-origin:center;animation:spin 110s linear infinite}}
.ring2{{transform-box:fill-box;transform-origin:center;animation:spin 26s linear infinite reverse}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
{RM}
</style>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
{ring}
{''.join(parts)}
<g class="in">{eb}</g>
<g class="bloom1"><path d="{wm_d}" fill="{CY}" filter="url(#b1)"/></g>
<g class="bloom2"><path d="{wm_d}" fill="{CY}" filter="url(#b2)"/></g>
<g class="in"><path d="{wm_d}" fill="{TXT}"/></g>
<path class="draw" pathLength="1" d="M120 352H1800" stroke="url(#rule)" stroke-width="3" fill="none" stroke-linecap="round"/>
<path class="pulse" pathLength="1" d="M120 352H1800" stroke="{BR}" stroke-width="5" fill="none" stroke-linecap="round" filter="url(#gl)"/>
<g class="in2">{p1}</g>
<g class="in3">{p2}</g>
<g class="in4"><image x="120" y="{556-48}" width="{disp_w}" height="{disp_h}" xlink:href="data:image/png;base64,{b64}"/>{tg}</g>
</svg>'''
    write("header.svg", svg)
    print("wordmark width", wm_w)

# ---------------------------------------------------------------- divider
def divider():
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 20" width="1200" height="20" role="presentation" aria-hidden="true">
<defs>
<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{BR}" stop-opacity="0"/><stop offset=".5" stop-color="{BR}"/><stop offset="1" stop-color="{BR}" stop-opacity="0"/></linearGradient>
<linearGradient id="base" x1="0" x2="1"><stop offset="0" stop-color="{CY}" stop-opacity=".4"/><stop offset="1" stop-color="{CY}" stop-opacity=".05"/></linearGradient>
<filter id="gl" x="-20%" y="-300%" width="140%" height="700%"><feGaussianBlur stdDeviation="3"/></filter>
</defs>
<style>
.s{{animation:sweep 5.5s cubic-bezier(.33,1,.68,1) infinite}}
@keyframes sweep{{0%{{transform:translateX(0)}}85%,100%{{transform:translateX(1620px)}}}}
{RM}
</style>
<rect x="0" y="9.5" width="1200" height="1" fill="url(#base)"/>
<rect class="s" x="-400" y="8.5" width="360" height="3" fill="url(#g)" filter="url(#gl)" opacity=".9"/>
<rect class="s" x="-400" y="9" width="360" height="2" fill="url(#g)"/>
<rect x="0" y="6" width="2" height="8" fill="{CY}"/>
</svg>'''
    write("divider.svg", svg)

# ---------------------------------------------------------------- diagrams
def lit_keyframes(name, cycle, start, dur, rise=.4, fall=.6, peak=1):
    """CSS keyframes: opacity 0 -> peak within window starting at `start` seconds."""
    def p(t):
        return f"{t / cycle * 100:.2f}%"
    return (f"@keyframes {name}{{0%,{p(start)}{{opacity:0}}{p(start+rise)}{{opacity:{peak}}}"
            f"{p(start+dur)}{{opacity:{peak}}}{p(start+dur+fall)}{{opacity:0}}100%{{opacity:0}}}}")

class Dia:
    def __init__(self, W, H, cycle):
        self.W, self.H, self.cycle = W, H, cycle
        self.body, self.css, self.n = [], [], 0
    def node(self, x, y, w, h, title, subs, lit_at, lit_dur=1.2, tsize=21, accent=CY, subsz=13):
        self.n += 1
        k = f"n{self.n}"
        self.css.append(lit_keyframes(k, self.cycle, lit_at, lit_dur, .3, .7))
        self.css.append(f".{k}{{animation:{k} {self.cycle}s linear infinite}}")
        t, _ = tpath(SG(600), title, tsize, x + 14, y + 14 + tsize * .75, .03, TXT)
        ss = []
        for i, s in enumerate(subs):
            d, _ = tpath(JB(400), s, subsz, x + 14, y + 14 + tsize * .75 + 8 + (i + 1) * (subsz + 4), 0, MUT)
            ss.append(d)
        self.body.append(f'''<g>
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{PANEL}" stroke="{CY}" stroke-opacity=".28"/>
<rect x="{x+10}" y="{y}" width="{w-20}" height="1.5" fill="{CY}" opacity=".45"/>
<rect class="{k}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{CY}" fill-opacity=".07" stroke="{BR}" stroke-width="1.6" opacity="0"/>
{t}{''.join(ss)}</g>''')
    def conn(self, d, pulse_at, dur=.9, id=None):
        self.n += 1
        k = f"c{self.n}"
        c = self.cycle
        s, e = pulse_at / c * 100, (pulse_at + dur) / c * 100
        self.css.append(f"@keyframes {k}{{0%,{s:.2f}%{{stroke-dashoffset:.07;opacity:1}}{e:.2f}%,100%{{stroke-dashoffset:-1;opacity:1}}}}")
        self.css.append(f".{k}{{animation:{k} {c}s linear infinite}}")
        self.body.insert(0, f'<path d="{d}" fill="none" stroke="{CY}" stroke-opacity=".3" stroke-width="1.5"/>')
        self.body.append(f'<path class="{k}" pathLength="1" d="{d}" fill="none" stroke="{BR}" stroke-width="3.5" stroke-linecap="round" stroke-dasharray=".07 2" stroke-dashoffset=".07" opacity="0" filter="url(#gl)"/>')
    def label(self, s, x, y, size=14, col=CY, track=.2, f=None):
        d, w = tpath(f or JB(500), s, size, x, y, track, col)
        self.body.append(d); return w
    def svg(self, title, extra_defs=""):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.W} {self.H}" width="{self.W}" height="{self.H}" role="img" aria-labelledby="t">
<title id="t">{title}</title>
<defs><filter id="gl" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>{extra_defs}</defs>
<style>{''.join(self.css)}{RM}</style>
<rect width="{self.W}" height="{self.H}" fill="{VOID}"/>
{''.join(self.body)}
</svg>'''

def pipeline():
    d = Dia(1200, 432, 8.0)
    yc = 226
    d.node(16, yc-45, 132, 90, "PHOTO", ["one still", "9:16 portrait"], 0.0)
    d.node(190, yc-45, 150, 90, "DEPTH+MASK", ["depth map", "subject mask"], 1.0, tsize=19)
    lanes = [(106, "GEOMETRY-LED", ["vertigo · crash zoom · pull back", "depth reprojection"]),
             (yc, "MOTION-LED", ["levitate", "prompt-led"]),
             (346, "MATERIAL-LED", ["petrify", "two-step chain"])]
    for i, (ly, t, s_) in enumerate(lanes):
        d.node(384, ly-42, 280, 84, t, s_, 2.0 + i * .25, tsize=19)
    d.node(714, yc-45, 128, 90, "LTX-2.5", ["image-to-video", "open weights"], 3.2, subsz=12)
    d.node(886, yc-45, 112, 90, "POLISH", ["speed ramp", "grade chip"], 4.4)
    d.node(1040, yc-62, 150, 124, "OUTPUT", ["MP4 + recipe tags", "recipe card", "optional QR"], 5.6)
    d.conn(f"M148 {yc}H190", .5, .6)
    for i, (ly, _, _) in enumerate(lanes):
        d.conn(f"M340 {yc}C362 {yc} 362 {ly} 384 {ly}", 1.5 + i * .25, .6)
    for i, (ly, _, _) in enumerate(lanes):
        d.conn(f"M664 {ly}C689 {ly} 689 {yc} 714 {yc}", 2.7, .6)
    d.conn(f"M842 {yc}H886", 3.9, .6)
    d.conn(f"M998 {yc}H1040", 5.1, .6)
    d.label("ONE SHARED PIPELINE", 16, 34, 15)
    d.label("SHOTGRAMMAR NODES + LTX-2.5 ON YOUR OWN GPU", 16, 420, 12, MUT, .12)
    write("pipeline.svg", d.svg("The shared OPEN SAUCE pipeline: photo, depth and mask, then a geometry-led, motion-led or material-led lane, then LTX-2.5, polish, and an MP4 that carries its recipe, with an optional QR."))

def fork():
    d = Dia(1200, 448, 10.0)
    yc = 150
    xs = [16, 252, 488, 724, 960]
    w, h = 224, 92
    nodes = [("MP4", ["any OPEN SAUCE render"]),
             ("FORK", ["python -m app fork clip.mp4"]),
             ("RECIPE JSON", ["recipes/<id>.json"]),
             ("COMFYUI GRAPH", ["API workflow, exact"]),
             ("NEW RENDER", ["same seed, same shot"])]
    for i, ((t, s_), x) in enumerate(zip(nodes, xs)):
        d.node(x, yc-h//2, w, h, t, s_, i * 2.0, 1.7, tsize=21, subsz=13)
    for i in range(4):
        d.conn(f"M{xs[i]+w} {yc}H{xs[i+1]}", i * 2.0 + 1.55, .5)
    d.conn(f"M1072 {yc-h//2}C1072 44 128 44 128 {yc-h//2}", 8.7, 1.2)
    d.label("FORK THIS SHOT", 16, 30, 15)
    d.label("FORK IT AGAIN", 540, 66, 12, MUT, .2)
    car = [("MP4 METADATA", "tags inside the file"), ("SIDECAR JSON", "recipes/ in this repo"),
           ("RECIPE CARD", "PNG image"), ("QR CODE", "optional, last frames")]
    for i, (t, s_) in enumerate(car):
        d.node(16 + i * 296, 318, 280, 64, t, [s_], i * .6, 1.9, tsize=17, subsz=12)
    def line(p):
        return d.body.append(f'<path d="{p}" stroke="{CY}" stroke-opacity=".3" fill="none"/>')
    line(f"M156 {yc+h//2}V290"); line("M156 290H1044")
    for i in range(4):
        line(f"M{156+i*296} 290V318")
    d.label("THE RECIPE TRAVELS FOUR WAYS", 16, 414, 13, CY, .2)
    d.label("ANY FORK IS A NEW MP4 THAT CARRIES ITS OWN RECIPE", 16, 436, 12, MUT, .12)
    write("fork-this-shot.svg", d.svg("Fork This Shot: read the recipe out of an OPEN SAUCE MP4 (or scan its optional QR), open the recipe JSON, restore the ComfyUI graph, render a new video. The recipe travels in four carriers: MP4 metadata, sidecar JSON, recipe card PNG and a QR code."))

# ---------------------------------------------------------------- tiles
def tiles():
    rows = [("vertigo", "01", "VERTIGO", "THE RUSH"), ("crash_zoom", "02", "CRASH ZOOM", "THE HIT"),
            ("disintegrate", "03", "DISINTEGRATE", "THE CRUMBLE"), ("petrify", "04", "PETRIFY", "THE REVEAL"),
            ("levitate", "05", "LEVITATE", "THE RISE"), ("trailer", "06", "MAIN CHARACTER TRAILER", "THE TITLE LANDS")]
    for i, (slug, num, name, tag) in enumerate(rows):
        W, H = 480, 76
        n, _ = tpath(JB(500), num, 20, 16, 34, .05, CY)
        nm, nw = text(RAJ(), name, 31 if len(name) < 18 else 25, 58, 35, .06)
        tg, tw = text(JB(500), tag, 14, 0, 0, .18)
        tg, _ = text(JB(500), tag, 14, 58, 60, .18)
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{num} {name.title()}: {tag.lower()}</title>
<defs>
<clipPath id="c"><rect width="{W}" height="{H}"/></clipPath>
<linearGradient id="sw" x1="0" x2="1"><stop offset="0" stop-color="{BR}" stop-opacity="0"/><stop offset=".5" stop-color="{BR}" stop-opacity=".28"/><stop offset="1" stop-color="{BR}" stop-opacity="0"/></linearGradient>
</defs>
<style>.s{{animation:sw 7s cubic-bezier(.33,1,.68,1) {i*.7:.1f}s infinite backwards}}
@keyframes sw{{0%{{transform:translateX(0)}}30%,100%{{transform:translateX(900px)}}}}{RM}</style>
<rect width="{W}" height="{H}" fill="{PANEL}"/>
<g clip-path="url(#c)"><g transform="skewX(-18)"><rect class="s" x="-300" y="0" width="200" height="{H}" fill="url(#sw)"/></g></g>
<rect x="0" y="0" width="{W}" height="2" fill="{CY}"/>
<rect x="0" y="0" width="{W}" height="2" fill="{BR}" opacity=".0"/>
{n}<path d="{nm}" fill="{TXT}"/><path d="{tg}" fill="{MUT}"/>
</svg>'''
        write(f"tile_{slug}.svg", svg)

if __name__ == "__main__":
    b, w_, h_ = logo_png(360, 192)
    open(os.path.join(OUT, 'lightbrush-logo.png'), 'wb').write(b); print('logo', len(b), w_, h_)
    header(); divider(); pipeline(); fork(); tiles()
