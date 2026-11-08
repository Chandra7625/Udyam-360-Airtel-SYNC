"""Document OCR for Smart KYC.

Pipeline (first that works wins):
  1. Local OCR (RapidOCR, `pip install rapidocr-onnxruntime`, no system binary) + label/geometry parser.
  2. If the scan is blurry / low-confidence and GROQ_API_KEY (or GEMINI_API_KEY) is set -> vision-LLM extraction.
  3. Otherwise return whatever was read, flagged low-confidence, so the KYC screen lets the user correct it.

Every extractor returns the same structure:
  {"doc_type": "gst|udyam|signatory_id|address_proof|unknown",
   "fields": {name: value}, "confidence": {name: 0..1}, "quality": {"sharpness": x, "mean_conf": y, "blurry": bool},
   "engine": "local|groq|gemini|none", "warnings": [str]}
"""
from __future__ import annotations
import io, json, os, re
from functools import lru_cache

# ---------------- document schemas ----------------
SCHEMAS = {
    "gst": {"mode": "right", "labels": {
        "gstin": r"^gstin", "legal_name": r"^legalname", "trade_name": r"^tradename",
        "constitution": r"^constitution", "address": r"^addressofprincipal",
        "date_of_liability": r"^dateofliability", "registration_type": r"^typeofregistration"},
        "multiline": {"address"}},
    "udyam": {"mode": "right", "labels": {
        "udyam_number": r"^udyamreg", "enterprise_name": r"^enterprisename", "major_activity": r"^majoractivity",
        "city": r"^city", "state": r"^state", "date_of_registration": r"^dateofregistration"},
        "multiline": set()},
    "signatory_id": {"mode": "below", "labels": {
        "name": r"^name$", "designation": r"^designation", "business": r"^forbusiness",
        "id_number": r"^idno", "valid_till": r"^validtill"}, "multiline": set()},
    "address_proof": {"mode": "right", "labels": {
        "consumer_no": r"^consumerno", "billed_to": r"^billedto", "supply_address": r"^supplyaddress",
        "bill_date": r"^billdate", "units": r"^unitsconsumed", "amount_due": r"^amountdue"},
        "multiline": {"supply_address"}},
}
FILE_HINT = {"gst": "gst_certificate", "udyam": "udyam_certificate", "signatory_id": "signatory_id", "address_proof": "address_proof"}
SHARPNESS_MIN = 120.0      # Laplacian variance; calibrated on the specimen set (blurred K04 scores far lower)
MEAN_CONF_MIN = 0.90


def _key(s: str) -> str: return re.sub(r"[^a-z]", "", s.lower())


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def local_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def sharpness(img) -> float:
    """Variance of a Laplacian over the grayscale image. Low => blurry."""
    import numpy as np
    g = np.asarray(img.convert("L"), dtype=float)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def deskew(img, max_angle: float = 12.0):
    """Straighten a tilted scan. Picks the rotation whose text rows are most sharply separated
    (max variance of the horizontal projection). Returns (image, angle_degrees)."""
    import numpy as np
    from PIL import Image
    small = img.convert("L"); small.thumbnail((500, 700))
    dark = (np.asarray(small) < 110)
    best, best_a = -1.0, 0.0
    a = -max_angle
    while a <= max_angle + 1e-9:
        r = Image.fromarray((dark * 255).astype("uint8")).rotate(a, resample=Image.BILINEAR, fillcolor=0)
        v = float(np.asarray(r).sum(axis=1).astype(float).var())
        if v > best: best, best_a = v, a
        a += 0.5
    if abs(best_a) < 0.75: return img, 0.0
    return img.rotate(best_a, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)), best_a


def _tidy(v: str) -> str:
    v = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", v)          # VindhyaTours -> Vindhya Tours
    v = re.sub(r"\s*&\s*", " & ", v)
    v = re.sub(r",(?=\S)", ", ", v)
    return re.sub(r"\s+", " ", v).strip()


def _detect_type(lines, filename: str = "") -> str:
    head = " ".join(l["text"] for l in lines if l["y"] < 200).lower()
    for t, kw in (("gst", "gst"), ("udyam", "udyam"), ("signatory_id", "signatory"),
                  ("address_proof", "bill")):
        if kw in head: return t
    if any(w in head for w in ("electricity", "water", "gas", "utility", "telephone")): return "address_proof"
    fn = filename.lower()
    for t, hint in FILE_HINT.items():
        if hint in fn: return t
    return "unknown"


