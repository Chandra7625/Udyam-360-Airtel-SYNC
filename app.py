import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import fitz
from dotenv import load_dotenv
load_dotenv()
from modules.data_loader import load_catalogue
from modules.recommendations import recommend, eligible_products, validate_bundle
from modules.advisor import explain_recommendation
from modules.pricing import quote
from modules.kyc import lookup_gstin, lookup_udyam, basic_gstin_format_check
from modules.database import create_order, get_orders
from modules.analytics import load_leads
from modules.data_loader import load_registry
from modules.kyc import create_kyc_application
from modules.ocr import extract
from modules.kyc_checks import validate_applicant, summarise



st.set_page_config(page_title="Udyam360 | MSME onboarding",page_icon="🏪",layout="wide")
def prepare_document(file):
    """
    Convert an uploaded image or PDF into image bytes for OCR.
    Processes a maximum of 3 PDF pages.
    """
    filename = file.name
    file_bytes = file.getvalue()

    if filename.lower().endswith(".pdf"):
        try:
            pdf = fitz.open(stream=file_bytes, filetype="pdf")

            if pdf.page_count == 0:
                raise ValueError("The PDF contains no pages.")

            pages = []

            for page_number in range(min(pdf.page_count, 3)):
                page = pdf.load_page(page_number)
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    alpha=False
                )

                pages.append((
                    f"{filename} - page {page_number + 1}",
                    pix.tobytes("png")
                ))

            pdf.close()
            return pages

        except Exception as exc:
            raise ValueError(f"Could not read PDF: {exc}") from exc

    return [(filename, file_bytes)]
def extract_uploaded_document(file):
    """
    Prepare an uploaded PDF/image and run OCR on each page.
    Returns one extraction result per page.
    """
    pages = prepare_document(file)
    results = []

    for page_name, image_bytes in pages:
        result = extract(
            image_bytes,
            filename=page_name,
            use_gemini=True
        )

        results.append({
            "page_name": page_name,
            "doc_type": result.get("doc_type", "unknown"),
            "fields": result.get("fields", {}),
            "confidence": result.get("confidence", {}),
            "engine": result.get("engine", "none"),
            "warnings": result.get("warnings", []),
            "quality": result.get("quality", {})
        })

    return results
st.markdown("""<style>
.block-container{padding-top:1.4rem;padding-bottom:2rem} .hero{padding:1.5rem;border-radius:18px;background:linear-gradient(120deg,#063b2b,#13845a);color:white} .hero h1{font-size:2.5rem;margin:0} .hero p{opacity:.9;margin-bottom:0} div[data-testid="stMetric"]{background:#f5faf7;padding:14px;border-radius:12px;border:1px solid #e4eee8;color:#173b2d !important}
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] *,
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] *,
div[data-testid="stMetric"] [data-testid="stMetricDelta"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] *,
div[data-testid="stMetric"] p,
div[data-testid="stMetric"] span{color:#173b2d !important; -webkit-text-fill-color:#173b2d !important}
</style>""",unsafe_allow_html=True)

@st.cache_data
def catalogue(): return load_catalogue()
cat=catalogue()
if "profile" not in st.session_state: st.session_state.profile=None
if "bundle" not in st.session_state: st.session_state.bundle=pd.DataFrame()
if "order_id" not in st.session_state: st.session_state.order_id=None

st.sidebar.markdown("# 🟢 Udyam360")
st.sidebar.caption("Digital onboarding for India's MSMEs")
page=st.sidebar.radio("Navigate",["Home","AI Business Advisor","Bundle & Checkout","Smart KYC","Order Tracker","Sales Intelligence"])

if page=="Home":
    st.markdown('<div class="hero"><h1>Udyam360</h1><p>Make your business digital in one sitting. Discover, bundle, verify and activate — all in one place.</p></div>',unsafe_allow_html=True)
    st.write("")
    a,b,c=st.columns(3); a.metric("Products in catalogue",len(cat)); b.metric("Mock GSTIN records",3534); c.metric("Mock Udyam records",2723)
    st.subheader("Your digital business journey")
    cols=st.columns(4)
    for col,num,title,desc in zip(cols,["01","02","03","04"],["Discover","Choose","Verify","Activate"],["Tell us about your business","Get a transparent bundle quote","Verify registrations with consent","Track installation and activation"]):
        with col:
            st.markdown(f"### {num} · {title}"); st.write(desc)

