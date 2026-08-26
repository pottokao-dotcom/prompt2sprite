#!/usr/bin/env python3
"""Generate K candidates per piece (structured candy subjects the model handles well) at 32px with
theme=candy, save each, and lay a contact sheet (rows=piece, cols=candidate) for a human/agent visual
judge to pick the best. -> candidates_sheet.png + cand_out/<slug>_<k>.png
"""
import os
from PIL import Image, ImageDraw
import make_sprite as M

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cand_out"); os.makedirs(OUT, exist_ok=True)
K = 3
PIECES = [   # structured, distinct — the model draws these far better than abstract symbols
    ("a round peppermint candy with a red and white swirl", "mint"),
    ("a lollipop with a spiral swirl on a stick",           "lolli"),
    ("a green gummy bear",                                  "gummy"),
    ("a chocolate bar with square segments",                "choco"),
    ("a pink frosted donut with sprinkles",                 "donut"),
    ("a juicy orange citrus slice",                         "orange"),
]
C = 120

def main():
    grid = []
    for subj, slug in PIECES:
        row = []
        for k in range(K):
            print(f"{slug} {k}", flush=True)
            img = M.make(subj, 32, 4, 1, style="flat", slug=f"{slug}_{k}", method="modal_oklab",
                         colors=15, theme="candy")
            row.append(img)
        grid.append((slug, row))
    W = 90 + K*C; H = 6 + len(PIECES)*C
    sheet = Image.new("RGB", (W, H), (20, 20, 28)); d = ImageDraw.Draw(sheet)
    for ri, (slug, row) in enumerate(grid):
        y = 6 + ri*C; d.text((4, y+C//2), slug, fill=(220, 220, 240))
        for k, img in enumerate(row):
            x = 90 + k*C
            for yy in range(C):
                for xx in range(C):
                    if (xx//8 + yy//8) % 2 == 0: sheet.putpixel((x+xx, y+yy), (40, 40, 50))
            if img:
                im = img.convert("RGBA"); sheet.paste(im, (x+(C-im.width)//2, y+(C-im.height)//2), im)
            d.text((x+2, y+2), f"#{k}", fill=(150, 200, 150))
    sheet.save(f"{os.path.dirname(OUT)}/candidates_sheet.png"); print("saved candidates_sheet.png", flush=True)

if __name__ == "__main__":
    main()
