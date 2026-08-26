#!/usr/bin/env python3
"""make_sprite — basic SNES sprite maker (native SVG, draw-big-then-shrink).
Pipeline: qwen38 draws the subject as SVG at 4x the SNES target (comfortable size) -> downscale 4:1
(pixel-perfect) -> quantise <=16 colours + colour-key transparent index 0 -> preview PNG (+CHR-ready).
Best-of-N with a non-degenerate probe so it never ships a blank.

  make_sprite.py "a shiny gold coin with a star" --size 16 --tries 3
Outputs: out/<slug>_<size>.png (target, nearest-upscaled preview) + out/<slug>_src.png (the 4x draw).
"""
import os, re, io, json, sys, argparse, urllib.request
import cairosvg
from PIL import Image
import quant
URL  = os.getenv("SFC_LLM_URL", "http://localhost:8001")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = f"{HERE}/out"; os.makedirs(OUT, exist_ok=True)
KEY  = (255, 0, 255)
DRAW_CAP = 64   # model's comfortable pixel-art zone; drawing bigger (e.g. 128) goes sparse/incomplete

def llm(prompt, mt=8000, temp=0.5):
    b = json.dumps({"model": "qwen38", "messages": [{"role": "user", "content": prompt}],
                    "temperature": temp, "max_tokens": mt, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    r = urllib.request.Request(f"{URL}/v1/chat/completions", b, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read())["choices"][0]["message"]["content"]

# Soft front-end gamut constraint: loose to the LLM, but bounds the whole game's colours.
# It IS just a prompt table — formalised as a numbered registry (1..N) so it's a first-class,
# reproducible knob. theme=0/"none" = no constraint; any unknown string = custom palette phrase (BYO).
THEMES = {   # ordered; the number is (index+1)
    "morandi":     "muted Morandi palette — low-saturation greyed tones: dusty rose, sage, taupe, slate blue, warm grey; no pure/neon.",
    "earth":       "earth-tone palette — browns, ochre, terracotta, olive, warm tan, muted forest green.",
    "pastel":      "soft pastel palette — light pink, mint, baby blue, cream, lavender; gentle and airy.",
    "cartoon":     "bright saturated cartoon palette (Pokémon-like) — bold clean primary colours, cheerful.",
    "candy":       "candy palette — bright bubblegum pink, purple, teal, lemon yellow, glossy sweet colours.",
    "gameboy":     "4-shade Game Boy palette — only dark olive, mid green, light green, pale yellow-green.",
    "neon":        "neon palette — electric cyan, hot magenta, lime green on a deep near-black background.",
    "sunset":      "warm sunset palette — orange, coral pink, gold, magenta, deep purple gradient.",
    "ocean":       "ocean palette — teals, deep blue, aqua, seafoam, pale sand.",
    "forest":      "forest palette — deep green, moss, olive, bark brown, warm highlight.",
    "desert":      "desert palette — sand, tan, dusty orange, clay red, muted cactus green.",
    "ice":         "icy palette — pale cyan, ice blue, white, soft lavender, cool grey.",
    "lava":        "volcanic palette — bright red, orange, yellow core, charcoal black, ember glow.",
    "autumn":      "autumn palette — russet red, burnt orange, gold, brown, deep amber.",
    "spring":      "spring palette — fresh green, blossom pink, soft yellow, sky blue, cream.",
    "grayscale":   "grayscale palette — only shades of grey from black to white, no hue.",
    "sepia":       "sepia palette — warm browns, tan, cream, dark coffee; vintage monochrome-ish.",
    "cyberpunk":   "cyberpunk palette — hot magenta, electric cyan, violet, acid yellow on black.",
    "royal":       "royal palette — deep purple, gold, crimson, navy, ivory; regal and rich.",
    "jungle":      "tropical jungle palette — vivid leaf greens, parrot red/blue/yellow accents.",
    "halloween":   "Halloween palette — pumpkin orange, purple, black, toxic lime green.",
    "christmas":   "Christmas palette — pine green, holly red, white, gold accents.",
    "sakura":      "cherry-blossom palette — soft pink, white, pale green, warm brown branch.",
    "mintchoc":    "mint-chocolate palette — mint green, dark cocoa brown, cream, soft teal.",
    "vaporwave":   "vaporwave palette — pastel pink, cyan, lavender, peach; dreamy retro neon.",
    "military":    "military palette — olive drab, khaki, brown, slate grey, muted tan.",
    "goldlux":     "luxury palette — polished gold, black, cream, deep espresso; opulent.",
    "berry":       "berry palette — raspberry, blueberry, plum, deep magenta, dark leaf green.",
    "tropicfruit": "tropical-fruit palette — mango orange, lime, watermelon pink, kiwi green; juicy bright.",
    "steampunk":   "steampunk palette — brass, copper, aged bronze, dark brown, gunmetal.",
    "aurora":      "arctic-aurora palette — deep midnight blue, violet, teal, green glow, white stars.",
    "coral":       "coral-reef palette — coral orange, turquoise, sunny yellow, soft pink, sea blue.",
}
THEME_LIST = list(THEMES)   # index+1 = the number

def resolve_theme(arg):
    """arg -> palette phrase. Accepts: 0/'none'/'' (no constraint), a number 1..N, a preset name,
    or ANY other string (used verbatim as a custom palette description = theme 0 / bring-your-own)."""
    s = (arg or "").strip()
    if s in ("", "0", "none"): return ""
    if s.isdigit():
        i = int(s)
        return THEMES[THEME_LIST[i-1]] if 1 <= i <= len(THEME_LIST) else ""
    if s in THEMES: return THEMES[s]
    return s   # custom free-text palette prompt

STYLE = {
    "flat":    "STYLE: flat solid colour fills — no shading, no gradient; each region one bright saturated "
               "colour. The silhouette must be the object's ACTUAL shape (curves, points, notches), never a "
               "plain square. A thin darker edge on the shape is fine to define it.",
    "shade":   "STYLE: NO outline/border strokes (flat fills only, fill= no stroke=); bright saturated colours; "
               "give volume with SINGLE-SIDE shading — a darker shade along the bottom-right edge and a lighter "
               "tint on the top-left of each region; no full black outline.",
    "outline": "STYLE: bright saturated flat fills with a clean 1px dark outline around the silhouette and key "
               "internal features; classic readable game-sprite look.",
}

def chibi_wrap(subject, chibi):
    return (f"a chibi / super-deformed version of {subject}, big head ~half the body, tiny body, huge expressive "
            f"eyes, exaggerated signature features, cute mascot") if chibi else subject

def svg_raster(subject, px, style="flat", theme="none"):
    tw = resolve_theme(theme)
    t = llm(f"Draw {subject} as {px}x{px} pixel art. It must be INSTANTLY recognisable — a viewer names it "
            f"at a glance. Draw the object's OWN characteristic outline shape and its key defining features "
            f"(a heart's two lobes + point, a star's points, a leaf's veins) — NOT a filled rectangle or a "
            f"vague blob. Centre it large but leave a little transparent margin so the true silhouette shows. "
            f"Each <rect> is one pixel/block on a clean grid, shape-rendering=crispEdges, transparent background. "
            f"{STYLE.get(style, STYLE['flat'])} "
            f"{('PALETTE: keep every colour within this family — ' + tw) if tw else ''} "
            f"Output ONLY <svg viewBox='0 0 {px} {px}'>...</svg>.",
            min(16000, 1000 + px*px*4))
    o = re.search(r"<svg[^>]*>", t); body = "".join(re.findall(r"<(?:rect|circle|ellipse|polygon|path|line)[^>]*?/>", t))
    if not body: return None, t
    svg = (o.group(0) if o else f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {px} {px}'>") + body + "</svg>"
    try:
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px, output_height=px)
        return Image.open(io.BytesIO(png)).convert("RGBA"), t
    except Exception:
        return None, t

def nondegenerate(img, n):
    """not blank / not one colour: >=8% non-transparent AND >=3 distinct colours."""
    px = img.load(); nz = 0; cols = set()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a > 32: nz += 1; cols.add((r >> 5, g >> 5, b >> 5))
    return nz / (img.width*img.height) > 0.08 and len(cols) >= 3

def to_target(src, size, method=quant.DEFAULT, colors=15):
    img, _pal = quant.to_target(src, size, method, colors)     # pluggable: see quant.METHODS
    return img

def preview(img, out, scale):
    big = img.resize((img.width*scale, img.height*scale), Image.NEAREST)
    bg = Image.new("RGBA", big.size, (0, 0, 0, 0)); bp = bg.load()
    for y in range(big.height):
        for x in range(big.width):
            bp[x, y] = (60, 60, 70, 255) if ((x//scale + y//scale) % 2 == 0) else (44, 44, 54, 255)
    Image.alpha_composite(bg, big).save(out)

def make(subject, size, scale, tries, style="flat", chibi=False, slug=None, method=quant.DEFAULT, colors=15, theme="none"):
    subject = chibi_wrap(subject, chibi)
    slug = slug or re.sub(r"[^a-z0-9]+", "_", subject.lower())[:24].strip("_")
    # The model's comfortable drawing zone is ~64px; forcing a 128px SVG makes it draw sparse/incomplete.
    # Cap the draw size at DRAW_CAP and keep an integer downscale ratio (16->64 is 4x, 32->64 is 2x).
    draw_px = size * scale
    while draw_px > DRAW_CAP and draw_px - size >= size:  # step down whole multiples of size
        draw_px -= size
    best = None
    for i in range(tries):
        src, _ = svg_raster(subject, draw_px, style, theme)
        if src and nondegenerate(src, draw_px):
            best = src; break
        best = best or src
    if not best:
        print(f"  ! {subject}: all {tries} tries degenerate"); return None
    tgt = to_target(best, size, method, colors)
    tgt.save(f"{OUT}/{slug}_{size}_raw.png")   # RAW transparent sprite (use THIS for sheets/CHR, not the preview)
    preview(best.resize((draw_px, draw_px)), f"{OUT}/{slug}_src.png", max(1, 256//draw_px))
    preview(tgt, f"{OUT}/{slug}_{size}.png", 256//size)
    ok = nondegenerate(tgt, size)
    print(f"  {subject}: {draw_px}px SVG -> {size}x{size}  ({'ok' if ok else 'WEAK'})  -> {slug}_{size}.png")
    return tgt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("subject", nargs="?")
    ap.add_argument("--size", type=int, default=16, help="SNES target (16 or 32)")
    ap.add_argument("--scale", type=int, default=4, help="draw at size*scale (default 4x)")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--style", default="flat", choices=list(STYLE),
                    help="flat=solid blocks (best all-rounder); shade=single-side (organic FX: fire/smoke); outline")
    ap.add_argument("--chibi", action="store_true", help="chibi/super-deformed (exaggerate features; for characters)")
    ap.add_argument("--method", default=quant.DEFAULT, choices=list(quant.METHODS),
                    help="quantisation method (see quant.METHODS)")
    ap.add_argument("--colors", type=int, default=15, help="palette size (<=15 + transparent)")
    ap.add_argument("--theme", default="none",
                    help="palette gamut for whole-game coherence: 0/none, a preset name or number 1..%d, "
                         "or any custom phrase (BYO). Apply the SAME theme to every asset." % len(THEMES))
    ap.add_argument("--list-themes", action="store_true", help="print the numbered theme table and exit")
    a = ap.parse_args()
    if a.list_themes:
        for i, k in enumerate(THEME_LIST, 1): print(f"{i:2d}  {k:12s}  {THEMES[k]}")
        sys.exit(0)
    if not a.subject:
        ap.error("subject is required (or use --list-themes)")
    make(a.subject, a.size, a.scale, a.tries, a.style, a.chibi, method=a.method, colors=a.colors, theme=a.theme)