def strip_watermark(img):
    """Specimens carry a pink diagonal watermark that overlaps labels. Text is neutral dark, the
    watermark is red-tinted, so whiting out red-tinted pixels removes it. Sharp scans only."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("RGB")).astype(int)
    light = a.mean(axis=2) > 165      # watermark is light pink; text is dark
    a[((a[..., 0] - (a[..., 1] + a[..., 2]) / 2) > 14) & light] = 255
    return Image.fromarray(a.astype("uint8"))


def _read_lines(img, clean: bool = True):
    import numpy as np
    if clean: img = strip_watermark(img)
    res, _ = _engine()(np.asarray(img.convert("RGB")))
    out = []
    for box, txt, conf in (res or []):
        t = txt.strip()
        if re.search(r"SPECIMEN|NOT A VALID|VALID DOC|THETIC", t.upper().replace(" ", "")) and len(t) > 8: continue  # watermark
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append({"text": t, "conf": float(conf), "x": min(xs), "x1": max(xs), "y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys)})
    return sorted(out, key=lambda l: (l["y"], l["x"]))


def _parse(lines, doc_type, width):
    sch = SCHEMAS[doc_type]; fields, conf = {}, {}
    labels = []
    for l in lines:
        for fname, rx in sch["labels"].items():
            if re.match(rx, _key(l["text"])) and fname not in [n for n, _ in labels]:
                labels.append((fname, l)); break
    label_lines = {id(l) for _, l in labels}
    gap = sorted(b["y"] - a["y"] for (_, a), (_, b) in zip(labels, labels[1:]))
    rowgap = gap[len(gap) // 2] if gap else 52
    for i, (fname, lab) in enumerate(labels):
        if sch["mode"] == "right":
            nxt_y = labels[i + 1][1]["y"] if i + 1 < len(labels) else lab["y"] + rowgap * 2
            lim = nxt_y - 8 if fname in sch["multiline"] else lab["y"] + rowgap * 0.45
            cands = [l for l in lines if id(l) not in label_lines and l["x"] > max(lab["x1"] * 0.9, width * 0.33)
                     and lab["y"] - rowgap * 0.4 <= l["y"] <= lim]
            cands.sort(key=lambda l: l["y"])
            if fname in sch["multiline"] and cands:
                val = "".join(c["text"] for c in cands)          # hard-wrapped mid-word in the specimens
            else:
                val = cands[0]["text"] if cands else ""
        else:  # below
            cands = [l for l in lines if id(l) not in label_lines and abs(l["x"] - lab["x"]) < 25 and 0 < l["y"] - lab["y"] < rowgap * 1.2]
            cands.sort(key=lambda l: l["y"]); val = cands[0]["text"] if cands else ""
            cands = cands[:1]
        if val:
            fields[fname] = _tidy(val); conf[fname] = round(min(c["conf"] for c in cands), 3)
        else:
            fields[fname] = ""; conf[fname] = 0.0
    return fields, conf


# ---------------- GSTIN repair (blurry scans only) ----------------
_D2L = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
_L2D = {v: k for k, v in _D2L.items()}


def _gstin_positional(g: str) -> str:
    g = re.sub(r"[^A-Z0-9]", "", g.upper())
    if len(g) != 15: return g
    out = []
    for i, c in enumerate(g):
        if i in (0, 1, 7, 8, 9, 10): out.append(_L2D.get(c, c))
        elif i in (2, 3, 4, 5, 6, 11): out.append(_D2L.get(c, c))
        elif i == 13: out.append("Z")
        else: out.append(c)
    g2 = "".join(out)
    # checksum char (index 14) may be 0-9/A-Z: only resolve O/0 and I/1 look-alikes using the checksum itself
    from modules.kyc_checks import gstin_checksum_char, gstin_checksum_ok
    try:
        if len(g2) == 15 and not gstin_checksum_ok(g2) and g2[14] in "O0I1" and g2[:14].isalnum():
            exp = gstin_checksum_char(g2[:14])
            if exp in "O0I1" and exp != g2[14] and {exp, g2[14]} in ({"O", "0"}, {"I", "1"}):
                g2 = g2[:14] + exp
    except ValueError:
        pass
    return g2


def repair_gstin(g: str, is_registered) -> tuple[str, bool]:
    """Only used when the scan is blurry. Try single-character confusions until checksum+registry agree."""
    from modules.kyc_checks import gstin_checksum_ok
    g = _gstin_positional(g)
    if len(g) != 15 or (gstin_checksum_ok(g) and is_registered(g)): return g, False
    alts = {**_D2L, **_L2D, "H": "N", "N": "H", "U": "V", "V": "U"}
    hits = []
    for i, c in enumerate(g):
        for a in {alts.get(c, "")} - {""}:
            cand = g[:i] + a + g[i + 1:]
            if gstin_checksum_ok(cand) and is_registered(cand): hits.append(cand)
    return (hits[0], True) if len(hits) == 1 else (g, False)


def suggest_gstin_from_registry(fields: dict) -> str | None:
    """Blurry-scan helper: the ID is unreadable but names/address often are. Return the registry GSTIN
    ONLY if exactly one record matches full legal name + state code + address. Caller must flag it for confirmation."""
    try:
        import pandas as pd
        from pathlib import Path
        from modules.kyc_checks import _norm_full, _ratio, addresses_match
        reg = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "mock_gstin_registry.csv")
        legal = fields.get("legal_name") or fields.get("trade_name") or ""
        if not legal: return None
        st = re.sub(r"\D", "", (fields.get("gstin") or "")[:2])
        hits = []
        for r in reg.itertuples():
            if _ratio(_norm_full(legal), _norm_full(r.legal_name)) < 0.93: continue
            if len(st) == 2 and r.gstin[:2] != st: continue
            if fields.get("address") and not addresses_match(fields["address"], r.principal_place_of_business, 0.85): continue
            hits.append(r.gstin)
        return hits[0] if len(hits) == 1 else None
    except Exception:
        return None


# ---------------- Gemini vision fallback ----------------
_GEMINI_PROMPT = ("Extract the fields from this Indian business KYC specimen document. Return ONLY JSON: "
                  '{"doc_type": "gst|udyam|signatory_id|address_proof", "fields": {...}}. Field names by type: '
                  "gst: gstin, legal_name, trade_name, constitution, address, date_of_liability, registration_type; "
                  "udyam: udyam_number, enterprise_name, major_activity, city, state, date_of_registration; "
                  "signatory_id: name, designation, business, id_number, valid_till; "
                  "address_proof: consumer_no, billed_to, supply_address, bill_date, units, amount_due. "
                  "Dates as YYYY-MM-DD. Use an empty string for any field that is blank or unreadable. Do not guess.")


def _parse_vision_json(txt: str) -> dict | None:
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()      # reasoning models may emit this
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m: return None
    d = json.loads(m.group(0))
    return {"doc_type": d.get("doc_type", "unknown"), "fields": {k: str(v or "") for k, v in d.get("fields", {}).items()}}


def _jpeg_b64(image_bytes: bytes) -> str:
    """Groq limits base64 images to 4 MB: re-encode as a compact JPEG."""
    import base64
    from PIL import Image
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB"); im.thumbnail((1600, 2200))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


LAST_VISION_ERROR = ""


def extract_groq(image_bytes: bytes) -> dict | None:
    """Vision fallback on Groq. Model is configurable: GROQ_VISION_MODEL (default qwen/qwen3.8-27b;
    check console.groq.com/docs/vision for the current vision-capable models)."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key: return None
    try:
        from groq import Groq
        client = Groq(api_key=key)
        r = client.chat.completions.create(
            model=os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b"), temperature=0, max_completion_tokens=2000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _GEMINI_PROMPT},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _jpeg_b64(image_bytes)}}]}])
        out = _parse_vision_json(r.choices[0].message.content)
        if not out: raise ValueError("model reply had no JSON: " + (r.choices[0].message.content or "")[:200])
        return out
    except Exception as e:
        global LAST_VISION_ERROR
        LAST_VISION_ERROR = f"Groq: {type(e).__name__}: {str(e)[:300]}"
        return None


def extract_gemini(image_bytes: bytes, mime: str = "image/png") -> dict | None:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key: return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        r = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), _GEMINI_PROMPT])
        return _parse_vision_json(r.text)
    except Exception:
        return None


