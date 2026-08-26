#!/usr/bin/env python3
"""Native-resolution shoot-out for the Klein front-end: can a 9B diffusion model draw a 16x16 sprite
DIRECTLY, or does it also need the draw-big-then-compress route the LLM needed?

This is METHODOLOGY section 2's experiment re-run against a different generator. There it was settled
for an LLM emitting SVG (C1 draw-at-16 < C2 draw-at-64-then-shrink), and the reason was specific to
that generator -- at 16 the model had too few <rect>s to spend and went sparse. A diffusion model has
the opposite failure mode (it has no native output below ~512px at all and is always upscaling a
pretend grid), so the answer does NOT transfer and has to be measured again.

Routes to one 16x16 sprite, all from the same 1024px native render:
  N16   ask Klein for a 16-cell grid  -> recover 16x16                        (direct)
  N32   ask for 32 -> recover 32x32   -> quant 2:1 -> 16
  N64   ask for 64 -> recover 64x64   -> quant 4:1 -> 16                      (the repo's default)

TWO things are measured, and the objective one is the point:

  1. GRID FIDELITY (objective, no judge): when told "16x16", how many cells does Klein actually lay
     down? `pixelgrid` detects it. If asking for 16 reliably yields ~16, direct is real; if it yields
     43, the model is drawing "pixel-art-ish texture" and the prompt's number is decoration.
  2. RECOGNISABILITY (0-10, the repo's only scoring axis) via judge.py if a vision endpoint is
     reachable, else left blank for a human pass over the montage.

  python3 compare_native.py --workflow klein.json
  python3 compare_native.py --workflow klein.json --theme candy --tries 2 --style comic

-> native_montage.png + native_scores.json
"""
import argparse, json, os

from PIL import Image, ImageDraw

import flux_front as F
import pixelgrid
import quant

try:
    import judge
except Exception:
    judge = None

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 170
TARGET = 16

SUBJECTS = [
    "a shiny gold coin with a star",
    "a red mushroom with white spots",
    "a wooden treasure chest with iron bands",
    "a jazz white rabbit with sunglasses and a golden saxophone",
]
ROUTES = [16, 32, 64]      # logical grid asked of Klein; all shrink to TARGET


