
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"

def load_leads():
    """
    Load only the original supplied MSME lead dataset.
    Never generate synthetic replacement data.
    """
    original = DATA / "smb_leads.csv"

    if not original.exists():
        return pd.DataFrame(), None

    df = pd.read_csv(original)

    if df.empty:
        return df, "data/smb_leads.csv"

    return df, "data/smb_leads.csv"
