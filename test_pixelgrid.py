#!/usr/bin/env python3
"""Evidence for pixelgrid.py: can it recover the true grid from a fake-pixel-art render, and can it
tell a grid from something that merely looks arty? No GPU, no server -- synthetic renders only.

    python3 test_pixelgrid.py

THE FIXTURE IS THE EXPERIMENT. An earlier version of this used scattered random rectangles, which is
not what pixel art looks like, and it produced a materially wrong conclusion: the grid gate appeared
useless (sprites 0.55-1.3 vs controls 0.47-0.67, overlapping). Real pixel art is ONE connected
silhouette filling much of the frame, with a hard 1px ink outline and large flat interior shading
regions. Swap that in and the same gate separates cleanly (sprites 2.2-8.2), because the outline is a
high-contrast edge running along cell boundaries for long unbroken stretches -- the single richest
source of periodic evidence in the frame, and the thing confetti has none of.

The scattered fixture was not merely less realistic. It was WRONG IN BOTH DIRECTIONS at once: it
over-supplied boundary evidence (every cell edge carried a colour change, which real sprites' flat
bodies do not) while under-supplying the outline. So it made pitch recovery look easy and the gate
look impossible, and both readings were artefacts.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import pixelgrid as PG

MAG = (255, 0, 255)


# ---------- fixtures ----------
def sprite_like(n, seed=0, fill=0.78, ncol=8, outline=True):
    """One connected silhouette + 1px outline + flat shading regions + a few details, limited palette."""
    r = np.random.default_rng(seed)
    im = Image.new("RGB", (n, n), MAG); d = ImageDraw.Draw(im)
    base = tuple(int(v) for v in r.integers(70, 210, 3))
    dark = tuple(max(0, int(c * 0.55)) for c in base)
    lite = tuple(min(255, int(c * 1.35)) for c in base)
    ink = tuple(max(0, int(c * 0.25)) for c in base)
    m = n * (1 - fill) / 2

    d.rounded_rectangle([m + n*0.18, m + n*0.30, n - m - n*0.18, n - m], radius=max(1, n//12), fill=base)
    d.ellipse([m + n*0.10, m, n - m - n*0.10, m + n*0.42], fill=base)
    d.rectangle([m, m + n*0.36, m + n*0.20, m + n*0.66], fill=base)
    d.rectangle([n - m - n*0.20, m + n*0.36, n - m, m + n*0.66], fill=base)
    d.pieslice([m + n*0.10, m, n - m - n*0.10, m + n*0.42], 20, 160, fill=dark)
    d.rectangle([m + n*0.18, n - m - n*0.22, n - m - n*0.18, n - m], fill=dark)
    d.rectangle([m + n*0.18, m + n*0.30, m + n*0.34, n - m - n*0.22], fill=lite)
    for _ in range(int(r.integers(3, 6))):
        x, y = r.integers(int(n*0.25), int(n*0.72), 2); s = max(1, n // 16)
        d.rectangle([x, y, x + s, y + s], fill=tuple(int(v) for v in r.integers(0, 255, 3)))

    if outline:
        a = np.array(im); solid = np.abs(a.astype(int) - np.array(MAG)).max(2) > 20
        edge = solid & ~(np.roll(solid, 1, 0) & np.roll(solid, -1, 0) &
                         np.roll(solid, 1, 1) & np.roll(solid, -1, 1))
        a[edge] = ink; im = Image.fromarray(a, "RGB")

    q = np.array(im.quantize(colors=ncol, method=Image.MEDIANCUT).convert("RGB"))
    q[np.abs(np.array(im).astype(int) - np.array(MAG)).max(2) <= 20] = MAG
    return Image.fromarray(q, "RGB")


def render(sm, px=1024, blur=1.6, noise=5.0, shift=(0, 0), seed=0):
    """What a diffusion model hands you: the logical art, upscaled, anti-aliased, noisy, off-phase."""
    r = np.random.default_rng(seed)
    big = Image.fromarray(np.array(sm), "RGB").resize((px, px), Image.NEAREST) \
                                              .filter(ImageFilter.GaussianBlur(blur))
    v = np.clip(np.array(big).astype(float) + r.normal(0, noise, (px, px, 3)), 0, 255).astype(np.uint8)
    return Image.fromarray(np.roll(v, shift, axis=(0, 1)), "RGB")


def gradient(px=1024):
    x = np.linspace(0, 255, px); a = np.stack(np.meshgrid(x, x), -1)
    return Image.fromarray(np.dstack([a[..., 0], a[..., 1], a.sum(2) / 2]).astype(np.uint8), "RGB")


def blobs(px=1024, seed=3):
    r = np.random.default_rng(seed); im = Image.new("RGB", (px, px), (30, 40, 60)); d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y, s = r.integers(0, px, 3)
        d.ellipse([x, y, x + s//3, y + s//3], fill=tuple(int(v) for v in r.integers(0, 255, 3)))
    return im.filter(ImageFilter.GaussianBlur(6))


def blurred_noise(px=1024, seed=4):
    r = np.random.default_rng(seed)
    return Image.fromarray(r.integers(0, 255, (px, px, 3)).astype(np.uint8), "RGB") \
                .filter(ImageFilter.GaussianBlur(9))


# ---------- suites ----------
def t_pitch():
    print("== A. pitch recovery ==")
    rows = []
    for n in (16, 24, 32, 48, 64):
        for px, blur in ((1024, 1.5), (1024, 3.0), (896, 1.5), (700, 1.2)):
            for seed in (1, 2, 3):
                d = PG.detect_grid(render(sprite_like(n, seed=seed), px, blur=blur, seed=seed))
                rows.append((n, d["n"] == n, d["n"]))
    for n in (16, 24, 32, 48, 64):
        sub = [r for r in rows if r[0] == n]
        print(f"  n={n:<3} {sum(r[1] for r in sub):>2}/{len(sub)}   saw {sorted({r[2] for r in sub})}")
    tot = sum(r[1] for r in rows)
    print(f"  TOTAL {tot}/{len(rows)}")
    return tot == len(rows)


def t_phase():
    print("\n== B. phase robustness (n=64, sub-cell shifts) ==")
    ok = True
    for sh in (0, 3, 7, -5, 11):
        d = PG.detect_grid(render(sprite_like(64, seed=1), 1024, shift=(sh, sh), seed=1))
        ok &= d["n"] == 64
        print(f"  shift {sh:>3}px -> n={d['n']:<4} ox={d['ox']:.0f} oy={d['oy']:.0f}  score {d['score']:.2f}")
    return ok


def t_reconstruct():
    print("\n== C. reconstruction (forced-n path: detected phase, asked-for n) ==")
    ok = True
    for n in (16, 32, 64):
        for blur, noise in ((1.0, 3), (2.0, 6), (3.5, 10)):
            truth = np.array(sprite_like(n, seed=4))
            img = render(sprite_like(n, seed=4), 1024, blur=blur, noise=noise, seed=4)
            d = PG.detect_grid(img)
            rec = np.array(PG.snap_grid(img, n, d["ox"], d["oy"]))
            hit = (np.abs(rec.astype(int) - truth.astype(int)).max(2) <= 8).mean()
            ok &= hit > 0.75
            print(f"  n={n:<3} blur={blur} noise={noise:<3} cells within 8/255: {hit*100:5.1f}%")
    return ok


def t_keying():
    print("\n== D. background keying ==")
    n = 32
    truth = np.array(sprite_like(n, seed=5))
    d = PG.detect_grid(render(sprite_like(n, seed=5), 1024, seed=5))
    rgba = np.array(PG.key_bg(PG.snap_grid(render(sprite_like(n, seed=5), 1024, seed=5),
                                           n, d["ox"], d["oy"])))
    is_bg = np.abs(truth.astype(int) - np.array(MAG)).max(2) <= 20
    cleared = rgba[..., 3] == 0
    print(f"  background cells cleared {(cleared & is_bg).sum()}/{is_bg.sum()}"
          f"   sprite cells wrongly cleared {(cleared & ~is_bg).sum()}")
    # an interior region sharing the key colour must SURVIVE -- the point of flooding from the border
    t2 = sprite_like(n, seed=5); a2 = np.array(t2); a2[n//2:n//2+3, n//2:n//2+3] = MAG
    d2 = PG.detect_grid(render(Image.fromarray(a2, "RGB"), 1024, seed=5))
    r2 = np.array(PG.key_bg(PG.snap_grid(render(Image.fromarray(a2, "RGB"), 1024, seed=5),
                                         n, d2["ox"], d2["oy"])))
    kept = (r2[n//2:n//2+3, n//2:n//2+3, 3] == 255).mean()
    print(f"  interior key-coloured patch kept opaque: {kept*100:.0f}%")
    return (cleared & is_bg).sum() >= is_bg.sum() * 0.95 and kept > 0.5


def t_gate():
    print("\n== E. gate separation ==")
    sp = [PG.detect_grid(render(sprite_like(n, seed=s), 1024, seed=s))["score"]
          for n in (16, 32, 64) for s in (1, 2, 3, 4)]
    ctl = [(name, PG.detect_grid(im)["score"]) for name, im in
           (("smooth gradient", gradient()), ("soft blobs", blobs()), ("blurred noise", blurred_noise()))]
    print(f"  sprite-like : {min(sp):.2f} .. {max(sp):.2f}  (median {np.median(sp):.2f}, n={len(sp)})")
    for name, s in ctl:
        print(f"  control {name:<16}: {s:.2f}")
    keep = sum(s >= 1.0 for s in sp)
    print(f"  min_score=1.0 -> keeps {keep}/{len(sp)} sprites, rejects "
          f"{sum(s < 1.0 for _, s in ctl)}/{len(ctl)} controls")
    return keep == len(sp) and all(s < 1.0 for _, s in ctl)


if __name__ == "__main__":
    res = [("pitch", t_pitch()), ("phase", t_phase()), ("reconstruct", t_reconstruct()),
           ("keying", t_keying()), ("gate", t_gate())]
    print("\n" + "  ".join(f"{k}:{'PASS' if v else 'FAIL'}" for k, v in res))
    raise SystemExit(0 if all(v for _, v in res) else 1)
