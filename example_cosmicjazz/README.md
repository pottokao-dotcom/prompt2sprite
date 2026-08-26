# Example — COSMIC JAZZ (full worked SNES match-3)

The complete, runnable game that the `../END_TO_END.md` and `../TUTORIAL_sound_effects.md` write-ups are
based on. A 6×6 match-3 whose sprites were made by `make_sprite.py` (SVG → CHR), with a full "juice" stack.

Build it (the repo `.gitignore` excludes ROMs/build output, so the sources are here but `candy.sfc` is
not — `make` regenerates it and the soundbank from the checked-in graphics/audio assets):

```sh
source <pvsneslib env.sh>       # sets PVSNESLIB_HOME
make clean && make buildActual  # -> candy.sfc, then run in any SNES emulator
```

Prefer to just watch it? See `../evidence/cosmicjazz_gameplay.gif` / `.mp4`.

Play: **START** to begin, **D-pad** to move the cursor, **A** to swap with the piece to the right.

## What it demonstrates (all verified on-emulator)

- **Generated art on hardware** — 6 candy pieces + 2 mascots, made by the art pipeline, in one shared
  16-colour OBJ palette (`res/candy.pic`/`.pal`), laid out as 32×32 OBJs.
- **Idle animation** — mascots bob + mirror-sway to the beat, opposite phase (no extra frames).
- **Per-event reaction** — on a match the mascots swap to a celebrate pose and jump.
- **Match juice** — cleared pieces blink/pop, the whole board shakes (OBJ + BG), a brightness flash.
- **Sound effect** — a marimba whose pitch rises with cascade depth (`spcLoadEffect`/`spcEffect`).

See `../evidence/cosmicjazz_gameplay.gif` (and `.mp4`) for it in motion.

## Map of the source (`src/main.c`)

| Concern | Where |
|---|---|
| Sprite tile math (gfx4snes 4×2/4×3 reflow: `(id>>2)*64+(id&3)*4`) | `draw_candy` / `draw_mascot` |
| Playable start grid (all 6 pieces, no initial triple, swaps can match) | `GRID0` / `init_grid` |
| Match + cascade **cap** (avoids the recolour infinite-loop) | `game_update` |
| Cleared-cell pop markers | `hit[]` |
| Idle bob + sway / reaction jump | `BOB` / `JUMP` + the PLAY draw block |
| Screen shake (OBJ+BG) + brightness flash | the `amp`/`sox`/`soy` block |
| Audio init (⚠ pump `spcProcess`+`WaitForVBlank` so `spcLoadEffect` finishes) | top of `main` |
| Match SFX trigger | `if(sfx) spcEffect(...)` |

## Notes / honest caveats

- This started as the stock `candy_game_proj` scaffold; the match "clear" still recolours pieces to
  `(id+1)%6` rather than doing gravity/refill — deliberately simple, and the cascade **cap** is what
  keeps that from looping forever.
- The BGM is the scaffold's stock track, not a jazz tune yet.
- Everything here was checked headless via Mesen2 Lua probes (OAM / WRAM / S-DSP), not by eye or ear —
  the screen and speaker lie, the state doesn't.
