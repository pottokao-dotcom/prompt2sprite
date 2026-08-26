# Methodology — how each design decision was decided, and the experiment that decided it

The pipeline (`SVG → modal downscale → OKLab reduce → BGR555 → shared palette`) is not a set of
preferences; every step was chosen by an experiment against alternatives, scored on **one axis only:
recognisability / on-theme, 0–10** — art beauty explicitly ignored. Each section below states the
question, the experiment (with the bench script and evidence image), the numbers, the decision, and
**what result would have overturned it** (so these are falsifiable findings, not assumptions). Raw model
outputs (SVG/JS/txt) and PNGs are kept per cell so the scoring can be re-checked.

**Two roles, two models (state this before reading any number):**
- **Generator** — every sprite was drawn by **Qwen3.8-27B** (base, no LoRA). The method is model-agnostic,
  but these specific numbers are that generator's.
- **Judge** — the recognisability scores and the best-of-N candidate picks were made by **Claude Opus 4.8**,
  a vision-capable agent, *not* a human panel or an automated metric. It is a single judge; the scores are
  *relative* evidence between methods on one generator, judged consistently by one model — which is exactly
  what choosing between methods needs, and no more than that.

---

## 1. Why SVG is treated as the model's *native* pixel representation

**Question.** A sprite can be asked for in several encodings. Which one does the base model actually
produce reliably — i.e. which is *native* to it?

**Experiment** (`compare_style.py` ancestry / `gen_matrix.py` → `matrix_montage.png`). One subject (the
sax rabbit) drawn **4 ways × 3 sizes (16/32/64)**, each rasterised and scored:
- `svg` — `<rect>` per pixel, fixed `viewBox`.
- `canvas` — JS run headless, pixels read back.
- `ascii` — hex-digit grid + palette line.
- `json` — `{palette, grid[][]}` index array.

**Evidence (recognisability 0–10):**

| method | 16 | 32 | 64 | avg | behaviour |
|---|---|---|---|---|---|
| **svg** | 7 | 2* | **9** | **6.0** | *the 2 is a single bad roll (white bars); 64 has all four features |
| canvas | 4 | 7 | 0 | 3.7 | high ceiling but **blanks** when it guesses the canvas size wrong |
| ascii | 0 | 0 | 0 | 0.0 | collapses at every size |
| json | 0 | 0 | 0 | 0.0 | collapses at every size |

**Decision.** **SVG is the front-end.** It is declarative, anchors to a fixed `viewBox` coordinate
system, and has zero execution risk — which is exactly the "draw into a fixed tile size" task. Canvas has
a higher ceiling but high variance (it owns the whole coordinate system, so a wrong size assumption →
blank); it is a "need-more-detail" option that *requires* a render-and-retry check. The **raw pixel
grids (ascii/json) are a dead representation** — they score 0 everywhere. This matches an earlier direct
measurement outside this repo (the same model: JS sprite 116/256 vs a raw CHR grid 0/256).

**What would have overturned it.** If `canvas` or a raw grid had beaten SVG on average *and* not blanked,
the front-end would be that instead. It didn't.

---

## 2. Why draw at 4× the target, then downscale (and why the draw size is *capped*)

**Question.** At what resolution should the model draw, given the SNES target is only 16 or 32 px?

**Experiment A — draw-big-then-compress** (`gen_sprite2/3.py`). Three routes to a 16×16 sprite:
- C1: draw directly at 16 (sparse, brittle).
- C2: draw at 64, then a ruthless PY LANCZOS+median-cut shrink.
- C3: draw at 64, then let the **model itself** redraw it small.

Result: **C3 > C2 > C1.** Drawing at a comfortable large size and compressing preserves the silhouette;
drawing straight at 16 is starved. (The user's analogy: write the essay at a comfortable length, then
compress it to a poem — and let the poet do the compressing.)

**Experiment B — the comfort-zone cap** (the `gen_cj32` batches). Applying "always 4×" to a **32 px**
target means a **128 px** SVG. At 128 px the model draws **sparse / incomplete** — the candy batch drawn
at 128 collapsed into blobs and near-empty frames. Redrawing the *same subjects* at **64 px** (2×) fixed
it. The comfortable zone is ~64 px regardless of target.

**Decision.** Draw at `min(size × 4, 64)`, keeping an **integer** downscale ratio:
- 16 px target → draw 64 (**4×**), shrink 4:1.
- 32 px target → draw 64 (**2×**), shrink 2:1.

4× is the headline because 64/16 = 4 is a **pixel-perfect integer downscale** (no fractional remainder
to smear), and 64 px sits in the model's fluent range. The cap (`DRAW_CAP = 64`) is not cosmetic — it is
the line past which quality *inverts*.

**What would have overturned it.** If 128 px draws had been *richer* than 64 px, the cap would be higher.
Measured: they were sparser.

---

## 3. Why this quantisation (modal downscale · OKLab · BGR555), not LANCZOS+median-cut

**Question.** How to turn the 64 px raster into a SNES-legal ≤15-colour + transparent sprite without
muddying it?

**Experiment** (`compare_quant.py` → `quant_montage.png`). **One** source draw per subject, run through
**every** method (a downsampler × a colour-reducer), so the comparison is fair (no regeneration
confound):

| subject | LANCZOS + median-cut (old) | **modal + OKLab (chosen)** |
|---|---|---|
| gold coin | 15 colours, soft/banded, magenta edge fringe | **3 colours**, clean gold + crisp dark-gold edge |
| fireball | 15 colours, blurry | **4 colours**, crisp orange/red edge |
| sax rabbit | 15 colours, slightly soft | 12 colours, crisper edges |

