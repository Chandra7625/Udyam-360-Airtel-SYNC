# Udyam360 – AI-Powered Business Enablement Platform

Udyam360 is an AI-powered platform designed to support small businesses and entrepreneurs by simplifying business onboarding, improving access to relevant services, and providing data-driven business insights.

Our goal is to bring essential business services together in one platform, making it easier for businesses to manage their operations and discover growth opportunities.

## Key Features

### 1. Smart KYC
Simplifies business verification through document processing and validation.

- Upload multiple KYC documents in PDF, JPG and PNG formats.
- Supports GST certificates, Udyam certificates, signatory IDs and address proofs.
- Extracts information using OCR.
- Uses RapidOCR for local text extraction, with Groq/Gemini vision-based fallback.
- Allows users to review and correct extracted information.
- Validates GSTIN and Udyam details against mock registries.
- Performs cross-document consistency checks.
- Identifies errors and flags cases requiring manual review.

*Note: OCR results are suggestions and require human verification. Registry checks use mock/demo data and do not constitute official government verification.*

### 2. AI Business Advisor
Provides AI-assisted recommendations and guidance to help businesses make informed decisions.

### 3. Bundle & Checkout
Helps businesses explore eligible products and services, validate bundles and view pricing.

### 4. Order Tracker
Allows users to track their orders and monitor order progress.

### 5. Sales Intelligence
Provides business insights through sales and lead analytics to support better decision-making.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | Streamlit |
| Programming Language | Python |
| Data Processing | Pandas, NumPy |
| Visualization | Plotly |
| OCR | RapidOCR, PyMuPDF |
| AI Integration | Groq, Google Gemini |
| Configuration | python-dotenv |
| Data Storage | CSV-based demo data |

## Project Structure

```text
Udyam360/
│
├── app.py
├── requirements.txt
├── .env
│
├── modules/
│   ├── kyc.py
│   ├── ocr.py
│   ├── kyc_checks.py
│   ├── data_loader.py
│   ├── recommendations.py
│   ├── advisor.py
│   ├── pricing.py
│   ├── database.py
│   └── analytics.py
│
├── scripts/
│   └── run_specimens.py
│
└── data/
    ├── mock_gstin_registry.csv
    └── mock_udyam_registry.csv
```

## Installation and Setup

### Prerequisites

- Python 3.10 or later
- Git
- pip

### 1. Clone the repository

```bash
git clone https://github.com/Chandra7625/Airtel_Udyam_360.git
cd Airtel_Udyam_360
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and add the API keys required by the application.

Do not upload API keys or the `.env` file to GitHub.

### 5. Run the application

```bash
python -m streamlit run app.py
```

The application will open in your browser.

## Smart KYC Workflow

1. Enter business and outlet information.
2. Select available GSTIN and Udyam registrations.
3. Provide consent for document processing.
4. Upload supporting KYC documents.
5. Run OCR to extract relevant information.
6. Review and correct extracted fields.
7. Run validation checks.
8. Review passed checks, errors and warnings.
9. Submit the application for appropriate human review.

## Privacy and Validation

- Uploaded documents are processed in memory and are not intended to be permanently stored as raw files.
- Extracted information and application metadata may be stored in the demo application's CSV files.
- API credentials should be maintained locally in environment variables.
- Mock registry data is used for demonstration purposes.
- Automated checks do not replace official verification or human approval.

## Future Enhancements

- Integration with official GST and Udyam verification services.
- Improved OCR accuracy and document classification.
- Secure database integration.
- Enhanced fraud detection and document authenticity checks.
- More advanced AI-powered business recommendations.
- Deployment and scalability improvements.

## Team

**Udyam360 – Airtel SYNC**

- Chandratapa Dewan
- Anika Singhal

---

*Udyam360 aims to make business onboarding and enablement simpler, smarter and more accessible through AI and technology.*
