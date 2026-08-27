#!/usr/bin/env python3
"""diffuse_quant — back-end for RASTER sprites (e.g. a ComfyUI / diffusion pixel-art image), reusing the
same quant maths as the SVG path. A diffusion model gives a big raster on a solid background; this:
  strip background (flood-fill from corners) -> crop to the sprite -> square-pad -> modal downscale to
  the SNES target -> quantise (free OKLab, OR HARD-LOCK to a fixed palette) -> BGR555 -> preview + raw.

  diffuse_quant.py shot.png --size 16                        # free palette
  diffuse_quant.py shot.png --size 16 --palette palettes/candy.hex   # hard palette lock
The fixed-palette path is the honest test of "can we lock the palette": the model's colours are ignored,
every pixel is remapped to the nearest legal colour in the given bank (same one the SVG candy set used).
"""
import os, re, sys, argparse
import numpy as np
from PIL import Image, ImageDraw
import quant

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f"{HERE}/out"; os.makedirs(OUT, exist_ok=True)
KEY = (255, 0, 255)

def load_palette(spec):
    """hex file (one #rrggbb per line) or an indexed PNG -> Nx3 uint8, snapped to BGR555."""
    if spec.lower().endswith(".png"):
        p = Image.open(spec).getpalette()[:48]
        cols = [tuple(p[i:i+3]) for i in range(0, 48, 3)][1:]
    else:
        cols = [tuple(int(h.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
                for h in open(spec).read().split() if h.strip()]
    return quant.snap555(np.array(cols, np.uint8))

def strip_bg(img, thresh):
    """flood-fill the solid background from the 4 corners -> alpha. Keeps same-colour regions INSIDE
    the sprite (they aren't connected to a corner)."""
    rgb = img.convert("RGB")
    for c in [(0, 0), (rgb.width-1, 0), (0, rgb.height-1), (rgb.width-1, rgb.height-1)]:
        ImageDraw.floodfill(rgb, c, KEY, thresh=thresh)
    a = np.array(rgb); mask = ~np.all(a == KEY, axis=-1)
    out = np.dstack([a, np.where(mask, 255, 0).astype(np.uint8)])
    return Image.fromarray(out, "RGBA")

def crop_square(img, margin=0.06):
    a = np.array(img); ys, xs = np.where(a[..., 3] >= quant.A_OPAQUE)
    if len(xs) == 0: return img
    x0, x1, y0, y1 = xs.min(), xs.max()+1, ys.min(), ys.max()+1
    sub = img.crop((x0, y0, x1, y1))
    s = int(max(sub.width, sub.height) * (1 + 2*margin))
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.alpha_composite(sub, ((s-sub.width)//2, (s-sub.height)//2))
    return sq

def crop_fit(img, tw, th, margin=0.03):
    """crop to the sprite, then pad to the target aspect (tw:th) so nothing is squashed."""
    a = np.array(img); ys, xs = np.where(a[..., 3] >= quant.A_OPAQUE)
    if len(xs) == 0: return img.resize((tw, th))
    sub = img.crop((xs.min(), ys.min(), xs.max()+1, ys.max()+1))
    m = 1 + 2*margin
    cw, ch = sub.width*m, sub.height*m
    if cw/ch < tw/th: cw = ch*tw/th          # letterbox to the target aspect
    else: ch = cw*th/tw
    box = Image.new("RGBA", (int(cw), int(ch)), (0, 0, 0, 0))
    box.alpha_composite(sub, ((box.width-sub.width)//2, (box.height-sub.height)//2))
    return box

def ds_modal_rect(src, tw, th):
    a = np.array(src.convert("RGBA")); H, W = a.shape[:2]; sx = max(1, W//tw); sy = max(1, H//th)
    out = np.zeros((th, tw, 4), np.uint8)
    for y in range(th):
        for x in range(tw):
            blk = a[y*sy:(y+1)*sy, x*sx:(x+1)*sx].reshape(-1, 4); op = blk[blk[:, 3] >= quant.A_OPAQUE]
            if len(op) < sy*sx*0.34: continue
            cols, cnt = np.unique(op[:, :3], axis=0, return_counts=True); out[y, x, :3] = cols[cnt.argmax()]; out[y, x, 3] = 255
    return Image.fromarray(out, "RGBA")

def process_rect(path, tw, th, kind="spr", colors=15):
    """general W×H processor: bg = full frame; sprite = strip → crop-to-aspect → modal → quantise."""
    r = Image.open(path).convert("RGBA")
    if kind == "bg":
        a = np.array(r); a[..., 3] = 255; small = ds_modal_rect(Image.fromarray(a, "RGBA"), tw, th)
    else:
        small = ds_modal_rect(crop_fit(strip_bg(r, 40), tw, th), tw, th)
    a = np.array(small); m = a[..., 3] >= quant.A_OPAQUE; px = a[..., :3][m]
    if not len(px): return small
    pal = quant.snap555(quant.cr_oklab(px, colors))
    return quant.remap_to(small, pal)

def preview(img, out, scale):
    big = img.resize((img.width*scale, img.height*scale), Image.NEAREST)
    bg = Image.new("RGBA", big.size, (0, 0, 0, 0)); bp = bg.load()
    for y in range(big.height):
        for x in range(big.width):
            bp[x, y] = (60, 60, 70, 255) if ((x//scale + y//scale) % 2 == 0) else (44, 44, 54, 255)
    Image.alpha_composite(bg, big).save(out)

def run(path, size, method, palette, bg_thresh, do_crop, bg_tile=False):
    raster = Image.open(path).convert("RGBA")
    if bg_tile:                                            # background tile: keep the whole frame, opaque
        a = np.array(raster); a[..., 3] = 255; sprite = Image.fromarray(a, "RGBA")
    else:
        sprite = strip_bg(raster, bg_thresh)
        if do_crop: sprite = crop_square(sprite)
    if palette is not None:
        small = quant.DOWNSAMPLE[quant.METHODS[method][0]](sprite, size)   # downsample only
        tgt = quant.remap_to(small, palette); used = palette
    else:
        tgt, used = quant.to_target(sprite, size, method)
    slug = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(path))[0].lower())[:24].strip("_")
    tgt.save(f"{OUT}/{slug}_{size}_raw.png")
    preview(tgt, f"{OUT}/{slug}_{size}.png", 256//size)
    a = np.array(tgt); op = a[..., 3] >= quant.A_OPAQUE
    ncol = len(set(map(tuple, a[..., :3][op])))
    print(f"  {slug}: {raster.size}->{size}x{size}  opaque={op.mean():.2f}  colours={ncol}"
          f"{'  (locked '+str(len(used))+')' if palette is not None else ''}  -> {slug}_{size}.png")
    return tgt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("raster")
    ap.add_argument("--size", type=int, default=16)
    ap.add_argument("--method", default="modal_oklab", choices=list(quant.METHODS))
    ap.add_argument("--palette", help="hex file or indexed PNG -> HARD palette lock")
    ap.add_argument("--bg-thresh", dest="bg_thresh", type=int, default=40, help="flood-fill bg tolerance")
    ap.add_argument("--no-crop", dest="crop", action="store_false")
    ap.add_argument("--bg", dest="bg_tile", action="store_true", help="background tile: keep whole frame, no strip/crop")
    a = ap.parse_args()
    pal = load_palette(a.palette) if a.palette else None
    run(a.raster, a.size, a.method, pal, a.bg_thresh, a.crop, a.bg_tile)
