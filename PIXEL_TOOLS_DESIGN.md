# SNES Pixel-Art Asset Tools — Architecture & Reasoning (frozen)

> The durable design behind `make_sprite.py` / `quant.py` / the `compare_*.py` benches.
> Captures not just WHAT the pipeline is but WHY each choice was made, so future methods slot in
> without re-deriving the logic. Built 2026-08-26. Benchmarks: `PIXEL_CAPABILITY_REPORT.md`.

---

## 0. The one-paragraph model of the problem

qwen38 (base) **cannot emit raw pixel grids** (index arrays / ascii-hex → blank, its dead
representation) but **draws fluently in code** (SVG best, canvas high-variance). So we let the model
do what it is native at — **choose shapes and colours as SVG** — and let **Python** do the
deterministic, hardware-bound maths — **downsample, perceptual colour reduction, BGR555 snap, shared
palette**. Division of labour is the whole idea: *poet picks the words, typesetter sets the page.*

## 1. Pipeline (fixed)

```
 LLM  ─ SVG, style=flat, drawn at 4x the SNES target (16→64, 32→128)
        └ best-of-N + non-degenerate probe (never ships blank)
 PY   ─ downsample 4:1  (method-dependent operator)
        └ colour-reduce to ≤15 + transparent, in OKLab
        └ snap to BGR555 (5-bit/channel)
 proj ─ (optional) shared master palette across all assets → remap each
 out  ─ target PNG (+ later: CHR bitplane via gfx4snes)
```

## 2. Why each choice (the reasoning, frozen)

**Why SVG (not canvas / raw grid).** Method matrix (`matrix_montage.png`): SVG `<rect>` is the most
*native and most stable* — declarative, fixed `viewBox` coordinate anchor, zero execution risk — it
targets "draw into a fixed tile size" exactly. canvas has a higher ceiling but high variance (guesses
the canvas size wrong → blank). ascii/json grids collapse to 0 at every size. → **SVG front-end,
canvas only as a "need more detail" option with playwright verify.**

**Why draw at 4× then shrink (not draw at target).** 64/128px sits in the model's comfortable/
recognisable zone (benchmark), and 4:1 is an **integer downscale** (pixel-perfect, no leftover
fractional pixels). Drawing straight at 16 is sparse/brittle; drawing at 4× then shrinking is the
"draw big → compress" finding — better silhouettes survive.

**Why `flat` is the default style.** Style shoot-out (`style_montage.png`, 0–10 recognisability):
flat solid blocks won overall (rabbit flat = 8, top of the board; never collapses). `shade`
(single-side) only wins on **organic/gradient** subjects (fire 7 vs 5); hard-edge icons get muddied
by shading. `outline` was worst (the "draw a border" instruction produced washed-out messes).
→ **default flat; shade for FX; outline demoted.** `chibi` is NOT default: at 32px the big head
crowds out the signature prop (rabbit's saxophone blurred). Chibi helps "recognised-by-face"
characters, hurts "recognised-by-prop" ones.

**Why modal downsample (not LANCZOS).** A flat SVG's palette is **discrete by construction** (each
`<rect fill>` = one colour). LANCZOS/bilinear **blends at edges → invents dozens of intermediate
colours → forces heavy re-quant → mud + pink fringe.** Modal (majority colour per 4×4 block)
**preserves the discrete fills** and votes instead of LANCZOS-averaging or NEAREST's top-left bias.
→ flat art: **modal**; gradient/FX: **box** (area average), because there the blend IS the signal.

**Why OKLab (not RGB) for colour distance.** median-cut / nearest-colour default to RGB Euclidean,
which mis-ranks perceptually (green under-weighted, luminance jumps). Clustering + nearest-match in
**OKLab** makes the same 15 colours land where the eye wants them. Zero-cost pure-maths upgrade.