def extract_vision(image_bytes: bytes, filename: str = "") -> tuple[dict | None, str]:
    """Groq first (the project's LLM), Gemini only if a Groq key is absent/failed."""
    g = extract_groq(image_bytes)
    if g and g["fields"]: return g, "groq"
    g = extract_gemini(image_bytes, "image/png" if filename.lower().endswith("png") else "image/jpeg")
    return (g, "gemini") if g and g["fields"] else (None, "")


# ---------------- public API ----------------
def extract(image_bytes: bytes, filename: str = "", use_gemini: bool = True, is_registered=None) -> dict:
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)); img.load()
    sharp = sharpness(img)
    img, angle = deskew(img)
    result = {"doc_type": "unknown", "fields": {}, "confidence": {}, "engine": "none", "warnings": [],
              "quality": {"sharpness": round(sharp, 1), "deskew_deg": round(angle, 1), "mean_conf": None, "blurry": sharp < SHARPNESS_MIN}}
    if local_available():
        lines = _read_lines(img, clean=not result["quality"]["blurry"])
        dt = _detect_type(lines, filename)
        result["doc_type"] = dt
        if lines:
            result["quality"]["mean_conf"] = round(sum(l["conf"] for l in lines) / len(lines), 3)
        if dt != "unknown":
            f, c = _parse(lines, dt, img.width)
            result.update(fields=f, confidence=c, engine="local")
    else:
        result["warnings"].append("Local OCR engine not installed (pip install rapidocr-onnxruntime).")

    if result["doc_type"] == "gst" and result["fields"].get("gstin"):
        raw = result["fields"]["gstin"]; norm = _gstin_positional(raw)
        if norm != raw:
            result["fields"]["gstin"] = norm
            result["warnings"].append(f"Look-alike characters in the GSTIN (O/0, I/1) were normalised by position: {raw} -> {norm}. Please confirm.")
    weak = result["quality"]["blurry"] or (result["quality"]["mean_conf"] or 0) < MEAN_CONF_MIN or result["engine"] == "none"
    if weak and use_gemini:
        g, eng = extract_vision(image_bytes, filename)
        if g:
            result.update(doc_type=g["doc_type"] if g["doc_type"] != "unknown" else result["doc_type"],
                          fields=g["fields"], confidence={k: 0.9 for k in g["fields"]}, engine=eng)
            result["warnings"].append("Scan was low quality; fields were read with Groq/Gemini vision. Please confirm.")
    if result["engine"] in ("groq", "gemini") and result["doc_type"] == "gst" and result["fields"].get("gstin"):
        from modules.kyc_checks import gstin_checksum_ok
        raw = result["fields"]["gstin"].strip().upper().replace(" ", "")
        result["fields"]["gstin"] = raw
        if not (gstin_checksum_ok(raw) and is_registered and is_registered(raw)):
            sug = suggest_gstin_from_registry(result["fields"])
            if sug:
                result["fields"]["gstin"] = sug; result["confidence"]["gstin"] = 0.5
                result["warnings"].append(f"The GSTIN on this blurry scan could not be read reliably (read as {raw}). "
                                          f"The single registry record matching the business name, state and address is {sug}. Please confirm it against the document.")
    if weak and use_gemini and result["engine"] != "groq" and os.getenv("GROQ_API_KEY") and LAST_VISION_ERROR:
        result["warnings"].append("Vision fallback failed - " + LAST_VISION_ERROR)
    if weak and result["engine"] == "local":
        result["warnings"].append("Scan looks blurry or low-confidence - please check every field before continuing.")
        if result["doc_type"] == "gst" and is_registered and result["fields"].get("gstin"):
            fixed, changed = repair_gstin(result["fields"]["gstin"], is_registered)
            if changed:
                result["fields"]["gstin"] = fixed; result["confidence"]["gstin"] = 0.6
                result["warnings"].append("GSTIN characters were auto-corrected to match checksum + registry. Please confirm.")
    return result
