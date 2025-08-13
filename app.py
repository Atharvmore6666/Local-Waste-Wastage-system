import os
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, date
from PIL import Image

# =========================
# CONFIG + THEME (Green on Beige)
# =========================
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

THEME_CSS = """
<style>
:root {
    --beige: #E8E2D0;
    --dark-green: #2E5339;
    --accent-green: #4F8F4F;
    --text-green: #2E5339;
}
.stApp {
    background-color: var(--beige);
    color: var(--text-green);
    font-family: 'Segoe UI', sans-serif;
}
h1,h2,h3,h4,h5,h6, p, span, div, label {
    color: var(--text-green) !important;
}
section[data-testid="stSidebar"] {
    background-color: var(--dark-green);
    color: white !important;
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p {
    color: white !important;
}
.block-container { padding-top: 0.5rem; }
.stButton>button, .stDownloadButton>button, .st-form button {
    background-color: var(--accent-green);
    color: white !important;
    border: none; border-radius: 10px; padding: 0.5rem 1rem; font-weight: 700;
}
.stButton>button:hover, .stDownloadButton>button:hover {
    background-color: var(--dark-green);
}
.dataframe th, .stDataFrame thead tr th { background-color: var(--accent-green) !important; color: white !important; }
[data-baseweb="select"] span { color: var(--text-green) !important; }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# =========================
# DB SETUP
# =========================
DB_PATH = "food_wastage.db"

@st.cache_resource(show_spinner=False)
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

def table_exists(name: str) -> bool:
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", conn, params=(name,))
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

# Optional: one-click refresh from CSVs if user wants (keeps formats same)
def refresh_db_from_csvs():
    csvs = {
        "Providers": "providers_data.csv",
        "Receivers": "receivers_data.csv",
        "Food_Listings": "food_listings_data.csv",
        "Claims": "claims_data.csv",
    }
    missing = [k for k,v in csvs.items() if not os.path.exists(v)]
    if missing:
        st.error("Missing CSV files: " + ", ".join([csvs[m] for m in missing]))
        return False

    try:
        for table, path in csvs.items():
            df = pd.read_csv(path, dtype=str)
            # trim text
            for c in df.select_dtypes(include="object").columns:
                df[c] = df[c].str.strip()
            # types
            if table == "Food_Listings" and "Expiry_Date" in df.columns:
                df["Expiry_Date"] = pd.to_datetime(df["Expiry_Date"], errors="coerce")
            if table == "Claims" and "Timestamp" in df.columns:
                df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
            df.to_sql(table, conn, index=False, if_exists="replace")
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Failed to refresh DB from CSVs: {e}")
        return False

# =========================
# IMAGES / HEADER
# =========================
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None

c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img: st.image(left_img, width=90)
with c2:
    st.markdown("<h1 style='text-align:center;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img: st.image(right_img, width=70)
st.markdown("---")

# =========================
# SIDEBAR NAV
# =========================
with st.sidebar:
    st.header("Navigation")
    page = st.radio("Go to", ["Dashboard", "Filter Food Donations", "Queries", "CRUD", "About"], index=0)
    with st.expander("Database Utilities"):
        if st.button("🔄 Refresh DB from CSVs"):
            if refresh_db_from_csvs():
                st.success("DB refreshed from CSVs. Reload the page to see updates.")

# =========================
# SHARED HELPERS (Filters)
# =========================
def get_base_frames():
    providers = run_sql("SELECT * FROM Providers") if table_exists("Providers") else pd.DataFrame()
    receivers = run_sql("SELECT * FROM Receivers") if table_exists("Receivers") else pd.DataFrame()
    listings  = run_sql("SELECT * FROM Food_Listings") if table_exists("Food_Listings") else pd.DataFrame()
    claims    = run_sql("SELECT * FROM Claims") if table_exists("Claims") else pd.DataFrame()

    # Parse dates
    if "Expiry_Date" in listings.columns:
        listings["Expiry_Date"] = pd.to_datetime(listings["Expiry_Date"], errors="coerce")
    if "Timestamp" in claims.columns:
        claims["Timestamp"] = pd.to_datetime(claims["Timestamp"], errors="coerce")

    # days_to_expiry as ABS (no negatives)
    if "Expiry_Date" in listings.columns:
        today = pd.to_datetime(date.today())
        listings["Days_To_Expiry"] = (listings["Expiry_Date"].dt.date - today.date()).apply(lambda d: abs(d.days) if pd.notnull(d) else None)

    return providers, receivers, listings, claims

def apply_global_filters(listings, claims, providers):
    # Join to enrich listings with provider name & city
    if not listings.empty and not providers.empty and "Provider_ID" in listings.columns and "Provider_ID" in providers.columns:
        listings = listings.merge(
            providers[["Provider_ID", "Name", "City", "Contact", "Type"]],
            on="Provider_ID", how="left", suffixes=("", "_Provider")
        ).rename(columns={"Name": "Provider_Name", "City": "Provider_City", "Type": "Provider_Type_Master"})

    # Sidebar slicers
    st.sidebar.subheader("🔍 Global Filters")

    city_opts = sorted(list(set(listings["Provider_City"].dropna().unique().tolist() if "Provider_City" in listings.columns else []) |
                             set(listings["Location"].dropna().unique().tolist() if "Location" in listings.columns else [])))
    provider_opts = sorted(listings["Provider_Name"].dropna().unique().tolist()) if "Provider_Name" in listings.columns else []
    foodtype_opts = sorted(listings["Food_Type"].dropna().unique().tolist()) if "Food_Type" in listings.columns else []
    mealtype_opts = sorted(listings["Meal_Type"].dropna().unique().tolist()) if "Meal_Type" in listings.columns else []

    sel_cities = st.sidebar.multiselect("City", options=city_opts, default=[])
    sel_providers = st.sidebar.multiselect("Provider", options=provider_opts, default=[])
    sel_foodtypes = st.sidebar.multiselect("Food Type", options=foodtype_opts, default=[])
    sel_mealtypes = st.sidebar.multiselect("Meal Type", options=mealtype_opts, default=[])

    # Days to expiry slicer
    only_upcoming = st.sidebar.checkbox("Only upcoming (Expiry ≥ today)", value=True)
    min_days, max_days = 0, int(listings["Days_To_Expiry"].max()) if "Days_To_Expiry" in listings.columns and listings["Days_To_Expiry"].notna().any() else 30
    sel_days = st.sidebar.slider("Days to Expiry (absolute)", min_value=min_days, max_value=max_days, value=(min_days, max_days))

    # Date range slicer for claims
    if not claims.empty and "Timestamp" in claims.columns and claims["Timestamp"].notna().any():
        min_d = claims["Timestamp"].min().date()
        max_d = claims["Timestamp"].max().date()
        dr = st.sidebar.date_input("Claim Date Range", value=(min_d, max_d))
        if isinstance(dr, tuple) and len(dr) == 2:
            claims = claims[(claims["Timestamp"].dt.date >= dr[0]) & (claims["Timestamp"].dt.date <= dr[1])]

    # Apply filters to listings
    lf = listings.copy()
    if sel_cities:
        lf = lf[(lf.get("Provider_City").isin(sel_cities)) | (lf.get("Location").isin(sel_cities))]
    if sel_providers:
        lf = lf[lf.get("Provider_Name").isin(sel_providers)]
    if sel_foodtypes:
        lf = lf[lf.get("Food_Type").isin(sel_foodtypes)]
    if sel_mealtypes:
        lf = lf[lf.get("Meal_Type").isin(sel_mealtypes)]
    if "Expiry_Date" in lf.columns and only_upcoming:
        lf = lf[lf["Expiry_Date"] >= pd.to_datetime(date.today())]
    if "Days_To_Expiry" in lf.columns:
        lf = lf[(lf["Days_To_Expiry"] >= sel_days[0]) & (lf["Days_To_Expiry"] <= sel_days[1])]

    return lf, claims

# =========================
# QUERIES (15)
# =========================
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
    "Q15: Listings expiring within next 3 days": """
        SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location,
               ABS(CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER)) AS Days_To_Expiry
        FROM Food_Listings f
        LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
        WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now','+3 days')
        ORDER BY Days_To_Expiry ASC;
    """,
}

# =========================
# DASHBOARD (Power BI style)
# =========================
if page == "Dashboard":
    st.header("📊 Dashboard (Interactive EDA)")
    providers, receivers, listings, claims = get_base_frames()
    if listings.empty:
        st.warning("Food_Listings table is empty or missing.")
        st.stop()

    # Apply global filters
    fl, fc = apply_global_filters(listings, claims, providers)

    # KPIs
    total_providers = len(providers) if not providers.empty else 0
    total_receivers = len(receivers) if not receivers.empty else 0
    total_food_qty  = int(fl["Quantity"].fillna(0).astype(float).sum()) if "Quantity" in fl.columns else 0
    total_claims    = len(fc) if not fc.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Providers", total_providers)
    k2.metric("Receivers", total_receivers)
    k3.metric("Total Food Quantity (Filtered)", total_food_qty)
    k4.metric("Claims (Filtered Range)", total_claims)

    # Chart type selector for status distribution
    chart_type = st.selectbox("Chart type for Status Distribution", ["Bar", "Pie"], index=1)

    # --- Row 1: Top Providers + Status Distribution
    cA, cB = st.columns([3,2])

    with cA:
        st.subheader("🏭 Top Providers by Donated Quantity (Filtered)")
        topN = st.slider("Top N", 5, 20, 10, key="top_providers_slider")
        if "Provider_Name" in fl.columns:
            top_prov = fl.groupby("Provider_Name", dropna=False)["Quantity"].sum().reset_index().sort_values("Quantity", ascending=False).head(topN)
            if not top_prov.empty:
                ch = alt.Chart(top_prov).mark_bar().encode(
                    x=alt.X("Quantity:Q", title="Total Donated Quantity"),
                    y=alt.Y("Provider_Name:N", sort='-x', title="Provider"),
                    tooltip=["Provider_Name", "Quantity"]
                ).properties(height=350)
                st.altair_chart(ch, use_container_width=True)
            else:
                st.info("No providers match current filters.")
        else:
            st.info("Provider_Name not available in Food_Listings join.")

    with cB:
        st.subheader("📌 Claims Status Distribution")
        if not fc.empty and "Status" in fc.columns:
            status_df = fc.groupby("Status").size().reset_index(name="Count")
            if chart_type == "Bar":
                ch2 = alt.Chart(status_df).mark_bar().encode(
                    x=alt.X("Status:N", title="Status"),
                    y=alt.Y("Count:Q", title="Count"),
                    tooltip=["Status", "Count"]
                ).properties(height=320)
            else:
                ch2 = alt.Chart(status_df).mark_arc().encode(
                    theta=alt.Theta("Count:Q"),
                    color=alt.Color("Status:N"),
                    tooltip=["Status", "Count"]
                ).properties(height=320)
            st.altair_chart(ch2, use_container_width=True)
        else:
            st.info("No claims in selected date range.")

    st.markdown("---")

    # --- Row 2: Food Type & Meal Type Distribution
    cC, cD = st.columns(2)

    with cC:
        st.subheader("🍲 Food Type Distribution (Filtered Listings)")
        if "Food_Type" in fl.columns:
            ft = fl["Food_Type"].fillna("Unknown").value_counts().reset_index()
            ft.columns = ["Food_Type", "Count"]
            ch3 = alt.Chart(ft).mark_arc().encode(
                theta=alt.Theta("Count:Q"),
                color=alt.Color("Food_Type:N"),
                tooltip=["Food_Type", "Count"]
            ).properties(height=320)
            st.altair_chart(ch3, use_container_width=True)
        else:
            st.info("Food_Type column missing.")

    with cD:
        st.subheader("🍽️ Meal Type Distribution (Filtered Listings)")
        if "Meal_Type" in fl.columns:
            mt = fl["Meal_Type"].fillna("Other").value_counts().reset_index()
            mt.columns = ["Meal_Type", "Count"]
            ch4 = alt.Chart(mt).mark_bar().encode(
                x=alt.X("Count:Q", title="Count"),
                y=alt.Y("Meal_Type:N", sort='-x', title="Meal Type"),
                tooltip=["Meal_Type", "Count"]
            ).properties(height=320)
            st.altair_chart(ch4, use_container_width=True)
        else:
            st.info("Meal_Type column missing.")

    st.markdown("---")

    # --- Row 3: Trends & Expiry
    cE, cF = st.columns([3,2])

    with cE:
        st.subheader("📅 Claims Quantity Over Time")
        if not fc.empty and "Timestamp" in fc.columns:
            # join to get quantity per claim (sum quantity of claimed items)
            if not listings.empty and "Food_ID" in listings.columns and "Food_ID" in fc.columns:
                cl_join = fc.merge(listings[["Food_ID","Quantity"]], on="Food_ID", how="left")
                trend = cl_join.dropna(subset=["Timestamp"]).groupby(cl_join["Timestamp"].dt.to_period("M"))["Quantity"].sum().reset_index()
                trend["Timestamp"] = trend["Timestamp"].astype(str)
                ch5 = alt.Chart(trend).mark_line(point=True).encode(
                    x=alt.X("Timestamp:T", title="Month"),
                    y=alt.Y("Quantity:Q", title="Total Quantity Claimed"),
                    tooltip=["Timestamp:T","Quantity:Q"]
                ).properties(height=350)
                st.altair_chart(ch5, use_container_width=True)
            else:
                st.info("Cannot compute trend — missing Food_ID join.")
        else:
            st.info("No claims in current range.")

    with cF:
        st.subheader("⏳ Listings by Days to Expiry (Absolute)")
        if "Days_To_Expiry" in fl.columns:
            exp_hist = fl.dropna(subset=["Days_To_Expiry"])
            if not exp_hist.empty:
                ch6 = alt.Chart(exp_hist).mark_bar().encode(
                    x=alt.X("Days_To_Expiry:Q", bin=alt.Bin(maxbins=25), title="Days to Expiry (abs)"),
                    y=alt.Y("count():Q", title="Listings"),
                    tooltip=[alt.Tooltip("count():Q", title="Listings")]
                ).properties(height=320)
                st.altair_chart(ch6, use_container_width=True)
            else:
                st.info("No expiry information for current filters.")
        else:
            st.info("Days_To_Expiry missing.")

# =========================
# FILTER FOOD DONATIONS PAGE
# =========================
elif page == "Filter Food Donations":
    st.header("🔎 Find & Contact Food Providers")
    providers, receivers, listings, _ = get_base_frames()
    if listings.empty or providers.empty:
        st.warning("Required tables missing (Food_Listings / Providers).")
        st.stop()

    df = listings.merge(
        providers[["Provider_ID","Name","Contact","City"]], on="Provider_ID", how="left"
    ).rename(columns={"Name": "Provider_Name", "City": "Provider_City"})

    # Filters
    cities = ["All"] + sorted(list(set(df["Provider_City"].dropna().unique().tolist() + df["Location"].dropna().unique().tolist())))
    providers_opt = ["All"] + sorted(df["Provider_Name"].dropna().unique().tolist())
    ftypes = ["All"] + sorted(df["Food_Type"].dropna().unique().tolist())

    colA, colB, colC = st.columns(3)
    sel_city = colA.selectbox("City", cities)
    sel_provider = colB.selectbox("Provider", providers_opt)
    sel_ftype = colC.selectbox("Food Type", ftypes)

    view = df.copy()
    if sel_city != "All":
        view = view[(view["Provider_City"] == sel_city) | (view["Location"] == sel_city)]
    if sel_provider != "All":
        view = view[view["Provider_Name"] == sel_provider]
    if sel_ftype != "All":
        view = view[view["Food_Type"] == sel_ftype]

    if not view.empty:
        view_show = view[["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Food_Type","Meal_Type","Provider_Name","Provider_City","Contact"]].sort_values("Expiry_Date")
        st.dataframe(view_show, use_container_width=True)

        st.caption("Click to contact:")
        for _, r in view_show.iterrows():
            tel = str(r.get("Contact", "")).strip()
            if tel and tel.lower() != "nan":
                st.markdown(f"- **{r['Provider_Name']}** — 📞 [{tel}](tel:{tel})")
    else:
        st.info("No matching listings.")

# =========================
# QUERIES PAGE (15 with toggles)
# =========================
elif page == "Queries":
    st.header("🧮 SQL Queries & Outputs")
    keys = list(QUERIES.keys())
    sel = st.selectbox("Choose a query", keys)
    show_as = st.radio("Show as", ["Table", "Bar Chart", "Pie Chart"], horizontal=True)

    params = None
    if sel == "Q3: Contact info of providers in a city (param)":
        city = st.text_input("Enter city name (case-insensitive)")
        if city:
            params = (city,)

    if (sel != "Q3: Contact info of providers in a city (param)") or params:
        df = run_sql(QUERIES[sel], params=params)
        if df.empty:
            st.info("No results.")
        else:
            if show_as == "Table":
                st.dataframe(df, use_container_width=True)
            elif show_as == "Bar Chart":
                # guess sensible axes
                numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                cat_cols = [c for c in df.columns if c not in numeric_cols]
                if numeric_cols and cat_cols:
                    ch = alt.Chart(df).mark_bar().encode(
                        x=alt.X(numeric_cols[0]+":Q", title=numeric_cols[0]),
                        y=alt.Y(cat_cols[0]+":N", sort='-x', title=cat_cols[0]),
                        tooltip=df.columns.tolist()
                    ).properties(height=400)
                    st.altair_chart(ch, use_container_width=True)
                else:
                    st.info("Need at least one numeric and one categorical column.")
            else:  # Pie
                numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                cat_cols = [c for c in df.columns if c not in numeric_cols]
                if numeric_cols and cat_cols:
                    ch = alt.Chart(df).mark_arc().encode(
                        theta=alt.Theta(numeric_cols[0]+":Q"),
                        color=alt.Color(cat_cols[0]+":N"),
                        tooltip=df.columns.tolist()
                    ).properties(height=400)
                    st.altair_chart(ch, use_container_width=True)
                else:
                    st.info("Need at least one numeric and one categorical column.")
            st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), file_name=f"{sel.replace(' ','_')}.csv")

# =========================
# CRUD PAGE
# =========================
elif page == "CRUD":
    st.header("🛠️ Manage Records (CRUD)")

    tables = ["Providers", "Receivers", "Food_Listings", "Claims"]
    tsel = st.selectbox("Select table", tables)

    if not table_exists(tsel):
        st.warning(f"Table `{tsel}` not found.")
        st.stop()

    df = run_sql(f"SELECT * FROM {tsel}")
    st.subheader(f"Existing records in {tsel}")
    st.dataframe(df, use_container_width=True)

    st.markdown("### ➕ Add new record")
    # get empty schema to build form
    empty = run_sql(f"SELECT * FROM {tsel} LIMIT 0")
    add_vals = {}
    cols = list(empty.columns)

    # treat common PK names as optional (autoincrement)
    pk_like = {c for c in cols if c.lower() in {"id","provider_id","receiver_id","food_id","claim_id"}}
    for c in cols:
        if c in pk_like:
            st.text(f"{c} (auto / optional)")
            continue
        if c.lower().endswith("date"):
            v = st.date_input(c, value=date.today(), key=f"add_{c}")
            add_vals[c] = v.isoformat()
        elif c.lower() == "timestamp":
            v = st.text_input(c, value=datetime.now().isoformat(), key=f"add_{c}")
            add_vals[c] = v
        else:
            add_vals[c] = st.text_input(c, key=f"add_{c}")

    if st.button("Add Record"):
        cols_ins = ", ".join(add_vals.keys())
        placeholders = ", ".join(["?"]*len(add_vals))
        values = tuple(add_vals.values())
        ok = exec_sql(f"INSERT INTO {tsel} ({cols_ins}) VALUES ({placeholders})", values)
        if ok: st.success("Record added.")

    st.markdown("---")
    st.markdown("### ✏️ Update record")
    if not df.empty:
        # assume first column is PK
        pk_col = df.columns[0]
        ids = df[pk_col].tolist()
        sel_id = st.selectbox(f"Select {pk_col} to update", ids)
        row = df[df[pk_col] == sel_id].iloc[0]
        upd_vals = {}
        for c in df.columns:
            if c == pk_col:
                st.text(f"{pk_col} (PK): {sel_id}")
                continue
            upd_vals[c] = st.text_input(c, value=str(row[c]), key=f"upd_{c}")
        if st.button("Update Record"):
            set_clause = ", ".join([f"{c}=?" for c in upd_vals])
            params = tuple(upd_vals.values()) + (sel_id,)
            ok = exec_sql(f"UPDATE {tsel} SET {set_clause} WHERE {pk_col} = ?", params)
            if ok: st.success("Record updated.")

    st.markdown("---")
    st.markdown("### 🗑️ Delete record")
    if not df.empty:
        pk_col = df.columns[0]
        del_id = st.selectbox(f"Select {pk_col} to delete", df[pk_col].tolist(), key="del_id")
        if st.button("Delete Record"):
            ok = exec_sql(f"DELETE FROM {tsel} WHERE {pk_col} = ?", (del_id,))
            if ok: st.success("Record deleted.")

# =========================
# ABOUT PAGE
# =========================
elif page == "About":
    st.header("About this app")
    st.markdown("""
**Local Food Wastage Management System** — connects surplus food providers with people in need.

**What you can do here**
- Filter donations (location, provider, food type), and directly **contact providers**.
- Perform **CRUD** on Providers, Receivers, Food Listings, and Claims.
- Explore **15 SQL-driven insights** with chart/table toggles & CSV download.
- A **Power BI–style dashboard** with interactive slicers, KPIs, and charts.

**Tech**: Streamlit, SQLite, Pandas, Altair.
""")
