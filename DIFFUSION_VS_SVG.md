# The diffusion front-end — full guide (setup, prompts, palette/theme, findings)

`prompt2sprite` has **two front-ends**, and one shared back-end:

| front-end | draws with | quality | needs | use when |
|---|---|---|---|---|
| **SVG** (default) | an LLM emits SVG (`make_sprite.py`) | good | any OpenAI-compatible LLM, **no GPU** | anywhere, zero deps |
| **Diffusion** | Z-Image Turbo via ComfyUI (`comfyui/gen_zimage_sprites.py`) | **better**, esp. at 32×32 | a GPU + ComfyUI | when you have the GPU |

**The whole back-end is shared** — `quant.py` (modal downscale · OKLab · BGR555 · shared palette) and
`diffuse_quant.py` (background strip · crop). Swapping the front-end changes *how the pixels are drawn*,
nothing downstream. This doc covers the diffusion path; the SVG path's methodology is in
[`METHODOLOGY.md`](METHODOLOGY.md).

**Rendered report (open in a browser):** [`reports/diffusion_vs_svg.html`](reports/diffusion_vs_svg.html)
— sprites, the resolution ladder, palette lock, verdict.

---

## 1. The logic (both front-ends, one pipeline)

```
 FRONT-END (swappable) ─────────────┐
   SVG:       LLM → SVG  (draw ×4 the target, cap ~64px)         zero GPU
   Diffusion: Z-Image Turbo → raster (generate ×4 the target)    needs GPU, better quality
                                     │
 BACK-END (shared, diffuse_quant + quant.py) ──────────────────┐
   strip background (diffusion only) → crop to sprite
   → modal downscale to the SNES target (16/32/8)
   → colour: free OKLab reduce, OR HARD-LOCK to a fixed palette
   → snap BGR555  →  (CHR via gfx4snes)
```

Two rules hold for **both** modalities, proven by experiment (see the report):
- **Never generate the true tiny grid.** Diffusion *native ×1* (generate at 32) collapses; SVG at 16 is
  starved. Generate bigger, then downscale.
- **Lock the palette in post, not in the model.** Colour words only *steer*; the guarantee comes from a
  deterministic remap to a fixed bank.

## 2. Efficiency — how big to generate (the ×N sweet spot)

Measured on Z-Image Turbo (nvfp4, GB10), generating the same coin then downscaling to 32:

| gen canvas | multiple | result → 32 | gen time |
|---|---|---|---|
| 32px | ×1 native | **collapses** (a few stray pixels) | ~0.3s |
| 64px | ×2 | works (readable) | ~0.4s |
| **128px** | **×4** | **crispest — sweet spot** | **0.61s** |
| 256px | ×8 | good, softer | 0.91s |
| 512px | ×16 | good, no gain | 2.12s |

