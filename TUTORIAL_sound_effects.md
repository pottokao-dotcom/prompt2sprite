# Tutorial — Adding a sound effect to a PVSnesLib game

A self-contained, step-by-step guide to play a **sound effect** (e.g. a "ding" on a match) on top of
your background music, using PVSnesLib / snesmod. Every snippet here is from a game that was built and
verified on the SNES — including the one gotcha that silently eats an afternoon.

> **Mental model.** The SNES has no square-wave "beep". The SPC700 sound chip only plays **BRR samples**.
> So a sound effect = a small sampled instrument compiled into your **soundbank**, loaded into the sound
> chip's RAM, then triggered. snesmod (PVSnesLib's sound driver) gets those samples from an **effects
> module** — an Impulse Tracker `.it` file whose instruments are used as effects.

---

## What you need first

- A PVSnesLib project that already builds and **plays background music** (`spcBoot` / `spcSetBank` /
  `spcLoad` / `spcPlay` / `spcProcess` in your loop). If music already works, SFX is ~15 lines more.
- An **effects `.it`** file (the instruments become your effects). If you don't have one, borrow the
  stock example's: `pvsneslib/snes-examples/audio/effectsandmusic/res/effectssfx.it` — it has a handful
  of samples (tada, strings, piano, marimba, cowbell).

---

## Step 1 — Put the effects module in the soundbank

Copy the effects `.it` into your `res/`, then edit your **Makefile**. The effects module must be listed
**first** in `AUDIOFILES`, and you must add the `-f` flag:

```makefile
# before:
# AUDIOFILES  := res/song.it
# SMCONVFLAGS := -s -o $(SOUNDBANK) -V -b 5

AUDIOFILES  := res/effectssfx.it res/song.it     # effects FIRST, then your music
SMCONVFLAGS := -s -o $(SOUNDBANK) -V -b 5 -f      # -f = size-check for effects
```

## Step 2 — Rebuild the soundbank and read the IDs

```sh
rm -f res/soundbank.*        # force a clean regen
make musics
cat res/soundbank.h
```

You'll get one `MOD_*` per `.it`, in list order:

```c
#define MOD_EFFECTSSFX  0     // the effects module (index 0)
#define MOD_SONG        1     // your music is now index 1
```

Note your music module moved to index 1 — but the generated `#define MOD_SONG` tracks it, so
`spcLoad(MOD_SONG)` keeps working unchanged.

## Step 3 — The API

```c
void spcLoadEffect(u16 sfxIndex);              // load one effect sample into the sound chip
void spcEffect(u16 pitch, u16 sfxIndex, u8 volpan);   // play a loaded effect
```

- `sfxIndex` — which sample in the effects module (0..N-1).
- `pitch` — playback rate: **1 = 4 KHz, 2 = 8 KHz, 4 = 16 KHz, 8 = 32 KHz** (higher = higher-pitched).
- `volpan` — `volume*16 + pan`, e.g. `15*16 + 8` = full volume, centre pan.

## Step 4 — Init (⚠ the gotcha that matters)

`spcLoadEffect` does **not** load immediately — it *queues a message* for the sound driver, which only
runs when you call `spcProcess()`. If you `spcLoad`/`spcPlay` before the effect finishes loading, its ARAM
gets overwritten and **the effect silently never plays**. So pump the driver between each step:

```c
spcBoot();
/* ... video init ... */
spcSetBank(&SOUNDBANK__);

spcStop();
spcLoad(MOD_SONG);                                   // queue: load music
for (i = 0; i < 20; i++) { spcProcess(); WaitForVBlank(); }   // let it finish

spcLoadEffect(SFX_MATCH);                             // queue: load effect sample
for (i = 0; i < 20; i++) { spcProcess(); WaitForVBlank(); }   // let it finish  <-- do NOT skip

spcPlay(0);                                           // start the music
```

`#define SFX_MATCH 0` (or whichever sample index you want). Keep calling `spcProcess()` once per frame in
your main loop — that's already required for music.

## Step 5 — Trigger it from game logic

Set a flag where the event happens, play it once from the loop (don't call `spcEffect` deep inside
nested game logic — do it at the top level next to `spcProcess`):

```c
// in your match/score/hit code:
if (matched) { sfx = 1; }               // sfx is a global u8

// in the main loop, right after game_update():
if (sfx) { spcEffect(2 + combo, SFX_MATCH, 15*16 + 8); sfx = 0; }
//         ^ pitch rises with combo depth: a small, free "reward escalates" feel
```

That's the whole feature.

## Step 6 — Verify headless (you have no ears)

Running under an emulator with no audio capture, confirm the effect fired by reading the **S-DSP voice
state**, not by listening. A new effect key-on shows up as an extra active voice whose sample
(`brrAddress`) sits **outside your music's sample range**. Mesen2 Lua:

```lua
local s = emu.getState()
local n, fx = 0, 0
for v = 0, 7 do
  if (s["spc.dsp.voices["..v.."].envVolume"] or 0) > 0 then
    n = n + 1
    if (s["spc.dsp.voices["..v.."].brrAddress"] or 0) >= 7850 then fx = fx + 1 end
  end
end
-- before the match: n == 3 (music), fx == 0
-- on the match:     n jumps to 4, fx == 1   => the effect keyed on
```

In the real test the music voices sat at addresses ~7400–7700 and the effect at ~7900–8300, so a
threshold cleanly separates "music" from "effect fired". This is the "the screen (or speaker) lies, the
state doesn't" discipline applied to audio.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `spcEffect` plays **nothing** | `spcLoadEffect` didn't finish before `spcLoad`/`spcPlay` overwrote ARAM | pump `spcProcess()+WaitForVBlank()` ~20 frames after each load (Step 4) |
| Effect plays but is the wrong sound | `sfxIndex` points at a different sample | check `soundbank.h` / try index 0 |
| Music stops when effect plays | too few voices, or effect stole a music channel | acceptable for short SFX; snesmod re-uses a voice and the music resumes |
| No `MOD_*` for your effects | effects `.it` not first in `AUDIOFILES`, or `-f` missing | Step 1 |

## Full minimal example (music + one match SFX)

```c
#include <snes.h>
#include "../res/soundbank.h"          // defines MOD_EFFECTSSFX=0, MOD_SONG=1
extern char SOUNDBANK__;
#define SFX_MATCH 0
unsigned char sfx = 0, combo = 0;

int main(void) {
    unsigned char i;
    spcBoot();
    /* ... your video + game init ... */
    spcSetBank(&SOUNDBANK__);
    spcStop(); spcLoad(MOD_SONG);
    for (i = 0; i < 20; i++) { spcProcess(); WaitForVBlank(); }
    spcLoadEffect(SFX_MATCH);
    for (i = 0; i < 20; i++) { spcProcess(); WaitForVBlank(); }
    spcPlay(0);

    while (1) {
        /* ... game_update(): set sfx=1 and combo when a match happens ... */
        if (sfx) { spcEffect(2 + combo, SFX_MATCH, 15*16 + 8); sfx = 0; }
        /* ... draw ... */
        spcProcess();
        WaitForVBlank();
    }
    return 0;
}
```

Worked reference: `END_TO_END.md` (the COSMIC JAZZ match-3, where this drives a marimba whose pitch rises
with the cascade depth, alongside a screen shake + flash + mascot celebrate on every clear).