def cell(img, label, sub="", sub2=""):
    t = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0)); tp = t.load()
    for y in range(CELL):
        for x in range(CELL):
            tp[x, y] = (46, 46, 56, 255) if ((x // 8 + y // 8) % 2 == 0) else (34, 34, 44, 255)
    if img:
        sc = max(1, (CELL - 40) // max(img.width, img.height))
        im = img.resize((img.width * sc, img.height * sc), Image.NEAREST)
        t.alpha_composite(im, ((CELL - im.width) // 2, (CELL - im.height) // 2 + 12))
    d = ImageDraw.Draw(t)
    d.text((4, 2), label, fill=(200, 220, 255, 255))
    if sub:  d.text((4, 13), sub,  fill=(150, 200, 150, 255))
    if sub2: d.text((4, 24), sub2, fill=(230, 180, 120, 255))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True, help="ComfyUI API-format workflow JSON")
    ap.add_argument("--node", action="append", default=[])
    ap.add_argument("--tries", type=int, default=2)
    ap.add_argument("--styles", default="flat",
                    help="comma list, e.g. flat,comic. Adds a style axis: does asking for a look "
                         "that fights the grid (manga cel-shading wants smooth even-weight ink; a "
                         "64px grid can only give staircases) cost grid fidelity?")
    ap.add_argument("--theme", default="none")
    ap.add_argument("--chibi", action="store_true")
    ap.add_argument("--px", type=int, default=1024)
    ap.add_argument("--colors", type=int, default=15)
    a = ap.parse_args()

    wf = json.load(open(a.workflow))
    nodes = F.resolve_nodes(wf, dict(kv.split("=", 1) for kv in a.node))
    if "positive" not in nodes:
        ap.error("could not resolve the 'positive' node; pass --node positive=<node_id>")

    styles = [s.strip() for s in a.styles.split(",") if s.strip()]
    for s in styles:
        if s not in F.STYLE:
            ap.error(f"unknown style {s!r}; choose from {list(F.STYLE)}")

    rows, results = [], []
    for subj in SUBJECTS:
        for style in styles:
            row = []
            for n in ROUTES:
                print(f"  {subj[:28]:<30} {style:<8} ask n={n}", flush=True)
                best = None
                for _ in range(max(1, a.tries)):
                    # trust_detect=True: what Klein ACTUALLY drew is the measurement, not a nuisance
                    logical, meta = F.render(subj, n, wf, nodes, style, a.theme, a.chibi,
                                             px=a.px, trust_detect=True)
                    if best is None or (meta["matched"] and not best[1]["matched"]):
                        best = (logical, meta)
                    if meta["matched"] and meta["gridded"]:
                        break
                logical, meta = best
                det = meta["detected"]

                # Every route lands on the same 16x16 target, so the comparison is like-for-like.
                tgt, pal = quant.to_target(logical, TARGET, colors=a.colors)
                sc = judge.score(tgt, subj) if judge else None

                rec = {"subject": subj, "style": style, "asked_n": n, "detected_n": det["n"],
                       "matched": meta["matched"], "grid_score": round(det["score"], 3),
                       "contrast": round(det["contrast"], 2), "gridded": meta["gridded"],
                       "palette": len(pal), "seed": meta["seed"],
                       "recognisability": (sc[0] if sc else None), "seen": (sc[1] if sc else "")}
                results.append(rec)
                row.append(cell(tgt, f"ask {n} -> {TARGET}",
                                f"drew n={det['n']} {'OK' if meta['matched'] else 'MISMATCH'}",
                                f"score {rec['recognisability']}" if sc else f"grid {det['score']:.2f}"))
            rows.append((f"{subj}  [{style}]", row))

    W = 230 + len(ROUTES) * (CELL + 6); H = 22 + len(rows) * (CELL + 6)
    mont = Image.new("RGBA", (W, H), (18, 18, 26, 255)); D = ImageDraw.Draw(mont)
    D.text((6, 6), f"Klein 9B native-resolution shoot-out -> {TARGET}x{TARGET}  "
                   f"(styles={','.join(styles)} theme={a.theme}{' chibi' if a.chibi else ''})",
           fill=(220, 230, 255, 255))
    for r, (label, row) in enumerate(rows):
        y = 22 + r * (CELL + 6)
        D.text((6, y + CELL // 2), label[:32], fill=(200, 200, 210, 255))
        for c, im in enumerate(row):
            mont.alpha_composite(im, (230 + c * (CELL + 6), y))
    mont.convert("RGB").save(f"{HERE}/native_montage.png")
    json.dump(results, open(f"{HERE}/native_scores.json", "w"), indent=1)

    print("\n-- grid fidelity: does Klein lay down the cell count it was told? --")
    print(f"  {'':<10}" + "".join(f"ask {n:<10}" for n in ROUTES))
    for style in styles:
        line = f"  {style:<10}"
        for n in ROUTES:
            sub = [r for r in results if r["asked_n"] == n and r["style"] == style]
            line += f"{sum(r['matched'] for r in sub)}/{len(sub):<12}"
        print(line)
    if len(styles) > 1:
        print("\n  (a style that fights the grid should show up as a lower row here, not as a "
              "prettier montage)")
    for style in styles:
        for n in ROUTES:
            sub = [r for r in results if r["asked_n"] == n and r["style"] == style]
            print(f"    {style:<9} asked {n:>3}: drew {[r['detected_n'] for r in sub]}")

    scored = [r["recognisability"] for r in results if r["recognisability"] is not None]
    if scored:
        print("\n-- recognisability (0-10) --")
        for style in styles:
            for n in ROUTES:
                s = [r["recognisability"] for r in results
                     if r["asked_n"] == n and r["style"] == style and r["recognisability"] is not None]
                if s:
                    print(f"  {style:<9} asked {n:>3}: avg {sum(s)/len(s):.1f}   {s}")
    else:
        print("\n(no vision judge reachable -- score native_montage.png by hand, "
              "or set VISION_URL/VISION_MODEL)")
    print("\n-> native_montage.png + native_scores.json")


if __name__ == "__main__":
    main()
