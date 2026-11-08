# Udyam360 — Hackathon MVP

## Data folder setup
Place these files in `data/`:
- `product_catalogue.csv`
- `mock_gstin_registry.csv`
- `mock_udyam_registry.csv`
- `smb_leads.csv` (your original lead dataset)
- `kyc_documents/` (folder containing all supplied K01–K12 specimen files)

The app automatically uses `smb_leads.csv` if present. It falls back to generated synthetic leads only if the original is absent. KYC specimen files are listed and previewed from `data/kyc_documents/`.

## Windows / VS Code
```powershell
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

Copy `.env.example` to `.env` and add `GEMINI_API_KEY`. Gemini is optional; rule-based advisor fallback remains available.

## Demo flow
Home → AI Business Advisor → Bundle & Checkout → Smart KYC → Order Tracker → Sales Intelligence.

## Prototype boundaries
- GSTIN/Udyam checks use fictional mock registries, not live government APIs.
- Document upload and specimen preview work; OCR is not yet integrated.
- Prices use catalogue midpoint estimates.
- Never commit `.env`, uploaded customer documents, or real personal data.
