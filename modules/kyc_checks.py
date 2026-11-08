"""KYC validators. Input = fields extracted by modules/ocr.py (possibly hand-corrected on screen).
Output = list of Check results. Never raises."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from modules.kyc import lookup_gstin as _lg, lookup_udyam as _lu

TODAY = date(2026, 7, 15)          # case README: use this as "today"
ADDRESS_PROOF_MAX_DAYS = 90


def lookup_gstin(g):
    return (_lg(g) or {}).get("record")


def lookup_udyam(u):
    return (_lu(u) or {}).get("record")


def gstin_checksum_ok(g: str) -> bool:
    g = (g or "").strip().upper()
    return len(g) == 15 and all(c in _CS for c in g) and gstin_checksum_char(g[:14]) == g[14]

# ---------- GSTIN ----------
_CS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# 4th PAN char is [A-Z] so the dataset's 'X' passes (README says accept X).
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
STATE_CODES = {"01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh"}


def gstin_checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _CS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _CS[(36 - total % 36) % 36]


def gstin_format_ok(g: str) -> bool:
    g = (g or "").strip().upper()
    return bool(GSTIN_RE.match(g)) and gstin_checksum_char(g[:14]) == g[14]


# ---------- masking (use these for EVERY log line / UI echo / LLM prompt) ----------
def mask_gstin(g: str) -> str:
    g = g or ""
    return g[:2] + "X" * max(len(g) - 5, 0) + g[-3:] if len(g) >= 8 else "****"


def mask_id(s: str) -> str:
    s = s or ""
    return "*" * max(len(s) - 4, 0) + s[-4:]


def mask_udyam(u: str) -> str:
    return u[:9] + "*" * max(len(u) - 12, 0) + u[-3:] if u and len(u) > 12 else "****"


# ---------- fuzzy helpers ----------
def _norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(prop\.?[^)]*\)", " ", s)          # "(Prop. X)" in legal names
    s = s.replace("pvt.", "private").replace("pvt", "private").replace("ltd.", "limited").replace("ltd", "limited")
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)               # also fixes OCR line-wrap breaks


def _norm_full(s: str) -> str:
    """Like _norm_name but KEEPS the '(Prop. X)' part - the proprietor's business name must match too."""
    s = (s or "").lower().replace("&", "and").replace("pvt", "private").replace("ltd", "limited")
    return re.sub(r"[^a-z0-9]", "", s)


def _prop_part(legal: str) -> str:
    m = re.search(r"\(prop\.?\s*(.*?)\)", legal or "", re.I)
    return m.group(1).strip() if m else ""


