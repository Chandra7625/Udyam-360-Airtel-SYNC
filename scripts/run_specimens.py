"""Run OCR + validation on every specimen K01..K12 and cache the extractions.
   python scripts/run_specimens.py            # uses cache if present
   python scripts/run_specimens.py --fresh    # re-run OCR
The cache (data/kyc_extractions/*.json) lets the demo work offline and instantly."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from modules.ocr import extract
from modules.kyc_checks import validate_applicant, summarise, lookup_gstin

DOCS = ROOT / "data" / "kyc_documents"; CACHE = ROOT / "data" / "kyc_extractions"
TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
KEY = {"gst_certificate": "gst", "udyam_certificate": "udyam", "signatory_id": "signatory_id", "address_proof": "address_proof"}


def process(kid, fresh=False):
    cf = CACHE / f"{kid}.json"
    if cf.exists() and not fresh: return json.loads(cf.read_text())
    out = {"applicant_id": kid, "docs": {}, "meta": {}}
    for t in TYPES:
        p = DOCS / f"{kid}_{t}.png"
        if not p.exists(): continue
        r = extract(p.read_bytes(), p.name, use_gemini=True, is_registered=lambda g: lookup_gstin(g) is not None)
        out["docs"][KEY[t]] = r["fields"]
        out["meta"][KEY[t]] = {k: r[k] for k in ("engine", "quality", "warnings", "confidence")}
    CACHE.mkdir(exist_ok=True); cf.write_text(json.dumps(out, indent=1)); return out


if __name__ == "__main__":
    fresh = "--fresh" in sys.argv
    for i in range(1, 13):
        kid = f"K{i:02d}"; t = time.time(); d = process(kid, fresh)
        s = summarise(validate_applicant(d["docs"]))
        flags = ", ".join(e["code"] for e in s["errors"] + s["warnings"]) or "-"
        blurry = [k for k, m in d["meta"].items() if m["quality"]["blurry"]]
        print(f"{kid} {s['status']:17s} {flags}" + (f"  [blurry: {blurry}]" if blurry else ""), f"({time.time()-t:.0f}s)")
