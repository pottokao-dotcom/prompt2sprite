#!/usr/bin/env python3
"""quant — pluggable quantisation registry for the SNES pixel-art pipeline.

The downscale+colour-reduce step is an OPEN SLOT: a method = (downsampler x colour-reducer),
each registered by name, one picked as DEFAULT. Add a new idea = add one entry; nothing else moves.

Two levels of the SNES palette constraint are modelled:
  per-asset  -> <=15 colours + index0 transparent, snapped to BGR555 (5-bit/chan).
  whole-game -> shared master palette across ALL assets (8 sprite banks x 16 = 128 CGRAM),
                so every sprite draws from the same golds/reds -> hardware-legal AND consistent.

Division of labour: the LLM chooses shapes+colours (SVG fills = a semantic palette); PY does the
geometry-preserving downsample, perceptual colour maths (OKLab), and the BGR555 snap. The model is
never asked to do pixel remap maths or emit raw grids (its dead representation).
"""
import numpy as np
from PIL import Image

A_OPAQUE = 110   # alpha >= this = opaque; below = transparent (index 0)

# ---------- colour maths ----------
def _srgb_lin(c):
    return np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)

def srgb_to_oklab(rgb):
    """rgb uint8 (...,3) -> OKLab float (...,3). Perceptual space: Euclidean distance ~ human diff."""
    c = _srgb_lin(rgb.astype(np.float64)/255.0)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    l = 0.4122214708*r + 0.5363325363*g + 0.0514459929*b
    m = 0.2119034982*r + 0.6806995451*g + 0.1073969566*b
    s = 0.0883024619*r + 0.2817188376*g + 0.6299787005*b
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([
        0.2104542553*l_ + 0.7936177850*m_ - 0.0040720468*s_,
        1.9779984951*l_ - 2.4285922050*m_ + 0.4505937099*s_,
        0.0259040371*l_ + 0.7827717662*m_ - 0.8086757660*s_], axis=-1)

def snap555(rgb):
    """uint8 -> nearest BGR555-legal colour (5 bits/channel, expanded back to 8-bit for preview)."""
    q = (rgb.astype(np.int32) >> 3)
    return ((q << 3) | (q >> 2)).clip(0, 255).astype(np.uint8)

def _nearest(px, pal):
    """index of nearest pal colour for each px, in OKLab."""
    lp, lc = srgb_to_oklab(px), srgb_to_oklab(pal)
    return (((lp[:, None, :] - lc[None, :, :])**2).sum(2)).argmin(1)

# ---------- downsamplers (src RGBA at draw_px -> RGBA at size) ----------
def ds_modal(src, size):
    """majority colour per scale x scale block; keeps DISCRETE flat fills crisp (no blended edges)."""
    a = np.array(src.convert("RGBA")); H = a.shape[0]; s = max(1, H//size)
    out = np.zeros((size, size, 4), np.uint8)
    for y in range(size):
        for x in range(size):
            blk = a[y*s:(y+1)*s, x*s:(x+1)*s].reshape(-1, 4)
            op = blk[blk[:, 3] >= A_OPAQUE]
            if len(op) < s*s*0.34: continue                     # mostly transparent -> stay transparent
            cols, cnt = np.unique(op[:, :3], axis=0, return_counts=True)
            out[y, x, :3] = cols[cnt.argmax()]; out[y, x, 3] = 255
    return Image.fromarray(out, "RGBA")

def _pil_ds(src, size, flt):
    im = src.convert("RGBA").resize((size, size), flt); a = np.array(im)
    a[..., 3] = np.where(a[..., 3] >= A_OPAQUE, 255, 0)
    return Image.fromarray(a, "RGBA")
def ds_box(src, size):     return _pil_ds(src, size, Image.BOX)       # area-average: for gradients/FX
def ds_lanczos(src, size): return _pil_ds(src, size, Image.LANCZOS)  # blends: baseline, muddies flats
def ds_nearest(src, size): return _pil_ds(src, size, Image.NEAREST)

DOWNSAMPLE = {"modal": ds_modal, "box": ds_box, "lanczos": ds_lanczos, "nearest": ds_nearest}

# ---------- colour reducers (opaque px Nx3 uint8 -> palette Mx3 uint8, M<=n) ----------
def cr_mediancut(px, n):
    im = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8), "RGB").quantize(colors=n, method=Image.MEDIANCUT)
    return np.array(im.getpalette()[:n*3]).reshape(-1, 3)[:n].astype(np.uint8)

