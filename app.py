# app.py - Robust, defensive Streamlit app for Local Food Wastage Management System
# - Uses food_wastage.db if present, otherwise attempts to build DB from CSVs in repo root.
# - Dashboard contains 6+ EDA charts (no geographic map).
# - Full Queries (15), CRUD, Data download pages included.

import os
import sqlite3
from datetime import date
from typing import Tuple

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

# -------------------------
# Config & Styling
# -------------------------
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

st.markdown("""
<style>
:root { --beige:#E8E2D0; --dark-green:#2E5339; --accent:#4F8F4F; --ink:#1A1A1A; }
.stApp { background:var(--beige); color:var(--dark-green); font-family: 'Segoe UI', sans-serif; }
h1,h2,h3 { color:var(--dark-green) !important; font-weight:700; }
section[data-testid="stSidebar"] { background:var(--dark-green); color: #eaf3ea; }
.stButton>button { background:var(--accent); color:white; border-radius:8px; border: none; padding:.5rem 1rem; font-weight:700; }
.card { background:white; padding:12px; border-radius:8px; box-shadow: 0 6px 18px rgba(0,0,0,0.06);}
</style>
""", unsafe_allow_html=True)

# -------------------------
# Paths / DB helpers
# -------------------------
DB_PATH = "food_wastage.db"
CSV_MAP = {
    "Providers": "providers_data.csv",
    "Receivers": "receivers_data.csv",
    "Food_Listings": "food_listings_data.csv",
    "Claims": "claims_data.csv",
}

@st.cache_resource
def get_conn(path: str = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(path, check_same_thread=False)

# Try to ensure the DB exists or build from CSVs
def ensure_db_from_csvs(conn: sqlite3.Connection) -> Tuple[bool, str]:
    missing = [p for p in CSV_MAP.values() if not os.path.exists(p)]
    if missing:
        return False, f"Missing CSVs: {', '.join(missing)}"
    try:
        for tbl, csv in CSV_MAP.items():
            df = pd.read_csv(csv, dtype=str)
            # trim whitespace in text cols
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].str.strip().replace({"nan": "", "None": ""})
            # write to sqlite (replace)
            df.to_sql(tbl, conn, index=False, if_exists="replace")
        conn.commit()
        return True, "DB created from CSVs"
    except Exception as e:
        return False, f"Failed to create DB from CSVs: {e}"

# Connect
if not os.path.exists(DB_PATH):
    # create db and try to load CSVs
    conn_temp = sqlite3.connect(DB_PATH)
    ok, msg = ensure_db_from_csvs(conn_temp)
    conn_temp.close()
    if not ok:
        st.warning("Database not found and could not create from CSVs: " + msg)

conn = get_conn()

def table_exists(name: str) -> bool:
    try:
        q = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", conn, params=(name,))
        return not q.empty
    except Exception:
        return False

def run_sql(sql: str, params: tuple | None = None) -> pd.DataFrame:
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

def exec_sql(sql: str, params: tuple | None = None) -> bool:
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"DB exec error: {e}")
        return False

# -------------------------
# Load tables defensively
# -------------------------
@st.cache_data(show_spinner=False)
def load_tables() -> dict:
    out = {}
    for t in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        if table_exists(t):
            df = pd.read_sql(f"SELECT * FROM {t}", conn)
            # normalize column names and strip text
            df.columns = df.columns.str.strip()
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": "", "None": ""})
            out[t] = df
        else:
            out[t] = pd.DataFrame()
    return out

tables = load_tables()
providers = tables["Providers"]
receivers = tables["Receivers"]
food = tables["Food_Listings"]
claims = tables["Claims"]

# -------------------------
# Utility helpers
# -------------------------
def safe_dt(series):
    return pd.to_datetime(series, errors="coerce")

