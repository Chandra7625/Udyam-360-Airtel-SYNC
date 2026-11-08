from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_catalogue():
    p = DATA / "product_catalogue.csv"
    if not p.exists(): raise FileNotFoundError(f"Missing {p}")
    df = pd.read_csv(p).fillna("")
    for c in ["price_min_inr_per_month", "price_max_inr_per_month", "one_time_setup_inr", "min_contract_months", "min_employees", "min_sites", "typical_install_days"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df

def load_registry(filename, key):
    p = DATA / filename
    if not p.exists(): raise FileNotFoundError(f"Missing {p}")
    df = pd.read_csv(p, dtype=str).fillna("")
    df[key] = df[key].astype(str).str.strip().str.upper()
    return df
