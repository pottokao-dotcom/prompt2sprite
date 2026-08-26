#!/usr/bin/env python3
"""Two worries, one test:
  (1) does compressing / palette-extraction make colours DRIFT?
  (2) do the flat-style + theme constraints make the model draw DUMBER (less recognisable)?
For each subject draw FREE (no style, no theme) vs CONSTRAINED (flat + theme), quantise each to its
own palette, then remap the CONSTRAINED set to ONE shared master. Report per-asset own->shared OKLab
drift, and palette spread (how far apart the assets' colours are) free vs themed.
Cols: [free own-pal] [themed own-pal] [themed SHARED-pal]. -> constraint_montage.png
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
import make_sprite as M
import quant

HERE = os.path.dirname(os.path.abspath(__file__)); CELL = 150
THEME = sys.argv[1] if len(sys.argv) > 1 else "candy"
# (subject, size, style_for_constrained)
JOBS = [
    ("a round hard candy", 16, "flat"),
    ("a lollipop", 16, "flat"),
    ("a chocolate bar", 16, "flat"),
    ("a gummy bear", 16, "flat"),
]

def draw(subj, px, style, theme):
    for _ in range(3):
        src, _ = M.svg_raster(subj, px, style, theme)
        if src and M.nondegenerate(src, px): return src
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
    im = Image.new("RGB", (w, h), (18, 18, 26)); d = ImageDraw.Draw(im); bw = w // max(1, len(pal))
    for i, c in enumerate(pal): d.rectangle([i*bw, 0, (i+1)*bw-1, h-1], fill=tuple(int(v) for v in c))
    return im

def opx(img):
    a = np.array(img); return a[..., :3][a[..., 3] >= quant.A_OPAQUE]

def drift(a, b):
    m = np.array(a)[..., 3] >= quant.A_OPAQUE
    pa = quant.srgb_to_oklab(np.array(a)[..., :3][m]); pb = quant.srgb_to_oklab(np.array(b)[..., :3][m])
    return float(np.sqrt(((pa-pb)**2).sum(1)).mean())

def spread(imgs):
    """mean pairwise OKLab distance between asset palette centroids — how 'scattered' the set's colour is."""
    cents = [quant.srgb_to_oklab(opx(i)).mean(0) for i in imgs if len(opx(i))]
    if len(cents) < 2: return 0.0
    ds = [np.sqrt(((cents[i]-cents[j])**2).sum()) for i in range(len(cents)) for j in range(i+1, len(cents))]
    return float(np.mean(ds))

def main():
    free, themed = [], []
    for subj, size, style in JOBS:
        print(f"free  {subj[:20]}", flush=True); free.append(draw(subj, size*4, "outline", "none"))
        print(f"theme {subj[:20]}", flush=True); themed.append(draw(subj, size*4, style, THEME))
    sizes = [s for _, s, _ in JOBS]
    free_q  = [quant.to_target(f, sz, "modal_oklab")[0] for f, sz in zip(free, sizes)]
    them_q  = [quant.to_target(t, sz, "modal_oklab")[0] for t, sz in zip(themed, sizes)]
    smalls  = [quant.ds_modal(t, sz) for t, sz in zip(themed, sizes)]
    master  = quant.shared_palette(smalls, 15)
    them_sh = [quant.remap_to(s, master) for s in smalls]
    drifts  = [drift(o, s) for o, s in zip(them_q, them_sh)]

    n = len(JOBS); W = 10 + 3*(CELL+6); H = 20 + n*(CELL+6) + 50
    mont = Image.new("RGBA", (W, H), (18, 18, 26, 255)); D = ImageDraw.Draw(mont)
    D.text((10, 2), f"THEME={THEME}   col1 FREE(outline,no theme)   col2 themed+flat   col3 themed->SHARED master",
           fill=(230, 230, 240, 255))
    for i, ((subj, sz, _), fq, tq, ts, dr) in enumerate(zip(JOBS, free_q, them_q, them_sh, drifts)):
        y = 18 + i*(CELL+6); nm = subj.replace("a ", "")[:12]
        mont.alpha_composite(cell(fq, nm, "free"), (10, y))
        mont.alpha_composite(cell(tq, "", "themed own"), (10+CELL+6, y))
        mont.alpha_composite(cell(ts, "", f"shared d={dr:.3f}"), (10+2*(CELL+6), y))
    mont.paste(swatch(master, W-20, 34), (10, 18+n*(CELL+6)))
    D.text((10, H-14),
           f"palette DRIFT own->shared mean={np.mean(drifts):.3f} (JND~0.02)   "
           f"colour SPREAD free={spread(free_q):.3f} vs themed={spread(them_q):.3f} (lower=more coherent)",
           fill=(150, 200, 150, 255))
    mont.convert("RGB").save(f"{HERE}/constraint_montage.png")
    print(f"saved constraint_montage.png  drift={np.mean(drifts):.3f}  "
          f"spread free={spread(free_q):.3f} themed={spread(them_q):.3f}", flush=True)

if __name__ == "__main__": main()
