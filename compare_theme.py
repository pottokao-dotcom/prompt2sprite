#!/usr/bin/env python3
"""Show a front-end THEME makes back-end palette extraction easy.
Draw several assets under ONE theme, extract a single shared master palette, remap all to it, and
measure distortion (own-palette vs shared-palette, mean OKLab delta). Low delta = theme pre-aligned
the colours so the shared bank barely changes them. -> theme_montage.png
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
import make_sprite as M
import quant

HERE = os.path.dirname(os.path.abspath(__file__)); CELL = 150
THEME = sys.argv[1] if len(sys.argv) > 1 else "candy"
ASSETS = ["a round hard candy", "a lollipop", "a chocolate bar", "a gummy bear", "a star sweet"]

def draw(subj):
    for _ in range(3):
        src, _ = M.svg_raster(subj, 64, "flat", THEME)
        if src and M.nondegenerate(src, 64): return src
    return src

def cell(img, top, bot):
    t = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0)); tp = t.load()
    for y in range(CELL):
        for x in range(CELL): tp[x, y] = (46, 46, 56, 255) if ((x//8+y//8) % 2 == 0) else (34, 34, 44, 255)
    if img:
        sc = max(1, (CELL-24)//max(img.width, img.height)); im = img.resize((img.width*sc, img.height*sc), Image.NEAREST)
        t.alpha_composite(im, ((CELL-im.width)//2, (CELL-im.height)//2 + 8))
    d = ImageDraw.Draw(t); d.text((4, 2), top, fill=(200, 220, 255, 255))
    if bot: d.text((4, CELL-12), bot, fill=(150, 200, 150, 255))
    return t

def swatch(pal, w, h):
    im = Image.new("RGB", (w, h), (18, 18, 26)); d = ImageDraw.Draw(im); n = len(pal); bw = w // max(1, n)
    for i, c in enumerate(pal): d.rectangle([i*bw, 0, (i+1)*bw-1, h-1], fill=tuple(c))
    return im

def oklab_delta(a, b):
    ma = np.array(a)[..., 3] >= quant.A_OPAQUE
    pa = quant.srgb_to_oklab(np.array(a)[..., :3][ma]); pb = quant.srgb_to_oklab(np.array(b)[..., :3][ma])
    return float(np.sqrt(((pa-pb)**2).sum(1)).mean())

def main():
    srcs = [(a, draw(a)) for a in ASSETS]
    smalls = [quant.ds_modal(s, 16) for _, s in srcs]
    own = [quant.to_target(s, 16, "modal_oklab")[0] for _, s in srcs]           # each its own palette
    master = quant.shared_palette(smalls, 15)                                    # ONE shared bank
    shared = [quant.remap_to(sm, master) for sm in smalls]
    deltas = [oklab_delta(o, s) for o, s in zip(own, shared)]
    n = len(ASSETS)
    W = 10 + n*(CELL+6); H = 6 + 2*(CELL+6) + 60
    mont = Image.new("RGBA", (W, H), (18, 18, 26, 255)); D = ImageDraw.Draw(mont)
    D.text((10, 2), f"THEME = {THEME}   (top: own palette   bottom: ONE shared master   delta = OKLab shift)",
           fill=(230, 230, 240, 255))
    for i, ((name, _), o, s, dl) in enumerate(zip(srcs, own, shared, deltas)):
        x = 10 + i*(CELL+6)
        mont.alpha_composite(cell(o, name.replace("a ", "")[:14], "own"), (x, 18))
        mont.alpha_composite(cell(s, "", f"shared d={dl:.3f}"), (x, 18+CELL+6))
    sw = swatch([tuple(int(v) for v in c) for c in master], W-20, 40)
    mont.paste(sw, (10, 18+2*(CELL+6)))
    D.text((10, H-16), f"shared master = {len(master)} colours   mean delta = {np.mean(deltas):.3f} "
           f"(low = theme pre-aligned colours, extraction easy)", fill=(150, 200, 150, 255))
    mont.convert("RGB").save(f"{HERE}/theme_montage.png")
    print(f"saved theme_montage.png  mean OKLab delta={np.mean(deltas):.3f}  master={len(master)}c", flush=True)

if __name__ == "__main__": main()
