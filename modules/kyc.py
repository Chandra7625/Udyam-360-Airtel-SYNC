
import re
import uuid
from pathlib import Path
from datetime import datetime

import pandas as pd
from modules.data_loader import load_registry


def lookup_gstin(gstin):
    value = str(gstin).strip().upper()

    if not value:
        return {
            "status": "Missing",
            "message": "Enter a GSTIN to search the mock registry."
        }

    df = load_registry("mock_gstin_registry.csv", "gstin")
    row = df[df.gstin == value]

    if row.empty:
        return {
            "status": "Not found",
            "message": "No matching record in the supplied mock GSTIN registry."
        }

    record = row.iloc[0].to_dict()
    status = (
        "Verified"
        if str(record.get("status", "")).lower() == "active"
        else "Rejected"
    )

    return {
        "status": status,
        "message": f"Registry status: {record.get('status', 'Unknown')}",
        "record": record
    }


def lookup_udyam(number):
    value = str(number).strip().upper()

    if not value:
        return {
            "status": "Missing",
            "message": "Enter a Udyam number to search the mock registry."
        }

    df = load_registry("mock_udyam_registry.csv", "udyam_number")
    row = df[df.udyam_number == value]

    if row.empty:
        return {
            "status": "Not found",
            "message": "No matching record in the supplied mock Udyam registry."
        }

    return {
        "status": "Verified",
        "message": "Matching record found in the supplied mock Udyam registry.",
        "record": row.iloc[0].to_dict()
    }


def basic_gstin_format_check(value):
    # Exercise-specific identifiers deliberately use X in character 4.
    v = str(value).strip().upper()
    return bool(
        re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9]Z[A-Z0-9]", v)
    )


def create_kyc_application(
    business_name,
    outlet_name,
    gstin,
    udyam_number,
    document_names
):
    """Save a new KYC application and its document filenames."""

    application_id = "KYC-" + uuid.uuid4().hex[:8].upper()

    application = {
        "application_id": application_id,
        "business_name": str(business_name).strip(),
        "outlet_name": str(outlet_name).strip(),
        "gstin": str(gstin).strip().upper(),
        "udyam_number": str(udyam_number).strip().upper(),
        "document_names": "; ".join(document_names),
        "status": "Pending Manual Review",
        "submitted_at": datetime.now().isoformat(timespec="seconds")
    }

    output_file = Path("data") / "kyc_applications.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    new_row = pd.DataFrame([application])

    if output_file.exists():
        new_row.to_csv(
            output_file,
            mode="a",
            header=False,
            index=False
        )
    else:
        new_row.to_csv(output_file, index=False)

    return application