**Why extract the model's own fills (`keep`).** The SVG already encodes a *semantic* palette (coin =
gold/dark-gold/white-shine). Keeping the top-N discrete fills is more meaningful than statistically
re-deriving them; only AA leak-colours get remapped. Crispest for pure-flat art.

**Why snap BGR555.** SNES CGRAM is 15-bit (5 bits/channel, 32768 colours). Every final colour must be
`>>3<<3`-legal. Do it as the last step (or quantise directly into the 555 grid) so preview == ROM.

## 3. The SNES palette constraint has TWO levels (this drives the whole-game feature)

| level | limit | who enforces |
|---|---|---|
| **per-asset (sprite)** | one 16-colour palette, colour 0 = transparent → **15 visible** | `quant.to_target` |
| **whole-game (CGRAM)** | 256 colours total; **sprites = 8 banks × 16 = 128** | `quant.shared_palette` |

A game with 20 sprites **cannot** median-cut each one independently — each would pick its own gold/red,
they won't fit 8 banks, and the screen looks incoherent. → **shared master palette**: pool every
asset's colours, cluster once in OKLab to ≤15 (or into the 8 banks), remap all assets to it. Result =
hardware-legal **and** visually consistent (one gold, one red across the whole game). This is a
**cross-asset / project-level** optimisation, not per-image. `dithering` is deliberately avoided at
sprite scale (noisy on 16×16); only BG gradients (sky) warrant light ordered dither.

## 3b. Whole-game colour coherence has TWO handles (front + back)

Consistency across a game's sprites can be enforced at **two ends**, and they stack:

**Back-end (hard, mechanical): shared master palette.** After drawing, pool every asset's colours and
cluster once → one CGRAM bank all sprites remap to (`quant.shared_palette` + `remap_to`). Guarantees
hardware-legal + identical golds/reds. This is the "extract at the end" model — correct, but post-hoc.

**Front-end (soft, semantic): a palette-theme / mood prompt.** Tell the model up front to draw in a
named aesthetic — *Morandi*, *earth tones*, *pastel*, *Pokémon-bright*, *Game Boy*, *candy*, *neon*.
A mood word is **loose to the LLM (it still picks specific colours, feels free) but is really a gamut
constraint** — the model is native at these aesthetic vocabularies from pre-training, so it naturally
keeps the whole game inside one colour family. Same theme on every asset ⇒ coherent game palette from
the start. Bonus: it makes the **back-end extraction cleaner** — colours already cluster tightly, so
the shared 15-colour master fits with less distortion.

→ Design consequence: `make_sprite --theme <n|name|phrase>` (registry `THEMES`, resolver
`resolve_theme`), applied identically across an asset batch. **Front-end theme (soft) + back-end
shared palette (hard) compose** — theme sets the gamut, extraction snaps it to a legal bank. Mirrors
the pipeline's whole ethos: *give the LLM a constraint loose enough to feel free but tight enough to
be coherent* (same idea as "draw at a comfortable big size, then compress"). This is the recommended
way to get a house style.

**Theme is a first-class numbered knob, not a "prompt tip".** It IS just a table of palette phrases,
but formalised as a registry so it's discoverable, reproducible, and documented:
`--theme 0` / `none` = no constraint; `--theme 1..32` or a preset name (morandi, earth, candy,
gameboy, cyberpunk, sakura, …) = a curated gamut; **any other string = a custom BYO palette phrase**
(theme 0 = "write your own"). `--list-themes` prints the table. Same resolver handles all three forms.

**Measured payoff (test method + result).** `compare_theme.py <theme>` draws N assets under one theme,
then extracts a **single** shared master palette and remaps every asset to it, reporting the **mean
OKLab shift** between each asset's own palette and the shared one. Low shift = the theme pre-aligned
the colours so the shared bank barely changes them. On a 5-asset **candy** set (hard candy, lollipop,
chocolate bar, gummy bear, star sweet) → **mean OKLab delta = 0.008** (per-asset 0.001–0.024), well
under the ~0.02 just-noticeable threshold — i.e. extracting one 15-colour master for the whole set is
**visually near-lossless**. Evidence: `theme_montage.png` (top row own palette, bottom row shared
master, plus the extracted swatch strip). Conclusion: a front-end theme turns "quantise + extract
palette" from *cleaning up a mess of colours after the fact* into *snapping already-tidy colours to a
legal bank*.