**Rule of thumb: generate at ×4 the target** (128px for a 32-sprite, 64px for a 16-sprite). Same quality
as 512, ~3.5× faster; below 128px fixed overhead dominates so going smaller barely saves. Native ×1 is a
dead end. (SVG's equivalent is ×4 into a ~64px cap.)

## 3. ComfyUI workflow — the basic setup

Any **Z-Image Turbo** text-to-image workflow works; you patch four things per job via the HTTP API. The
node ids below are from the workflow this used (`zimage_base2_turbo8_gx10_nvfp4all.json`); match yours.

| node | class | what to set |
|---|---|---|
| `84:66` | `CLIPTextEncodeLumina2` | **`user_prompt`** = your prompt · `system_prompt` = `"superior"` |
| `79` | `EmptySD3LatentImage` | `width`, `height` = the gen canvas (128 for a 32-sprite) |
| `81`, `81b` | `KSamplerAdvanced` (base→turbo) | `seed` / `noise_seed` |
| `9` | `SaveImage` | (output) |

Turbo settings already in the workflow: **10 steps, cfg ≈ 1.2, `res_multistep`/`simple`**, Lumina2 text
encoder. Two gotchas that cost real time:

- **The prompt field is `user_prompt`, NOT `text`.** `CLIPTextEncodeLumina2` has `system_prompt` +
  `user_prompt`. Setting `["text"]` does nothing → you get the model's default (portraits/garbage).
- **Stale model refs 400 the whole prompt.** An old workflow pointed its CLIP loader at a removed
  `…-Q4_K_M.gguf`; it had to point at the current `Z-Image-Engineer-V6-kitchen-nvfp4.safetensors`. If
  `/prompt` returns `400 value_not_in_list`, the node's model name isn't in ComfyUI's list — fix the name.

The driver `comfyui/gen_zimage_sprites.py` does exactly this: load workflow → set `user_prompt`, latent
size, seeds → POST `/prompt` → poll `/history/{id}` → copy the saved PNG out.

## 4. Prompts

**Positive template** (fill `{subject}`):
```
{subject}, pixel art, 16-bit SNES sprite, single game asset, centered, front view,
flat bright colors, hard edges, crisp pixels on a grid, limited palette, plain solid white background
```
**`system_prompt`:** `superior` (a quality preset of the Lumina2 node — leave it).
**Negative** (node `84:33` is `ConditioningZeroOut` here, and at cfg ≈ 1.2 the negative barely acts, so
don't rely on it). If your workflow has a real negative slot:
```
blurry, anti-aliasing, smooth gradient, soft shading, 3d render, realistic, photo, noise, text, watermark,
multiple objects, cluttered background, drop shadow
```
**Subject choice** (same lesson as SVG): structured objects/food/characters read well; abstract symbols
(heart/star/clover) come out generic — describe the thing concretely.

## 5. Palette & theme — the coherence control (both modalities)

This is the important part: **how a prompt yields a *coherent whole-game set*, not a lone sprite.** Two
handles, and they compose — a soft one at the front, a hard one at the back:

**Front-end (soft, per modality) — steer the gamut:**
- **SVG:** the `--theme` knob — a named gamut (*morandi, candy, gameboy, cyberpunk…*, 32 presets + any
  custom phrase) is injected into the draw prompt. The LLM is native at these aesthetics, so it keeps the
  set inside one family. Measured: applying one theme across a set makes the later shared-palette
  extraction near-lossless (**mean OKLab delta 0.008**, colour spread **0.272 → 0.089**, ~3× tighter).
- **Diffusion:** append colour words to the prompt — `…, using ONLY bubblegum pink, purple, teal, lemon
  yellow, cream and white`. This *steers* but does **not** obey at the pixel level (diffusion has no
  palette constraint), so it is the weaker handle here.

**Back-end (hard, shared) — guarantee the bank:** the deterministic lock, identical for both front-ends.
- Build one master palette (`quant.shared_palette` over the set, or a hand-set list), then remap every
  asset to it: `diffuse_quant.py … --palette palettes/candy.hex` (or `quant.remap_to`). Every pixel snaps
  to the nearest legal colour; the model's colours are *ignored*. This is what makes the output
  **hardware-legal (≤15 + transparent, one 16-colour OBJ bank) and identical across the set**.
- `palettes/candy.hex` here is the exact 15-colour bank the SVG candy set converged to — so both modalities
  can be locked to the *same* palette and compared directly.

**So the recipe for a coherent set is the same on both paths:** one soft theme/colour-phrase up front for
a pleasant natural gamut, then one hard shared palette in post for the guarantee. On the diffusion path
the hard lock does most of the work (the soft steer is weak); on the SVG path the soft theme is strong
enough that the hard lock is nearly free. Either way: **one theme → one coherent, hardware-legal set.**

## 6. Reproduce

```sh
# 1) generate rasters on a ComfyUI host running Z-Image Turbo (gen at ×4 the target)
python3 comfyui/gen_zimage_sprites.py            # -> ~/zimage_sprites/*.png ; copy to ./zimage_raw/

# 2) downscale + quantise (free, or hard-locked to a fixed bank)
python3 diffuse_quant.py zimage_raw/A_coin_512.png --size 32
python3 diffuse_quant.py zimage_raw/D_mint_512.png --size 16 --palette palettes/candy.hex

# 3) rebuild the report
python3 build_page.py                            # -> reports/diffusion_vs_svg.html
```

## 7. Verdict

| Question | Answer | What we saw |
|---|---|---|
| Quality vs SVG (H3) | **diffusion wins** | far richer 512px art; **32×32 clearly beats SVG**; 16×16 comparable-to-better |
| Draw a true 8/16/32 grid (H1) | **no** | renders big, you downscale; native ×1 collapses; **×4 is the sweet spot** |
| Lock the palette (H2) | **yes, in post** | not a model feature; deterministic remap to a fixed bank works cleanly |
| Whole-set coherence (H4) | **soft theme + hard bank** | per-image model; front-end steer + back-end shared palette, same as SVG |
