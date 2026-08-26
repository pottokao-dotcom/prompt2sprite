#!/usr/bin/env python3
"""pixelgrid — recover a TRUE logical pixel grid from a big "fake pixel art" render.

Why this exists. `quant.py` assumes its input is already on an aligned integer grid — which holds for
a cairosvg raster of an LLM's SVG (we chose the viewBox), but NOT for a general image model. A 9B
diffusion model asked for "64x64 pixel art" emits a 1024px picture whose cells are ~15.7px, drift out
of phase across the frame, carry anti-aliased edges and low-amplitude noise. Feeding that straight
into `quant.ds_modal` (which slices fixed W//size blocks from x=0) smears every cell boundary and the
whole colour pipeline is wasted.

So the front-end is an OPEN SLOT, exactly like quant's method registry: SVG raster is one source,
a diffusion render is another. This module is the adapter that makes the second one legal:

    render (1024px RGB, fake grid)  ->  detect_grid  ->  snap_grid  ->  key_bg  ->  n x n RGBA
                                                                                      |
                                                             then the unchanged quant.to_target()

Order matters: snap FIRST, key SECOND. Keying on the 1024px render means a million-pixel flood fill
and AA fringe votes; keying on the n x n snap is 4096 flat cells and the fringe is already gone.
"""
import numpy as np
from PIL import Image

import quant

# Logical grid sizes worth testing. Sprite work lives in 16..128; the scan is continuous but these
# get a small tie-break bonus because a model told "64x64" usually lands on or near a round number.
NICE = (16, 24, 32, 48, 64, 96, 128)
SCAN = range(8, 161)


# ---------- edge energy ----------
def _edge_profiles(a):
    """RGB uint8 HxWx3 -> (col, row) 1-D EXCESS edge energy. col[i] = strength of the vertical edge
    lying between source columns i and i+1 (i.e. at real x-coordinate i+1); row likewise for y.

    The median subtraction is not cosmetic — without it the scan degenerates. Render noise of sigma s
    contributes |diff| ~ 1.1*s at EVERY index, and taking the mean of absolute values down a column
    never cancels it, so the profile sits on a flat pedestal. On a 1024px render of a 16-cell sprite
    there are only 15 real boundaries: the pedestal then carries ~90% of the total energy, `recall`
    measures mostly pedestal, and score becomes a monotone function of coverage — i.e. "the finest
    grid always wins". Subtracting the median (a robust estimate of that pedestal, since most of the
    profile IS flat interior) leaves only what the drawing actually put there.
    """
    g = a.astype(np.float64).mean(2)
    col = np.abs(np.diff(g, axis=1)).mean(0)   # len W-1
    row = np.abs(np.diff(g, axis=0)).mean(1)   # len H-1
    return (np.clip(col - np.median(col), 0, None),
            np.clip(row - np.median(row), 0, None))


def _score_pitch(e, span, n, phase):
    """How well does a grid of n cells across `span` px, offset by `phase`, explain edge energy `e`?

    ENERGY CONCENTRATION: how much of the profile's edge energy the grid captures, per unit of profile
    it had to claim to capture it.

        recall   = share of ALL edge energy lying on a predicted boundary   ("did I find every line?")
        coverage = share of the profile those boundaries occupy             ("how much did I claim?")
        score    = recall^2 / coverage        (== precision * recall, with precision = recall/coverage)

    Both halves are load-bearing, and each kills one failure mode. A sub-harmonic (n=32 when the truth
    is 64) claims very little and every line it predicts is real, but it captures only half the edge
    energy — recall^2 quarters it. A super-harmonic (n=128) captures everything, but claims twice the
    profile to do it — coverage halves it. Only the true pitch is both complete and cheap.

    Two earlier formulations failed here, both for accounting reasons worth remembering:
      - mean(at) - mean(away): at small n the 'away' set is overwhelmingly flat cell interior, so the
        skipped real boundaries sitting in it barely moved the mean, and sub-harmonics won.
      - summing a per-boundary local MAX: adjacent slack windows both claim the same peak, so 'captured'
        energy could exceed the total and recall saturated at 1 for every large n.
    Hence the mask below is deduplicated and the energy under it counted exactly once.
    """
    cell = span / n
    if cell < 3.0:                       # below ~3 px/cell there is no grid left to resolve
        return -np.inf
    slack = 1 if cell >= 6 else 0        # AA lets the true edge sit a px off; at tiny cells it can't
    b = np.rint(phase + cell * np.arange(1, n)) - 1     # diff-index of each interior boundary
    b = b[(b >= 0) & (b < len(e))].astype(int)
    if len(b) < 3:
        return -np.inf

    mask = np.zeros(len(e), bool)
    for d in range(-slack, slack + 1):
        mask[np.clip(b + d, 0, len(e) - 1)] = True
    tot = e.sum()
    if tot <= 0:
        return -np.inf
    recall = e[mask].sum() / tot
    coverage = mask.sum() / len(e)
    return float(recall * recall / max(coverage, 1e-9))