def compute_days_to_expiry(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Expiry_Date" not in df.columns:
        return df
    df = df.copy()
    df["Expiry_Date"] = safe_dt(df["Expiry_Date"])
    today = pd.to_datetime(date.today())
    # absolute days to expiry (non-negative)
    df["Days_To_Expiry"] = (df["Expiry_Date"].dt.normalize() - today).dt.days.abs().astype("Int64")
    return df

def contact_md(name, contact):
    if not contact or str(contact).strip().lower() in {"", "nan", "none"}:
        return f"- **{name}** — (no contact)"
    c = str(contact).strip()
    if "@" in c:
        return f"- **{name}** — [{c}](mailto:{c})"
    return f"- **{name}** — [{c}](tel:{c})"

# Prepare some cleaned DF copies for analysis
food = compute_days_to_expiry(food)
# coerce numeric quantity where possible
if "Quantity" in food.columns:
    food["Quantity"] = pd.to_numeric(food["Quantity"], errors="coerce").fillna(0)

if "Quantity" in claims.columns:
    claims["Quantity"] = pd.to_numeric(claims["Quantity"], errors="coerce").fillna(0)

# -------------------------
# Header images + title
# -------------------------
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None
c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img: st.image(left_img, width=80)
with c2:
    st.markdown("<h1 style='text-align:center;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img: st.image(right_img, width=70)
st.markdown("---")

# -------------------------
# Sidebar navigation
# -------------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Donations Analysis", "Providers Insights", "Receivers Insights",
                                 "Wastage & Expiry", "Filter Food Donations", "Queries", "CRUD", "Data", "About"])

with st.sidebar.expander("DB actions"):
    if st.button("Refresh DB from CSVs"):
        ok, msg = ensure_db_from_csvs(conn)
        if ok:
            st.experimental_rerun()
        else:
            st.error(msg)