elif page=="AI Business Advisor":
    st.title("Your business, understood")
    st.write("Answer a few questions. We'll shortlist products using the supplied catalogue's eligibility rules.")
    with st.form("profile_form"):
        c1,c2=st.columns(2)
        with c1:
            business=st.text_input("Business name",placeholder="e.g. Saffron Bakers")
            btype=st.selectbox("Business type",["Kirana store","Salon","Pharmacy","Clinic","Dental clinic","CA firm","Coaching centre","Restaurant","Retail chain","Auto-parts unit","Small manufacturer","Other"])
            segment=st.selectbox("Business segment",["Micro retail & services","Professional offices","Small multi-site businesses","Small manufacturers"])
            employees=st.number_input("Number of employees",1,5000,4)
            sites=st.number_input("Number of locations",1,500,1)
        with c2:
            city=st.text_input("City",value="Chennai")
            tier=st.selectbox("City tier",["1","2"])
            language=st.selectbox("Preferred language",["English","Hindi","Tamil","Bengali","Telugu","Malayalam","Marathi","Kannada","Punjabi"])
            hasgst=st.checkbox("I have a GSTIN")
            budget=st.number_input("Monthly budget (₹)",500,500000,3000,step=250)
            need=st.multiselect("What do you need?",["Reliable internet","Business mobile connectivity","Customer messaging","Cloud email/storage","Cybersecurity","CCTV/POS connectivity"],default=["Reliable internet"])
        submitted=st.form_submit_button("Find my business bundle",type="primary",use_container_width=True)
    if submitted:
        segcode={"Micro retail & services":"micro","Professional offices":"prof","Small multi-site businesses":"multi","Small manufacturers":"mfg"}[segment]
        profile={"business":business or "My Business","business_type":btype,"segment":segment,"segment_code":segcode,"employees":int(employees),"sites":int(sites),"city":city,"city_tier":tier,"language":language,"has_gstin":hasgst,"budget":budget,"needs":need}
        st.session_state.profile=profile
        bundle,why=recommend(cat,profile,budget)
        st.session_state.bundle=bundle
        st.session_state.recommendation_why=why
    if st.session_state.profile:
        p=st.session_state.profile; bundle=st.session_state.bundle
        st.success(f"Profile saved for {p['business']} · {p['language']}")
        st.subheader("Recommended bundle")
        st.write(explain_recommendation(p,bundle))
        if not bundle.empty:
            display=bundle[["product_id","product_name","description","price_min_inr_per_month","price_max_inr_per_month","typical_install_days"]].copy()
            display.columns=["ID","Product","What it does","Monthly from (₹)","Monthly up to (₹)","Install days"]
            st.dataframe(display,use_container_width=True,hide_index=True)
            _,monthly,setup,contract=quote(bundle)
            x,y,z=st.columns(3); x.metric("Estimated monthly",f"₹{monthly:,.0f}"); y.metric("One-time setup",f"₹{setup:,.0f}"); z.metric("Minimum contract",f"{contract} months")
            st.info("Prices shown as catalogue midpoint estimates. Confirm final selected products and price in Bundle & Checkout.")
            st.caption("Next: open **Bundle & Checkout** from the left navigation to confirm your selected products.")

elif page=="Bundle & Checkout":
    st.title("Build your bundle")
    if st.session_state.profile is None:
        st.warning("Complete your business profile in AI Business Advisor first.")
    else:
        p=st.session_state.profile; st.caption(f"Quote for {p['business']} · {p['city']}")
        eligible=eligible_products(cat,p)
        if eligible.empty: st.warning("No products are eligible for this profile.")
        else:
            default=list(st.session_state.bundle.product_id.astype(str)) if not st.session_state.bundle.empty else []
            selected=st.multiselect("Choose products",options=eligible.product_id.astype(str).tolist(),default=[x for x in default if x in eligible.product_id.astype(str).tolist()],format_func=lambda x: f"{x} · {eligible.loc[eligible.product_id.astype(str)==x,'product_name'].iloc[0]}")
            bundle=eligible[eligible.product_id.astype(str).isin(selected)].copy()
            errors=validate_bundle(bundle,p)
            if errors:
                for e in errors: st.error(e)
            q,monthly,setup,contract=quote(bundle)
            if not q.empty:
                st.dataframe(q[["product_id","product_name","monthly_price_inr","setup_fee_inr"]].rename(columns={"product_id":"ID","product_name":"Product","monthly_price_inr":"Monthly estimate ₹","setup_fee_inr":"Setup ₹"}),use_container_width=True,hide_index=True)
            a,b,c=st.columns(3); a.metric("Monthly total",f"₹{monthly:,.0f}"); b.metric("Setup total",f"₹{setup:,.0f}"); c.metric("Contract",f"{contract} months")
            if st.button("Confirm quote & place demo order",type="primary",disabled=not selected or bool(errors)):
                st.session_state.bundle=bundle
                oid=create_order(p['business'],", ".join(bundle.product_name.astype(str)),monthly,setup)
                st.session_state.order_id=oid
                st.success(f"Demo order created: {oid}. Go to Order Tracker.")


