# End-to-end: text subject → sprite → CHR → running SNES ROM

Proven path from a text prompt to pixels rendering on the emulated SNES.

```
make_sprite "…"  →  RAW <slug>_<size>_raw.png            (SVG draw → quantise → BGR555)
   → compose into a sprite sheet (one sprite wide: 16×N or 32×N)
   → agent_v2/chr_pipeline.build_chr(sheet, res, "candy", tile)   (gfx4snes → .pic/.pal)
   → PVSnesLib `make`  →  candy.sfc
   → Mesen2 headless (run_probe.sh + probes/start_then_png.lua)  →  screenshot
```

`evidence/onROM_6x6_32px.png` — a 6×6 board of 32×32 candy pieces (peppermint, lollipop, gummy bear,
chocolate bar, donut, orange slice) rendering on the emulated SNES, all sharing **one 16-colour OBJ
palette** (the whole-sheet quantise = the shared-bank hardware constraint, live).

## Five gotchas found doing this (so you don't rediscover them)

1. **Cap the draw size at ~64px.** Drawing a 32px target at 4× (=128px SVG) makes the model draw
   sparse/incomplete. `DRAW_CAP = 64` in `make_sprite.py` (16→64 = 4×, 32→64 = 2×).
2. **Structured subjects only.** The model draws objects/characters (rabbit, candies, food) well but
   renders abstract symbols (heart, star, clover) as generic gems/diamonds. Pick structured subjects.
3. **Single-shot is high-variance → judge the candidates.** `gen_candidates.py` makes N per piece for a
   visual judge to pick the best; the non-degenerate probe alone passes crude blobs. (Automating this
   with a vision model that scores recognisability is the proper upgrade.)
4. **Use the RAW sprite, not the preview.** `make_sprite` saves a checkerboarded preview for viewing
   *and* a `<slug>_<size>_raw.png`. Sheets/CHR must use the RAW one; the preview's checker background
   collapses a sheet to 2 colours.
5. **gfx4snes reflows the sheet.** A 32×192 strip is repacked into 4×2 blocks of 32×32 in the
   16-tile-wide OBJ grid, so a 32×32 piece's base tile is `(id>>2)*64 + (id&3)*4`, **not** `id*16`
   (16×16 pieces stay linear at `id*4`). Verify sprite tiles with an OAM probe, not by eye — the OAM
   read showed all 37 sprites set correctly while the screen was blank, pinpointing the tile-data bug.

The `draw_candy` change for 32×32 pieces on a 6×6 board (fits 256×224; an 8×8 board of 32px would be
256×256 — too tall):

```c
static void draw_candy(unsigned short slot, unsigned char col, unsigned char row, unsigned char id){
    unsigned char base = (id>>2)*64 + (id&3)*4;              // gfx4snes 4x2 reflow, not id*16
    oamSet(slot<<2, col*32+32, row*32+16, 3,0,0, base, 0);
    oamSetEx(slot<<2, OBJ_LARGE, OBJ_SHOW);                  // OBJ_SIZE16_L32: large = 32
}
```

## Free idle animation (no new frames)

Mascots "dance to the jazz" without generating a second pose: bob the sprite 2px up/down on the beat
and mirror it horizontally (`hflip`) on a slower cycle, the two mascots in **opposite phase** so they
look lively rather than synchronised. Costs nothing — no extra CHR, just OAM fields per frame.

```c
static const unsigned char BOB[4] = {0,1,2,1};                 // gentle 2px up/down
{ unsigned char ph=(timer>>3)&3, sw=(timer>>4)&1;              // idle dance
  draw_mascot(37, 0,   88+BOB[ph],       6, sw);               // rabbit left
  draw_mascot(38, 224, 88+BOB[(ph+2)&3], 7, sw^1); }           // groundhog, opposite phase
```

Verified from state (an OAM probe over time), not by eye: rab_y cycles 90→89→88→89 while grd_y runs the
opposite phase, and each mascot's hflip bit toggles every ~16 frames. `evidence/mascot_idle_dance.png`
shows two frames with the mascots mirrored & bobbed. Richer per-event animation (blow-a-note on match-3,
headbang on combo) would need real extra frames — that's the next step, and where a judged generation
round pays off.

## Per-event reaction (match-3 → celebrate) + a latent bug the feature exposed

On a match, the mascots swap to a **celebrate pose** (extra generated frames, id 8/9 in the sheet) and
do a big jump + rapid shake for ~48 frames; `combo` (cascade depth) is available to scale it. Hook: the
match loop in `game_update` counts cascades and sets a `react` timer.

```c
combo = 0;
do { /* clear matches ... */ if (changed) combo++; } while (changed && combo < 6);
if (combo) react = 48;          /* draw loop shows cheer pose (id 8/9) + jump while react-- > 0 */
```

