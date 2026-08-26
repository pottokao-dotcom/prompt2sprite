#!/usr/bin/env python3
"""Quantisation shoot-out: ONE source draw per subject, run EVERY method in quant.METHODS on that
same source (fair — no regen confound). Bottom row: shared master palette across all three assets.
Montage rows=subject, cols=method; last panel = shared-palette remap. -> quant_montage.png
"""
import os
from PIL import Image, ImageDraw
import make_sprite as M
import quant

HERE = os.path.dirname(os.path.abspath(__file__)); CELL = 150
SUBJECTS = [
    ("a shiny gold coin with a star", 16, "flat"),
    ("a flaming fireball projectile pointing up", 16, "shade"),
    ("a jazz white rabbit with sunglasses and a golden saxophone", 32, "flat"),
]
METHS = list(quant.METHODS)

def draw_src(subj, size):
    dp = size*4
    for _ in range(3):
        src, _ = M.svg_raster(subj, dp, "flat")
        if src and M.nondegenerate(src, dp): return src, size
    return src, size

def cell(img, label, sub=""):
    t = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0)); tp = t.load()
    for y in range(CELL):
        for x in range(CELL): tp[x, y] = (46, 46, 56, 255) if ((x//8+y//8) % 2 == 0) else (34, 34, 44, 255)
    if img:
        sc = max(1, (CELL-24)//max(img.width, img.height)); im = img.resize((img.width*sc, img.height*sc), Image.NEAREST)
        t.alpha_composite(im, ((CELL-im.width)//2, (CELL-im.height)//2 + 8))
    d = ImageDraw.Draw(t); d.text((4, 2), label, fill=(200, 220, 255, 255))
    if sub: d.text((4, 13), sub, fill=(150, 200, 150, 255))
    return t

def main():
    rows = []
    srcs = []
    for subj, size, _ in SUBJECTS:
        print(f"draw {subj[:24]} @{size}", flush=True)
        src, size = draw_src(subj, size); srcs.append((src, size))
    ncol = len(METHS) + 1
    W = 70 + ncol*(CELL+6); H = 6 + len(SUBJECTS)*(CELL+6)
    mont = Image.new("RGBA", (W, H), (18, 18, 26, 255)); D = ImageDraw.Draw(mont)
    # precompute downsampled smalls per subject for shared palette (use modal)
    for ri, ((subj, size, _), (src, _)) in enumerate(zip(SUBJECTS, srcs)):
        y = 6 + ri*(CELL+6); D.text((4, y+CELL//2), subj.split()[2][:8], fill=(230, 230, 240, 255))
        for ci, m in enumerate(METHS):
            print(f"  {subj[:16]} {m}", flush=True)
            try: img, pal = quant.to_target(src, size, m); lbl = f"{m}"; sub = f"{len(pal)}c"
            except Exception as e: img, lbl, sub = None, m, str(e)[:10]
            mont.alpha_composite(cell(img, lbl, sub), (70+ci*(CELL+6), y))
    # shared master palette across all 3 (modal downsample each, one pooled palette)
    smalls = [quant.ds_modal(s, sz) for (s, sz) in srcs]
    master = quant.shared_palette(smalls, 15)
    for ri, (small, (subj, size, _)) in enumerate(zip(smalls, SUBJECTS)):
        y = 6 + ri*(CELL+6)
        img = quant.remap_to(small, master)
        mont.alpha_composite(cell(img, "SHARED pal", "15c/all"), (70+len(METHS)*(CELL+6), y))
    mont.convert("RGB").save(f"{HERE}/quant_montage.png"); print("saved quant_montage.png", flush=True)

if __name__ == "__main__": main()