def cr_keep(px, n):
    """keep the n most frequent discrete colours (the model's own SVG fills); rare AA px remap to these."""
    cols, cnt = np.unique(px, axis=0, return_counts=True)
    return cols[cnt.argsort()[::-1][:n]].astype(np.uint8)

def cr_oklab(px, n, iters=14):
    """k-means in OKLab (farthest-point init). Palette colour = sRGB mean of each cluster."""
    uniq = np.unique(px, axis=0)
    if len(uniq) <= n: return uniq.astype(np.uint8)
    lab = srgb_to_oklab(px); ul = srgb_to_oklab(uniq)
    cent = [0]; d = np.full(len(ul), np.inf)
    for _ in range(n-1):
        d = np.minimum(d, ((ul - ul[cent[-1]])**2).sum(1)); cent.append(int(d.argmax()))
    C = ul[cent].copy()
    for _ in range(iters):
        a = (((lab[:, None, :] - C[None, :, :])**2).sum(2)).argmin(1)
        newC = np.array([lab[a == k].mean(0) if (a == k).any() else C[k] for k in range(n)])
        if np.allclose(newC, C): break
        C = newC
    a = (((lab[:, None, :] - C[None, :, :])**2).sum(2)).argmin(1)
    return np.array([px[a == k].mean(0).round() if (a == k).any() else [0, 0, 0]
                     for k in range(n)]).astype(np.uint8)

REDUCE = {"mediancut": cr_mediancut, "keep": cr_keep, "oklab": cr_oklab}

# ---------- method registry: name -> (downsampler, reducer, note) ----------
METHODS = {
    "lanczos_mc":  ("lanczos", "mediancut", "OLD baseline: blends edges then median-cut, muddies flats"),
    "modal_mc":    ("modal",   "mediancut", "majority block downscale + median-cut"),
    "modal_oklab": ("modal",   "oklab",     "majority + perceptual k-means (DEFAULT, best flat all-rounder)"),
    "modal_keep":  ("modal",   "keep",      "majority + keep model's own discrete fills (crispest flat)"),
    "box_oklab":   ("box",     "oklab",     "area-average + perceptual (shaded / gradient FX)"),
}
DEFAULT = "modal_oklab"

def _apply_palette(small, pal):
    a = np.array(small); mask = a[..., 3] >= A_OPAQUE
    px = a[..., :3][mask]
    out = np.zeros_like(a)
    if len(px):
        out[..., :3][mask] = pal[_nearest(px, pal)]; out[..., 3][mask] = 255
    return Image.fromarray(out, "RGBA")

def to_target(src, size, method=DEFAULT, colors=15):
    """draw-4x RGBA -> SNES-legal target RGBA (<=colors + transparent, BGR555). Returns (img, palette)."""
    ds, cr, _ = METHODS[method]
    small = DOWNSAMPLE[ds](src, size)
    a = np.array(small); px = a[..., :3][a[..., 3] >= A_OPAQUE]
    if len(px) == 0: return small, []
    pal = snap555(REDUCE[cr](px, colors))
    return _apply_palette(small, pal), [tuple(int(v) for v in c) for c in pal]

# ---------- whole-game constraint: shared master palette across assets ----------
def shared_palette(smalls, colors=15):
    """pool opaque px of many downsampled assets -> one master palette (one CGRAM bank)."""
    pool = np.concatenate([np.array(s)[..., :3][np.array(s)[..., 3] >= A_OPAQUE] for s in smalls], 0)
    return snap555(cr_oklab(pool, colors))

def remap_to(small, pal):
    return _apply_palette(small, pal)
