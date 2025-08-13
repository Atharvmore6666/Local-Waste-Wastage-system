# app.py
# Local Food Wastage Management System – Power BI style
# Uses food_wastage.db + providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv

import os
import sqlite3
from datetime import datetime, date

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

# -----------------------
# CONFIG + THEME
# -----------------------
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

THEME_CSS = """
<style>
:root {
  --beige: #E8E2D0;
  --dark-green: #2E5339;
  --accent-green: #4F8F4F;
  --ink: #1A1A1A;
}
.stApp{ background:var(--beige); color:var(--dark-green); font-family:'Segoe UI',system-ui,sans-serif; }
h1,h2,h3,h4,h5{ color:var(--dark-green) !important; font-weight:700; }
section[data-testid="stSidebar"]{ background:var(--dark-green); color:#dbe7db; }
section[data-testid="stSidebar"] *{ color:#dbe7db !important; }
.block-container{ padding-top:0.8rem; }
.card{ background:#fff; border-radius:12px; padding:1rem; box-shadow:0 4px 12px rgba(0,0,0,.08); }
.kpi{ font-size:14px; text-transform:uppercase; letter-spacing:.04em; opacity:.9; }
.kpi-value{ font-size:28px; font-weight:800; color:var(--dark-green); }
.stButton>button{ background:var(--accent-green); color:#fff; border:none; border-radius:10px; padding:.5rem 1rem; font-weight:700; }
.stButton>button:hover{ background:var(--dark-green); }
.dataframe th{ background:var(--accent-green) !important; color:#fff !important; }
.dataframe td{ color:var(--dark-green) !important; }
.link { text-decoration:none; font-weight:700; color:var(--accent-green); }
.small{ font-size:12px; opacity:.85; }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# -----------------------
# CONSTANTS / PATHS
# -----------------------
DB_PATH = "food_wastage.db"
CSV_FILES = {
    "Providers": "providers_data.csv",
    "Receivers": "receivers_data.csv",
    "Food_Listings": "food_listings_data.csv",
    "Claims": "claims_data.csv",
}

# -----------------------
# DB HELPERS
# -----------------------
@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

def table_exists(name: str) -> bool:
    try:
        df = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
            conn, params=(name,)
        )
        return not df.empty
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
        cur.execute(sql, params or tuple())
        conn.commit()
        return True
    except Exception as e:
        st.error(f"DB command error: {e}")
        return False

# -----------------------
# LOAD HEADER IMAGES
# -----------------------
LOGO_LEFT = "logo.png"
LOGO_RIGHT = "recycle.png"
left_img = Image.open(LOGO_LEFT) if os.path.exists(LOGO_LEFT) else None
right_img = Image.open(LOGO_RIGHT) if os.path.exists(LOGO_RIGHT) else None

c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img: st.image(left_img, width=84)
with c2:
    st.markdown("<h1 style='text-align:center;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img: st.image(right_img, width=64)
st.markdown("---")

# -----------------------
# SIDEBAR NAV
# -----------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go to",
    [
        "Dashboard",
        "Donations Analysis",
        "Providers Insights",
        "Receivers Insights",
        "Wastage & Expiry",
        "Filter Food",
        "Queries",
        "CRUD",
        "Data",
        "About",
    ],
)

# -----------------------
# SHARED DATAFRAMES (lazy)
# -----------------------
@st.cache_data(show_spinner=False)
def load_base_tables():
    dfs = {}
    for t in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        dfs[t] = run_sql(f"SELECT * FROM {t}") if table_exists(t) else pd.DataFrame()
    return dfs

dfs = load_base_tables()
providers = dfs["Providers"]
receivers = dfs["Receivers"]
food = dfs["Food_Listings"]
claims = dfs["Claims"]

# Helpers
def int_safe(x):
    try: return int(x)
    except: return 0

def compute_days_to_expiry(df: pd.DataFrame) -> pd.DataFrame:
    if "Expiry_Date" not in df.columns: return df
    out = df.copy()
    out["Expiry_Date"] = pd.to_datetime(out["Expiry_Date"], errors="coerce")
    today = pd.to_datetime(date.today())
    # absolute difference (no negative sign)
    out["Days_To_Expiry"] = (out["Expiry_Date"].dt.normalize() - today).dt.days.abs()
    return out

def mailto_link(label, email_or_phone):
    if pd.isna(email_or_phone) or str(email_or_phone).strip()=="":
        return "-"
    val = str(email_or_phone).strip()
    if any(ch.isalpha() for ch in val) and "@" in val:
        return f"<a class='link' href='mailto:{val}'>{label}</a>"
    # assume it's a phone otherwise
    return f"<a class='link' href='tel:{val}'>{label}</a>"

# =========================================================
# PAGE: DASHBOARD  (Power BI–style + global interactive filters)
# =========================================================
if page == "Dashboard":
    st.header("Dashboard")

    if any(df.empty for df in [providers, receivers, food]):
        st.warning("Missing tables in database. Ensure Providers, Receivers and Food_Listings exist.")
        st.stop()

    # Global interactive filters
    with st.expander("🔎 Filters", expanded=True):
        colf1, colf2, colf3, colf4 = st.columns(4)
        cities = sorted(list(set(providers.get("City", pd.Series()).dropna().unique()) |
                             set(receivers.get("City", pd.Series()).dropna().unique()) |
                             set(food.get("Location", pd.Series()).dropna().unique())))
        city = colf1.selectbox("City", ["All"] + cities)
        meal_types = sorted(food.get("Meal_Type", pd.Series()).dropna().unique().tolist())
        meal = colf2.multiselect("Meal Type", meal_types, default=meal_types)
        food_types = sorted(food.get("Food_Type", pd.Series()).dropna().unique().tolist())
        ftypes = colf3.multiselect("Food Type", food_types, default=food_types)
        max_days = int(food.shape[0] and 30 or 0)
        days_window = colf4.slider("Days to Expiry (absolute)", value=(0, 7), min_value=0, max_value=60)

    # Prep working DF with absolute days to expiry
    wf = compute_days_to_expiry(food)
    if city != "All":
        wf = wf[(wf["Location"] == city) | (wf["Location"] == city.title())]
    if meal:
        wf = wf[wf["Meal_Type"].isin(meal)]
    if ftypes:
        wf = wf[wf["Food_Type"].isin(ftypes)]
    wf = wf[(wf["Days_To_Expiry"] >= days_window[0]) & (wf["Days_To_Expiry"] <= days_window[1])]

    # KPIs
    cK1, cK2, cK3, cK4 = st.columns(4)
    k_providers = int(run_sql("SELECT COUNT(*) c FROM Providers")["c"].iloc[0]) if not providers.empty else 0
    k_receivers = int(run_sql("SELECT COUNT(*) c FROM Receivers")["c"].iloc[0]) if not receivers.empty else 0
    k_food_qty = int_safe(wf["Quantity"].sum()) if "Quantity" in wf.columns else 0
    k_claims = int(run_sql("SELECT COUNT(*) c FROM Claims")["c"].iloc[0]) if not claims.empty else 0

    with cK1: st.markdown("<div class='card kpi'>Providers<div class='kpi-value'>%d</div></div>" % k_providers, unsafe_allow_html=True)
    with cK2: st.markdown("<div class='card kpi'>Receivers<div class='kpi-value'>%d</div></div>" % k_receivers, unsafe_allow_html=True)
    with cK3: st.markdown("<div class='card kpi'>Total Food Quantity<div class='kpi-value'>%d</div></div>" % k_food_qty, unsafe_allow_html=True)
    with cK4: st.markdown("<div class='card kpi'>Total Claims<div class='kpi-value'>%d</div></div>" % k_claims, unsafe_allow_html=True)

    st.markdown("")

    # Chart type selector (Bar or Pie) for Claims status
    chart_type = st.selectbox("Chart type for status breakdown", ["Bar", "Pie"], index=0)

    grid1 = st.columns((2, 1))
    # Top Providers by donated quantity
    top_prov_sql = """
        SELECT p.Name, SUM(f.Quantity) AS Total_Donated
        FROM Food_Listings f
        JOIN Providers p ON f.Provider_ID = p.Provider_ID
        GROUP BY p.Name
        ORDER BY Total_Donated DESC
        LIMIT 15;
    """
    top_prov = run_sql(top_prov_sql)
    with grid1[0]:
        st.subheader("Top Providers by Donated Quantity")
        if not top_prov.empty:
            ch = (
                alt.Chart(top_prov)
                .mark_bar()
                .encode(
                    x=alt.X("Total_Donated:Q", title="Quantity Donated"),
                    y=alt.Y("Name:N", sort="-x", title="Provider"),
                    tooltip=["Name", "Total_Donated"],
                )
                .properties(height=380)
            )
            st.altair_chart(ch, use_container_width=True)
        else:
            st.info("No donation data available.")

    # Claims status distribution (bar/pie)
    with grid1[1]:
        st.subheader("Claims Status")
        status_df = run_sql("SELECT Status, COUNT(*) AS Count FROM Claims GROUP BY Status")
        if not status_df.empty:
            if chart_type == "Pie":
                ch2 = (
                    alt.Chart(status_df)
                    .mark_arc()
                    .encode(theta="Count:Q", color="Status:N", tooltip=["Status", "Count"])
                    .properties(height=280, width=280)
                )
            else:
                ch2 = (
                    alt.Chart(status_df)
                    .mark_bar()
                    .encode(x=alt.X("Status:N", title="Status"), y=alt.Y("Count:Q"), tooltip=["Status", "Count"])
                    .properties(height=280)
                )
            st.altair_chart(ch2, use_container_width=True)
        else:
            st.info("No claims data.")

    # Listings expiring soon (uses absolute Days_To_Expiry)
    st.subheader("Listings matching your filters")
    show_cols = ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Location", "Provider_ID", "Food_Type", "Meal_Type", "Days_To_Expiry"]
    for c in show_cols:
        if c not in wf.columns: wf[c] = None
    st.dataframe(wf[show_cols].sort_values("Days_To_Expiry", ascending=True))

# =========================================================
# PAGE: DONATIONS ANALYSIS (EDA #1‒#3)
# =========================================================
elif page == "Donations Analysis":
    st.header("Donations Analysis")

    if food.empty:
        st.warning("Food_Listings table is empty.")
        st.stop()

    f = food.copy()
    f["Expiry_Date"] = pd.to_datetime(f["Expiry_Date"], errors="coerce")
    f["YearMonth"] = f["Expiry_Date"].dt.to_period("M").astype(str)

    # EDA #1: Trend – Total quantity listed by month
    st.subheader("📅 Monthly Quantity Listed")
    m = f.groupby("YearMonth", as_index=False)["Quantity"].sum()
    line = alt.Chart(m).mark_line(point=True).encode(
        x=alt.X("YearMonth:N", title="Month"),
        y=alt.Y("Quantity:Q", title="Total Quantity"),
        tooltip=["YearMonth", "Quantity"],
    )
    st.altair_chart(line, use_container_width=True)

    # EDA #2: Distribution – Food type vs quantity
    st.subheader("🍽️ Food Type Distribution (Quantity)")
    ft = f.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
    bar = alt.Chart(ft).mark_bar().encode(
        x=alt.X("Quantity:Q"),
        y=alt.Y("Food_Type:N", sort="-x"),
        tooltip=["Food_Type", "Quantity"],
    ).properties(height=360)
    st.altair_chart(bar, use_container_width=True)

    # EDA #3: Meal type share (Pie)
    st.subheader("🥣 Meal Type Share")
    mt = f.groupby("Meal_Type", as_index=False)["Quantity"].sum()
    pie = alt.Chart(mt).mark_arc().encode(
        theta="Quantity:Q",
        color="Meal_Type:N",
        tooltip=["Meal_Type", "Quantity"],
    ).properties(height=320, width=320)
    st.altair_chart(pie, use_container_width=False)

# =========================================================
# PAGE: PROVIDERS INSIGHTS (EDA #4)
# =========================================================
elif page == "Providers Insights":
    st.header("Providers Insights")

    if providers.empty or food.empty:
        st.warning("Providers or Food_Listings table is empty.")
        st.stop()

    pf = (
        food.merge(providers[["Provider_ID", "Name", "City", "Type"]], on="Provider_ID", how="left")
        .rename(columns={"Name": "Provider_Name", "Type": "Provider_Type"})
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏭 Top Providers (Quantity)")
        topP = pf.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
        ch = alt.Chart(topP).mark_bar().encode(
            x="Quantity:Q", y=alt.Y("Provider_Name:N", sort="-x"),
            tooltip=["Provider_Name", "Quantity"]
        ).properties(height=500)
        st.altair_chart(ch, use_container_width=True)

    with c2:
        st.subheader("🏷️ Provider Type Contribution")
        pt = pf.groupby("Provider_Type", as_index=False)["Quantity"].sum()
        ch2 = alt.Chart(pt).mark_bar().encode(
            x="Quantity:Q", y=alt.Y("Provider_Type:N", sort="-x"),
            tooltip=["Provider_Type", "Quantity"]
        ).properties(height=500)
        st.altair_chart(ch2, use_container_width=True)

    st.subheader("📍 Providers by City (Count vs Quantity)")
    by_city = pf.groupby("City", as_index=False).agg(Providers=("Provider_ID", "nunique"), Total_Quantity=("Quantity", "sum"))
    ch3 = alt.Chart(by_city).mark_circle(size=200).encode(
        x=alt.X("Providers:Q", title="Unique Providers"),
        y=alt.Y("Total_Quantity:Q", title="Total Quantity"),
        tooltip=["City", "Providers", "Total_Quantity"],
    )
    st.altair_chart(ch3, use_container_width=True)

    st.markdown("**Contact Providers (click to call / email):**")
    cp = providers.fillna("")
    cp["ContactLink"] = cp["Contact"].apply(lambda v: mailto_link("Contact", v))
    st.write(cp[["Provider_ID", "Name", "Type", "City"]].assign(Contact=cp["ContactLink"]).to_html(escape=False, index=False), unsafe_allow_html=True)

# =========================================================
# PAGE: RECEIVERS INSIGHTS (EDA #5)
# =========================================================
elif page == "Receivers Insights":
    st.header("Receivers Insights")

    if receivers.empty or claims.empty or food.empty:
        st.warning("Receivers, Claims or Food_Listings table is empty.")
        st.stop()

    cf = (
        claims.merge(receivers[["Receiver_ID", "Name", "Type", "City", "Contact"]], on="Receiver_ID", how="left")
        .merge(food[["Food_ID", "Quantity", "Meal_Type", "Food_Type", "Location"]], on="Food_ID", how="left")
        .rename(columns={"Name": "Receiver_Name"})
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📦 Top Receivers by Claimed Quantity")
        r1 = cf.groupby("Receiver_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
        ch = alt.Chart(r1).mark_bar().encode(
            x="Quantity:Q", y=alt.Y("Receiver_Name:N", sort="-x"),
            tooltip=["Receiver_Name", "Quantity"],
        ).properties(height=500)
        st.altair_chart(ch, use_container_width=True)

    with c2:
        st.subheader("🗺️ Receiver Cities – Claims Count")
        r2 = cf.groupby("City", as_index=False)["Receiver_ID"].count().rename(columns={"Receiver_ID": "Claims"})
        ch2 = alt.Chart(r2).mark_bar().encode(
            x="Claims:Q", y=alt.Y("City:N", sort="-x"),
            tooltip=["City", "Claims"],
        ).properties(height=500)
        st.altair_chart(ch2, use_container_width=True)

    st.subheader("☎️ Contact Receivers")
    rr = receivers.fillna("")
    rr["ContactLink"] = rr["Contact"].apply(lambda v: mailto_link("Contact", v))
    st.write(rr[["Receiver_ID", "Name", "Type", "City"]].assign(Contact=rr["ContactLink"]).to_html(escape=False, index=False), unsafe_allow_html=True)

# =========================================================
# PAGE: WASTAGE & EXPIRY (EDA #6 + filters)
# =========================================================
elif page == "Wastage & Expiry":
    st.header("Wastage & Expiry Risk")

    if food.empty:
        st.warning("Food_Listings table is empty.")
        st.stop()

    f = compute_days_to_expiry(food)
    colf1, colf2 = st.columns(2)
    ftypes_all = sorted(f["Food_Type"].dropna().unique().tolist())
    meals_all = sorted(f["Meal_Type"].dropna().unique().tolist())
    choose_ft = colf1.multiselect("Food Type", options=ftypes_all, default=ftypes_all)
    choose_meal = colf2.multiselect("Meal Type", options=meals_all, default=meals_all)
    days_rng = st.slider("Days to Expiry (absolute)", 0, 60, (0, 10))

    ff = f[(f["Food_Type"].isin(choose_ft)) & (f["Meal_Type"].isin(choose_meal))]
    ff = ff[(ff["Days_To_Expiry"] >= days_rng[0]) & (ff["Days_To_Expiry"] <= days_rng[1])]

    st.subheader("⏳ Quantity by Days-to-Expiry (Absolute)")
    dte = ff.groupby("Days_To_Expiry", as_index=False)["Quantity"].sum().sort_values("Days_To_Expiry")
    ch = alt.Chart(dte).mark_bar().encode(
        x=alt.X("Days_To_Expiry:Q", title="Days To Expiry (abs)"),
        y=alt.Y("Quantity:Q"),
        tooltip=["Days_To_Expiry", "Quantity"],
    )
    st.altair_chart(ch, use_container_width=True)

    st.subheader("⚠️ Expired Listings")
    expired = f[pd.to_datetime(f["Expiry_Date"], errors="coerce") < pd.to_datetime(date.today())]
    show = ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Location", "Food_Type", "Meal_Type", "Days_To_Expiry"]
    st.dataframe(expired[show].sort_values("Expiry_Date"))

# =========================================================
# PAGE: FILTER FOOD (search + contact)
# =========================================================
elif page == "Filter Food":
    st.header("Filter Food Donations")

    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers table is empty.")
        st.stop()

    ff = food.merge(providers[["Provider_ID", "Name", "Contact"]], on="Provider_ID", how="left").rename(
        columns={"Name": "Provider_Name", "Contact": "Provider_Contact"}
    )
    cities = ["All"] + sorted(ff["Location"].dropna().unique().tolist())
    providers_list = ["All"] + sorted(ff["Provider_Name"].dropna().unique().tolist())
    ftypes = ["All"] + sorted(ff["Food_Type"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    city = c1.selectbox("City", cities)
    prov = c2.selectbox("Provider", providers_list)
    ftype = c3.selectbox("Food Type", ftypes)

    res = ff.copy()
    if city != "All": res = res[res["Location"] == city]
    if prov != "All": res = res[res["Provider_Name"] == prov]
    if ftype != "All": res = res[res["Food_Type"] == ftype]

    if res.empty:
        st.info("No matching listings.")
    else:
        res["ContactLink"] = res["Provider_Contact"].apply(lambda v: mailto_link("Contact", v))
        cols = ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Location", "Provider_Name", "Food_Type", "Meal_Type"]
        st.dataframe(res[cols].assign(Contact=res["ContactLink"]).sort_values("Expiry_Date").to_html(escape=False, index=False), unsafe_allow_html=True)

# =========================================================
# PAGE: QUERIES (15 predefined)
# =========================================================
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
        "Q5: Total quantity of food available": """
            SELECT IFNULL(SUM(Quantity),0) AS Total_Quantity FROM Food_Listings;
        """,
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

    qname = st.selectbox("Choose query", list(QUERIES.keys()))
    st.code(QUERIES[qname], language="sql")

    params = None
    if qname.startswith("Q3"):
        city = st.text_input("Enter city (case-insensitive)").strip()
        if city:
            params = (city,)
        else:
            st.info("Enter a city to run Q3.")

    if (qname.startswith("Q3") and params) or not qname.startswith("Q3"):
        out = run_sql(QUERIES[qname], params)
        if out.empty:
            st.warning("No results.")
        else:
            st.dataframe(out)
            st.download_button("Download CSV", out.to_csv(index=False).encode("utf-8"), file_name=f"{qname.replace(' ','_')}.csv")

# =========================================================
# PAGE: CRUD
# =========================================================
elif page == "CRUD":
    st.header("CRUD Operations")
    st.markdown("Add / Update / Delete items. Changes write directly to SQLite DB.")

    table = st.selectbox("Select table", ["Providers", "Receivers", "Food_Listings", "Claims"])

    # READ
    df = run_sql(f"SELECT * FROM {table}") if table_exists(table) else pd.DataFrame()
    st.subheader(f"Existing records – {table}")
    st.dataframe(df)

    st.markdown("---")
    # CREATE
    st.subheader(f"➕ Add new record to {table}")
    if not df.empty:
        cols = df.columns.tolist()
    else:
        # fallbacks
        fallback = {
            "Providers": ["Name","Type","Address","City","Contact"],
            "Receivers": ["Name","Type","City","Contact"],
            "Food_Listings": ["Food_Name","Quantity","Expiry_Date","Provider_ID","Provider_Type","Location","Food_Type","Meal_Type"],
            "Claims": ["Food_ID","Receiver_ID","Status","Timestamp"],
        }
        cols = fallback.get(table, [])

    new_vals = {}
    for c in cols:
        # skip obvious PKs if present
        if c.lower() in {"provider_id","receiver_id","food_id","claim_id"} and c in df.columns and df[c].dtype.kind in "iu":
            continue
        if c.lower().endswith("date") or c.lower()=="timestamp":
            dt = st.date_input(c, value=date.today(), key=f"add_{c}")
            new_vals[c] = str(dt)
        elif c.lower() in {"quantity"}:
            new_vals[c] = st.number_input(c, min_value=0, value=0, step=1, key=f"add_{c}")
        else:
            new_vals[c] = st.text_input(c, key=f"add_{c}")

    if st.button("Add Record"):
        if new_vals:
            colnames = ", ".join(new_vals.keys())
            placeholders = ", ".join(["?"] * len(new_vals))
            ok = exec_sql(f"INSERT INTO {table} ({colnames}) VALUES ({placeholders})", tuple(new_vals.values()))
            if ok: st.success("Record added.")

    st.markdown("---")
    # UPDATE
    st.subheader(f"✏️ Update record in {table}")
    if not df.empty:
        pk = df.columns[0]
        target_id = st.selectbox(f"Select {pk} to update", df[pk].tolist())
        current = df[df[pk] == target_id].iloc[0].to_dict()
        upd_vals = {}
        for c in df.columns:
            if c == pk:
                st.caption(f"Primary key: **{pk} = {target_id}**")
                continue
            default = "" if pd.isna(current[c]) else str(current[c])
            upd_vals[c] = st.text_input(c, value=default, key=f"upd_{c}")
        if st.button("Update Record"):
            set_clause = ", ".join([f"{k}=?" for k in upd_vals.keys()])
            ok = exec_sql(f"UPDATE {table} SET {set_clause} WHERE {pk} = ?", tuple(upd_vals.values()) + (target_id,))
            if ok: st.success("Record updated.")

    st.markdown("---")
    # DELETE
    st.subheader(f"🗑️ Delete record from {table}")
    if not df.empty:
        pk = df.columns[0]
        del_id = st.selectbox(f"Select {pk} to delete", df[pk].tolist(), key="del_id")
        if st.button("Delete Record"):
            ok = exec_sql(f"DELETE FROM {table} WHERE {pk} = ?", (del_id,))
            if ok: st.success("Record deleted.")

# =========================================================
# PAGE: DATA (quick download)
# =========================================================
elif page == "Data":
    st.header("Raw Data & Downloads")
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        st.subheader(t)
        if table_exists(t):
            d = run_sql(f"SELECT * FROM {t}")
            st.dataframe(d)
            st.download_button(f"Download {t}.csv", d.to_csv(index=False).encode("utf-8"), file_name=f"{t}.csv")
        else:
            st.info(f"Table {t} not found.")

# =========================================================
# PAGE: ABOUT
# =========================================================
elif page == "About":
    st.header("About this app")
    st.markdown("""
**Local Food Wastage Management System** — Streamlit app for redistributing surplus food.

**What you can do here**
- Filter donations by city, provider & food type; contact providers/receivers directly.
- Full CRUD on Providers / Receivers / Listings / Claims.
- 15 SQL queries for reporting.
- Power BI–style analytics with 6+ EDA reports:
  - Monthly donation trends
  - Food/meal type distributions
  - Provider performance & type contribution
  - Receiver demand patterns
  - City-level supply/demand
  - Expiry risk analysis (absolute Days-to-Expiry)

**Tech**: Python • SQLite • Pandas • Streamlit • Altair
""")