**Bug found (and why the cap is there).** The original clear replaces a matched run with `(id+1)%6`,
which can immediately re-match — an **infinite cascade**. The stock grid never matched at all, so this
latent hang was invisible; a *playable* grid triggered it. Symptom via a WRAM probe (addresses from the
`.sym`: `react`/`combo`): `combo` climbed 9→18→…→74 unbounded while `react` stayed 0 and the frame
counter still advanced — the CPU was stuck in the `do/while` while the PPU kept drawing. The screen
looked fine; the state showed the loop never exiting. Capping the cascade (`combo < 6`) bounds it, lets
`react` get set, and doubles as the reaction-intensity signal. `evidence/mascot_event_react.png` shows
idle vs. the match-3 celebrate (both mascots jumped, pose swapped). Deeper per-event frames
(combo×5 headbang/guitar-smash) follow the same pattern — one judged generation round per pose.

## Match juice: screen shake + flash

On a clear, add game-feel: a decaying **screen shake** (a per-frame offset applied to every OBJ *and*
the BG scroll, so the whole board jolts together) plus a **brightness flash** flicker on impact. Both
gated by the same `react` timer so they fire exactly with the mascot celebrate.

```c
{ unsigned char amp = (react>32) ? (react-32) : 0;         // shake amplitude, decays over ~16 frames
  sox = (timer&1)?amp:0;  soy = (timer&1)?0:amp;           // diagonal jolt each frame; sox/soy are globals
  bgSetScroll(0, sox, soy);                                // BG shakes...
  setBrightness((react>40 && (react&1)) ? 6 : 15); }       // ...brightness flicker
// draw_candy / draw_cursor add sox,soy to every oamSet -> the OBJ layer shakes with the BG
```

Key point: shaking `bgSetScroll` alone only moves the background; the candies are OBJs, so the offset
must also be added to their `oamSet` x/y or the pieces stay put while only the backdrop jitters. Verified
by capturing adjacent frames — `evidence/match_juice_shake_flash.png` (idle vs two react frames) shows the
whole board offset differently between consecutive frames, and a luma probe showed the brightness dip.

## Match sound effect (SPC700) + the queued-load gotcha

SNES audio needs BRR samples (no simple square-wave beep). PVSnesLib/snesmod plays SFX from an effects
`.it` module: list it FIRST in `AUDIOFILES`, add `-f` to `SMCONVFLAGS`, then `spcLoadEffect(idx)` to load
a sample and `spcEffect(pitch, idx, volpan)` to fire it (pitch 1=4KHz…8=32KHz). On a match we play a
marimba with the pitch rising by cascade depth:

```c
// init: MUST let the queued effect load finish before playing, or it silently never loads
spcStop(); spcLoad(MOD_SONG);
for(i=0;i<20;i++){ spcProcess(); WaitForVBlank(); }
spcLoadEffect(SFX_MATCH);
for(i=0;i<20;i++){ spcProcess(); WaitForVBlank(); }
spcPlay(0);
// on match:
if(sfx){ spcEffect(2+combo, SFX_MATCH, 15*16+8); sfx=0; }   // pitch rises with combo
```

**Gotcha (cost hours):** `spcLoadEffect` only *queues* a message; calling `spcLoad`/`spcPlay` before it
drains overwrites ARAM and the effect never loads — `spcEffect` then plays silence. Pump
`spcProcess()+WaitForVBlank()` (~20 frames) between the steps. **Verify by state, not by ear:** with no
audio capture, read the S-DSP per-voice `brrAddress` over time — a match makes a NEW voice key on with an
address outside the BGM's sample range (BGM ~7400–7700, effect ~7900–8300), and the active-voice count
rises 3→4. That is how the SFX was confirmed headless.

## Candy clear pop (the pieces react too)

Instant `(id+1)` recolour reads as "nothing happened". Give the *cleared pieces* a pop: mark them during
the match scan and blink them off/on for the first ~12 frames of `react`, then let them settle to the new
colour.

```c
unsigned char hit[36];                                  // 1 = this cell was just cleared
// in the match scan (both axes), when a run len>=3 clears a cell:
hit[cell] = 1; grid[cell] = (id+1)%6;
// reset at the start of each move: for(i=0;i<36;i++) hit[i]=0;

// in the draw loop:
for(i=0;i<36;i++){
  if(hit[i] && react>36 && (timer&2)){ oamSet(i<<2,0,240,0,0,0,0,0); oamSetEx(i<<2,OBJ_LARGE,OBJ_HIDE); }
  else draw_candy(i,i%6,i/6,grid[i]);
}
```

Verified by state (count visible candy OBJs over time): a 9-cell cascade made the on-screen candy count
oscillate **36 → 27 → 36 → 27** through the pop window, then settle at 36 — i.e. the 9 cleared pieces
blinked ~3 times. `evidence/candy_pop_sequence.png` (before / pop-on / pop-off / settled).

With this, a single clear now fires the full feedback stack together: **cleared pieces pop + screen shake
+ brightness flash + mascots celebrate + marimba SFX (pitch by combo depth).**
