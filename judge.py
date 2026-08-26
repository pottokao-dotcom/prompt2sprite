#!/usr/bin/env python3
"""judge — the eye in the sprite loop. Scores how recognisable a rendered sprite is as its subject,
so best-of-N picks by ACTUAL recognisability, not just the non-degenerate probe (which passes blobs).

Points at any OpenAI-compatible vision endpoint via VISION_URL / VISION_MODEL. If none is reachable,
score() returns None so the caller falls back to the non-degenerate probe — "nobody was looking" is
distinct from "looked bad".
"""
import base64, io, json, os, urllib.request
from PIL import Image

VISION_URL   = os.environ.get("VISION_URL",   "http://localhost:8001/v1/chat/completions")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen38")
_UP = 8   # nearest-upscale factor so the judge sees crisp pixels

PROMPT = ("This is a small pixel-art game sprite meant to depict: {subj}. "
          "Judge ONLY how instantly recognisable it is as that thing (ignore art beauty). "
          "A screen that is one flat blob or a generic geometric shape (a plain square, diamond, "
          "triangle) is NOT recognisable. Answer strictly as JSON: "
          '{{"score": <0-10 integer>, "seen": "<3-6 words: what it actually looks like>"}}')

def _png_b64(img):
    im = img.convert("RGBA"); im = im.resize((im.width*_UP, im.height*_UP), Image.NEAREST)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    buf = io.BytesIO(); Image.alpha_composite(bg, im).convert("RGB").save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()

def score(img, subject, timeout=40):
    """-> (score 0-10, seen str) or None if no judge reachable / call failed."""
    body = json.dumps({"model": VISION_MODEL, "max_tokens": 120,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT.format(subj=subject)},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png_b64(img)}}]}]}).encode()
    try:
        r = urllib.request.Request(VISION_URL, body, {"Content-Type": "application/json"})
        txt = json.loads(urllib.request.urlopen(r, timeout=timeout).read())["choices"][0]["message"]["content"]
        m = json.loads(txt[txt.find("{"):txt.rfind("}")+1])
        return int(m.get("score", 0)), str(m.get("seen", ""))[:40]
    except Exception:
        return None

def available():
    try:
        base = VISION_URL.rsplit("/v1/", 1)[0]
        urllib.request.urlopen(base + "/v1/models", timeout=5).read()
        # probe a 1px image to confirm the endpoint actually accepts vision input
        return score(Image.new("RGBA", (4, 4), (200, 40, 40, 255)), "a red square", timeout=15) is not None
    except Exception:
        return False

if __name__ == "__main__":
    import sys
    print("judge available:", available(), "@", VISION_URL, VISION_MODEL)