def _norm_addr(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def names_match(a: str, b: str, threshold: float = 0.85) -> bool:
    na, nb = _norm_name(a), _norm_name(b)
    return _ratio(na, nb) >= threshold or (bool(na) and bool(nb) and (na in nb or nb in na) and min(len(na), len(nb)) > 6)


def addresses_match(a: str, b: str, threshold: float = 0.9) -> bool:
    return _ratio(_norm_addr(a), _norm_addr(b)) >= threshold


def _d(s) -> date | None:
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


@dataclass
class Check:
    code: str
    ok: bool
    message: str
    field: str = ""          # which input field the UI should highlight for manual correction
    severity: str = "error"  # error blocks KYC, warn goes to a human reviewer

    def dict(self): return asdict(self)


def validate_applicant(x: dict, today: date = TODAY) -> list[Check]:
    """x = {"gst": {...}, "udyam": {...}, "signatory_id": {...}, "address_proof": {...}}
    Any section may be missing/None (e.g. a business with no GSTIN). Never raises."""
    out: list[Check] = []
    add = lambda *a, **k: out.append(Check(*a, **k))
    gst, udy = x.get("gst") or {}, x.get("udyam") or {}
    if udy and not (udy.get("udyam_number") or "").strip():
        add("UDYAM_MISSING", False, "Udyam number is blank or unreadable on the certificate", "udyam.udyam_number")
    sid, adr = x.get("signatory_id") or {}, x.get("address_proof") or {}

    # --- GST certificate ---
    g = (gst.get("gstin") or "").strip().upper()
    reg_g = None
    if gst:
        if not gstin_format_ok(g):
            add("GSTIN_FORMAT", False, f"GSTIN {mask_gstin(g)} fails the format/checksum test", "gst.gstin")
        else:
            add("GSTIN_FORMAT", True, "GSTIN format and checksum valid", "gst.gstin")
            if STATE_CODES.get(g[:2]) and gst.get("address") and STATE_CODES[g[:2]].lower() not in gst["address"].lower():
                add("GSTIN_STATE", False, "GSTIN state code does not match the address state", "gst.address", "warn")
            reg_g = lookup_gstin(g)
            if not reg_g:
                add(
                    "GSTIN_REGISTRY",
                    False,
                    "GSTIN not found in the supplied mock registry. Manual review required.",
                    "gst.gstin",
                    "warn"
                )
            elif str(reg_g.get("status", "")).strip().lower() != "active":
                add(
                    "GSTIN_STATUS",
                    False,
                    f"GSTIN status is {reg_g.get('status', 'Unknown')} in the mock registry. Manual review required.",
                    "gst.gstin",
                    "warn"
                )
            else:
                add("GSTIN_STATUS", True, "GSTIN is Active in the registry", "gst.gstin")
                nm_doc = gst.get("legal_name") or gst.get("trade_name") or ""
                if _ratio(_norm_full(nm_doc), _norm_full(reg_g["legal_name"])) < 0.95:
                    add("GST_NAME_MATCH", False, f"Legal name on certificate ({nm_doc!r}) differs from the GST registry ({reg_g['legal_name']!r})", "gst.legal_name")
                else:
                    add("GST_NAME_MATCH", True, "Name matches the GST registry", "gst.legal_name")
                if gst.get("trade_name") and _ratio(_norm_full(gst["trade_name"]), _norm_full(reg_g["trade_name"])) < 0.95:
                    add("GST_TRADE_MISMATCH", False, "Trade name on certificate differs from the GST registry", "gst.trade_name")
                if gst.get("address") and not addresses_match(gst["address"], reg_g["principal_place_of_business"]):
                    add("GST_ADDR_MATCH", False, "Address on certificate differs from the GST registry", "gst.address")
    else:
        add("GST_PRESENT", False, "No readable GST certificate (missing, or too blurry to read) - enter the details manually or re-upload; GST-gated products stay excluded until verified", "gst", "warn")

    pp = _prop_part(gst.get("legal_name", ""))
    if pp and gst.get("trade_name") and _ratio(_norm_full(pp), _norm_full(gst["trade_name"])) < 0.93:
        add("GST_PROP_MISMATCH", False, f"Proprietor's business name {pp!r} does not match the trade name {gst['trade_name']!r}", "gst.legal_name")
    if not udy:
        add("UDYAM_ABSENT", False, "No Udyam certificate supplied", "udyam", "warn")

    # --- Udyam certificate ---
    reg_u = None
    if udy:
        u = (udy.get("udyam_number") or "").strip().upper()
        if not u:
            pass
        elif not UDYAM_RE.match(u):
            add("UDYAM_FORMAT", False, f"Udyam number {mask_udyam(u)} has an invalid format", "udyam.udyam_number")
        else:
            reg_u = lookup_udyam(u)
            if not reg_u:
                add(
                    "UDYAM_REGISTRY",
                    False,
                    "Udyam number not found in the supplied mock registry. Manual review required.",
                    "udyam.udyam_number",
                    "warn"
                )
            else:
                add("UDYAM_REGISTRY", True, "Udyam number found in the registry", "udyam.udyam_number")
                if not names_match(udy.get("enterprise_name"), reg_u["enterprise_name"]):
                    add("UDYAM_NAME_MATCH", False, "Enterprise name differs from the Udyam registry", "udyam.enterprise_name")
        rd = _d(udy.get("date_of_registration"))
        if rd and rd > today:
            add("UDYAM_DATE", False, "Udyam registration date is in the future", "udyam.date_of_registration")

    # --- cross-document consistency ---
    names = {"GST": gst.get("trade_name"), "Udyam": udy.get("enterprise_name"),
             "ID": sid.get("business"), "Address proof": adr.get("billed_to")}
    names = {k: v for k, v in names.items() if v}
    ref_k = next(iter(names), None)
    for k, v in names.items():
        if k != ref_k and not names_match(v, names[ref_k]):
            add("CROSS_NAME", False, f"Business name on {k} does not match {ref_k} ({v!r} vs {names[ref_k]!r})", f"{k}")
    if gst.get("address") and adr.get("supply_address") and not addresses_match(gst["address"], adr["supply_address"]):
        add("CROSS_ADDRESS", False, "Address proof does not match the GST principal place of business", "address_proof.supply_address")

    # --- address proof recency (<= 90 days, not future-dated) ---
    if adr:
        bd = _d(adr.get("bill_date"))
        if not bd:
            add("ADDR_DATE", False, "Could not read the bill date", "address_proof.bill_date")
        elif bd > today:
            add("ADDR_DATE", False, "Bill date is in the future", "address_proof.bill_date")
        elif (today - bd).days > ADDRESS_PROOF_MAX_DAYS:
            add("ADDR_STALE", False, f"Address proof is {(today - bd).days} days old (limit {ADDRESS_PROOF_MAX_DAYS})", "address_proof.bill_date")
        else:
            add("ADDR_STALE", True, f"Address proof is {(today - bd).days} days old", "address_proof.bill_date")
    else:
        add("ADDR_PRESENT", False, "Address proof missing", "address_proof")

    # --- signatory ID ---
    if sid:
        vt = _d(sid.get("valid_till"))
        if vt and vt < today:
            add("ID_EXPIRED", False, f"Signatory ID expired on {vt}", "signatory_id.valid_till")
        elif vt:
            add("ID_EXPIRED", True, "Signatory ID is valid", "signatory_id.valid_till")
        owner = (reg_g or {}).get("legal_name", "")
        if reg_g and sid.get("name") and reg_g["constitution"] == "Proprietorship" and not names_match(sid["name"], re.sub(r"\s*\(.*", "", owner)):
            add("SIGNATORY_NAME", False, "Signatory name differs from the proprietor on the GST record", "signatory_id.name", "warn")
    else:
        add("ID_PRESENT", False, "Signatory ID missing", "signatory_id")
    return out


def summarise(checks: list[Check]) -> dict:
    errs = [c for c in checks if not c.ok and c.severity == "error"]
    warns = [c for c in checks if not c.ok and c.severity == "warn"]
    return {"status": "pass" if not errs and not warns else ("needs_correction" if errs else "needs_review"),
            "errors": [c.dict() for c in errs], "warnings": [c.dict() for c in warns],
            "passed": [c.dict() for c in checks if c.ok]}