def detect_grid(img, scan=SCAN, phases=8):
    """Find the logical cell count of a fake-pixel-art render.

    Returns dict(n, nx, ny, ox, oy, score). `n` is the square answer actually used downstream; nx/ny
    are the independent per-axis winners and are worth eyeballing — if they disagree wildly the render
    probably isn't on a grid at all (see `looks_gridded`).
    """
    a = np.array(img.convert("RGB"))
    H, W = a.shape[:2]
    col, row = _edge_profiles(a)

    def best_axis(e, span):
        out = []
        for n in scan:
            cell = span / n
            ph = np.linspace(0, cell, phases, endpoint=False)
            s, p = max(((_score_pitch(e, span, n, q), q) for q in ph), key=lambda t: t[0])
            if np.isfinite(s):
                out.append((s * (1.03 if n in NICE else 1.0), s, n, p))
        if not out:
            return 0, 0.0, 0.0
        _, s, n, p = max(out, key=lambda t: t[0])
        return n, s, p

    nx, sx, ox = best_axis(col, W)
    ny, sy, oy = best_axis(row, H)
    n = nx if sx >= sy else ny                  # square sprites: trust the better-resolved axis
    return {"n": n, "nx": nx, "ny": ny, "ox": ox, "oy": oy, "score": (sx + sy) / 2,
            "contrast": float(max(col.max(), row.max()))}


def looks_gridded(det, min_score=1.0, max_axis_ratio=1.25):
    """WEAK heuristic: does this render look like it is on a pixel grid at all?

    Treat the boolean as a hint and the numbers in `det` as the real output. This separates a grid
    from a smooth render, and it does NOT reliably separate a simple flat sprite from soft blobby art:
    measured on synthetic cases, sprites score 0.55-1.3 while non-grid controls score 0.47-0.67, and
    those ranges overlap. Three other statistics were tried and are worse, each defeated by a
    different control -- cell flatness (a smooth gradient is the flattest thing there is, 0.996),
    the between/within-cell variance ratio (same gradient, highest score of everything at 37000),
    and absolute hard-edge contrast (averaging |diff| down 1024 rows dilutes a real edge that only
    30% of rows cross, to below a blurred blob's). Deciding this properly is a classifier, not a
    threshold, and it is not what this module is for.

    What it IS safe for: rejecting obviously-smooth output, and flagging samples for review in bulk
    generation. `min_score` is uncalibrated -- it comes from synthetic renders, not from Klein. Run a
    few hundred real ones, look at `score`/`contrast`/`nx` vs `ny` in the saved metadata, and set your
    own threshold before trusting this to throw anything away.
    """
    if det["n"] <= 0 or det["score"] < min_score:
        return False
    lo, hi = sorted((det["nx"], det["ny"]))
    return hi <= lo * max_axis_ratio if lo else False


