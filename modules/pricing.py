import pandas as pd

def quote(bundle, selected_ids=None):
    if selected_ids is not None: bundle=bundle[bundle.product_id.astype(str).isin(set(map(str,selected_ids)))]
    if bundle.empty: return bundle,0,0,12
    q=bundle.copy()
    q["monthly_price_inr"]=(pd.to_numeric(q.price_min_inr_per_month)+pd.to_numeric(q.price_max_inr_per_month))/2
    q["setup_fee_inr"]=pd.to_numeric(q.one_time_setup_inr,errors="coerce").fillna(0)
    monthly=float(q.monthly_price_inr.sum()); setup=float(q.setup_fee_inr.sum())
    contract=int(pd.to_numeric(q.min_contract_months,errors="coerce").fillna(12).max())
    return q,monthly,setup,contract