**Why each sub-choice:**
- **Modal downscale (majority colour per `scale×scale` block), not LANCZOS.** A flat SVG's palette is
  *discrete by construction* (one `fill` per region). LANCZOS/bilinear **blends at edges → invents dozens
  of intermediate colours → forces a heavy re-quantise → mud + a pink fringe**. Modal keeps the discrete
  fills and *votes* (better than NEAREST's top-left bias). The colour-count drop is the tell: a coin that
  LANCZOS spent all 15 colours on needs only **3** under modal — and looks *crisper*, not poorer. (Box
  averaging is kept only for genuinely gradient/organic art — fire/smoke — where the blend *is* signal.)
- **OKLab, not RGB, for colour distance.** median-cut / nearest-colour default to RGB Euclidean, which
  mis-ranks perceptually (green under-weighted, luminance jumps). Clustering + nearest-match in **OKLab**
  put the same ≤15 colours where the eye wants them. Zero-cost pure-maths upgrade.
- **Transparency by alpha, not a magenta colour-key.** Compositing the shrunk sprite onto a magenta
  background (then quantising) leaves half-transparent LANCZOS edge pixels as **pink fringe**. Deciding
  transparency straight from the alpha channel removes it.
- **Snap to BGR555 last.** SNES CGRAM is 15-bit (5 bits/channel, 32768 colours); every final colour is
  `(c>>3<<3)`-legal so the preview equals the ROM.

**Decision.** `modal + OKLab + BGR555` as the default (`quant.METHODS["modal_oklab"]`); the whole thing
is a **registry** (`downsampler × reducer`) so a future method is one entry, and the verdict lives here
and in `PIXEL_CAPABILITY_REPORT.md`.

**What would have overturned it.** If modal had lost detail vs LANCZOS at equal crispness, or OKLab had
matched RGB, the default would differ. Measured: modal was both crisper *and* far fewer colours.

---

## 4. Why the palette control is a THEME (front-end soft constraint), and why it composes with extraction

**Question.** A whole game's sprites must be coherent *and* fit the hardware (SNES sprites = **8 banks ×
16 colours**; a 20-sprite game can't median-cut each independently). Enforce coherence at which end?

**Two handles, and they stack:**
- **Back-end (hard):** after drawing, pool every asset's colours and cluster once → one shared bank all
  sprites remap to (`shared_palette` + `remap_to`). Correct, but post-hoc "clean up the mess".
- **Front-end (soft):** tell the model up front to draw in a named aesthetic — *Morandi, earth, candy,
  Game Boy, cyberpunk…* A mood word is **loose to the LLM (it still picks specific colours, feels free)
  but is really a gamut constraint** — the model is native at these aesthetic vocabularies from
  pre-training, so it keeps the whole game inside one colour family by construction.

**Experiment A — does the front-end theme make the back-end extraction near-lossless?**
(`compare_theme.py` → `theme_montage.png`.) Draw 5 candy assets under one `candy` theme, extract **one**
15-colour master, remap all, measure the mean OKLab shift per asset:
- **mean OKLab delta = 0.008** (per-asset 0.001–0.024) — well under the ~0.02 just-noticeable threshold.
  I.e. extracting one shared palette for the whole set is **visually loss-free**, because the theme
  already seated the colours on it.

**Experiment B — the two-direction tension** (`compare_constraint.py` → `constraint_montage.png`). Two
opposite fears must both be satisfied: (1) don't let the constraint make the model draw *worse*; (2)
don't let free colours scatter so far that forcing one palette mutates every asset. Draw each subject
FREE vs CONSTRAINED (flat + theme), quantise, then remap the constrained set to one master:
- **Palette drift (own→shared) = 0.000** — compression does not wobble colours (deterministic, and the
  theme pre-seats them). → fear (2) answered.
- **Colour spread free = 0.272 vs themed = 0.089** (~**3× tighter**) — free assets genuinely scatter and
  are hard to unify; a theme makes them coherent *by construction*. → theme is the lever for (2).
- **Recognisability: themed+flat won 3 of 4** — constraints did **not** dumb it down; they helped. →
  fear (1) answered.
- **The one real boundary:** a chocolate bar under the *candy* theme got *worse* (brown forced pink). Rule:
  when an asset's identity **is** a colour (chocolate=brown, blood=red, gold coin=gold), a theme that
  conflicts hurts recognisability — exempt those.

**Decision.** Ship the palette control as a **first-class numbered theme knob** (`--theme 0/none |
1..32 | any custom phrase`), applied identically across an asset batch: **front-end theme (soft) +
back-end shared palette (hard) compose** — the theme sets the gamut, extraction snaps it to a legal bank
almost for free. This mirrors the whole pipeline's ethos, *give the model a constraint loose enough to
feel free but tight enough to be coherent* — the same idea as "draw big, then compress".

**What would have overturned it.** If the shared-palette delta had been large (theme didn't pre-align
colours) or themed art had scored lower, theme would be a cosmetic option, not the recommended path.
Measured: delta 0.008, spread 3× tighter, recognisability unharmed.

---

## Honest limits of the method (so the evidence isn't over-read)

- **Single-shot is high-variance.** These are per-cell *single* draws to measure bare capability; in
  production you take best-of-N with a judge (`gen_candidates.py` + a vision judge / a human). The
  non-degenerate probe rejects blanks, not "drew a gem instead of a heart" — a *recognisability* judge is
  needed for that.
- **The model draws structured objects/characters, not abstract symbols.** heart/star/clover came out as
  generic gems/diamonds/chevrons; rabbits, candies and food read fine. Pick structured subjects.
- **Resolution is a hard floor.** A coin's star does not survive 16 px by any method — simplify the
  description or go 32.
- **Scores are single-axis and single-judge.** They rank recognisability, not beauty, and there is no
  external ground-truth panel — treat them as *relative* evidence between methods on the same model, which
  is exactly what the decisions needed.
