# app.py
# Local Food Wastage Management System — Robust rewrite with interactive Dashboard (8 EDA charts),
# defensive data handling, CRUD, Queries (15), Data export, and contact links.
#
# Expects (in repo root):
#   - food_wastage.db
#   - providers_data.csv
#   - receivers_data.csv
#   - food_listings_data.csv
#   - claims_data.csv

import os
import sqlite3
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

# ---------------------------
# Styling
# ---------------------------
THEME_CSS = """
<style>
:root { --beige:#E8E2D0; --dark-green:#2E5339; --accent-green:#4F8F4F; --ink:#1A1A1A; }
.stApp { background:var(--beige); color:var(--dark-green); font-family: 'Segoe UI', sans-serif; }
h1,h2,h3,h4 { color:var(--dark-green) !important; font-weight:700; }
section[data-testid="stSidebar"] { background:var(--dark-green); color:#e8efe8; }
section[data-testid="stSidebar"] * { color:#e8efe8 !important; }
.card { background:#fff; border-radius:10px; padding:12px; box-shadow: 0 4px 12px rgba(0,0,0,0.06);}
.kpi { font-size:12px; color:#6b8f73; text-transform:uppercase; }
.kpi-value { font-size:26px; font-weight:800; color:var(--dark-green); }
.stButton>button { background:var(--accent-green); color:white; border-radius:8px; border:none; padding:.5rem .8rem; font-weight:700; }
.dataframe th { background:var(--accent-green) !important; color:white !important; }
.link { color:var(--accent-green); font-weight:700; text-decoration:none; }
.small { font-size:12px; opacity:.9; }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# ---------------------------
# Paths & DB helpers
# ---------------------------
DB_PATH = "food_wastage.db"
CSV_FILES = {
    "Providers": "providers_data.csv",
    "Receivers": "receivers_data.csv",
    "Food_Listings": "food_listings_data.csv",
    "Claims": "claims_data.csv",
}

@st.cache_resource
def get_conn(path=DB_PATH):
    return sqlite3.connect(path, check_same_thread=False)

conn = get_conn(DB_PATH)

def table_exists(name: str) -> bool:
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", conn, params=(name,))
        return not df.empty
    except Exception:
        return False

def run_sql(sql: str, params=None) -> pd.DataFrame:
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

def exec_sql(sql: str, params=None) -> bool:
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"DB command error: {e}")
        return False

# Optional: refresh DB from CSVs (keeps schema same)
def refresh_db_from_csvs():
    missing = [name for name, path in CSV_FILES.items() if not os.path.exists(path)]
    if missing:
        st.error("Missing CSVs: " + ", ".join(missing))
        return False
    try:
        for tbl, path in CSV_FILES.items():
            df = pd.read_csv(path, dtype=str)
            # trim whitespace in string cols
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].str.strip()
            # write to sqlite
            df.to_sql(tbl, conn, index=False, if_exists="replace")
        conn.commit()
        st.success("DB refreshed from CSVs.")
        return True
    except Exception as e:
        st.error("Failed to refresh DB from CSVs: " + str(e))
        return False

# ---------------------------
# Header images
# ---------------------------
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None

c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img: st.image(left_img, width=80)
with c2:
    st.markdown("<h1 style='text-align:center;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img: st.image(right_img, width=64)
st.markdown("---")

# ---------------------------
# Sidebar / Navigation
# ---------------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", [
    "Dashboard",
    "Donations Analysis",
    "Providers Insights",
    "Receivers Insights",
    "Wastage & Expiry",
    "Filter Food Donations",
    "Queries",
    "CRUD",
    "Data",
    "About"
])

with st.sidebar.expander("Database actions"):
    if st.button("🔄 Refresh DB from CSVs"):
        refresh_db_from_csvs()

# ---------------------------
# Load and prepare tables (defensive)
# ---------------------------
@st.cache_data(show_spinner=False)
def load_tables():
    out = {}
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        if table_exists(t):
            df = pd.read_sql(f"SELECT * FROM {t}", conn)
            # normalize column names
            df.columns = df.columns.str.strip()
            # strip whitespace from object columns
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip()
            out[t] = df
        else:
            out[t] = pd.DataFrame()
    return out

dfs = load_tables()
providers = dfs["Providers"]
receivers = dfs["Receivers"]
food = dfs["Food_Listings"]
claims = dfs["Claims"]

# Utility helpers
def safe_to_datetime(s):
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.Series(pd.NaT, index=s.index if hasattr(s, "index") else None)

def compute_days_to_expiry(df):
    if df.empty or "Expiry_Date" not in df.columns:
        return df
    out = df.copy()
    out["Expiry_Date"] = safe_to_datetime(out["Expiry_Date"])
    today = pd.to_datetime(date.today())
    out["Days_To_Expiry"] = (out["Expiry_Date"].dt.normalize() - today).dt.days.abs()
    # cast to Int where possible
    out["Days_To_Expiry"] = out["Days_To_Expiry"].astype("Int64")
    return out

def make_contact_markdown(name, contact):
    if not contact or str(contact).strip().lower() in {"", "nan", "none"}:
        return f"- **{name}** — (no contact)"
    contact_s = str(contact).strip()
    if "@" in contact_s:
        return f"- **{name}** — [{contact_s}](mailto:{contact_s})"
    return f"- **{name}** — [{contact_s}](tel:{contact_s})"

# ---------------------------
# Defensive checks for columns expected
# ---------------------------
# Fix potential column name mismatches / duplicates
def normalize_provider_columns(df):
    if df.empty: return df
    df = df.copy()
    # unify Provider_Type: prefer Provider_Type, else Type (from Providers or Food_Listings)
    if "Provider_Type" not in df.columns and "Type" in df.columns:
        df.rename(columns={"Type":"Provider_Type"}, inplace=True)
    return df

food = compute_days_to_expiry(food)
providers = normalize_provider_columns(providers)

# ---------------------------
# DASHBOARD (interactive EDA)
# ---------------------------
if page == "Dashboard":
    st.header("Dashboard — Interactive EDA")

    if food.empty or providers.empty:
        st.warning("Required tables missing: Food_Listings and Providers are needed for full dashboard.")
        st.info("Go to 'Data' page to confirm table presence or use 'Refresh DB from CSVs' in sidebar.")
    # Global filters container
    with st.expander("Global filters (affect all dashboard visuals)", expanded=True):
        # City choices (from providers.city, food.location, receivers.city)
        city_choices = sorted(list(set(
            providers.get("City", pd.Series()).dropna().unique().tolist() +
            receivers.get("City", pd.Series()).dropna().unique().tolist() +
            food.get("Location", pd.Series()).dropna().unique().tolist()
        )))
        sel_city = st.selectbox("City", ["All"] + city_choices, index=0)
        ft_choices = sorted(food.get("Food_Type", pd.Series()).dropna().unique().tolist())
        sel_food_types = st.multiselect("Food Type (multi)", options=ft_choices, default=ft_choices if ft_choices else [])
        meal_choices = sorted(food.get("Meal_Type", pd.Series()).dropna().unique().tolist())
        sel_meals = st.multiselect("Meal Type", options=meal_choices, default=meal_choices if meal_choices else [])
        # days to expiry slider
        min_day = int(food["Days_To_Expiry"].min()) if "Days_To_Expiry" in food.columns and food["Days_To_Expiry"].notna().any() else 0
        max_day = int(food["Days_To_Expiry"].max()) if "Days_To_Expiry" in food.columns and food["Days_To_Expiry"].notna().any() else 30
        sel_days = st.slider("Days to expiry (absolute)", min_value=min_day, max_value=max_day if max_day>min_day else min_day+7, value=(min_day, min_day+7))

    # Apply same filters programmatically
    wf = food.copy()
    if sel_city and sel_city != "All":
        wf = wf[
            wf["Location"].astype(str).str.lower().eq(sel_city.lower()) |
            wf.get("Provider_City", pd.Series([""]*len(wf))).astype(str).str.lower().eq(sel_city.lower())
        ]
    if sel_food_types:
        wf = wf[wf["Food_Type"].isin(sel_food_types)]
    if sel_meals:
        wf = wf[wf["Meal_Type"].isin(sel_meals)]
    if "Days_To_Expiry" in wf.columns:
        wf = wf[(wf["Days_To_Expiry"].notna()) & (wf["Days_To_Expiry"] >= sel_days[0]) & (wf["Days_To_Expiry"] <= sel_days[1])]

    # KPIs
    st.subheader("Key Metrics")
    k1, k2, k3, k4 = st.columns(4)
    try:
        total_providers = int(run_sql("SELECT COUNT(*) AS c FROM Providers")["c"].iloc[0]) if table_exists("Providers") else 0
    except Exception:
        total_providers = 0
    try:
        total_receivers = int(run_sql("SELECT COUNT(*) AS c FROM Receivers")["c"].iloc[0]) if table_exists("Receivers") else 0
    except Exception:
        total_receivers = 0
    total_food_qty = int(wf["Quantity"].astype(float).sum()) if "Quantity" in wf.columns and not wf.empty else 0
    try:
        total_claims = int(run_sql("SELECT COUNT(*) AS c FROM Claims")["c"].iloc[0]) if table_exists("Claims") else 0
    except Exception:
        total_claims = 0

    k1.metric("Providers", total_providers)
    k2.metric("Receivers", total_receivers)
    k3.metric("Total Food Quantity (filtered)", total_food_qty)
    k4.metric("Total Claims (DB)", total_claims)

    st.markdown("---")

    # Chart 1: Food Type Distribution (pie)
    st.subheader("1) Food Type Distribution")
    if "Food_Type" in wf.columns and not wf.empty:
        ft = wf.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        ch = alt.Chart(ft).mark_arc().encode(theta="Quantity:Q", color="Food_Type:N", tooltip=["Food_Type", "Quantity"])
        st.altair_chart(ch, use_container_width=True)
    else:
        st.info("No Food_Type data available for the current filters.")

    # Chart 2: Top Providers by total donation (horizontal bar)
    st.subheader("2) Top Providers by Donated Quantity")
    prov_join = wf.merge(providers[["Provider_ID","Name"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name"})
    prov_join["Quantity"] = pd.to_numeric(prov_join.get("Quantity", 0), errors="coerce").fillna(0)
    top_prov = prov_join.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(15)
    if not top_prov.empty:
        ch = alt.Chart(top_prov).mark_bar().encode(
            x="Quantity:Q",
            y=alt.Y("Provider_Name:N", sort='-x'),
            tooltip=["Provider_Name", "Quantity"]
        ).properties(height=380)
        st.altair_chart(ch, use_container_width=True)
    else:
        st.info("No provider donation data for the filters.")

    # Chart 3: Monthly donation trends (from Food_Listings expiry/listing date if available)
    st.subheader("3) Monthly Quantity Listed (by expiry month if present)")
    if "Expiry_Date" in food.columns:
        mx = food.copy()
        mx["Expiry_Date"] = safe_to_datetime(mx["Expiry_Date"])
        mx["YearMonth"] = mx["Expiry_Date"].dt.to_period("M").astype(str).fillna("Unknown")
        monthly = mx.groupby("YearMonth", as_index=False)["Quantity"].sum().sort_values("YearMonth")
        st.altair_chart(alt.Chart(monthly).mark_line(point=True).encode(x="YearMonth:N", y="Quantity:Q", tooltip=["YearMonth","Quantity"]), use_container_width=True)
    else:
        st.info("No expiry/listing date column to build monthly trend.")

    # Chart 4: Top claim locations — join claims -> food -> receivers (if available)
    st.subheader("4) Top Claim Locations (by claim count)")
    if not claims.empty:
        loc_df = claims.copy()
        # join food to extract Location
        if "Food_ID" in claims.columns and "Food_ID" in food.columns:
            loc_df = loc_df.merge(food[["Food_ID","Location"]], on="Food_ID", how="left")
        loc_counts = loc_df["Location"].value_counts().reset_index().rename(columns={"index":"Location","Location":"Claims"}).head(15)
        if not loc_counts.empty:
            st.altair_chart(alt.Chart(loc_counts).mark_bar().encode(x="Claims:Q", y=alt.Y("Location:N", sort="-x"), tooltip=["Location","Claims"]), use_container_width=True)
        else:
            st.info("No claim location data.")
    else:
        st.info("No claims data available.")

    # Chart 5: Provider vs Receiver count by city (grouped bar)
    st.subheader("5) Provider vs Receiver Counts by City")
    cities = sorted(set(providers.get("City", pd.Series()).dropna().unique().tolist() + receivers.get("City", pd.Series()).dropna().unique().tolist()))
    pr_counts = []
    for c in cities:
        pcount = int(providers[providers.get("City","").str.lower() == str(c).lower()].shape[0]) if not providers.empty else 0
        rcount = int(receivers[receivers.get("City","").str.lower() == str(c).lower()].shape[0]) if not receivers.empty else 0
        pr_counts.append({"City": c, "Providers": pcount, "Receivers": rcount})
    prdf = pd.DataFrame(pr_counts)
    if not prdf.empty:
        pr_long = prdf.melt(id_vars="City", value_vars=["Providers","Receivers"], var_name="Type", value_name="Count")
        st.altair_chart(alt.Chart(pr_long).mark_bar().encode(x="Count:Q", y=alt.Y("City:N", sort="-x"), color="Type:N", tooltip=["City","Type","Count"]), use_container_width=True)
    else:
        st.info("No city-level provider/receiver data available.")

    # Chart 6: Average claim-to-donation time (boxplot) — requires Claims.Timestamp and Food_Listings listing date
    st.subheader("6) Claim-to-Donation Time (days) — distribution")
    if not claims.empty and "Timestamp" in claims.columns and "Food_ID" in claims.columns and "Food_ID" in food.columns:
        # earliest listing date from food's Expiry_Date used as proxy for listing date if no explicit listing date exists
        cf = claims.merge(food[["Food_ID","Expiry_Date"]], on="Food_ID", how="left")
        cf["Claim_Timestamp"] = pd.to_datetime(cf["Timestamp"], errors="coerce")
        cf["Expiry_Date"] = safe_to_datetime(cf["Expiry_Date"])
        # compute difference in days where both present
        cf["LagDays"] = (cf["Claim_Timestamp"].dt.normalize() - cf["Expiry_Date"].dt.normalize()).dt.days.abs()
        lf = cf.dropna(subset=["LagDays"])
        if not lf.empty:
            box = alt.Chart(lf).mark_boxplot().encode(
                y=alt.Y("LagDays:Q", title="Days (abs)"),
                tooltip=["Food_ID","Receiver_ID","LagDays"]
            )
            st.altair_chart(box, use_container_width=True)
        else:
            st.info("No valid timestamps/dates to compute claim-to-donation lag.")
    else:
        st.info("Claims timestamps or food listing dates missing for lag analysis.")

    # Chart 7: Correlation heatmap of numeric fields across food
    st.subheader("7) Numeric Correlation (Food listings)")
    numeric_cols = [c for c in food.columns if pd.api.types.is_numeric_dtype(food[c])]
    if numeric_cols:
        corr = food[numeric_cols].corr()
        # transform to long form for Altair heatmap
        corr_long = corr.reset_index().melt(id_vars="index")
        corr_long.columns = ["var1", "var2", "corr"]
        heat = alt.Chart(corr_long).mark_rect().encode(
            x=alt.X("var1:N", title=""),
            y=alt.Y("var2:N", title=""),
            color=alt.Color("corr:Q", scale=alt.Scale(scheme="redyellowgreen")),
            tooltip=["var1","var2","corr"]
        ).properties(height=400)
        st.altair_chart(heat, use_container_width=True)
    else:
        st.info("No numeric columns to compute correlation.")

    # Chart 8: Wastage trend — expired quantities over time (if Expiry_Date exists)
    st.subheader("8) Wastage (expired) quantity by expiry date")
    if "Expiry_Date" in food.columns:
        fexp = food.copy()
        fexp["Expiry_Date"] = safe_to_datetime(fexp["Expiry_Date"])
        expired = fexp[fexp["Expiry_Date"] < pd.to_datetime(date.today())]
        if not expired.empty:
            exp_month = expired.groupby(expired["Expiry_Date"].dt.to_period("M").astype(str), as_index=False)["Quantity"].sum()
            st.altair_chart(alt.Chart(exp_month).mark_line(point=True).encode(x="Expiry_Date:T", y="Quantity:Q", tooltip=["Expiry_Date","Quantity"]), use_container_width=True)
        else:
            st.info("No expired listings found.")
    else:
        st.info("No Expiry_Date column for wastage trend.")

# ---------------------------
# Donations Analysis
# ---------------------------
elif page == "Donations Analysis":
    st.header("Donations Analysis")

    if food.empty:
        st.warning("No Food_Listings table.")
        st.stop()

    f = food.copy()
    f["Expiry_Date"] = safe_to_datetime(f.get("Expiry_Date", pd.Series()))
    f["YearMonth"] = f["Expiry_Date"].dt.to_period("M").astype(str).fillna("Unknown")
    # Monthly quantity listed
    st.subheader("Monthly quantity (by expiry month)")
    monthly = f.groupby("YearMonth", as_index=False)["Quantity"].sum().sort_values("YearMonth")
    if not monthly.empty:
        st.altair_chart(alt.Chart(monthly).mark_line(point=True).encode(x="YearMonth:N", y="Quantity:Q", tooltip=["YearMonth","Quantity"]), use_container_width=True)
    else:
        st.info("Not enough date/quantity data for monthly chart.")

    # Food type distribution
    st.subheader("Food type distribution")
    if "Food_Type" in f.columns:
        ft = f.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        st.altair_chart(alt.Chart(ft).mark_bar().encode(x="Quantity:Q", y=alt.Y("Food_Type:N", sort="-x"), tooltip=["Food_Type","Quantity"]), use_container_width=True)
    else:
        st.info("No Food_Type column.")

    # Meal types
    st.subheader("Meal type breakdown")
    if "Meal_Type" in f.columns:
        mt = f.groupby("Meal_Type", as_index=False)["Quantity"].sum()
        st.altair_chart(alt.Chart(mt).mark_arc().encode(theta="Quantity:Q", color="Meal_Type:N", tooltip=["Meal_Type","Quantity"]), use_container_width=True)
    else:
        st.info("No Meal_Type column.")

# ---------------------------
# Providers Insights
# ---------------------------
elif page == "Providers Insights":
    st.header("Providers Insights")
    if providers.empty or food.empty:
        st.warning("Providers or Food_Listings missing.")
        st.stop()

    pf = food.merge(providers[["Provider_ID","Name","City","Type"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Type":"Provider_Type"})
    # ensure Provider_Type present as simple 1D column
    if "Provider_Type" not in pf.columns:
        pf["Provider_Type"] = pf.get("Provider_Type", pf.get("Type", "Unknown")).astype(str)
    pf["Quantity"] = pd.to_numeric(pf.get("Quantity", 0), errors="coerce").fillna(0)

    st.subheader("Top Providers by donated quantity")
    topP = pf.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    if not topP.empty:
        st.altair_chart(alt.Chart(topP).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Name:N", sort="-x"), tooltip=["Provider_Name","Quantity"]), use_container_width=True)
    else:
        st.info("No provider quantity data.")

    st.subheader("Provider Type contributions")
    if "Provider_Type" in pf.columns:
        pt = pf.groupby("Provider_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        if not pt.empty:
            st.altair_chart(alt.Chart(pt).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Type:N", sort="-x"), tooltip=["Provider_Type","Quantity"]), use_container_width=True)
        else:
            st.info("Provider type aggregation empty.")
    else:
        st.info("Provider_Type column missing.")

    st.subheader("Provider contacts")
    md_lines = []
    for _, r in providers.fillna("").iterrows():
        md_lines.append(make_contact_markdown(r.get("Name","(no name)"), r.get("Contact","")))
    st.write("\n".join(md_lines))

# ---------------------------
# Receivers Insights
# ---------------------------
elif page == "Receivers Insights":
    st.header("Receivers Insights")
    if receivers.empty or claims.empty:
        st.warning("Receivers or Claims missing.")
        st.stop()

    cf = claims.merge(receivers[["Receiver_ID","Name","City","Contact"]], on="Receiver_ID", how="left").rename(columns={"Name":"Receiver_Name"})
    # join quantity from food if possible
    if "Food_ID" in cf.columns and "Food_ID" in food.columns:
        cf = cf.merge(food[["Food_ID","Quantity","Location"]], on="Food_ID", how="left")
    cf["Quantity"] = pd.to_numeric(cf.get("Quantity",0), errors="coerce").fillna(0)

    st.subheader("Top receivers by claimed quantity")
    rtop = cf.groupby("Receiver_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    if not rtop.empty:
        st.altair_chart(alt.Chart(rtop).mark_bar().encode(x="Quantity:Q", y=alt.Y("Receiver_Name:N", sort="-x"), tooltip=["Receiver_Name","Quantity"]), use_container_width=True)
    else:
        st.info("No receiver claim quantity data.")

    st.subheader("Receiver contact list")
    md_lines = []
    for _, r in receivers.fillna("").iterrows():
        md_lines.append(make_contact_markdown(r.get("Name","(no name)"), r.get("Contact","")))
    st.write("\n".join(md_lines))

# ---------------------------
# Wastage & Expiry
# ---------------------------
elif page == "Wastage & Expiry":
    st.header("Wastage & Expiry Analysis")
    if food.empty:
        st.warning("Food_Listings missing.")
        st.stop()

    f = compute_days_to_expiry(food)
    st.subheader("Quantity by absolute Days-to-Expiry")
    if "Days_To_Expiry" in f.columns:
        dte = f.groupby("Days_To_Expiry", as_index=False)["Quantity"].sum().sort_values("Days_To_Expiry")
        if not dte.empty:
            st.altair_chart(alt.Chart(dte).mark_bar().encode(x="Days_To_Expiry:Q", y="Quantity:Q", tooltip=["Days_To_Expiry","Quantity"]), use_container_width=True)
        else:
            st.info("No Days_To_Expiry aggregated data.")
    else:
        st.info("Expiry_Date column missing.")

    st.subheader("Expired listings (details)")
    expired = f[pd.to_datetime(f.get("Expiry_Date", pd.Series()), errors="coerce") < pd.to_datetime(date.today())]
    if not expired.empty:
        cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Food_Type","Meal_Type","Days_To_Expiry"] if c in expired.columns]
        st.dataframe(expired[cols].sort_values("Expiry_Date"), use_container_width=True)
    else:
        st.info("No expired records.")

# ---------------------------
# Filter Food Donations (search + contact)
# ---------------------------
elif page == "Filter Food Donations":
    st.header("Filter Food Donations")
    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers table missing.")
        st.stop()

    merged = food.merge(providers[["Provider_ID","Name","Contact"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Contact":"Provider_Contact"})
    cities = ["All"] + sorted(merged["Location"].dropna().unique().tolist())
    provs = ["All"] + sorted(merged["Provider_Name"].dropna().unique().tolist())
    ftypes = ["All"] + sorted(merged["Food_Type"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    sel_city = c1.selectbox("City", cities)
    sel_provider = c2.selectbox("Provider", provs)
    sel_foodtype = c3.selectbox("Food Type", ftypes)

    rs = merged.copy()
    if sel_city != "All":
        rs = rs[rs["Location"] == sel_city]
    if sel_provider != "All":
        rs = rs[rs["Provider_Name"] == sel_provider]
    if sel_foodtype != "All":
        rs = rs[rs["Food_Type"] == sel_foodtype]

    if rs.empty:
        st.info("No matching listings.")
    else:
        # show table normally
        display_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Provider_Name","Food_Type","Meal_Type"] if c in rs.columns]
        st.dataframe(rs[display_cols].sort_values("Expiry_Date"), use_container_width=True)

        st.markdown("**Contact links**")
        for _, r in rs[["Provider_Name","Provider_Contact"]].drop_duplicates().iterrows():
            st.markdown(make_contact_markdown(r.get("Provider_Name","(no name)"), r.get("Provider_Contact","")))

# ---------------------------
# Queries (15)
# ---------------------------
elif page == "Queries":
    st.header("SQL Queries & Outputs")
    QUERIES = {
        "Q1: Providers & Receivers per City": """
            SELECT City, SUM(Providers) AS Providers_Count, SUM(Receivers) AS Receivers_Count
            FROM (
                SELECT City, COUNT(Provider_ID) AS Providers, 0 AS Receivers FROM Providers GROUP BY City
                UNION ALL
                SELECT City, 0 AS Providers, COUNT(Receiver_ID) AS Receivers FROM Receivers GROUP BY City
            )
            GROUP BY City
            ORDER BY Providers_Count DESC;
        """,
        "Q2: Top contributing provider type (by quantity)": """
            SELECT Provider_Type, SUM(Quantity) AS Total_Quantity
            FROM Food_Listings
            GROUP BY Provider_Type
            ORDER BY Total_Quantity DESC;
        """,
        "Q3: Contact info of providers in a city (param)": """
            SELECT Name, Type, City, Contact
            FROM Providers
            WHERE LOWER(City) = LOWER(?);
        """,
        "Q4: Receivers with most claims": """
            SELECT r.Receiver_ID, r.Name, r.City, COUNT(c.Claim_ID) AS Total_Claims
            FROM Claims c
            JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID, r.Name
            ORDER BY Total_Claims DESC;
        """,
        "Q5: Total quantity of food available": "SELECT IFNULL(SUM(Quantity),0) AS Total_Quantity FROM Food_Listings;",
        "Q6: City with highest number of listings": """
            SELECT Location AS City, COUNT(*) AS Listings_Count
            FROM Food_Listings
            GROUP BY Location
            ORDER BY Listings_Count DESC
            LIMIT 10;
        """,
        "Q7: Most commonly available food types": """
            SELECT Food_Type, COUNT(*) AS Occurrences, SUM(Quantity) AS Total_Quantity
            FROM Food_Listings
            GROUP BY Food_Type
            ORDER BY Occurrences DESC;
        """,
        "Q8: Claims made per food item": """
            SELECT f.Food_ID, f.Food_Name, COUNT(c.Claim_ID) AS Claims_Count
            FROM Food_Listings f
            LEFT JOIN Claims c ON f.Food_ID = c.Food_ID
            GROUP BY f.Food_ID, f.Food_Name
            ORDER BY Claims_Count DESC;
        """,
        "Q9: Provider with highest successful claims": """
            SELECT p.Provider_ID, p.Name, p.City, COUNT(c.Claim_ID) AS Completed_Claims
            FROM Claims c
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE LOWER(c.Status) = 'completed'
            GROUP BY p.Provider_ID, p.Name
            ORDER BY Completed_Claims DESC
            LIMIT 10;
        """,
        "Q10: Claims status distribution (%)": """
            SELECT Status, COUNT(*) AS Count,
                   ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Claims),2) AS Percentage
            FROM Claims
            GROUP BY Status;
        """,
        "Q11: Average quantity claimed per receiver": """
            SELECT r.Receiver_ID, r.Name,
                   ROUND(AVG(f.Quantity),2) AS Avg_Quantity,
                   SUM(f.Quantity) AS Total_Quantity,
                   COUNT(c.Claim_ID) AS Claim_Count
            FROM Claims c
            JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            GROUP BY r.Receiver_ID, r.Name
            ORDER BY Total_Quantity DESC
            LIMIT 50;
        """,
        "Q12: Most claimed meal type": """
            SELECT f.Meal_Type, COUNT(c.Claim_ID) AS Claims_Count, SUM(f.Quantity) AS Total_Quantity
            FROM Claims c
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            GROUP BY f.Meal_Type
            ORDER BY Claims_Count DESC;
        """,
        "Q13: Total quantity donated by each provider": """
            SELECT p.Provider_ID, p.Name, p.City, SUM(f.Quantity) AS Total_Donated
            FROM Food_Listings f
            JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.Provider_ID, p.Name
            ORDER BY Total_Donated DESC
            LIMIT 50;
        """,
        "Q14: Expired food listings": """
            SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location
            FROM Food_Listings f
            LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) < date('now')
            ORDER BY f.Expiry_Date ASC;
        """,
        "Q15: Listings expiring within next 3 days (abs days)": """
            SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location,
                   ABS(CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER)) AS Days_To_Expiry
            FROM Food_Listings f
            LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now','+3 days')
            ORDER BY Days_To_Expiry ASC;
        """,
    }

    qkey = st.selectbox("Choose query", list(QUERIES.keys()))
    st.code(QUERIES[qkey], language="sql")
    params = None
    if qkey == "Q3: Contact info of providers in a city (param)":
        city = st.text_input("Enter city (case-insensitive)").strip()
        if city:
            params = (city,)
        else:
            st.info("Enter city to run Q3.")
    if qkey.startswith("Q3") and not params:
        pass
    else:
        out = run_sql(QUERIES[qkey], params)
        if out.empty:
            st.info("No results for this query.")
        else:
            st.dataframe(out, use_container_width=True)
            st.download_button("Download result as CSV", out.to_csv(index=False).encode("utf-8"), file_name=f"{qkey.replace(' ','_')}.csv")

# ---------------------------
# CRUD
# ---------------------------
elif page == "CRUD":
    st.header("CRUD operations (Providers / Receivers / Food_Listings / Claims)")

    table = st.selectbox("Select table", ["Providers","Receivers","Food_Listings","Claims"])
    if not table_exists(table):
        st.warning(f"Table {table} not found in DB.")
        st.stop()
    df = run_sql(f"SELECT * FROM {table}")
    st.subheader("Existing data")
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("Add new record")
    # if df empty, provide fallback columns
    if not df.empty:
        cols = df.columns.tolist()
    else:
        fallback = {
            "Providers": ["Name","Type","Address","City","Contact"],
            "Receivers": ["Name","Type","City","Contact"],
            "Food_Listings": ["Food_Name","Quantity","Expiry_Date","Provider_ID","Provider_Type","Location","Food_Type","Meal_Type"],
            "Claims": ["Food_ID","Receiver_ID","Status","Timestamp"]
        }
        cols = fallback.get(table, [])
    add_vals = {}
    pk_like = {c for c in cols if c.lower() in {"provider_id","receiver_id","food_id","claim_id"}}
    for c in cols:
        if c in pk_like:
            st.text(f"{c} (optional / autoincrement)")
            continue
        if c.lower().endswith("date") or c.lower() == "timestamp":
            val = st.date_input(c, value=date.today(), key=f"add_{c}")
            add_vals[c] = str(val)
        elif c.lower() == "quantity":
            add_vals[c] = st.number_input(c, min_value=0, value=1, key=f"add_{c}")
        else:
            add_vals[c] = st.text_input(c, key=f"add_{c}")
    if st.button("Add record"):
        if add_vals:
            colnames = ", ".join(add_vals.keys())
            placeholders = ", ".join(["?"]*len(add_vals))
            ok = exec_sql(f"INSERT INTO {table} ({colnames}) VALUES ({placeholders})", tuple(add_vals.values()))
            if ok:
                st.success("Record added.")

    st.markdown("---")
    st.subheader("Update record")
    if not df.empty:
        pk = df.columns[0]
        sel = st.selectbox(f"Select {pk} to update", df[pk].tolist())
        row = df[df[pk] == sel].iloc[0].to_dict()
        upd_vals = {}
        for c in df.columns:
            if c == pk:
                st.caption(f"{pk} (primary key): {sel}")
                continue
            upd_vals[c] = st.text_input(c, value=str(row[c]), key=f"upd_{c}")
        if st.button("Update record"):
            set_clause = ", ".join([f"{k}=?" for k in upd_vals.keys()])
            params = tuple(upd_vals.values()) + (sel,)
            ok = exec_sql(f"UPDATE {table} SET {set_clause} WHERE {pk} = ?", params)
            if ok:
                st.success("Record updated.")

    st.markdown("---")
    st.subheader("Delete record")
    if not df.empty:
        pk = df.columns[0]
        del_id = st.selectbox(f"Select {pk} to delete", df[pk].tolist(), key="del_id")
        if st.button("Delete record"):
            ok = exec_sql(f"DELETE FROM {table} WHERE {pk} = ?", (del_id,))
            if ok:
                st.success("Record deleted.")

# ---------------------------
# Data export view
# ---------------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        st.subheader(t)
        if table_exists(t):
            d = run_sql(f"SELECT * FROM {t}")
            st.dataframe(d, use_container_width=True)
            st.download_button(f"Download {t}.csv", d.to_csv(index=False).encode("utf-8"), file_name=f"{t}.csv")
        else:
            st.info(f"Table {t} not found.")

# ---------------------------
# About
# ---------------------------
elif page == "About":
    st.header("About")
    st.markdown("""
**Local Food Wastage Management System**

Features:
- Interactive Power BI–style Dashboard with multiple EDA views (8 charts)
- Global filters (city / food type / meal type / days to expiry)
- CRUD for Providers, Receivers, Food Listings, Claims
- 15 SQL queries with CSV download
- Contact links for providers & receivers

Data sources expected in the repo:
- food_wastage.db (preferred DB)
- providers_data.csv
- receivers_data.csv
- food_listings_data.csv
- claims_data.csv

If anything still fails, paste the full traceback from the app logs and I'll patch it immediately.
""")