elif page == "Smart KYC":
    st.title("Smart KYC verification")
    st.warning(
        "This prototype uses fictional mock registries. "
        "It is not connected to GSTN, Udyam or DigiLocker."
    )

    consent = st.checkbox(
        "I consent to use the details entered below for this simulated "
        "KYC verification. I understand this demo stores no uploaded "
        "document permanently."
    )

    st.subheader("Business and outlet details")

    business_name = st.text_input(
        "Business / trade name",
        placeholder="e.g. Saffron Bakers"
    )

    outlet_name = st.text_input(
        "Outlet name or location",
        placeholder="e.g. Saffron Bakers - Visakhapatnam"
    )

    if business_name.strip():
        gst_df = load_registry("mock_gstin_registry.csv", "gstin")
        ud_df = load_registry("mock_udyam_registry.csv", "udyam_number")

        # Find all GST registrations using the trade name
        gst_matches = gst_df[
            gst_df["trade_name"].astype(str).str.strip().str.casefold()
            == business_name.strip().casefold()
        ]

        # Find all Udyam registrations using the enterprise name
        ud_matches = ud_df[
            ud_df["enterprise_name"].astype(str).str.strip().str.casefold()
            == business_name.strip().casefold()
        ]

        st.divider()
        st.subheader("Select registrations for this outlet")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**GST registrations**")

            if not gst_matches.empty:
                gst_options = [""] + gst_matches["gstin"].astype(str).tolist()

                selected_gst = st.selectbox(
                    "Select the applicable GSTIN",
                    gst_options,
                    format_func=lambda x: x if x else "Select GSTIN",
                    key="selected_outlet_gstin"
                )
            else:
                selected_gst = ""
                st.info("No matching GSTIN registrations found.")

        with col2:
            st.markdown("**Udyam registrations**")

            if not ud_matches.empty:
                ud_options = [""] + ud_matches["udyam_number"].astype(str).tolist()

                selected_ud = st.selectbox(
                    "Select the applicable Udyam number",
                    ud_options,
                    format_func=lambda x: x if x else "Select Udyam number",
                    key="selected_outlet_udyam"
                )
            else:
                selected_ud = ""
                st.info("No matching Udyam registrations found.")

        st.divider()
        st.subheader("Verify selected registrations")

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "Verify selected GSTIN",
                disabled=not consent or not selected_gst
            ):
                if not basic_gstin_format_check(selected_gst):
                    st.error("GSTIN format check failed.")
                else:
                    res = lookup_gstin(selected_gst)
                    st.write("**Status:**", res["status"])
                    st.info(res["message"])

                    if res.get("record"):
                        st.json(res["record"])

        with col2:
            if st.button(
                "Verify selected Udyam",
                disabled=not consent or not selected_ud
            ):
                res = lookup_udyam(selected_ud)
                st.write("**Status:**", res["status"])
                st.info(res["message"])

                if res.get("record"):
                    st.json(res["record"])

        if selected_gst and selected_ud:
            
            st.info(
            "GSTIN and Udyam registrations were selected. "
            "Their relationship has not been independently verified. "
            "Supporting documents will be reviewed before final KYC approval."
            )

    else:
        st.info("Enter a business name to find its available registrations.")

        st.divider()
    st.subheader("Upload and scan KYC documents")

    st.caption(
        "Upload GST, Udyam, signatory ID and address proof. "
        "Documents are processed in memory and are not saved as raw files."
    )

    uploaded = st.file_uploader(
        "Upload documents (PDF, JPG or PNG)",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="kyc_document_uploader"
    )

    if "kyc_extractions" not in st.session_state:
        st.session_state.kyc_extractions = []

    if st.button(
        "Run OCR on uploaded documents",
        disabled=not consent or not uploaded
    ):
        results = []

        progress = st.progress(0)

        for index, file in enumerate(uploaded):
            try:
                pages = extract_uploaded_document(file)

                for page in pages:
                    page["source_file"] = file.name
                    results.append(page)

            except Exception as exc:
                st.error(f"Could not process {file.name}: {exc}")

            progress.progress((index + 1) / len(uploaded))

        st.session_state.kyc_extractions = results

        if results:
            st.success(
                f"OCR completed for {len(results)} document page(s). "
                "Please review the extracted information."
            )

    document_types = {
        "GST certificate": "gst",
        "Udyam certificate": "udyam",
        "Signatory ID": "signatory_id",
        "Address proof": "address_proof",
        "Other / Unknown": "unknown"
    }

    corrected_docs = {}

    for index, result in enumerate(
        st.session_state.kyc_extractions
    ):
        with st.expander(
            f"{result['source_file']} — {result['page_name']}",
            expanded=True
        ):
            st.write("**OCR engine:**", result["engine"])

            if result.get("warnings"):
                for warning in result["warnings"]:
                    st.warning(str(warning))

            quality = result.get("quality", {})

            if quality.get("blurry"):
                st.warning(
                    "This page may be blurry. Please check every field carefully."
                )

            detected = result.get("doc_type", "unknown")

            reverse_types = {
                value: label
                for label, value in document_types.items()
            }

            default_type = reverse_types.get(
                detected, "Other / Unknown"
            )

            selected_type = st.selectbox(
                "Document type",
                list(document_types.keys()),
                index=list(document_types.keys()).index(default_type),
                key=f"kyc_type_{index}"
            )

            doc_key = document_types[selected_type]

            fields = result.get("fields", {})

            if doc_key == "unknown":
                st.info(
                    "Select a document type to enable field validation."
                )
                continue

            st.caption(
                "Review and correct the OCR results before validation."
            )

            edited_fields = {}

            for field_name, field_value in fields.items():
                edited_fields[field_name] = st.text_input(
                    field_name.replace("_", " ").title(),
                    value="" if field_value is None else str(field_value),
                    key=f"kyc_field_{index}_{field_name}"
                )

            corrected_docs[doc_key] = edited_fields

    if st.session_state.kyc_extractions:
        st.divider()
        st.subheader("Validate extracted information")

        if st.button(
            "Validate KYC documents",
            disabled=not consent
        ):
            validation_docs = {}

            for index, result in enumerate(
                st.session_state.kyc_extractions
            ):
                selected_type = st.session_state.get(
                    f"kyc_type_{index}",
                    "Other / Unknown"
                )

                doc_key = document_types[selected_type]

                if doc_key == "unknown":
                    continue

                edited_fields = {}

                for field_name in result.get("fields", {}):
                    edited_fields[field_name] = st.session_state.get(
                        f"kyc_field_{index}_{field_name}",
                        ""
                    )

                validation_docs[doc_key] = edited_fields

            checks = validate_applicant(validation_docs)
            summary = summarise(checks)

            st.session_state.kyc_validation = summary

            if summary["status"] == "pass":
                st.success("All available checks passed.")

            elif summary["status"] == "needs_correction":
                st.error(
                    "Some checks need correction. "
                    "Review the errors below."
                )

            else:
                st.warning(
                    "Manual review is required. "
                    "This is not an automatic rejection."
                )

            if summary["errors"]:
                st.markdown("**Issues requiring correction**")

                for item in summary["errors"]:
                    st.error(
                        f"{item['code']}: {item['message']}"
                    )

            if summary["warnings"]:
                st.markdown("**Warnings for manual review**")

                for item in summary["warnings"]:
                    st.warning(
                        f"{item['code']}: {item['message']}"
                    )

            if summary["passed"]:
                st.markdown("**Passed checks**")

                for item in summary["passed"]:
                    st.success(
                        f"{item['code']}: {item['message']}"
                    )

    st.caption(
        "OCR results are suggestions, not proof of authenticity. "
        "Final KYC approval requires appropriate human review."
    )

