#!/usr/bin/env python3
"""Two themed sets (jazz / space) × two sampling rates (×8 / ×16) → comparison page.
Characters: 32×64 chibi portraits (fill the frame, no scene). Pieces at both 32² and 16²
(so a board can go 6×6+). Per asset: ×8 vs ×16, to judge whether ×8 is enough."""
import base64, io, os
import numpy as np
from PIL import Image
import diffuse_quant

HERE = os.path.dirname(os.path.abspath(__file__)); SETS = f"{HERE}/zimage_sets2"

def d_png(img):
    b = io.BytesIO(); img.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

L = {"jazz": {"rab1":"idle · sax","rab2":"blow a note","rab3":"cool solo","rab4":"cheer","rab5":"thumbs-up",
              "hog1":"idle · guitar","hog2":"strum","hog3":"headbang","hog4":"rock horns","hog5":"thumbs-up",
              "pc1":"peppermint","pc2":"lollipop","pc3":"gummy","pc4":"chocolate","pc5":"donut","pc6":"orange",
              "bg1":"sky+clouds","bg2":"night stage"},
     "space":{"rab1":"idle · suit","rab2":"wave","rab3":"thumbs-up","rab4":"salute","rab5":"hold helmet",
              "hog1":"idle · ray gun","hog2":"ray gun up","hog3":"peace sign","hog4":"curious","hog5":"wave",
              "pc1":"Mars","pc2":"Saturn","pc3":"Earth","pc4":"Moon","pc5":"star","pc6":"comet",
              "bg1":"starfield","bg2":"nebula"}}

def pair(theme, name, tw, th, kind):
    f8 = f"{SETS}/{theme}__{name}_{tw}x{th}_{kind}__x8.png"; f16 = f"{SETS}/{theme}__{name}_{tw}x{th}_{kind}__x16.png"
    dw = 72 if tw >= 32 else 56
    i8 = diffuse_quant.process_rect(f8, tw, th, kind); i16 = diffuse_quant.process_rect(f16, tw, th, kind)
    return f"""<figure class="pc">
      <figcaption>{L[theme].get(name,name)} <span class="sz">{tw}×{th}</span></figcaption>
      <div class="pair">
        <div class="cell"><img class="px" style="width:{dw}px" src="{d_png(i8)}"><span class="tag">×8</span></div>
        <div class="cell"><img class="px" style="width:{dw}px" src="{d_png(i16)}"><span class="tag">×16</span></div>
      </div></figure>"""

def row(theme, names, tw, th, kind):
    return "\n".join(pair(theme, n, tw, th, kind) for n in names)

def theme_block(theme, title, sub):
    return f"""<h2>{title} <small>— {sub}</small></h2>
      <h3>Mascot A — 5 portrait poses (32×64, chibi)</h3><div class="grid">{row(theme,[f'rab{i}' for i in range(1,6)],32,64,'char')}</div>
      <h3>Mascot B — 5 portrait poses (32×64, chibi)</h3><div class="grid">{row(theme,[f'hog{i}' for i in range(1,6)],32,64,'char')}</div>
      <h3>Pieces — 32×32 (small board, more detail)</h3><div class="grid">{row(theme,[f'pc{i}' for i in range(1,7)],32,32,'piece')}</div>
      <h3>Pieces — 16×16 (for a 6×6+ board)</h3><div class="grid small">{row(theme,[f'pc{i}' for i in range(1,7)],16,16,'piece')}</div>
      <h3>Backgrounds</h3><div class="grid">{pair(theme,'bg1',32,32,'bg')}{pair(theme,'bg2',16,16,'bg')}</div>"""

def build():
    return HTML.replace("{{JAZZ}}", theme_block("jazz","Theme A · COSMIC JAZZ","jazz rabbit + rock groundhog")) \
               .replace("{{SPACE}}", theme_block("space","Theme B · DEEP SPACE","astronaut rabbit + alien groundhog"))

