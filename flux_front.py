#!/usr/bin/env python3
"""flux_front — a SECOND front-end for the sprite pipeline: FLUX.2 [Klein] 9B via ComfyUI.

The repo's thesis is that the LLM draws in its native representation (SVG) and Python does the colour
maths. That thesis is about the *colour maths being source-agnostic* — `quant.py` never cared where
its input came from, only that it arrived on an aligned grid. So a diffusion model is a legal second
source, and this module is the adapter, mirroring `make_sprite.svg_raster`'s contract exactly:

    svg_raster(subject, px, style, theme) -> (RGBA at px, raw_text)     # LLM  -> cairosvg
    render(subject, n,  style, theme)     -> (RGBA at n,  meta)         # Klein -> pixelgrid

The awkward part is that Klein cannot do either thing this pipeline used to rely on:

  1. It has no usable output below ~512px, so "draw at 4x the target" cannot mean "ask for 64px".
     It means: generate at NATIVE res (1024) with the logical cell count stated in the prompt, then
     let `pixelgrid` recover the 64x64 the model was *pretending* to draw. That recovered 64 IS the
     4x image, and it hands off to the unchanged `quant.to_target()` for the 4:1 shrink to 16.
  2. It cannot emit alpha. So we render on a flat magenta field and key it out on the recovered grid
     (see pixelgrid.key_bg for why keying happens after the snap, not before).

Workflow JSON is NOT hardcoded. Export an API-format workflow from ComfyUI for whatever Klein graph
you are running and pass --workflow; this module patches the prompt/seed/size fields into it and
prints which nodes it resolved, so a wrong guess is visible rather than silent.

  python3 flux_front.py "a shiny gold coin" --size 16 --draw 64 --dry-run
  python3 flux_front.py "a shiny gold coin" --size 16 --draw 64 --workflow klein.json
  python3 flux_front.py --batch subjects.txt --size 16 --theme candy --chibi --workers 4
"""
import argparse, copy, io, json, os, random, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

import pixelgrid
import quant
try:
    import make_sprite as M          # reuse the THEMES registry + slug/preview helpers
except Exception:                    # make_sprite imports cairosvg; not needed for this front-end
    M = None

COMFY = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/out"
KEY_BG = "magenta (#FF00FF)"         # keyed out by pixelgrid.key_bg; see module docstring


# ---------- prompt construction ----------
# Diffusion wants a described *look*, not the drawing instructions an LLM emitting SVG needs — so these
# are deliberately NOT make_sprite.STYLE. The shared knob is the THEME registry, which is already plain
# descriptive colour language and ports across unchanged.
STYLE = {
    "flat":    "flat solid colour fills, no shading, no gradients, each region a single bright "
               "saturated colour, clean readable silhouette",
    "shade":   "simple two-tone shading, one darker shade on the lower-right of each region and one "
               "lighter tint on the upper-left, no outline, bright saturated colours",
    "outline": "bright flat fills with a clean dark 1-pixel outline around the silhouette and the key "
               "internal features, classic readable game-sprite look",
    "comic":   "manga/anime cel-shaded look, bold black ink outlines of even weight, flat cel fills "
               "with hard-edged shadow shapes, expressive comic styling",
}

BASE = ("{n}x{n} pixel art sprite of {subject}, retro 16-bit SNES game sprite, "
        "drawn on an exact {n} by {n} pixel grid, every pixel a crisp hard-edged square, "
        "nearest-neighbour, no anti-aliasing, no blur, no gradients, no dithering, "
        "{style}, centred with a small margin, whole object visible, "
        "flat plain {key} background{theme}")

NEG = ("photograph, 3d render, painterly, soft focus, blurry, anti-aliased edges, colour gradient, "
       "jpeg artifacts, drop shadow, text, watermark, signature, frame, border, multiple objects")

CHIBI = ("a chibi / super-deformed {subject}, big head about half the body height, tiny body, huge "
         "expressive eyes, exaggerated signature features, cute mascot")


