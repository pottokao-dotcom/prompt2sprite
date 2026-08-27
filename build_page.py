#!/usr/bin/env python3
"""Build the diffusion-vs-SVG results page: process each Z-Image raster in-memory (strip bg -> crop ->
downscale -> quantise, free & palette-locked), base64-embed, emit a self-contained HTML for Artifact."""
import base64, io, os
from PIL import Image
import diffuse_quant, quant, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); RAW = f"{HERE}/zimage_raw"
PAL = diffuse_quant.load_palette(f"{HERE}/palettes/candy.hex")

def process(path, size, palette=None):
    s = diffuse_quant.crop_square(diffuse_quant.strip_bg(Image.open(path).convert("RGBA"), 40))
    if palette is not None:
        small = quant.DOWNSAMPLE["modal"](s, size)
        return quant.remap_to(small, palette)
    return quant.to_target(s, size, "modal_oklab")[0]

def d_png(img):
    b = io.BytesIO(); img.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def d_jpg(path, box=240):
    im = Image.open(path).convert("RGB"); im.thumbnail((box, box))
    b = io.BytesIO(); im.save(b, "JPEG", quality=82); return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

def ncol(img):
    a = np.array(img); op = a[..., 3] >= quant.A_OPAQUE
    return len(set(map(tuple, a[..., :3][op])))

SUBJECTS = [  # (raw file, label)
    ("A_coin_512", "gold coin"), ("A_fireball_512", "fireball"), ("A_rabbit_512", "jazz rabbit"),
    ("D_mint_512", "peppermint"), ("D_lolli_512", "lollipop"), ("D_gummy_512", "gummy bear"),
    ("D_choco_512", "chocolate"), ("D_donut_512", "donut"), ("D_orange_512", "orange slice"),
]
SWEEP = [("A_coin_512", 512), ("B_coin_256", 256), ("B_coin_128", 128), ("B_coin_64", 64)]
LADDER = ["coin", "rabbit", "mint"]; GENS = [32, 64, 128, 256, 512]
TIMING = {512: 2.12, 256: 0.91, 128: 0.61}   # measured gen seconds (Z-Image Turbo, GB10)
CANDY = [("D_mint_512", "peppermint"), ("D_lolli_512", "lollipop"), ("D_gummy_512", "gummy"),
         ("D_choco_512", "chocolate"), ("D_donut_512", "donut"), ("D_orange_512", "orange")]

def sprite_card(raw, label):
    p = f"{RAW}/{raw}.png"
    t32 = process(p, 32); t16 = process(p, 16)
    return f"""<figure class="card">
      <figcaption>{label}</figcaption>
      <div class="triptych">
        <div class="cell"><img class="raster" src="{d_jpg(p)}" alt="{label} raster"><span class="tag">raster 512</span></div>
        <div class="arrow">→</div>
        <div class="cell"><img class="px" style="width:128px" src="{d_png(t32)}" alt="{label} 32"><span class="tag">32 · {ncol(t32)}c</span></div>
        <div class="cell"><img class="px" style="width:128px" src="{d_png(t16)}" alt="{label} 16"><span class="tag">16 · {ncol(t16)}c</span></div>
      </div></figure>"""

def ladder_grid():
    head = "".join(f'<th>gen {g}<span class="mx">{"native ×1" if g==32 else "×"+str(g//32)}</span></th>' for g in GENS)
    rows = ""
    for s in LADDER:
        cells = ""
        for g in GENS:
            p = f"{HERE}/zimage_ladder/{s}_{g}.png"
            cls = " sweet" if g == 512 else (" speed" if g == 128 else (" dead" if g == 32 else ""))
            img = f'<img class="px" style="width:92px" src="{d_png(process(p,32))}">' if os.path.exists(p) else ""
            cells += f'<td class="lad{cls}">{img}</td>'
        rows += f'<tr><th class="rside">{s}</th>{cells}</tr>'
    times = " · ".join(f"{g}px <b>{TIMING[g]}s</b>" for g in (512, 256, 128))
    return (f'<div class="ladscroll"><table class="ladder"><tr><th></th>{head}</tr>{rows}</table></div>'
            f'<p class="time">gen time (Z-Image Turbo, GB10): {times} — below 128px fixed overhead dominates, so smaller barely saves.</p>')