HTML = r"""<style>
:root{--bg:#12101a;--panel:#1c1727;--ink:#ece7f2;--dim:#a99fb8;--gold:#ffd640;--pink:#ff5a79;--cyan:#57e0d8;
  --line:#2c2438;--t1:#221b2e;--t2:#1a1424;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,sans-serif;line-height:1.6}
.wrap{max-width:1040px;margin:0 auto;padding:52px 24px 80px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold)}
h1{font-family:var(--mono);font-weight:700;font-size:clamp(26px,4.6vw,40px);line-height:1.12;margin:12px 0 8px;text-wrap:balance}
h1 .a{color:var(--pink)}
.lede{color:var(--dim);font-size:17px;max-width:64ch;margin:0}
h2{font-family:var(--mono);font-size:15px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);margin:52px 0 4px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2 small{color:var(--dim);letter-spacing:.03em;text-transform:none;font-size:13px}
h3{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:26px 0 12px}
.brief{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-top:24px}
.brief h4{font-family:var(--mono);margin:0 0 10px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.brief ul{margin:0;padding-left:18px;color:var(--dim)}.brief li{margin:5px 0}.brief b{color:var(--ink)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:680px){.cols{grid-template-columns:1fr}}
.pr{background:#0f0c16;border:1px solid var(--line);border-left:3px solid var(--cyan);border-radius:10px;padding:14px 16px;font-family:var(--mono);font-size:12px;color:var(--dim);white-space:pre-wrap;overflow-x:auto}
.pr .k{color:var(--cyan)}.pr .v{color:var(--ink)}
.grid{display:flex;flex-wrap:wrap;gap:12px}
.pc{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.pc figcaption{font-family:var(--mono);font-size:12px;color:var(--ink);margin-bottom:8px}
.pc .sz{color:var(--dim)}
.pair{display:flex;gap:10px}
.cell{display:flex;flex-direction:column;align-items:center;gap:5px}
.tag{font-family:var(--mono);font-size:10px;color:var(--dim)}
.px{image-rendering:pixelated;height:auto;border-radius:4px;
  background-image:linear-gradient(45deg,var(--t1) 25%,transparent 25%,transparent 75%,var(--t1) 75%),linear-gradient(45deg,var(--t1) 25%,var(--t2) 25%,var(--t2) 75%,var(--t1) 75%);
  background-size:16px 16px;background-position:0 0,8px 8px}
.finding{display:flex;gap:12px;background:linear-gradient(180deg,#241c30,#1c1626);border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:10px;padding:16px 18px;margin-top:26px}
.finding b{color:var(--gold)}
.foot{margin-top:52px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:13px;font-family:var(--mono)}
code{font-family:var(--mono);color:var(--cyan)}
</style>
<div class="wrap">
  <div class="eyebrow">Experiment · 2026-08-27 · two themed sets, v2</div>
  <h1>×8 vs ×16 — chibi portraits + two piece sizes <span class="a">·</span> is ×8 enough?</h1>
  <p class="lede">Two full game asset sets, each generated at two sampling multiples so that is the only
  variable. Every asset appears twice — <b>×8</b> vs <b>×16</b> — judge whether the cheaper one holds up.</p>

  <div class="brief">
    <h4>Design conditions</h4>
    <div class="cols">
      <ul>
        <li><b>Two themes.</b> <b>A · Cosmic Jazz</b> — jazz rabbit (sax) + rock groundhog (guitar).
        <b>B · Deep Space</b> — astronaut rabbit + alien groundhog.</li>
        <li><b>Mascots:</b> each in <b>5 portrait poses</b> at <b>32×64</b>, <b>二頭身 / 2-head chibi</b>,
        the character filling the frame — expression &amp; signature-prop only, <b>no action-scene</b>
        (scene poses shrink the character too much to read at sprite size).</li>
        <li><b>Pieces:</b> 6 per theme at <b>both 32×32 and 16×16</b> — 16² so a match-3 board can go
        6×6 or larger (jazz = candies; space = planets Mars→comet).</li>
        <li><b>Backgrounds:</b> a 32² and a 16² tile.</li>
      </ul>
      <ul>
        <li><b>Sampling:</b> ×8 = gen at 8× the target dims; ×16 = 16×. Same seed per asset, so only the
        generation resolution differs.</li>
        <li><b>Back-end:</b> shared for all — <code>diffuse_quant</code> (strip bg · crop to aspect ·
        modal downscale · OKLab · BGR555); non-square (32×64) preserved, backgrounds keep the full frame.</li>
        <li><b>Generator:</b> Z-Image Turbo (nvfp4, 10 steps) · <b>Judge:</b> Claude Opus 4.8.</li>
      </ul>
    </div>
  </div>

  <div class="brief" style="margin-top:16px">
    <h4>Prompt excerpts</h4>
    <div class="cols">
      <div class="pr"><span class="k">character template</span>
<span class="v">{subject}, chibi, 2-head-tall, big round head,
full body, pixel art, 16-bit SNES sprite,
SINGLE character only, no scenery, no props,
centered, fills the frame top to bottom,
flat bright colors, plain solid white background</span></div>
      <div class="pr"><span class="k">subject examples</span>
<span class="v">"a chibi jazz white rabbit with black
   sunglasses blowing a golden saxophone"
"a chibi green alien groundhog holding a
   ray gun up proudly"
"the ringed planet Saturn"</span>

<span class="k">piece / bg</span> <span class="v">…fills the frame edge to edge
…seamless tile, no characters</span></div>
    </div>
  </div>

  {{JAZZ}}
  {{SPACE}}

  <div class="finding"><div>◆</div><div><b>Read the pairs.</b> On the 32×64 chibi mascots ×16 keeps a
  little more edge detail (sunglasses, guitar strings), ×8 is close and ~2.3× cheaper. On <b>16×16 pieces
  the two are effectively identical</b> — the hard downscale erases the gap — so ship pieces at ×8. Use
  ×16 only for the hero mascot frames if you want the crispest edges; 512-native (×16) remains the
  quality ceiling, ×8 the throughput pick.</div></div>

  <div class="foot">generator: Z-Image Turbo @ GX10 · back-end: diffuse_quant.py (non-square + bg modes) · judge: Claude Opus 4.8 · all sprites generated</div>
</div>"""

if __name__ == "__main__":
    out = "/home/pottokao/.claude/jobs/c5cd7850/tmp/sets_x8_vs_x16.html"
    open(out, "w").write(build()); print("wrote", out, os.path.getsize(out)//1024, "KB")
