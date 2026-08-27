#!/usr/bin/env python3
"""make_set_svg — beginner one-liner (PURE PYTHON, NO GPU): ONE game concept → a whole coherent sprite SET.

    python3 make_set.py "a candy match-3 game"
    python3 make_set.py "an underwater treasure hunt" --size 16 --pieces 6

An LLM plans the set (a palette theme + N piece subjects + a hero), each is drawn via the SVG
front-end (no GPU), and the whole set is locked to one shared palette so it's coherent and
hardware-legal. Output: a folder with every sprite + a preview contact sheet + the palette.
Needs an OpenAI-compatible LLM that can emit SVG (default http://localhost:8001, model qwen38)."""
import json, os, re, argparse, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # import root tools
from PIL import Image, ImageDraw
import make_sprite as M
import quant

def plan(concept, n):
    txt = M.llm(
        f"Design the pixel-art sprite set for a small retro game about: {concept}. "
        f'Return ONLY JSON: {{"palette_theme": "<a short colour-mood phrase, e.g. \'candy pastel\' '
        f'or \'deep space neon\'>", "pieces": [{n} short DISTINCT subjects for the collectible / '
        f'match-3 pieces — one object each], "hero": "<the main character subject>"}}.', 600, 0.5)
    return json.loads(re.search(r"\{.*\}", txt, re.S).group(0))

def contact(assets, out):
    C = 84; cols = min(len(assets), 6); rows = (len(assets)+cols-1)//cols
    o = Image.new("RGB", (cols*C, rows*C+18), (20, 20, 28)); d = ImageDraw.Draw(o)
    for i, (lab, im) in enumerate(assets):
        r, c = divmod(i, cols); x, y = c*C, r*C
        for yy in range(0, C, 8):
            for xx in range(0, C, 8):
                o.paste((40, 34, 54) if (xx//8+yy//8) % 2 else (30, 26, 40), (x+xx, y+yy, min(x+xx+8, x+C), min(y+yy+18, y+C+18)))
        s = max(1, (C-14)//max(im.width, im.height)); big = im.resize((im.width*s, im.height*s), Image.NEAREST)
        o.paste(big, (x+(C-big.width)//2, y+16+(C-16-big.height)//2), big)
        d.text((x+2, y+2), lab[:12], fill=(200, 220, 255))
    o.convert("RGB").save(out)

def make_set(concept, size, n, out):
    os.makedirs(out, exist_ok=True)
    p = plan(concept, n)
    theme = p.get("palette_theme", "none"); pieces = p["pieces"][:n]; hero = p.get("hero")
    print(f"■ concept : {concept}\n■ theme   : {theme}\n■ pieces  : {', '.join(pieces)}\n■ hero    : {hero}\n")
    raw = []
    for i, subj in enumerate(pieces):
        print(f"  drawing piece {i+1}/{len(pieces)}: {subj}", flush=True)
        im = M.make(subj, size, 4, 2, style="flat", slug=f"piece{i}", theme=theme)
        if im is not None: raw.append((subj, im))
    if hero:
        print(f"  drawing hero: {hero}", flush=True)
        h = M.make(hero, 32, 4, 3, style="flat", slug="hero", theme=theme)
        if h is not None: raw.append((hero, h))
    master = quant.shared_palette([im for _, im in raw], 15)          # one shared bank → coherent + legal
    final = [(lab, quant.remap_to(im, master)) for lab, im in raw]
    for i, (lab, im) in enumerate(final):
        im.save(f"{out}/{'hero' if lab == hero else f'piece{i}'}.png")
    open(f"{out}/palette.hex", "w").write("\n".join("#%02x%02x%02x" % tuple(int(v) for v in c) for c in master) + "\n")
    contact(final, f"{out}/preview.png")
    print(f"\n✓ set ready in {out}/  ({len(final)} sprites · one shared 15-colour palette)\n  open {out}/preview.png")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("concept", help='a game concept, e.g. "a candy match-3 game"')
    ap.add_argument("--size", type=int, default=16, help="piece size (16 or 32)")
    ap.add_argument("--pieces", type=int, default=6, help="how many pieces")
    ap.add_argument("--out", default=None, help="output folder")
    a = ap.parse_args()
    out = a.out or "set_" + re.sub(r"[^a-z0-9]+", "_", a.concept.lower())[:20].strip("_")
    make_set(a.concept, a.size, a.pieces, out)
