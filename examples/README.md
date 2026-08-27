# Examples — one concept → a whole sprite set

The beginner entry point: give **one game concept**, get a **whole coherent sprite set** (an LLM plans
the pieces + a hero, each is drawn, and the set is locked to one shared palette). Two versions — pick by
what hardware you have:

| script | draws with | needs a GPU? | quality | you need |
|---|---|---|---|---|
| **`make_set_svg.py`** | an LLM emitting SVG | **no** — pure Python | good | just a text-LLM endpoint |
| **`make_set_diffusion.py`** | Z-Image Turbo (ComfyUI) | **yes** | **better** | a GPU running ComfyUI + a Z-Image workflow |

Both use a text LLM only to *plan* the set (`SFC_LLM_URL`, default `http://localhost:8001`); the drawing
is where they differ.

## A · Pure Python, no GPU — `make_set_svg.py`

```sh
pip install pillow cairosvg numpy
export SFC_LLM_URL=http://localhost:8001        # any OpenAI-compatible LLM that can emit SVG
python3 make_set_svg.py "a candy match-3 game"
python3 make_set_svg.py "an underwater treasure hunt" --size 16 --pieces 6
```

## B · GPU path (higher quality) — `make_set_diffusion.py`

Needs a **ComfyUI** server running a **Z-Image Turbo** text-to-image workflow. Point the script at it:

```sh
export SFC_LLM_URL=http://localhost:8001                     # text LLM to plan the set
export COMFY_URL=http://localhost:8188                       # your ComfyUI server (can be another host)
export COMFY_WORKFLOW=/path/to/your_zimage_turbo.json        # a saved Z-Image Turbo workflow
# if your workflow's node ids differ from the Lumina2/Z-Image defaults, override:
#   COMFY_NODE_PROMPT=84:66  COMFY_NODE_LATENT=79  COMFY_NODE_SEEDS=81,81b
python3 make_set_diffusion.py "a candy match-3 game" --mult 8
```

The prompt goes into the workflow's `user_prompt` field; the latent size is set to `mult × target`
(×8 is a good default, ×16 for max quality — see [`../DIFFUSION_VS_SVG.md`](../DIFFUSION_VS_SVG.md)).

## What you get

Either script writes a folder `set_<concept>/`:

```
piece0.png … pieceN.png   the collectible / match-3 pieces (target size)
hero.png                  the main character (32²)
palette.hex               the one shared 15-colour bank the whole set is locked to
preview.png               a contact sheet — open this first
```

Every sprite in the set shares one hardware-legal palette, so it's coherent and ready for a match-3
board. From here: feed the sprites to `gfx4snes` (see [`../example_cosmicjazz/`](../example_cosmicjazz))
for the CHR bitplane, or just use the PNGs.

> These are the *examples*. The reusable **tools** they call live at the repo root
> (`make_sprite.py`, `quant.py`, `diffuse_quant.py`); the methodology is in
> [`../METHODOLOGY.md`](../METHODOLOGY.md).
