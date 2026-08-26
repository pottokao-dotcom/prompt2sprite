#!/usr/bin/env python3
"""Style shoot-out: flat vs shade vs outline (icons) + chibi vs normal (character).
Each cell = make_sprite output at its SNES target, nearest-upscaled, labelled. One montage to judge.
"""
import os
from PIL import Image, ImageDraw
import make_sprite as M

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 170
# (subject, size, style, chibi, label, slug)
JOBS = [
    ("a shiny gold coin with a star",              16, "flat",    False, "coin flat",    "coin_flat"),
    ("a shiny gold coin with a star",              16, "shade",   False, "coin shade",   "coin_shade"),
    ("a shiny gold coin with a star",              16, "outline", False, "coin outline", "coin_out"),
    ("a flaming fireball projectile pointing up",  16, "flat",    False, "fire flat",    "fire_flat"),
    ("a flaming fireball projectile pointing up",  16, "shade",   False, "fire shade",   "fire_shade"),
    ("a flaming fireball projectile pointing up",  16, "outline", False, "fire outline", "fire_out"),
    ("a jazz white rabbit with sunglasses and a golden saxophone", 32, "flat",    False, "rabbit flat",       "rab_flat"),
    ("a jazz white rabbit with sunglasses and a golden saxophone", 32, "shade",   False, "rabbit shade",      "rab_shade"),
    ("a jazz white rabbit with sunglasses and a golden saxophone", 32, "outline", True,  "rabbit chibi+out",  "rab_chibi_o"),
    ("a jazz white rabbit with sunglasses and a golden saxophone", 32, "flat",    True,  "rabbit chibi+flat", "rab_chibi_f"),
]
COLS = 3

def cell(png, label):
    tile = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0)); tp = tile.load()
    for y in range(CELL):
        for x in range(CELL): tp[x, y] = (46, 46, 56, 255) if ((x//8+y//8) % 2 == 0) else (34, 34, 44, 255)
    if png and os.path.exists(png):
        im = Image.open(png).convert("RGBA")
        tile.alpha_composite(im, ((CELL-im.width)//2, (CELL-im.height)//2 + 6))
    d = ImageDraw.Draw(tile); d.text((5, 3), label, fill=(200, 220, 255, 255))
    if not (png and os.path.exists(png)): d.text((CELL//2-14, CELL//2), "FAIL", fill=(255, 90, 90, 255))
    return tile

def main():
    imgs = []
    for subj, size, style, chibi, label, slug in JOBS:
        print(f"  {label} ({style}{' chibi' if chibi else ''}) @ {size}", flush=True)
        try:
            M.make(subj, size, 4, 2, style=style, chibi=chibi, slug=slug)
            imgs.append((f"{M.OUT}/{slug}_{size}.png", label))
        except Exception as e:
            print("   err", str(e)[:80]); imgs.append((None, label))
    rows = (len(imgs)+COLS-1)//COLS; pad = 6
    W = pad + COLS*(CELL+pad); H = pad + rows*(CELL+pad)
    mont = Image.new("RGBA", (W, H), (18, 18, 26, 255))
    for i, (png, label) in enumerate(imgs):
        r, c = divmod(i, COLS)
        mont.alpha_composite(cell(png, label), (pad+c*(CELL+pad), pad+r*(CELL+pad)))
    mont.convert("RGB").save(f"{HERE}/style_montage.png"); print("saved style_montage.png", flush=True)

if __name__ == "__main__": main()