# ---------- resample onto the recovered grid ----------
def snap_grid(img, n, ox=0.0, oy=0.0, inset=0.28, bits=5):
    """Resample to exactly n x n by taking one representative colour per (float-sized) cell.

    `inset` throws away the outer 28% of every cell before voting — that ring is where the model's
    anti-aliasing lives, and it is pure poison to a modal vote. `bits` bins colours before the vote so
    "the same flat colour plus render noise" counts as one candidate; the emitted colour is then the
    mean of the winning bin's ACTUAL pixels (same trick as quant.cr_oklab: vote in a coarse space,
    report in a fine one).
    """
    a = np.array(img.convert("RGB")).astype(np.int32)
    H, W = a.shape[:2]
    cw, ch = (W - ox) / n, (H - oy) / n
    out = np.zeros((n, n, 3), np.uint8)
    sh = 8 - bits
    for j in range(n):
        y0 = int(round(oy + (j + inset) * ch)); y1 = int(round(oy + (j + 1 - inset) * ch))
        y0, y1 = max(0, y0), max(1, min(H, y1))
        if y1 <= y0: y1 = min(H, y0 + 1)
        for i in range(n):
            x0 = int(round(ox + (i + inset) * cw)); x1 = int(round(ox + (i + 1 - inset) * cw))
            x0, x1 = max(0, x0), max(1, min(W, x1))
            if x1 <= x0: x1 = min(W, x0 + 1)
            blk = a[y0:y1, x0:x1].reshape(-1, 3)
            key = (blk >> sh)
            key1 = (key[:, 0] << (2 * bits)) | (key[:, 1] << bits) | key[:, 2]
            vals, cnt = np.unique(key1, return_counts=True)
            out[j, i] = blk[key1 == vals[cnt.argmax()]].mean(0).round()
    return Image.fromarray(out, "RGB")


# ---------- background -> alpha ----------
def key_bg(small, tol=0.10, corners_only=True):
    """Flood the background in from the border and make it transparent.

    A diffusion model cannot emit alpha, so the sprite arrives pasted on some flat field. A plain
    colour-equality key would also punch holes in any interior region that happens to share that
    colour (a blue robot on a blue field loses its chest); flooding from the border only removes the
    field that is actually connected to the outside. Distance is OKLab, so `tol` means the same thing
    across hues — reusing quant's colour maths rather than a second, inconsistent one.
    """
    a = np.array(small.convert("RGB"))
    n_h, n_w = a.shape[:2]
    lab = quant.srgb_to_oklab(a.reshape(-1, 3)).reshape(n_h, n_w, 3)

    border = [(0, x) for x in range(n_w)] + [(n_h - 1, x) for x in range(n_w)] + \
             [(y, 0) for y in range(n_h)] + [(y, n_w - 1) for y in range(n_h)]
    seeds = [(0, 0), (0, n_w - 1), (n_h - 1, 0), (n_h - 1, n_w - 1)] if corners_only else border
    cols, cnt = np.unique(np.array([a[y, x] for y, x in seeds]), axis=0, return_counts=True)
    bgc = quant.srgb_to_oklab(cols[cnt.argmax()][None, :])[0]

    similar = np.sqrt(((lab - bgc) ** 2).sum(2)) <= tol
    out = np.dstack([a, np.full((n_h, n_w), 255, np.uint8)])
    stack = [(y, x) for y, x in border if similar[y, x]]
    seen = np.zeros((n_h, n_w), bool)
    for y, x in stack:
        seen[y, x] = True
    while stack:                                    # n x n is only a few thousand cells: plain BFS
        y, x = stack.pop()
        out[y, x, 3] = 0
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < n_h and 0 <= nx < n_w and not seen[ny, nx] and similar[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return Image.fromarray(out, "RGBA")


def to_logical(img, n=None, tol=0.10, inset=0.28):
    """Full adapter: big fake-pixel render -> n x n RGBA on a true grid, ready for quant.to_target().

    Returns (rgba, detection). Pass `n` to skip detection when you already know what you asked for —
    but prefer detecting, because what the model *drew* and what you *asked for* routinely differ.
    """
    det = detect_grid(img)
    if n is None:
        n = det["n"]
    return key_bg(snap_grid(img, n, det["ox"], det["oy"], inset), tol), det