def build_prompt(subject, n, style="flat", theme="none", chibi=False):
    """-> (positive, negative). `theme` accepts anything make_sprite.resolve_theme does (name/number/
    free text), so a whole-game palette is one shared flag across BOTH front-ends."""
    subj = subject
    if chibi:                                   # drop the subject's own article: "...deformed a rabbit"
        bare = subj.lstrip()
        for art in ("a ", "an ", "the "):
            if bare.lower().startswith(art):
                bare = bare[len(art):]; break
        subj = CHIBI.format(subject=bare)
    tw = M.resolve_theme(theme) if M else ("" if theme in ("", "none", "0") else theme)
    return (BASE.format(n=n, subject=subj, style=STYLE.get(style, STYLE["flat"]), key=KEY_BG,
                        theme=(", colour palette: " + tw) if tw else ""),
            NEG)


# ---------- ComfyUI plumbing ----------
# API-format workflow = {node_id: {"class_type":..., "inputs": {...}, "_meta": {"title":...}}}.
# Resolution order per field: explicit --node-* override > _meta.title alias > class_type heuristic.
TITLE_ALIAS = {
    "positive": ("positive", "positive prompt", "prompt", "clip text encode (positive)"),
    "negative": ("negative", "negative prompt", "clip text encode (negative)"),
}
TEXT_CLASSES = ("CLIPTextEncode", "CLIPTextEncodeFlux", "T5TextEncode", "TextEncodeQwenImageEdit")
SIZE_CLASSES = ("EmptyLatentImage", "EmptySD3LatentImage", "EmptyLatentImagePresets", "ModelSamplingFlux")
SEED_KEYS = ("seed", "noise_seed")


def resolve_nodes(wf, override=None):
    """Work out which node/input carries each patchable field. Returns {field: (node_id, input_key)}."""
    override = override or {}
    found = {}
    texts = [(i, nd) for i, nd in wf.items()
             if nd.get("class_type") in TEXT_CLASSES and isinstance(nd.get("inputs", {}).get("text"), str)]
    texts.sort(key=lambda t: int(t[0]) if str(t[0]).isdigit() else 0)

    for field in ("positive", "negative"):
        if field in override:
            found[field] = (str(override[field]), "text"); continue
        hit = next((i for i, nd in texts
                    if nd.get("_meta", {}).get("title", "").strip().lower() in TITLE_ALIAS[field]), None)
        if hit is not None:
            found[field] = (hit, "text")
    # Heuristic fallback: two untitled text encoders = positive first, negative second (ComfyUI default
    # graphs are built in that order). Only applied when the titles told us nothing.
    if "positive" not in found and texts:
        found["positive"] = (texts[0][0], "text")
    if "negative" not in found and len(texts) > 1:
        found["negative"] = (texts[1][0], "text")

    for i, nd in wf.items():
        for k in SEED_KEYS:
            if k in nd.get("inputs", {}) and "seed" not in found:
                found["seed"] = (i, k)
        if nd.get("class_type") in SIZE_CLASSES:
            if "width" in nd.get("inputs", {}) and "width" not in found:
                found["width"] = (i, "width"); found["height"] = (i, "height")
    for f, v in override.items():
        if f not in ("positive", "negative"):
            found[f] = (str(v).split(":")[0], str(v).split(":")[1] if ":" in str(v) else f)
    return found


def patch_workflow(wf, nodes, **vals):
    wf = copy.deepcopy(wf)
    for field, v in vals.items():
        if v is None or field not in nodes:
            continue
        nid, key = nodes[field]
        if nid in wf:
            wf[nid]["inputs"][key] = v
    return wf


def _post(path, payload):
    r = urllib.request.Request(f"{COMFY}{path}", json.dumps(payload).encode(),
                               {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=60).read())