# -------------------------
# DASHBOARD (many EDA visuals - no geo)
# -------------------------
if page == "Dashboard":
    st.header("Dashboard — EDA (no geographic analysis)")

    # global filter choices
    with st.expander("Global filters", expanded=True):
        cities = sorted(set(
            providers.get("City", pd.Series()).dropna().unique().tolist() +
            receivers.get("City", pd.Series()).dropna().unique().tolist() +
            food.get("Location", pd.Series()).dropna().unique().tolist()
        ))
        city = st.selectbox("City (filter)", options=["All"] + cities, index=0)
        food_types = sorted(food.get("Food_Type", pd.Series()).dropna().unique().tolist())
        sel_food_types = st.multiselect("Food Type", options=food_types, default=food_types if food_types else [])
        meal_types = sorted(food.get("Meal_Type", pd.Series()).dropna().unique().tolist())
        sel_meals = st.multiselect("Meal Type", options=meal_types, default=meal_types if meal_types else [])
        min_day = int(food["Days_To_Expiry"].min()) if "Days_To_Expiry" in food.columns and food["Days_To_Expiry"].notna().any() else 0
        max_day = int(food["Days_To_Expiry"].max()) if "Days_To_Expiry" in food.columns and food["Days_To_Expiry"].notna().any() else min_day + 30
        sel_days = st.slider("Days to expiry (absolute)", min_value=min_day, max_value=max_day, value=(min_day, min(min_day+7, max_day)))

    # apply filters
    w = food.copy()
    if city and city != "All":
        w = w[(w.get("Location", "").astype(str).str.lower() == city.lower()) | (w.get("Provider_City", "").astype(str).str.lower() == city.lower())]
    if sel_food_types:
        w = w[w.get("Food_Type", "").isin(sel_food_types)]
    if sel_meals:
        w = w[w.get("Meal_Type", "").isin(sel_meals)]
    if "Days_To_Expiry" in w.columns:
        w = w[(w["Days_To_Expiry"].notna()) & (w["Days_To_Expiry"] >= sel_days[0]) & (w["Days_To_Expiry"] <= sel_days[1])]

    # KPIs
    st.subheader("Key metrics")
    col1, col2, col3, col4 = st.columns(4)
    total_providers = int(run_sql("SELECT COUNT(*) AS c FROM Providers")["c"].iloc[0]) if table_exists("Providers") else 0
    total_receivers = int(run_sql("SELECT COUNT(*) AS c FROM Receivers")["c"].iloc[0]) if table_exists("Receivers") else 0
    total_qty = int(w["Quantity"].sum()) if "Quantity" in w.columns and not w.empty else 0
    total_claims = int(run_sql("SELECT COUNT(*) AS c FROM Claims")["c"].iloc[0]) if table_exists("Claims") else 0
    col1.metric("Providers", total_providers)
    col2.metric("Receivers", total_receivers)
    col3.metric("Total Food Quantity (filtered)", total_qty)
    col4.metric("Total Claims", total_claims)

    st.markdown("---")

    # 1) Food Type distribution (pie) - safe
    st.subheader("1) Food Type distribution (by quantity)")
    if "Food_Type" in w.columns and not w.empty:
        ft = w.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        if not ft.empty:
            chart = alt.Chart(ft).mark_arc().encode(theta="Quantity:Q", color="Food_Type:N", tooltip=["Food_Type","Quantity"])
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No aggregated food-type data available.")
    else:
        st.info("No Food_Type data available for current filters.")

    # 2) Top providers by donated quantity (bar)
    st.subheader("2) Top providers by donated quantity")
    if "Provider_ID" in w.columns and not providers.empty:
        p = w.merge(providers[["Provider_ID","Name"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name"})
        p["Quantity"] = pd.to_numeric(p.get("Quantity", 0), errors="coerce").fillna(0)
        topp = p.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(12)
        if not topp.empty:
            chart = alt.Chart(topp).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Name:N", sort='-x'), tooltip=["Provider_Name","Quantity"])
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No provider donation data for filters.")
    else:
        st.info("Provider info or Provider_ID missing.")

    # 3) Monthly trend (by expiry month if present)
    st.subheader("3) Monthly quantity trend (Expiry month proxy)")
    if "Expiry_Date" in food.columns:
        ftmp = food.copy()
        ftmp["Expiry_Date"] = safe_dt(ftmp["Expiry_Date"])
        ftmp["YearMonth"] = ftmp["Expiry_Date"].dt.to_period("M").astype(str).fillna("Unknown")
        monthly = ftmp.groupby("YearMonth", as_index=False)["Quantity"].sum().sort_values("YearMonth")
        if not monthly.empty:
            chart = alt.Chart(monthly).mark_line(point=True).encode(x="YearMonth:N", y="Quantity:Q", tooltip=["YearMonth","Quantity"])
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Not enough date/quantity data to show monthly trend.")
    else:
        st.info("Expiry_Date column missing; monthly trend not available.")

    # 4) Claims status distribution (bar + pie)
    st.subheader("4) Claims status distribution")
    if not claims.empty and "Status" in claims.columns:
        status_counts = claims["Status"].value_counts(dropna=False).rename_axis("Status").reset_index(name="Count")
        if not status_counts.empty:
            c1, c2 = st.columns([1,1])
            with c1:
                st.altair_chart(alt.Chart(status_counts).mark_bar().encode(x="Count:Q", y=alt.Y("Status:N", sort="-x"), tooltip=["Status","Count"]), use_container_width=True)
            with c2:
                st.altair_chart(alt.Chart(status_counts).mark_arc().encode(theta="Count:Q", color="Status:N", tooltip=["Status","Count"]), use_container_width=True)
        else:
            st.info("No status data.")
    else:
        st.info("Claims table or Status column missing.")

    # 5) Wastage: expired quantities (by expiry date)
    st.subheader("5) Expired quantity over time")
    if "Expiry_Date" in food.columns:
        fexp = food.copy()
        fexp["Expiry_Date"] = safe_dt(fexp["Expiry_Date"])
        expired = fexp[fexp["Expiry_Date"] < pd.to_datetime(date.today())]
        if not expired.empty:
            exp_month = expired.groupby(expired["Expiry_Date"].dt.to_period("M").astype(str), as_index=False)["Quantity"].sum().rename(columns={"Expiry_Date":"Period"})
            st.altair_chart(alt.Chart(exp_month).mark_line(point=True).encode(x="Period:N", y="Quantity:Q", tooltip=["Period","Quantity"]), use_container_width=True)
        else:
            st.info("No expired records to show.")
    else:
        st.info("Expiry_Date column missing; cannot compute expired quantities.")

    # 6) Correlation heatmap (numeric columns in Food_Listings)
    st.subheader("6) Correlation heatmap (numeric fields in Food_Listings)")
    numeric_cols = [c for c in food.columns if pd.api.types.is_numeric_dtype(food[c])]
    if numeric_cols and len(numeric_cols) > 1:
        corr = food[numeric_cols].corr()
        corr_long = corr.reset_index().melt(id_vars="index")
        corr_long.columns = ["var1","var2","corr"]
        heat = alt.Chart(corr_long).mark_rect().encode(
            x="var1:N", y="var2:N",
            color=alt.Color("corr:Q", scale=alt.Scale(scheme="redyellowgreen")),
            tooltip=["var1","var2","corr"]
        ).properties(height=350)
        st.altair_chart(heat, use_container_width=True)
    else:
        st.info("Not enough numeric columns to compute correlation.")

    st.markdown("---")
    st.subheader("Listings sample (filtered)")
    sample_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Food_Type","Meal_Type","Days_To_Expiry"] if c in w.columns]
    if not w.empty and sample_cols:
        st.dataframe(w[sample_cols].sort_values("Days_To_Expiry", na_position="last"), use_container_width=True)
    else:
        st.info("No listings to show under current filters.")

# -------------------------
# Donations Analysis (additional dedicated EDA)
# -------------------------
elif page == "Donations Analysis":
    st.header("Donations Analysis (EDA)")
    if food.empty:
        st.warning("Food_Listings missing.")
        st.stop()

    f = food.copy()
    f["Expiry_Date"] = safe_dt(f.get("Expiry_Date", pd.Series()))
    f["YearMonth"] = f["Expiry_Date"].dt.to_period("M").astype(str).fillna("Unknown")

    st.subheader("Monthly Total Quantity")
    monthly = f.groupby("YearMonth", as_index=False)["Quantity"].sum().sort_values("YearMonth")
    if not monthly.empty:
        st.altair_chart(alt.Chart(monthly).mark_line(point=True).encode(x="YearMonth:N", y="Quantity:Q", tooltip=["YearMonth","Quantity"]), use_container_width=True)
    else:
        st.info("Not enough data for monthly view.")

    st.subheader("Food Type - Quantity (bar)")
    if "Food_Type" in f.columns:
        ft = f.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        if not ft.empty:
            st.altair_chart(alt.Chart(ft).mark_bar().encode(x="Quantity:Q", y=alt.Y("Food_Type:N", sort="-x"), tooltip=["Food_Type","Quantity"]), use_container_width=True)
        else:
            st.info("No food type aggregates.")
    else:
        st.info("Food_Type column missing.")

    st.subheader("Meal Type share")
    if "Meal_Type" in f.columns:
        mt = f["Meal_Type"].value_counts().reset_index().rename(columns={"index":"Meal_Type","Meal_Type":"Count"})
        st.altair_chart(alt.Chart(mt).mark_arc().encode(theta="Count:Q", color="Meal_Type:N", tooltip=["Meal_Type","Count"]), use_container_width=True)
    else:
        st.info("Meal_Type column missing.")

# -------------------------
# Providers Insights
# -------------------------
elif page == "Providers Insights":
    st.header("Providers Insights")
    if providers.empty or food.empty:
        st.warning("Providers or Food_Listings missing.")
        st.stop()

    pf = food.merge(providers[["Provider_ID","Name","Type"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Type":"Provider_Type"})
    # ensure Provider_Type is a plain column
    if "Provider_Type" not in pf.columns:
        pf["Provider_Type"] = pf.get("Type", "Unknown").astype(str)
    pf["Quantity"] = pd.to_numeric(pf.get("Quantity", 0), errors="coerce").fillna(0)

    st.subheader("Top Providers (by quantity)")
    top_prov = pf.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    if not top_prov.empty:
        st.altair_chart(alt.Chart(top_prov).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Name:N", sort='-x'), tooltip=["Provider_Name","Quantity"]), use_container_width=True)
    else:
        st.info("No provider donation aggregates.")

    st.subheader("Provider Type contribution")
    if "Provider_Type" in pf.columns:
        pt = pf.groupby("Provider_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        if not pt.empty:
            st.altair_chart(alt.Chart(pt).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Type:N", sort='-x'), tooltip=["Provider_Type","Quantity"]), use_container_width=True)
        else:
            st.info("No provider-type aggregates.")
    else:
        st.info("Provider_Type column missing.")

    st.subheader("Provider contacts")
    md = []
    for _, r in providers.fillna("").iterrows():
        md.append(contact_md(r.get("Name","(no name)"), r.get("Contact","")))
    st.markdown("\n".join(md))

# -------------------------
# Receivers Insights
# -------------------------
elif page == "Receivers Insights":
    st.header("Receivers Insights")
    if receivers.empty or claims.empty:
        st.warning("Receivers or Claims missing.")
        st.stop()

    cf = claims.merge(receivers[["Receiver_ID","Name","City","Contact"]], on="Receiver_ID", how="left").rename(columns={"Name":"Receiver_Name"})
    if "Food_ID" in cf.columns and "Food_ID" in food.columns:
        cf = cf.merge(food[["Food_ID","Quantity","Food_Type","Meal_Type"]], on="Food_ID", how="left")
    cf["Quantity"] = pd.to_numeric(cf.get("Quantity", 0), errors="coerce").fillna(0)

    st.subheader("Top Receivers by claimed quantity")
    top_recv = cf.groupby("Receiver_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    if not top_recv.empty:
        st.altair_chart(alt.Chart(top_recv).mark_bar().encode(x="Quantity:Q", y=alt.Y("Receiver_Name:N", sort='-x'), tooltip=["Receiver_Name","Quantity"]), use_container_width=True)
    else:
        st.info("No receiver aggregates.")

    st.subheader("Receiver contacts")
    md = []
    for _, r in receivers.fillna("").iterrows():
        md.append(contact_md(r.get("Name","(no name)"), r.get("Contact","")))
    st.markdown("\n".join(md))

# -------------------------
# Wastage & Expiry
# -------------------------
elif page == "Wastage & Expiry":
    st.header("Wastage & Expiry Analysis")
    if food.empty:
        st.warning("Food_Listings missing.")
        st.stop()

    f = compute_days_to_expiry(food)
    if "Days_To_Expiry" in f.columns:
        agg = f.groupby("Days_To_Expiry", as_index=False)["Quantity"].sum().sort_values("Days_To_Expiry")
        if not agg.empty:
            st.altair_chart(alt.Chart(agg).mark_bar().encode(x="Days_To_Expiry:Q", y="Quantity:Q", tooltip=["Days_To_Expiry","Quantity"]), use_container_width=True)
        else:
            st.info("No days-to-expiry aggregates.")
    else:
        st.info("Expiry_Date missing; cannot compute days-to-expiry.")

    st.subheader("Expired listings (detailed)")
    expired = f[pd.to_datetime(f.get("Expiry_Date", pd.Series()), errors="coerce") < pd.to_datetime(date.today())]
    if not expired.empty:
        cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Food_Type","Meal_Type","Days_To_Expiry"] if c in expired.columns]
        st.dataframe(expired[cols].sort_values("Expiry_Date"), use_container_width=True)
    else:
        st.info("No expired listings found.")

# -------------------------
# Filter Food Donations
# -------------------------
elif page == "Filter Food Donations":
    st.header("Filter Food Donations (search & contact)")

    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers missing.")
        st.stop()

    merged = food.merge(providers[["Provider_ID","Name","Contact"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Contact":"Provider_Contact"})
    cities = ["All"] + sorted(merged.get("Location", pd.Series()).dropna().unique().tolist())
    provs = ["All"] + sorted(merged.get("Provider_Name", pd.Series()).dropna().unique().tolist())
    ftypes = ["All"] + sorted(merged.get("Food_Type", pd.Series()).dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    sel_city = c1.selectbox("City", cities)
    sel_provider = c2.selectbox("Provider", provs)
    sel_foodtype = c3.selectbox("Food Type", ftypes)

    res = merged.copy()
    if sel_city != "All":
        res = res[res["Location"] == sel_city]
    if sel_provider != "All":
        res = res[res["Provider_Name"] == sel_provider]
    if sel_foodtype != "All":
        res = res[res["Food_Type"] == sel_foodtype]

    if res.empty:
        st.info("No matching listings.")
    else:
        display_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Provider_Name","Food_Type","Meal_Type"] if c in res.columns]
        st.dataframe(res[display_cols].sort_values("Expiry_Date", na_position="last"), use_container_width=True)
        st.markdown("**Contacts for matched providers**")
        for _, r in res[["Provider_Name","Provider_Contact"]].drop_duplicates().iterrows():
            st.markdown(contact_md(r.get("Provider_Name","(no name)"), r.get("Provider_Contact","")))

# -------------------------
# Queries (15 predefined)
# -------------------------
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

    qkey = st.selectbox("Select Query", list(QUERIES.keys()))
    st.code(QUERIES[qkey], language="sql")
    params = None
    if qkey == "Q3: Contact info of providers in a city (param)":
        city_val = st.text_input("City name (case-insensitive)").strip()
        if city_val:
            params = (city_val,)
        else:
            st.info("Enter a city to run this query.")
    if qkey.startswith("Q3") and params is None:
        pass
    else:
        out = run_sql(QUERIES[qkey], params)
        if out.empty:
            st.info("No results for this query.")
        else:
            st.dataframe(out, use_container_width=True)
            st.download_button("Download CSV", out.to_csv(index=False).encode("utf-8"), file_name=f"{qkey.replace(' ','_')}.csv")

# -------------------------
# CRUD page
# -------------------------
elif page == "CRUD":
    st.header("CRUD operations")
    table = st.selectbox("Select table to manage", ["Providers","Receivers","Food_Listings","Claims"])
    if not table_exists(table):
        st.warning(f"Table {table} not found.")
        st.stop()
    df = run_sql(f"SELECT * FROM {table}")
    st.subheader("Existing records (sample)")
    st.dataframe(df.head(200), use_container_width=True)

    st.markdown("### Add record")
    # use columns if present else fallback
    cols = df.columns.tolist() if not df.empty else {
        "Providers":["Name","Type","Address","City","Contact"],
        "Receivers":["Name","Type","City","Contact"],
        "Food_Listings":["Food_Name","Quantity","Expiry_Date","Provider_ID","Provider_Type","Location","Food_Type","Meal_Type"],
        "Claims":["Food_ID","Receiver_ID","Status","Timestamp"]
    }.get(table, [])
    add_vals = {}
    for c in cols:
        if c.lower().endswith("id") and c.lower() in {"provider_id","receiver_id","food_id","claim_id"}:
            st.caption(f"{c} (primary key / optional)")
            continue
        if c.lower().endswith("date") or c.lower() == "timestamp":
            d = st.date_input(f"{c} (date)", value=date.today(), key=f"add_{c}")
            add_vals[c] = str(d)
        elif c.lower() == "quantity":
            add_vals[c] = st.number_input(c, min_value=0, value=1, key=f"add_{c}")
        else:
            add_vals[c] = st.text_input(c, key=f"add_{c}")

    if st.button("Add record"):
        if add_vals:
            cols_ins = ", ".join(add_vals.keys())
            placeholders = ", ".join(["?"]*len(add_vals))
            ok = exec_sql(f"INSERT INTO {table} ({cols_ins}) VALUES ({placeholders})", tuple(add_vals.values()))
            if ok:
                st.success("Record added.")
                st.experimental_rerun()

    st.markdown("---")
    if not df.empty:
        st.subheader("Update record")
        pk = df.columns[0]
        sel = st.selectbox(f"Select {pk}", df[pk].tolist(), key="upd_select")
        row = df[df[pk] == sel].iloc[0].to_dict()
        upd_vals = {}
        for c in df.columns:
            if c == pk:
                st.caption(f"{pk}: {sel}")
                continue
            upd_vals[c] = st.text_input(c, value=str(row[c]), key=f"upd_{c}")
        if st.button("Update selected record"):
            set_clause = ", ".join([f"{k}=?" for k in upd_vals.keys()])
            params = tuple(upd_vals.values()) + (sel,)
            ok = exec_sql(f"UPDATE {table} SET {set_clause} WHERE {pk} = ?", params)
            if ok:
                st.success("Updated.")
                st.experimental_rerun()

    st.markdown("---")
    if not df.empty:
        st.subheader("Delete record")
        pk = df.columns[0]
        del_id = st.selectbox("Select id to delete", df[pk].tolist(), key="del_select")
        if st.button("Delete selected"):
            ok = exec_sql(f"DELETE FROM {table} WHERE {pk} = ?", (del_id,))
            if ok:
                st.success("Deleted.")
                st.experimental_rerun()

# -------------------------
# Data page
# -------------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        st.subheader(t)
        if table_exists(t):
            df = run_sql(f"SELECT * FROM {t}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"Download {t}.csv", df.to_csv(index=False).encode("utf-8"), file_name=f"{t}.csv")
        else:
            st.info(f"Table {t} not found in DB.")

# -------------------------
# About
# -------------------------
elif page == "About":
    st.header("About")
    st.markdown("""
**Local Food Wastage Management System**

This app:
- Connects surplus food providers with receivers
- Provides filtering, contact details, CRUD and 15 SQL queries
- Powerful dashboard (6+ EDA visuals) focusing on trends, providers, claims, expiry/wastage and correlations

Data sources (repo root expected):
- food_wastage.db (preferred)
- providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv (CSV fallback)
""")
