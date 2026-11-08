import pandas as pd

def _yes(v): return str(v).strip().lower() in {"yes", "y", "true", "1"}

def eligible_products(catalogue, profile):
    rows=[]
    for _, p in catalogue.iterrows():
        tiers=[x.strip() for x in str(p.available_city_tiers).split(';') if x.strip()]
        if tiers and str(profile.get("city_tier", "2")) not in tiers: continue
        if int(profile.get("employees",1)) < int(p.min_employees): continue
        if int(profile.get("sites",1)) < int(p.min_sites): continue
        if _yes(p.requires_gstin) and not _yes(profile.get("has_gstin",False)): continue
        target=[x.strip().lower() for x in str(p.target_segments).split(';') if x.strip()]
        seg=str(profile.get("segment_code","micro")).lower()
        if target and seg not in target: continue
        rows.append(p.to_dict())
    return pd.DataFrame(rows)

def recommend(catalogue, profile, budget=3000):
    eligible=eligible_products(catalogue, profile)
    if eligible.empty: return eligible, "No products currently satisfy all catalogue eligibility rules. Try changing the business profile or contact a partner."
    # Pick connectivity anchor where available, then segment-fit products; avoid dependency violations.
    eligible=eligible.copy()
    eligible["monthly_estimate"]=(eligible.price_min_inr_per_month+eligible.price_max_inr_per_month)/2
    seg=str(profile.get("segment_code","micro")).lower()
    eligible["score"] = eligible.target_segments.astype(str).apply(lambda x: 3 if seg in x.lower().split(';') else 0)
    eligible.loc[eligible.category.astype(str).str.lower().str.contains('connectivity'),"score"] += 4
    eligible["score"] += eligible.description.astype(str).str.lower().apply(lambda x: 1 if any(k in x for k in ['security','wifi','business']) else 0)
    eligible=eligible.sort_values(["score","monthly_estimate"],ascending=[False,True])
    chosen=[]; total=0
    # Prefer at least one connectivity item, then add up to 3 useful items under budget (soft budget).
    for _,r in eligible.iterrows():
        if len(chosen)>=4: break
        deps=[d.strip() for d in str(r.requires_one_of).split('|') if d.strip()]
        if deps and not any(d in [x.product_id for x in chosen] for d in deps): continue
        price=float(r.monthly_estimate)
        if chosen and total+price>max(float(budget)*1.25, float(budget)+500): continue
        chosen.append(r); total+=price
    if not chosen: chosen=[eligible.iloc[0]]
    result=pd.DataFrame(chosen).drop(columns=["score"],errors="ignore")
    why=f"Selected {len(result)} eligible products for a {profile.get('business_type','small business')} with {profile.get('employees',1)} employees across {profile.get('sites',1)} site(s). Prices use catalogue midpoints for estimation; final quote uses the selected catalogue price range."
    return result, why

def validate_bundle(bundle, profile):
    errors=[]; ids=set(bundle.product_id.astype(str)) if not bundle.empty else set()
    for _,p in bundle.iterrows():
        deps=[d.strip() for d in str(p.requires_one_of).split('|') if d.strip()]
        if deps and not ids.intersection(deps): errors.append(f"{p.product_name} requires one of: {', '.join(deps)}")
        if str(p.requires_gstin).upper()=='Y' and not _yes(profile.get('has_gstin',False)): errors.append(f"{p.product_name} requires an active GSTIN")
    return errors
