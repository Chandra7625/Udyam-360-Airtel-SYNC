"""Shows the REAL Groq error for the blurry K04 scan.   python scripts/debug_vision.py"""
import os, sys, base64, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
from groq import Groq
from modules.ocr import _GEMINI_PROMPT, _jpeg_b64

key = os.getenv("GROQ_API_KEY", "")
print("key loaded:", bool(key), "| model:", os.getenv("GROQ_VISION_MODEL"))
c = Groq(api_key=key)
ids = [m.id for m in c.models.list().data]
print("model exists:", os.getenv("GROQ_VISION_MODEL") in ids)
print("candidate vision models on your account:", [i for i in ids if any(t in i.lower() for t in ("qwen", "scout", "maverick", "vision", "vl"))])
img = _jpeg_b64((ROOT / "data/kyc_documents/K04_gst_certificate.png").read_bytes())
msg = [{"role": "user", "content": [{"type": "text", "text": _GEMINI_PROMPT},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img}}]}]
for label, kw in [("json mode", {"response_format": {"type": "json_object"}}), ("plain", {})]:
    try:
        r = c.chat.completions.create(model=os.getenv("GROQ_VISION_MODEL"), messages=msg, temperature=0, **kw)
        print(f"\n[{label}] OK ->", (r.choices[0].message.content or "")[:600]); break
    except Exception as e:
        print(f"\n[{label}] FAILED -> {type(e).__name__}: {e}")