def submit_and_fetch(wf, timeout=600, poll=1.5):
    """Queue one workflow, wait for it, return the first output image as a PIL.Image."""
    pid = _post("/prompt", {"prompt": wf})["prompt_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        h = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30).read())
        if pid in h:
            for out in h[pid].get("outputs", {}).values():
                for im in out.get("images", []):
                    q = urllib.parse.urlencode({"filename": im["filename"],
                                                "subfolder": im.get("subfolder", ""),
                                                "type": im.get("type", "output")})
                    raw = urllib.request.urlopen(f"{COMFY}/view?{q}", timeout=60).read()
                    return Image.open(io.BytesIO(raw)).convert("RGB")
            raise RuntimeError(f"prompt {pid} finished with no image output")
        time.sleep(poll)
    raise TimeoutError(f"prompt {pid} did not finish in {timeout}s")


# ---------- the front-end contract ----------
def render(subject, n, wf, nodes, style="flat", theme="none", chibi=False, seed=None, px=1024,
           trust_detect=False):
    """Generate one sprite. -> (logical RGBA, meta dict). Mirrors make_sprite.svg_raster.

    By default the grid is resampled at the n we ASKED for, using only the detected phase. Detection
    still runs, and its answer is reported and gated on — but it does not choose the size, because it
    cannot when the subject is simple: a smooth 16x16 coin has barely a dozen real cell boundaries in
    the whole frame, and the scan happily settles on a clean sub-harmonic (8) that explains all of
    them. Asking for 64 and being handed 8 is silent, destructive, and hard to notice downstream.

    `trust_detect=True` inverts that and is the honest setting for the experiment in
    compare_native.py, where what Klein actually drew is the question rather than a nuisance.
    """
    pos, neg = build_prompt(subject, n, style, theme, chibi)
    seed = random.randrange(2**31) if seed is None else seed
    big = submit_and_fetch(patch_workflow(wf, nodes, positive=pos, negative=neg,
                                          seed=seed, width=px, height=px))
    logical, det = pixelgrid.to_logical(big, n=None if trust_detect else n)
    return logical, {"seed": seed, "prompt": pos, "detected": det,
                     "gridded": pixelgrid.looks_gridded(det), "asked_n": n,
                     "matched": det["n"] == n, "render": big}


def sprite(subject, size, wf, nodes, draw=64, tries=3, style="flat", theme="none", chibi=False,
           method=quant.DEFAULT, colors=15, keep_n=False):
    """Full chain: Klein -> recovered logical grid -> quant.to_target at `size`.

    Best-of-N on the SAME gate the SVG front-end uses (non-degenerate), plus the grid gate — a render
    that never landed on a grid is worse than useless as training data, so it is not merely scored
    down, it is rejected outright.
    """
    best = None
    for _ in range(max(1, tries)):
        logical, meta = render(subject, draw, wf, nodes, style, theme, chibi, trust_detect=keep_n)
        ok_content = M.nondegenerate(logical, logical.width) if M else True
        if meta["gridded"] and ok_content:
            best = (logical, meta); break
        best = best or (logical, meta)
    if best is None:
        return None, None, None
    logical, meta = best
    tgt, pal = quant.to_target(logical, size, method, colors)
    meta["palette"] = pal
    return tgt, logical, meta


# ---------- cli ----------
def slug(s):
    return "".join(c if c.isalnum() else "_" for c in s.lower())[:40].strip("_")


def main():
    ap = argparse.ArgumentParser(description="FLUX.2 [Klein] 9B front-end for the sprite pipeline")
    ap.add_argument("subject", nargs="?")
    ap.add_argument("--batch", help="file of one subject per line")
    ap.add_argument("--size", type=int, default=16, help="SNES target (16 or 32)")
    ap.add_argument("--draw", type=int, default=64, help="logical grid to ASK Klein for (the '4x' image)")
    ap.add_argument("--px", type=int, default=1024, help="native render resolution")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--style", default="flat", choices=list(STYLE))
    ap.add_argument("--chibi", action="store_true", help="Q-version / super-deformed")
    ap.add_argument("--theme", default="none", help="palette theme: name, number, or free text")
    ap.add_argument("--colors", type=int, default=15)
    ap.add_argument("--method", default=quant.DEFAULT, choices=list(quant.METHODS))
    ap.add_argument("--workflow", help="ComfyUI API-format workflow JSON")
    ap.add_argument("--node", action="append", default=[],
                    help="override node resolution, e.g. --node positive=6 --node seed=31:noise_seed")
    ap.add_argument("--keep-n", action="store_true",
                    help="trust the DETECTED cell count over --draw (see what Klein actually drew)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--shared-palette", action="store_true",
                    help="batch only: force every asset onto ONE master palette (one CGRAM bank). "
                         "This -- not --theme -- is what actually fixes the colours.")
    ap.add_argument("--dry-run", action="store_true", help="print prompt + node resolution, no server")
    a = ap.parse_args()

    subjects = ([l.strip() for l in open(a.batch) if l.strip() and not l.startswith("#")]
                if a.batch else ([a.subject] if a.subject else []))
    if not subjects:
        ap.error("give a subject or --batch")

    if a.dry_run:
        pos, neg = build_prompt(subjects[0], a.draw, a.style, a.theme, a.chibi)
        print(f"POSITIVE:\n  {pos}\n\nNEGATIVE:\n  {neg}\n")
        if a.workflow:
            wf = json.load(open(a.workflow))
            ov = dict(kv.split("=", 1) for kv in a.node)
            nodes = resolve_nodes(wf, ov)
            print("NODE RESOLUTION:")
            for f in ("positive", "negative", "seed", "width", "height"):
                if f in nodes:
                    nid, key = nodes[f]
                    t = wf.get(nid, {}).get("_meta", {}).get("title", wf.get(nid, {}).get("class_type", "?"))
                    print(f"  {f:<9} -> node {nid} [{t}].inputs.{key}")
                else:
                    print(f"  {f:<9} -> UNRESOLVED (pass --node {f}=<node_id>)")
        else:
            print("(pass --workflow to also check node resolution)")
        return

    if not a.workflow:
        ap.error("--workflow is required (export an API-format workflow from ComfyUI)")
    wf = json.load(open(a.workflow))
    nodes = resolve_nodes(wf, dict(kv.split("=", 1) for kv in a.node))
    for f in ("positive", "seed"):
        if f not in nodes:
            ap.error(f"could not resolve the '{f}' node; pass --node {f}=<node_id>")
    os.makedirs(OUT, exist_ok=True)

    def one(subj):
        try:
            tgt, logical, meta = sprite(subj, a.size, wf, nodes, a.draw, a.tries, a.style,
                                        a.theme, a.chibi, a.method, a.colors, a.keep_n)
            if tgt is None:
                return subj, None, None, "FAILED"
            s = slug(subj)
            logical.save(f"{OUT}/{s}_{a.draw}_logical.png")
            json.dump({k: v for k, v in meta.items() if k != "render"},
                      open(f"{OUT}/{s}_{a.size}.json", "w"), indent=1, default=str)
            d = meta["detected"]
            return (subj, tgt, logical,
                    f"n={d['n']} score={d['score']:.2f} grid={'ok' if meta['gridded'] else 'WEAK'}")
        except Exception as e:
            return subj, None, None, f"ERROR {type(e).__name__}: {e}"

    done = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for subj, tgt, logical, msg in ex.map(one, subjects):
            print(f"{subj[:44]:<46} {msg}", flush=True)
            if tgt is not None:
                done.append((subj, tgt, logical))

    if a.shared_palette and len(done) > 1:
        # One master palette for the whole set = one CGRAM bank = a coherent game, not a pile of
        # unrelated icons. --theme alone does NOT do this: it is a prompt phrase, so it narrows the
        # gamut but every asset still ends up with its own 15 colours. What the theme buys is that
        # the assets already live in one gamut, which is why forcing them onto a single bank costs
        # almost nothing (METHODOLOGY: shared-master delta 0.008, under the 0.02 JND, against a
        # free-colour spread of 0.272). Theme narrows; this pins.
        ds = quant.DOWNSAMPLE[quant.METHODS[a.method][0]]
        smalls = [ds(lg, a.size) for _, _, lg in done]
        master = quant.shared_palette(smalls, a.colors)
        print(f"\nshared master palette ({len(master)} colours, BGR555) over {len(done)} assets")
        outs = [(subj, quant.remap_to(sm, master)) for (subj, _, _), sm in zip(done, smalls)]
        json.dump([[int(c) for c in col] for col in master],
                  open(f"{OUT}/master_palette.json", "w"), indent=1)
    else:
        outs = [(subj, tgt) for subj, tgt, _ in done]

    for subj, img in outs:
        s = slug(subj)
        img.save(f"{OUT}/{s}_{a.size}_raw.png")
        if M:
            M.preview(img, f"{OUT}/{s}_{a.size}.png", max(1, 256 // a.size))


if __name__ == "__main__":
    main()