elif page=="Order Tracker":
    st.title("Track your order")
    orders=get_orders()
    if st.session_state.order_id: st.success(f"Your latest order reference: **{st.session_state.order_id}**")
    if not orders: st.info("No demo orders yet. Create one through Bundle & Checkout.")
    else:
        for o in orders:
            with st.expander(f"{o[0]} · {o[1]} · ₹{o[3]:,.0f}/month",expanded=(o[0]==st.session_state.order_id)):
                st.write("Products:",o[2]); st.write("Created:",o[6]); st.write("Status:",o[5])
                steps=["Order confirmed","KYC review","Installation scheduled","Activated"]
                st.progress(0.25); st.caption("Order confirmed → KYC review → Installation scheduled → Activated")
                st.caption("Demo status is simulated. Real activation requires operational integration.")


elif page == "Sales Intelligence":
    st.title("Sales Intelligence")
    st.caption(
        "Analyse MSME leads, conversion performance, customer segments "
        "and sales opportunities."
    )

    df, data_source = load_leads()
    st.caption(f"Data source: {data_source}")

    if df.empty:
        st.warning(
        "The original MSME lead dataset is not available or contains no records. "
        "Upload data/smb_leads.csv to enable lead analytics."
        )
        st.stop()

    # ---------------- FILTERS ----------------
    st.subheader("Filter sales data")

    f1, f2, f3 = st.columns(3)

    with f1:
        cities = sorted(df["city"].dropna().astype(str).unique())
        selected_city = st.multiselect(
            "City",
            cities,
            default=cities
        )

    with f2:
        segments = sorted(df["segment"].dropna().astype(str).unique())
        selected_segment = st.multiselect(
            "Business segment",
            segments,
            default=segments
        )

    with f3:
        sources = sorted(df["lead_source"].dropna().astype(str).unique())
        selected_source = st.multiselect(
            "Lead source",
            sources,
            default=sources
        )

    filtered = df[
        df["city"].astype(str).isin(selected_city)
        & df["segment"].astype(str).isin(selected_segment)
        & df["lead_source"].astype(str).isin(selected_source)
    ].copy()

    if filtered.empty:
        st.warning("No leads match the selected filters.")
        st.stop()

    # ---------------- KPIs ----------------
    activated = filtered[
        filtered["outcome"].astype(str).str.lower() == "activated"
    ]

    total_leads = len(filtered)
    activated_count = len(activated)
    activation_rate = activated_count / total_leads * 100

    avg_followups = pd.to_numeric(
        filtered["customer_follow_up_calls"], errors="coerce"
    ).mean()

    revenue = pd.to_numeric(
        activated.get("monthly_bundle_value_inr", pd.Series(dtype=float)),
        errors="coerce"
    ).sum()

    avg_revenue = (
        revenue / activated_count if activated_count else 0
    )

    m1, m2, m3, m4, m5 = st.columns(5)

    m1.metric("Total leads", f"{total_leads:,}")
    m2.metric("Activated", f"{activated_count:,}")
    m3.metric("Activation rate", f"{activation_rate:.1f}%")
    m4.metric("Avg. follow-up calls", f"{avg_followups:.1f}")
    m5.metric("Monthly bundle value", f"₹{revenue:,.0f}")

    st.caption(
        "Monthly bundle value is calculated from activated lead records. "
        "It is a dataset estimate, not independently verified billing revenue."
    )

    # ---------------- ACQUISITION FUNNEL ----------------
    st.divider()
    st.subheader("Acquisition funnel")

    stage_order = [
        "Lead",
        "Contacted",
        "Needs assessed",
        "Quote accepted",
        "KYC complete",
        "Activated"
    ]

    if "stage_reached" in filtered.columns:
        counts = filtered["stage_reached"].value_counts()

        # Convert final-stage counts into cumulative funnel counts.
        funnel_values = []
        for i in range(len(stage_order)):
            later_stages = stage_order[i:]
            count = sum(int(counts.get(stage, 0)) for stage in later_stages)
            funnel_values.append(count)

        funnel = pd.DataFrame({
            "Stage": stage_order,
            "Leads": funnel_values
        })

        st.plotly_chart(
            px.funnel(
                funnel,
                x="Leads",
                y="Stage",
                title="Lead progression funnel"
            ),
            use_container_width=True
        )
    else:
        st.info("Stage information is unavailable in this dataset.")

    # ---------------- SEGMENT AND SOURCE ANALYSIS ----------------
    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Leads by business segment")

        segment_data = (
            filtered.groupby(["segment", "outcome"])
            .size()
            .reset_index(name="Leads")
        )

        st.plotly_chart(
            px.bar(
                segment_data,
                x="segment",
                y="Leads",
                color="outcome",
                barmode="group",
                title="Lead outcomes by segment"
            ),
            use_container_width=True
        )

    with right:
        st.subheader("Conversion by lead source")

        source_data = (
            filtered.groupby("lead_source")
            .agg(
                Total_Leads=("lead_id", "count"),
                Activated=(
                    "outcome",
                    lambda x: (x.astype(str).str.lower() == "activated").sum()
                )
            )
            .reset_index()
        )

        source_data["Conversion_Rate"] = (
            source_data["Activated"]
            / source_data["Total_Leads"] * 100
        )

        st.plotly_chart(
            px.bar(
                source_data,
                x="lead_source",
                y="Conversion_Rate",
                title="Activation rate by lead source",
                labels={"Conversion_Rate": "Activation rate (%)"}
            ),
            use_container_width=True
        )

    # ---------------- LOCATION ANALYSIS ----------------
    st.divider()
    st.subheader("Geographical demand")

    city_data = (
        filtered.groupby("city")
        .size()
        .reset_index(name="Leads")
        .sort_values("Leads", ascending=False)
    )

    st.plotly_chart(
        px.bar(
            city_data,
            x="city",
            y="Leads",
            title="MSME leads by city"
        ),
        use_container_width=True
    )

    # ---------------- PRODUCT ANALYSIS ----------------
    st.divider()
    st.subheader("Product demand")

    if "products_of_interest" in filtered.columns:
        product_values = (
            filtered["products_of_interest"]
            .dropna()
            .astype(str)
        )

        product_values = product_values[
            product_values.str.strip() != ""
        ]

        if not product_values.empty:
            product_counts = (
                product_values.str.split(r"[,;|]")
                .explode()
                .str.strip()
            )

            product_counts = (
                product_counts[product_counts != ""]
                .value_counts()
                .head(10)
                .rename_axis("Product")
                .reset_index(name="Lead count")
            )

            st.plotly_chart(
                px.bar(
                    product_counts,
                    x="Lead count",
                    y="Product",
                    orientation="h",
                    title="Most requested products"
                ),
                use_container_width=True
            )
        else:
            st.info("No product-interest information is available.")
    else:
        st.info("Product-interest information is unavailable.")

    # ---------------- DROP REASONS ----------------
    st.divider()
    st.subheader("Why are leads dropping off?")

    drops = filtered[
        filtered["outcome"].astype(str).str.lower() == "dropped"
    ]

    if not drops.empty:
        drop_data = (
            drops["drop_reason"]
            .dropna()
            .astype(str)
            .value_counts()
            .head(8)
            .rename_axis("Reason")
            .reset_index(name="Leads")
        )

        st.plotly_chart(
            px.bar(
                drop_data,
                x="Leads",
                y="Reason",
                orientation="h",
                title="Top reasons for lost leads"
            ),
            use_container_width=True
        )
    else:
        st.info("No dropped leads in this selection.")

    # ---------------- SALES OPPORTUNITIES ----------------
    st.divider()
    st.subheader("Sales opportunities")

    if not activated.empty:
        st.success(
            f"{activated_count} leads have reached activation. "
            f"Their recorded monthly bundle value totals ₹{revenue:,.0f}."
        )

    if not drops.empty:
        top_reason = drops["drop_reason"].mode()

        if not top_reason.empty:
            st.warning(
                f"Most common recorded drop reason: {top_reason.iloc[0]}. "
                "The sales team should investigate this issue."
            )

    if "num_sites" in filtered.columns:
        multi_site = filtered[
            pd.to_numeric(filtered["num_sites"], errors="coerce") > 1
        ]

        st.info(
            f"{len(multi_site)} leads represent multi-site businesses. "
            "These may be candidates for multi-location connectivity bundles."
        )

    # ---------------- EXPORT ----------------
    st.divider()

    st.download_button(
        "Download filtered leads data",
        filtered.to_csv(index=False).encode("utf-8"),
        "udyam360_sales_intelligence.csv",
        "text/csv"
    )