def build():
    cards = "\n".join(sprite_card(r, l) for r, l in SUBJECTS)
    sweep = "\n".join(f'<div class="cell"><img class="px" style="width:112px" src="{d_png(process(f"{RAW}/{r}.png",16))}"><span class="tag">gen {g}px → 16</span></div>'
                      for r, g in SWEEP)
    lock = "\n".join(f"""<div class="lockrow"><span class="lockcap">{l}</span>
        <div class="cell"><img class="px" style="width:104px" src="{d_png(process(f'{RAW}/{r}.png',32))}"><span class="tag">free</span></div>
        <div class="cell"><img class="px" style="width:104px" src="{d_png(process(f'{RAW}/{r}.png',32,PAL))}"><span class="tag">locked</span></div></div>"""
        for r, l in CANDY)
    sw = "".join(f'<span class="chip" style="background:#{"".join(f"{c:02x}" for c in tuple(x))}"></span>' for x in PAL)
    return (HTML.replace("{{CARDS}}", cards).replace("{{SWEEP}}", sweep).replace("{{LOCK}}", lock)
            .replace("{{SWATCH}}", sw).replace("{{LADDER}}", ladder_grid()))

HTML = r"""<style>
:root{--bg:#141019;--panel:#1d1826;--ink:#ece7f2;--dim:#a99fb8;--gold:#ffd640;--pink:#ff5a79;--line:#2c2436;
  --tile1:#221b2e;--tile2:#1a1424;--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.6}
.wrap{max-width:1000px;margin:0 auto;padding:56px 24px 80px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold)}
h1{font-family:var(--mono);font-weight:700;font-size:clamp(28px,5vw,44px);line-height:1.1;margin:14px 0 8px;text-wrap:balance}
h1 .accent{color:var(--pink)}
.lede{color:var(--dim);font-size:18px;max-width:62ch;margin:0}
h2{font-family:var(--mono);font-size:13px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);
  margin:56px 0 6px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2 small{color:var(--dim);letter-spacing:.04em;text-transform:none;font-size:13px}
.note{color:var(--dim);max-width:64ch;margin:10px 0 22px}
.finding{display:flex;gap:14px;align-items:flex-start;background:linear-gradient(180deg,#241c30,#1c1626);
  border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:10px;padding:18px 20px;margin-top:26px}
.finding b{color:var(--gold)}
.grid{display:grid;gap:14px}
.card{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card figcaption{font-family:var(--mono);font-size:13px;color:var(--ink);letter-spacing:.04em;margin-bottom:10px}
.triptych{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.arrow{color:var(--dim);font-size:20px}
.cell{display:flex;flex-direction:column;align-items:center;gap:6px}
.tag{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.03em}
.raster{width:128px;height:128px;object-fit:contain;border-radius:6px;background:#0d0a12}
.px{image-rendering:pixelated;height:auto;border-radius:4px;
  background-image:linear-gradient(45deg,var(--tile1) 25%,transparent 25%,transparent 75%,var(--tile1) 75%),
  linear-gradient(45deg,var(--tile1) 25%,var(--tile2) 25%,var(--tile2) 75%,var(--tile1) 75%);
  background-size:16px 16px;background-position:0 0,8px 8px}
.strip{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}
.lockwrap{display:flex;flex-direction:column;gap:12px}
.lockrow{display:flex;align-items:center;gap:16px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 16px}
.lockcap{font-family:var(--mono);font-size:13px;width:96px;color:var(--ink)}
.swatch{display:flex;gap:3px;margin:10px 0 0}
.chip{width:20px;height:20px;border-radius:3px;border:1px solid #0004}
table{width:100%;border-collapse:collapse;margin-top:18px;font-size:15px}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}
td.v{font-family:var(--mono)}
.yes{color:#7ee081}.no{color:var(--pink)}.mid{color:var(--gold)}
.ladscroll{overflow-x:auto}
table.ladder{border-collapse:separate;border-spacing:6px;margin-top:16px}
table.ladder th{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:center;padding:0 2px;font-weight:400}
table.ladder th .mx{display:block;color:var(--gold);font-size:11px;letter-spacing:.05em;margin-top:2px}
table.ladder th.rside{color:var(--ink);text-align:right;padding-right:8px;font-size:13px}
td.lad{background:#0d0a12;border:1px solid var(--line);border-radius:8px;padding:6px;text-align:center;vertical-align:middle}
td.lad.sweet{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
td.lad.speed{border-color:var(--pink)}
td.lad.dead{border-color:#4a2733}
td.lad.sweet::after{content:"quality";display:block;font-family:var(--mono);font-size:10px;color:var(--gold);margin-top:3px}
td.lad.speed::after{content:"speed";display:block;font-family:var(--mono);font-size:10px;color:var(--pink);margin-top:3px}
.time{font-family:var(--mono);font-size:12.5px;color:var(--dim);margin:12px 0 0}.time b{color:var(--ink)}
.topbar{position:sticky;top:0;z-index:9;display:flex;justify-content:space-between;align-items:center;padding:12px 22px;background:rgba(18,16,26,.85);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);margin:-56px -24px 0}
.topbar a{font-family:var(--mono);text-decoration:none}.topbar .home{font-weight:700;color:var(--ink)}.topbar .home b{color:var(--pink)}
.topbar .ghl{font-size:13px;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 12px}.topbar .ghl:hover{border-color:var(--gold);color:var(--gold)}
.backhome{text-align:center;margin-top:40px}.backhome a{font-family:var(--mono);font-size:17px;color:var(--gold);text-decoration:none;border:1px solid var(--line);border-radius:10px;padding:11px 20px;display:inline-block;margin:6px}.backhome a:hover{border-color:var(--gold)}
.foot{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:14px;font-family:var(--mono)}
a{color:var(--gold)}
</style>
<div class="topbar"><a class="home" href="https://pottokao-dotcom.github.io/prompt2sprite/">prompt2<b>sprite</b></a>
  <a class="ghl" href="https://github.com/pottokao-dotcom/prompt2sprite" target="_blank" rel="noopener">★ View on GitHub ↗</a></div>
<div class="wrap">
  <div class="eyebrow">Experiment · 2026-08-27 · GX10</div>
  <h1>Z-Image Turbo → <span class="accent">SNES sprites</span></h1>
  <p class="lede">Can a diffusion model replace the LLM-draws-SVG front-end? Same subjects, same back-end
  (strip → crop → modal downscale → OKLab / BGR555), same judge. Generator: Z-Image Turbo (ComfyUI, nvfp4,
  10 steps). Downscale + palette: <code>diffuse_quant.py</code>.</p>

  <div class="finding"><div>▲</div><div><b>Headline.</b> Diffusion wins on raw sprite quality — its
  512px pixel-art is far richer than SVG, and downscaled to <b>32×32 it's genuinely better</b> (the coin
  keeps its star, the rabbit keeps shades + sax). But it confirms the SVG lessons rather than escaping
  them: it <b>cannot draw a true tiny grid</b> (it renders big, you downscale), and the <b>palette lock is
  a post-step</b>, not a model capability — done deterministically against a fixed bank.</div></div>

  <h2>The sprites <small>— raster 512 → 32 → 16, free palette</small></h2>
  <p class="note">Each drawn from one subject prompt. 32×32 is the sweet spot; 16×16 keeps the gist but
  loses fine features (the coin's star, the rabbit's sax) — the same resolution floor SVG hit.</p>
  <div class="grid">{{CARDS}}</div>

  <h2>Resolution floor <small>— H1: can it draw small directly?</small></h2>
  <p class="note">Same coin, <b>generated</b> at shrinking canvases, each then downscaled to 16. Below ~128px
  the model can't form the sprite — so "generate big, then downscale" is required (a bigger multiple than
  SVG's 4×), not a native small-grid output.</p>
  <div class="strip">{{SWEEP}}</div>

  <h2>How big to generate <small>— the efficiency sweet spot</small></h2>
  <p class="note">Same subject <b>generated</b> at each canvas, then downscaled to 32. The whole "×N
  multiple" question: <b>native ×1 (generate at 32) collapses</b> — diffusion can't form a sprite that
  small. <b>×2 (64px) already works</b>, and from <b>×4 (128px) up it's all good</b>. More source pixels =
  slightly crisper edges, so <b>512 is the quality pick</b>; ×4 is the throughput pick (~3.5× faster). The
  choice is only <em>how far above the target</em> to generate.</p>
  {{LADDER}}
  <div class="finding" style="border-left-color:var(--pink)"><div>◆</div><div><b>Two defaults, by priority.</b>
  <b>Quality-first → 512 → 32</b>: the most source detail before the shrink = the crispest edge, and at
  ~2s/sprite it's trivial for a game's asset set. <b>Scale/speed → ×4 (128)</b>: ~3.5× faster for a barely
  perceptible loss — worth it only when batching many. Native ×1 collapses. Either way the shrink also does
  transparency (bg-strip) and the BGR555 snap, so <code>diffuse_quant</code> runs on every path.</div></div>

  <h2>Palette lock <small>— H2: can we force a fixed bank?</small></h2>
  <p class="note">Not in the model — as a deterministic post-step. Each candy at 32, free colours vs. hard
  remapped to the <b>same 15-colour candy bank the SVG set converged to</b> (below). It works; the model's
  colours are ignored, every pixel snaps to a legal slot.</p>
  <div class="swatch">{{SWATCH}}</div>
  <div class="lockwrap" style="margin-top:14px">{{LOCK}}</div>

  <h2>Verdict</h2>
  <table>
    <tr><th>Question</th><th>Answer</th><th>What we saw</th></tr>
    <tr><td>Quality vs SVG (H3)</td><td class="v yes">diffusion wins</td><td>far richer 512px art; 32×32 clearly beats SVG, 16×16 comparable-to-better</td></tr>
    <tr><td>Draw true 8/16/32 directly (H1)</td><td class="v no">no</td><td>renders big; collapses below ~128px canvas → must downscale</td></tr>
    <tr><td>Lock the palette (H2)</td><td class="v mid">yes, in post</td><td>not a model feature; deterministic remap to a fixed bank works cleanly</td></tr>
    <tr><td>Whole-set coherence (H4)</td><td class="v mid">via shared bank</td><td>per-image model; one fixed/shared palette unifies the set, same as the SVG theme</td></tr>
  </table>

  <div class="backhome"><a href="https://pottokao-dotcom.github.io/prompt2sprite/">← prompt2sprite</a><a href="https://github.com/pottokao-dotcom/prompt2sprite" target="_blank" rel="noopener">GitHub repo ↗</a></div>
  <div class="foot">generator: Z-Image Turbo (nvfp4, ComfyUI @ GX10) · back-end: prompt2sprite/diffuse_quant.py ·
  judge: Claude Opus 4.8 · sprites are generated, no third-party assets</div>
</div>"""

if __name__ == "__main__":
    out = "/home/pottokao/.claude/jobs/c5cd7850/tmp/diffusion_vs_svg.html"
    open(out, "w").write(build()); print("wrote", out, os.path.getsize(out)//1024, "KB")