Note: SNES is **not** so restrictive that one palette is forced — sprites get **8 banks × 16**, so a
small game (a match-3's few pieces + 2 mascots) can give each type its own bank and skip sharing
entirely. Shared palette / theme are for **>8 sprite types, house-style consistency, or saving banks** —
opt-in, not mandatory. (Measured: coin needed 3 colours, fireball 4, rabbit 12 — each fits its own bank.)

## 3c. The two-direction tension (and how theme balances it)

Two opposite failure modes must be satisfied *at once*:

- **Direction 1 — don't constrain the model into drawing badly.** Worry: `flat` style + a theme dumb
  down the art.
- **Direction 2 — don't let free colours scatter so far that forcing one shared palette mutates every
  asset and they won't integrate.** Worry: quantising a rainbow of independent colours into one bank
  wrecks each sprite.

**Test (`compare_constraint.py <theme>`).** For each subject, draw FREE (outline, no theme) vs
CONSTRAINED (flat + theme); quantise each to its own palette; then remap the constrained set to ONE
shared master. Metrics: **palette drift** = mean own→shared OKLab shift (does compression wobble
colours?); **colour spread** = mean pairwise distance between assets' palette centroids (how scattered
the set is → how hard to unify). Evidence image: `constraint_montage.png`.

**Result (5-candy set):**
- **Palette drift = 0.000.** Compression / shared-palette extraction does **not** wobble colours — the
  step is deterministic and, because the theme already seats colours on the shared gamut, remapping to
  one master is loss-free. → Direction-2 worry (mutation) answered: no.
- **Colour spread: free 0.272 vs themed 0.089** (themed ~3× tighter). Free-drawn assets each drift
  their own way and are genuinely hard to fold into one bank; a theme makes them coherent *by
  construction*, so the unified palette is easy. → theme is the lever for Direction 2.
- **Recognisability: themed+flat won 3 of 4** (candy/lollipop/gummy-bear all clearer than the washed-out
  free `outline` draws) → constraints did **not** dumb it down; they helped. → Direction-1 worry: no.

**The one real boundary (recorded as a caveat).** The 4th subject — a **chocolate bar** under the
**candy** theme — got *worse* (brown chocolate forced pink → identity lost). Rule: **when an asset's
identity IS a colour** (chocolate=brown, blood=red, gold coin=gold), a theme that conflicts with it
will hurt recognisability. Mitigations: choose a theme compatible with the asset set; exempt
colour-defined items from the theme; or widen the theme phrase. So the two directions are in mild
tension and **`theme` is the single knob that balances them** — near-zero quality cost for high
coherence, *except* where it collides with a colour-defined identity.

## 3d. End-to-end to a running ROM (proven) + the gotchas

`make_sprite` PNG → `agent_v2/chr_pipeline.build_chr` (gfx4snes) → `.pic/.pal` incbin → PVSnesLib
`make` → `.sfc` → Mesen2 headless screenshot. A 6×6 board of 32×32 candy pieces renders correctly on
the emulated SNES, all sharing one 16-colour OBJ palette (the whole-sheet quantise = the shared-bank
constraint, on real hardware). Five real bugs/limits found and fixed along the way — record them:

1. **Draw-size cap.** Drawing at 4× a 32px target (=128px SVG) makes the model draw sparse/incomplete.
   The comfortable zone is ~64px → `DRAW_CAP = 64` (16→64 is 4×, 32→64 is 2×). Cap, keep integer ratio.
