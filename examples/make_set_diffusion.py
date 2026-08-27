#!/usr/bin/env python3
"""make_set_diffusion — beginner one-liner (NEEDS A GPU + ComfyUI): ONE game concept → a whole coherent
sprite SET, drawn by a diffusion model (Z-Image Turbo) instead of SVG. Higher quality, needs a GPU.

    python3 make_set_diffusion.py "a candy match-3 game"
    python3 make_set_diffusion.py "an underwater treasure hunt" --size 32 --mult 8

Requirements (this is the GPU path — the pure-Python one is make_set_svg.py):
  • a ComfyUI server running a Z-Image Turbo text-to-image workflow      (set COMFY_URL, default :8188)
  • that workflow saved as JSON                                          (set COMFY_WORKFLOW)
  • an OpenAI-compatible text LLM to plan the set                        (SFC_LLM_URL, default :8001)

An LLM plans the set (palette theme + N pieces + a hero); each is generated at ×`mult` the target size,
downscaled + quantised by diffuse_quant, then the whole set is locked to one shared palette.
"""
import json, os, re, sys, time, copy, argparse, urllib.request, urllib.parse, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # import root tools
import diffuse_quant, quant
from make_set_svg import plan, contact   # reuse the planner + contact-sheet

COMFY_URL = os.getenv("COMFY_URL", "http://localhost:8188")
WF_PATH   = os.getenv("COMFY_WORKFLOW", "")
# node ids for a Z-Image Turbo / Lumina2 workflow (override via env if yours differ)
N_PROMPT  = os.getenv("COMFY_NODE_PROMPT", "84:66")   # CLIPTextEncodeLumina2 · field = user_prompt
N_LATENT  = os.getenv("COMFY_NODE_LATENT", "79")      # EmptySD3LatentImage · width/height
N_SEEDS   = os.getenv("COMFY_NODE_SEEDS", "81,81b").split(",")

def _load_wf():
    if not WF_PATH:
        sys.exit("set COMFY_WORKFLOW=/path/to/your_zimage_turbo_workflow.json (see the docstring)")
    return json.load(open(WF_PATH))

def _submit(wf):
    r = urllib.request.Request(f"{COMFY_URL}/prompt", json.dumps({"prompt": wf}).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["prompt_id"]

def _wait(pid, timeout=180):
    t = time.time()
    while time.time()-t < timeout:
        h = json.loads(urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=15).read())
        if pid in h and h[pid].get("outputs"):
            for o in h[pid]["outputs"].values():
                if "images" in o: return o["images"][0]
        time.sleep(0.4)
    raise TimeoutError("ComfyUI job timed out")

PROMPT = ("{s}, pixel art, 16-bit SNES sprite, single game asset, centered, fills the frame, "
          "flat bright colors, hard edges, crisp pixels, limited palette, plain solid white background")

def gen(wf0, subject, tw, th, mult, tmp):
    wf = copy.deepcopy(wf0)
    wf[N_PROMPT]["inputs"]["user_prompt"] = PROMPT.format(s=subject)
    wf[N_LATENT]["inputs"]["width"] = tw*mult; wf[N_LATENT]["inputs"]["height"] = th*mult
    for sn in N_SEEDS:
        ip = wf.get(sn, {}).get("inputs", {})
        if "seed" in ip: ip["seed"] = abs(hash(subject)) % 100000
        if "noise_seed" in ip: ip["noise_seed"] = abs(hash(subject)) % 100000
    img = _wait(_submit(wf))
    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
    dst = os.path.join(tmp, re.sub(r"[^a-z0-9]+", "_", subject.lower())[:16]+".png")
    urllib.request.urlretrieve(f"{COMFY_URL}/view?{q}", dst); return dst   # download over HTTP (works remote)

def make_set(concept, size, n, mult, out):
    os.makedirs(out, exist_ok=True); wf0 = _load_wf()
    tmp = tempfile.mkdtemp()
    p = plan(concept, n); theme = p.get("palette_theme", ""); pieces = p["pieces"][:n]; hero = p.get("hero")
    print(f"■ concept : {concept}\n■ theme   : {theme}\n■ pieces  : {', '.join(pieces)}\n■ hero    : {hero}\n"
          f"■ backend : diffusion (Z-Image Turbo @ {COMFY_URL}), ×{mult}\n")
    raw = []
    for subj in pieces:
        print(f"  gen piece: {subj}", flush=True)
        r = gen(wf0, f"{subj}, {theme}", size, size, mult, tmp)
        raw.append((subj, diffuse_quant.process_rect(r, size, size, "spr")))
    if hero:
        print(f"  gen hero : {hero}", flush=True)
        r = gen(wf0, f"a chibi {hero}, {theme}", 32, 32, mult, tmp)
        raw.append((hero, diffuse_quant.process_rect(r, 32, 32, "spr")))
    master = quant.shared_palette([im for _, im in raw], 15)
    final = [(lab, quant.remap_to(im, master)) for lab, im in raw]
    for i, (lab, im) in enumerate(final):
        im.save(f"{out}/{'hero' if lab == hero else f'piece{i}'}.png")
    open(f"{out}/palette.hex", "w").write("\n".join("#%02x%02x%02x" % tuple(int(v) for v in c) for c in master)+"\n")
    contact(final, f"{out}/preview.png")
    print(f"\n✓ set ready in {out}/  ({len(final)} sprites · one shared palette · diffusion)\n  open {out}/preview.png")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("concept", help='a game concept, e.g. "a candy match-3 game"')
    ap.add_argument("--size", type=int, default=16, help="piece size (16 or 32)")
    ap.add_argument("--pieces", type=int, default=6)
    ap.add_argument("--mult", type=int, default=8, help="generate at mult× the target (8 or 16)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or "set_" + re.sub(r"[^a-z0-9]+", "_", a.concept.lower())[:20].strip("_")
    make_set(a.concept, a.size, a.pieces, a.mult, out)