2. **Abstract symbols fail.** qwen38 draws structured objects/characters well (rabbit, candies, food)
   but renders abstract symbols (heart, star, clover) as generic gems/diamonds/chevrons. Pick
   structured subjects; don't ask for icons defined only by an abstract outline.
3. **Single-shot is high-variance** → needs a **visual-judge gate**: render N candidates, keep the best
   by actual recognisability (not just the non-degenerate probe, which passes crude blobs).
   **Default judge = the vision-capable agent** (`gen_candidates.py` lays a contact sheet, the agent
   scores & picks). This is free (no GPU, no server change) and catches "drew a gem instead of a heart",
   which a text probe cannot. `judge.py` is the OPTIONAL unattended path: point `VISION_URL` at any
   vision endpoint and it scores 0–10 / regenerates low; with no endpoint it returns None and the caller
   falls back to the non-degenerate probe. (Not enabled by default — the local GPU is full with the
   generation server, and standing up a separate vision model / restarting that server was declined.)
4. **preview ≠ raw.** `make_sprite` saves a checkerboarded *preview* PNG for viewing; sheets/CHR must use
   the RAW transparent sprite (now also saved as `<slug>_<size>_raw.png`). Reading the preview into a
   sheet collapses it to the 2 checker colours.
5. **gfx4snes reflows the sheet.** A 32×192 vertical strip is repacked into 4×2 blocks of 32×32 in the
   16-tile-wide OBJ grid, so the base tile of 32×32 piece `id` is `(id>>2)*64 + (id&3)*4`, **not**
   `id*16`. (16×16 pieces stayed linear → `id*4` there.) Confirm sprite tile layout with an OAM probe,
   not by eye — "the screen lies, the state doesn't": OAM showed 37 sprites set correctly while the
   screen was blank, which localised the fault to the tile data, not the draw code.

## 4. Quantisation as an OPEN SLOT (extensibility)

`quant.py` models a method as **(downsampler × colour-reducer)**, each registered by name:

```
DOWNSAMPLE = { modal, box, lanczos, nearest }
REDUCE     = { mediancut, keep, oklab }
METHODS = {                       # name : (downsample, reduce, note)
  lanczos_mc  : (lanczos, mediancut)  # OLD baseline, muddies flats
  modal_mc    : (modal,   mediancut)
  modal_oklab : (modal,   oklab)      # DEFAULT — best flat all-rounder
  modal_keep  : (modal,   keep)       # crispest flat (model's own fills)
  box_oklab   : (box,     oklab)      # gradient / FX
}
DEFAULT = "modal_oklab"
```

**Adding a method = add one entry** (e.g. a future `wu` reducer, `error-diffusion` downsampler, or an
LLM-proposes-palette reducer). Nothing else moves. `--method` selects; default is the empirical winner.
The verdict lives in `PIXEL_CAPABILITY_REPORT.md`; benches (`compare_style.py`, `compare_quant.py`)
regenerate the evidence on demand.

## 5. Interfaces (frozen)

```
make_sprite.py "<subject>" --size 16 --style flat --method modal_oklab --colors 15 [--chibi]
quant.to_target(src_rgba_4x, size, method, colors) -> (target_rgba, palette)
quant.shared_palette([smalls...], colors) -> master_palette ;  quant.remap_to(small, palette)
```

Strategy: **every knob has a sensible default (drop one subject → get a sprite) but nothing is forced.**
best-of-N + non-degenerate probe guarantee no blank output. Downstream (CHR bitplane encode via
`chr_pipeline.build_chr` / gfx4snes) is deterministic.

## 6. Asset size budget (from the resolution sweep, recap)

icons (coin/fireball/pieces) = **16×16** (fine detail like a coin's star does not survive 16 → simplify
the description or go 32); characters/mascots = **32×32** or metasprite up to 32×48; RPG chibi 16×24.
See `finding_pixel_art_native_svg_and_resolution_budget` (memory) for the full table.
