# app.py
import os
import sqlite3
from datetime import date, datetime
from typing import Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

# -----------------------
# Config / styling
# -----------------------
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")
st.markdown(
    """
    <style>
    :root { --beige:#E8E2D0; --dark-green:#2E5339; --accent:#4F8F4F; --ink:#1A1A1A; }
    .stApp { background:var(--beige); color:var(--dark-green); font-family: 'Segoe UI', sans-serif; }
    h1,h2,h3 { color:var(--dark-green) !important; font-weight:700; }
    section[data-testid="stSidebar"] { background:var(--dark-green); color: #eaf3ea; }
    .card { background:white; padding:12px; border-radius:8px; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }
    .small-muted { color: #3b6b49; font-size:14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Paths & CSV map
# -----------------------
DB_PATH = "food_wastage.db"
CSV_MAP = {
    "Providers": "providers_data.csv",
    "Receivers": "receivers_data.csv",
    "Food_Listings": "food_listings_data.csv",
    "Claims": "claims_data.csv",
}

# -----------------------
# DB helpers
# -----------------------
@st.cache_resource
def get_conn(path: str = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(path, check_same_thread=False)


def ensure_db_from_csvs(conn: sqlite3.Connection) -> Tuple[bool, str]:
    """If DB missing, try to build from CSVs in repo root."""
    missing = [f for f in CSV_MAP.values() if not os.path.exists(f)]
    if missing:
        return False, f"Missing CSV files: {', '.join(missing)}"
    try:
        for table, csvfile in CSV_MAP.items():
            df = pd.read_csv(csvfile, dtype=str)
            # basic cleaning
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": "", "None": ""})
            df.to_sql(table, conn, index=False, if_exists="replace")
        conn.commit()
        return True, "DB created from CSVs"
    except Exception as e:
        return False, f"Failed to create DB from CSVs: {e}"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", conn, params=(name,))
        return not df.empty
    except Exception:
        return False


def run_sql(conn: sqlite3.Connection, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()


def exec_sql(conn: sqlite3.Connection, sql: str, params: Optional[tuple] = None) -> bool:
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


# -----------------------
# Connect / build DB if needed
# -----------------------
if not os.path.exists(DB_PATH):
    # create DB and try to load CSVs
    conn_tmp = sqlite3.connect(DB_PATH)
    ok, msg = ensure_db_from_csvs(conn_tmp)
    conn_tmp.close()
    if not ok:
        st.warning("Database not found and couldn't create from CSVs: " + msg)

conn = get_conn()

# -----------------------
# Load tables defensively
# -----------------------
@st.cache_data
def load_tables() -> dict:
    out = {}
    for tbl in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        if table_exists(conn, tbl):
            df = pd.read_sql(f"SELECT * FROM {tbl}", conn)
            # strip whitespace for object columns
            df.columns = df.columns.str.strip()
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": "", "None": ""})
            out[tbl] = df
        else:
            out[tbl] = pd.DataFrame()
    return out


tables = load_tables()
providers = tables["Providers"]
receivers = tables["Receivers"]
food = tables["Food_Listings"]
claims = tables["Claims"]

# -----------------------
# basic cleaning functions
# -----------------------
def safe_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def add_days_to_expiry(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Expiry_Date" not in df.columns:
        return df
    df = df.copy()
    df["Expiry_Date"] = safe_dt(df["Expiry_Date"])
    today = pd.to_datetime(date.today())
    # absolute (positive) difference in days - as user requested
    df["Days_To_Expiry"] = (df["Expiry_Date"].dt.normalize() - today).dt.days
    # remove sign (present as absolute positive)
    df["Days_To_Expiry"] = df["Days_To_Expiry"].abs().astype("Int64")
    return df


def coerce_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)
    return pd.Series(dtype="float64")


# Apply
food = add_days_to_expiry(food)
if "Quantity" in food.columns:
    food["Quantity"] = pd.to_numeric(food["Quantity"], errors="coerce").fillna(0)
if "Quantity" in claims.columns:
    claims["Quantity"] = pd.to_numeric(claims["Quantity"], errors="coerce").fillna(0)

# -----------------------
# Header
# -----------------------
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None
c1, c2, c3 = st.columns([1, 6, 1])
with c1:
    if left_img:
        st.image(left_img, width=80)
with c2:
    st.markdown("<div style='text-align:center'><h1 style='margin:0'>🌿 Local Food Wastage Management System</h1><div class='small-muted'>Interactive dashboard · SQL queries · CRUD</div></div>", unsafe_allow_html=True)
with c3:
    if right_img:
        st.image(right_img, width=70)
st.markdown("---")

# -----------------------
# Sidebar navigation
# -----------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Donations Explorer", "Queries", "CRUD", "Data", "About"])

# Global filters used in dashboard/explorer
with st.sidebar.expander("Global filters", expanded=False):
    # City options from available columns (search both providers/food/receivers)
    city_candidates = set()
    for df, col in [(providers, "City"), (receivers, "City"), (food, "Location")]:
        if not df.empty and col in df.columns:
            city_candidates.update(df[col].dropna().astype(str).unique().tolist())
    city_list = ["All"] + sorted([c for c in city_candidates if c])
    sel_city = st.selectbox("City", city_list, index=0)

    # Provider list
    prov_list = ["All"]
    if not providers.empty and "Name" in providers.columns:
        prov_list += sorted(providers["Name"].dropna().astype(str).unique().tolist())
    sel_provider = st.selectbox("Provider", prov_list, index=0)

    # Food type
    ft_list = ["All"]
    if not food.empty and "Food_Type" in food.columns:
        ft_list += sorted(food["Food_Type"].dropna().astype(str).unique().tolist())
    sel_food_type = st.selectbox("Food Type", ft_list, index=0)

    # Date range filter (based on expiry_date or Claims.Timestamp)
    min_date = None
    max_date = None
    # try to derive from food expiry
    if "Expiry_Date" in food.columns and not food["Expiry_Date"].dropna().empty:
        dmin = safe_dt(food["Expiry_Date"]).min()
        dmax = safe_dt(food["Expiry_Date"]).max()
        min_date, max_date = dmin.date(), dmax.date()
    # fallback to claims timestamp
    if (min_date is None or max_date is None) and "Timestamp" in claims.columns and not claims["Timestamp"].dropna().empty:
        dmin = safe_dt(claims["Timestamp"]).min()
        dmax = safe_dt(claims["Timestamp"]).max()
        min_date, max_date = dmin.date(), dmax.date()
    if min_date is None or max_date is None:
        min_date, max_date = date.today(), date.today()
    sel_date_range = st.date_input("Date range (uses expiry or claim timestamps)", [min_date, max_date])

# small helper to apply global filters to dataframes
def apply_filters(food_df: pd.DataFrame, claims_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    f = food_df.copy()
    c = claims_df.copy()
    # City filter: check food Location OR provider city
    if sel_city and sel_city != "All":
        cond_loc = f.get("Location", "").astype(str).str.lower() == sel_city.lower()
        # check provider city if mapping available
        if "Provider_ID" in f.columns and not providers.empty and "Provider_ID" in providers.columns:
            prov_map = providers[["Provider_ID", "City"]].drop_duplicates()
            prov_map["Provider_ID"] = prov_map["Provider_ID"].astype(str)
            f = f.merge(prov_map, on="Provider_ID", how="left", suffixes=("", "_prov"))
            cond_prov = f.get("City_prov", "").astype(str).str.lower() == sel_city.lower()
            f = f[cond_loc | cond_prov]
            # drop helper city_prov
            f = f.drop(columns=[c for c in f.columns if c.endswith("_prov")], errors='ignore')
        else:
            f = f[cond_loc]
        # claims: join to food to filter
        if "Food_ID" in c.columns and not f.empty:
            c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]
    # Provider filter
    if sel_provider and sel_provider != "All" and "Provider_ID" in f.columns:
        # find provider id(s)
        if "Name" in providers.columns:
            matching = providers[providers["Name"].astype(str) == sel_provider]
            if not matching.empty and "Provider_ID" in matching.columns:
                ids = matching["Provider_ID"].astype(str).tolist()
                f = f[f["Provider_ID"].astype(str).isin(ids)]
                if "Food_ID" in c.columns:
                    c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]
    # Food type filter
    if sel_food_type and sel_food_type != "All" and "Food_Type" in f.columns:
        f = f[f["Food_Type"].astype(str) == sel_food_type]
        if "Food_ID" in c.columns:
            c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]
    # date range filter: attempt to apply to expiry_date and claims timestamp
    start_d, end_d = sel_date_range[0], sel_date_range[1]
    # food expiry
    if "Expiry_Date" in f.columns:
        f["Expiry_Date_dt"] = safe_dt(f["Expiry_Date"])
        f = f[(f["Expiry_Date_dt"].dt.date >= start_d) & (f["Expiry_Date_dt"].dt.date <= end_d) | (f["Expiry_Date_dt"].isna())]
        f = f.drop(columns=["Expiry_Date_dt"], errors="ignore")
    # claims timestamp
    if "Timestamp" in c.columns:
        c["Timestamp_dt"] = safe_dt(c["Timestamp"])
        c = c[(c["Timestamp_dt"].dt.date >= start_d) & (c["Timestamp_dt"].dt.date <= end_d) | (c["Timestamp_dt"].isna())]
        c = c.drop(columns=["Timestamp_dt"], errors="ignore")
    return f, c


# -----------------------
# Dashboard page
# -----------------------
if page == "Dashboard":
    st.header("Dashboard — Interactive EDA (6+ reports)")

    # apply filters
    f, c = apply_filters(food, claims)

    # KPIs
    st.subheader("Key Metrics")
    k1, k2, k3, k4 = st.columns(4)
    total_providers = int(run_sql(conn, "SELECT COUNT(*) AS c FROM Providers")["c"].iloc[0]) if table_exists(conn, "Providers") else 0
    total_receivers = int(run_sql(conn, "SELECT COUNT(*) AS c FROM Receivers")["c"].iloc[0]) if table_exists(conn, "Receivers") else 0
    total_food_qty = int(f["Quantity"].sum()) if "Quantity" in f.columns and not f.empty else 0
    total_claims = int(c.shape[0]) if not c.empty else int(run_sql(conn, "SELECT COUNT(*) AS c FROM Claims")["c"].iloc[0]) if table_exists(conn, "Claims") else 0
    k1.metric("Providers (DB)", total_providers)
    k2.metric("Receivers (DB)", total_receivers)
    k3.metric("Total Food Quantity (filtered)", total_food_qty)
    k4.metric("Total Claims (filtered)", total_claims)

    st.markdown("---")

    # Chart group 1: Food type distribution (bar)
    st.subheader("1) Food type distribution (quantity)")
    if not f.empty and "Food_Type" in f.columns:
        agg_ft = f.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        if not agg_ft.empty:
            chart = alt.Chart(agg_ft).mark_bar().encode(
                x=alt.X("Quantity:Q", title="Total Quantity"),
                y=alt.Y("Food_Type:N", sort='-x', title="Food Type"),
                tooltip=["Food_Type", "Quantity"]
            ).properties(height=320)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No food-type aggregates.")
    else:
        st.info("No Food_Type/Quantity columns available to show distribution.")

    # Chart group 2: Meal type share (pie)
    st.subheader("2) Meal type share (count)")
    if not f.empty and "Meal_Type" in f.columns:
        mt = f["Meal_Type"].fillna("Unknown").astype(str).value_counts().reset_index()
        mt.columns = ["Meal_Type", "Count"]
        if not mt.empty:
            pie = alt.Chart(mt).mark_arc().encode(theta=alt.Theta("Count:Q"), color=alt.Color("Meal_Type:N"), tooltip=["Meal_Type", "Count"]).properties(height=320)
            st.altair_chart(pie, use_container_width=True)
        else:
            st.info("No Meal_Type data found.")
    else:
        st.info("Meal_Type column not present.")

    # Chart group 3: Top providers by quantity
    st.subheader("3) Top providers by donated quantity")
    if not f.empty and "Provider_ID" in f.columns and not providers.empty:
        merged = f.merge(providers[["Provider_ID", "Name"]], on="Provider_ID", how="left").rename(columns={"Name": "Provider_Name"})
        merged["Quantity"] = pd.to_numeric(merged.get("Quantity", 0), errors="coerce").fillna(0)
        top_providers = merged.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(12)
        if not top_providers.empty:
            b = alt.Chart(top_providers).mark_bar().encode(
                x=alt.X("Quantity:Q", title="Total Quantity"),
                y=alt.Y("Provider_Name:N", sort='-x', title="Provider"),
                tooltip=["Provider_Name", "Quantity"]
            ).properties(height=320)
            st.altair_chart(b, use_container_width=True)
        else:
            st.info("No provider donation data.")
    else:
        st.info("Provider info or Provider_ID missing.")

    # Chart group 4: Claims over time (line)
    st.subheader("4) Claims over time (by Timestamp or by Food expiry if Timestamp missing)")
    if not c.empty and "Timestamp" in c.columns:
        c["Timestamp_dt"] = safe_dt(c["Timestamp"])
        # group by month
        c_month = c.dropna(subset=["Timestamp_dt"]).groupby(pd.Grouper(key="Timestamp_dt", freq="M"))["Quantity"].sum().reset_index().rename(columns={"Timestamp_dt": "Period"})
        if not c_month.empty:
            c_month["PeriodStr"] = c_month["Period"].dt.strftime("%Y-%m")
            ln = alt.Chart(c_month).mark_line(point=True).encode(x=alt.X("PeriodStr:N", title="Month"), y=alt.Y("Quantity:Q", title="Total Quantity"), tooltip=["PeriodStr", "Quantity"]).properties(height=320)
            st.altair_chart(ln, use_container_width=True)
        else:
            st.info("No timestamped claims available for trend.")
    elif not f.empty and "Expiry_Date" in f.columns:
        tmp = f.copy()
        tmp["Expiry_Date_dt"] = safe_dt(tmp["Expiry_Date"])
        tmp = tmp.dropna(subset=["Expiry_Date_dt"])
        if not tmp.empty:
            tmp_month = tmp.groupby(pd.Grouper(key="Expiry_Date_dt", freq="M"))["Quantity"].sum().reset_index().rename(columns={"Expiry_Date_dt": "Period"})
            tmp_month["PeriodStr"] = tmp_month["Period"].dt.strftime("%Y-%m")
            ln = alt.Chart(tmp_month).mark_line(point=True).encode(x=alt.X("PeriodStr:N", title="Month (Expiry)"), y=alt.Y("Quantity:Q", title="Total Quantity"), tooltip=["PeriodStr", "Quantity"]).properties(height=320)
            st.altair_chart(ln, use_container_width=True)
        else:
            st.info("No expiry-date records for trend.")
    else:
        st.info("Neither claims Timestamp nor food Expiry_Date available for trend.")

    # Chart group 5: Expired quantities (area / line)
    st.subheader("5) Expired quantities (past)")
    if not f.empty and "Expiry_Date" in f.columns:
        f2 = f.copy()
        f2["Expiry_Date_dt"] = safe_dt(f2["Expiry_Date"])
        expired = f2[f2["Expiry_Date_dt"] < pd.to_datetime(date.today())]
        if not expired.empty:
            expired_month = expired.groupby(pd.Grouper(key="Expiry_Date_dt", freq="M"))["Quantity"].sum().reset_index()
            expired_month["PeriodStr"] = expired_month["Expiry_Date_dt"].dt.strftime("%Y-%m")
            area = alt.Chart(expired_month).mark_area(opacity=0.5).encode(x="PeriodStr:N", y="Quantity:Q", tooltip=["PeriodStr", "Quantity"]).properties(height=320)
            st.altair_chart(area, use_container_width=True)
        else:
            st.info("No expired listings found in filtered data.")
    else:
        st.info("Expiry_Date column not available.")

    # Chart group 6: Days-to-expiry histogram
    st.subheader("6) Days-to-expiry distribution (absolute days)")
    if not f.empty and "Days_To_Expiry" in f.columns:
        hist = f["Days_To_Expiry"].dropna().astype(int).value_counts().reset_index()
        hist.columns = ["Days_To_Expiry", "Count"]
        hist = hist.sort_values("Days_To_Expiry")
        if not hist.empty:
            ch = alt.Chart(hist).mark_bar().encode(x=alt.X("Days_To_Expiry:Q", title="Days to expiry (abs)"), y=alt.Y("Count:Q"), tooltip=["Days_To_Expiry", "Count"]).properties(height=320)
            st.altair_chart(ch, use_container_width=True)
        else:
            st.info("No Days_To_Expiry data.")
    else:
        st.info("Days_To_Expiry column missing.")

    st.markdown("---")
    st.subheader("Sample listings (filtered)")
    show_cols = [c for c in ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Location", "Food_Type", "Meal_Type", "Days_To_Expiry"] if c in f.columns]
    if not f.empty and show_cols:
        st.dataframe(f[show_cols].sort_values("Days_To_Expiry", na_position="last").head(300), use_container_width=True)
    else:
        st.info("No listings to display for current filters.")

# -----------------------
# Donations Explorer page (search / contact)
# -----------------------
elif page == "Donations Explorer":
    st.header("Donations Explorer — search, filter, contact")

    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers table missing.")
    else:
        merged = food.merge(providers[["Provider_ID", "Name", "Contact"]], on="Provider_ID", how="left").rename(columns={"Name": "Provider_Name", "Contact": "Provider_Contact"})
        # controls (local to explorer)
        col1, col2, col3 = st.columns([1, 1, 1])
        city_opts = ["All"] + sorted(merged.get("Location", pd.Series()).dropna().astype(str).unique().tolist())
        prov_opts = ["All"] + sorted(merged.get("Provider_Name", pd.Series()).dropna().astype(str).unique().tolist())
        ft_opts = ["All"] + sorted(merged.get("Food_Type", pd.Series()).dropna().astype(str).unique().tolist())
        sel_city_e = col1.selectbox("City", city_opts, index=0)
        sel_provider_e = col2.selectbox("Provider", prov_opts, index=0)
        sel_ft_e = col3.selectbox("Food Type", ft_opts, index=0)

        res = merged.copy()
        if sel_city_e != "All":
            res = res[res["Location"].astype(str) == sel_city_e]
        if sel_provider_e != "All":
            res = res[res["Provider_Name"].astype(str) == sel_provider_e]
        if sel_ft_e != "All":
            res = res[res["Food_Type"].astype(str) == sel_ft_e]

        if res.empty:
            st.info("No matching listings for selected filters.")
        else:
            display_cols = [c for c in ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Location", "Provider_Name", "Provider_Contact", "Food_Type", "Meal_Type"] if c in res.columns]
            st.dataframe(res[display_cols].sort_values("Expiry_Date", na_position="last"), use_container_width=True)
            st.markdown("**Contact details for matched providers**")
            for _, r in res[["Provider_Name", "Provider_Contact"]].drop_duplicates().iterrows():
                contact = r.get("Provider_Contact", "")
                name = r.get("Provider_Name", "(no name)")
                if contact and "@" in str(contact):
                    st.markdown(f"- **{name}** — [{contact}](mailto:{contact})")
                elif contact:
                    st.markdown(f"- **{name}** — {contact}")
                else:
                    st.markdown(f"- **{name}** — (no contact)")

# -----------------------
# Queries page (15 predefined)
# -----------------------
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
            GROUP BY City ORDER BY Providers_Count DESC;
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
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
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
            FROM Food_Listings f LEFT JOIN Claims c ON f.Food_ID = c.Food_ID
            GROUP BY f.Food_ID, f.Food_Name
            ORDER BY Claims_Count DESC;
        """,
        "Q9: Provider with highest successful claims": """
            SELECT p.Provider_ID, p.Name, p.City, COUNT(c.Claim_ID) AS Completed_Claims
            FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID
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
            FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            GROUP BY f.Meal_Type
            ORDER BY Claims_Count DESC;
        """,
        "Q13: Total quantity donated by each provider": """
            SELECT p.Provider_ID, p.Name, p.City, SUM(f.Quantity) AS Total_Donated
            FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.Provider_ID, p.Name
            ORDER BY Total_Donated DESC
            LIMIT 50;
        """,
        "Q14: Expired food listings": """
            SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location
            FROM Food_Listings f LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) < date('now')
            ORDER BY f.Expiry_Date ASC;
        """,
        "Q15: Listings expiring within next 3 days": """
            SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location,
                   CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER) AS days_to_expiry
            FROM Food_Listings f LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now','+3 days')
            ORDER BY days_to_expiry ASC;
        """,
    }

    qkey = st.selectbox("Choose query", list(QUERIES.keys()))
    st.code(QUERIES[qkey], language="sql")
    params = None
    if qkey == "Q3: Contact info of providers in a city (param)":
        cityinp = st.text_input("City (case-insensitive)")
        if cityinp:
            params = (cityinp,)
    if (qkey == "Q3: Contact info of providers in a city (param)" and not params):
        st.info("Enter a city to run this parametric query.")
    else:
        dfq = run_sql(conn, QUERIES[qkey], params)
        if dfq.empty:
            st.info("No results.")
        else:
            st.dataframe(dfq, use_container_width=True)
            st.download_button("Download CSV", dfq.to_csv(index=False).encode("utf-8"), file_name=f"{qkey.replace(' ','_')}.csv")

# -----------------------
# CRUD page
# -----------------------
elif page == "CRUD":
    st.header("CRUD — Add / Update / Delete records")
    table_choice = st.selectbox("Choose table", ["Providers", "Receivers", "Food_Listings", "Claims"])
    if not table_exists(conn, table_choice):
        st.warning(f"Table {table_choice} not found in DB.")
    else:
        df = run_sql(conn, f"SELECT * FROM {table_choice}")
        st.subheader("Existing records (preview)")
        st.dataframe(df.head(200), use_container_width=True)

        st.markdown("### Add new record")
        # simple add form respecting common columns
        cols = df.columns.tolist() if not df.empty else []
        add_values = {}
        for c in cols:
            if c.lower().endswith("id") and c.lower() in {"provider_id", "receiver_id", "food_id", "claim_id"}:
                # allow entering but optional
                add_values[c] = st.text_input(f"{c} (optional)", key=f"add_{c}")
            elif c.lower().endswith("date") or c.lower() == "timestamp":
                d = st.date_input(f"{c}", value=date.today(), key=f"add_{c}")
                add_values[c] = d.isoformat()
            elif c.lower() == "quantity":
                add_values[c] = st.number_input(c, min_value=0, value=1, key=f"add_{c}")
            else:
                add_values[c] = st.text_input(c, key=f"add_{c}")

        if st.button("Add record"):
            if not add_values:
                st.warning("No columns found to add.")
            else:
                cols_ins = ", ".join(add_values.keys())
                placeholders = ", ".join(["?"] * len(add_values))
                vals = tuple(v if v != "" else None for v in add_values.values())
                ok = exec_sql(conn, f"INSERT INTO {table_choice} ({cols_ins}) VALUES ({placeholders})", vals)
                if ok:
                    st.success("Record added. Refreshing tables...")
                    st.experimental_rerun()

        st.markdown("---")
        if not df.empty:
            st.subheader("Update existing record")
            pk = df.columns[0]
            sel_id = st.selectbox(f"Select {pk}", df[pk].tolist(), key="upd_id")
            row = df[df[pk] == sel_id].iloc[0].to_dict()
            upd_vals = {}
            for c in df.columns:
                if c == pk:
                    st.caption(f"{pk}: {sel_id}")
                    continue
                upd_vals[c] = st.text_input(c, value=str(row[c]), key=f"upd_{c}")
            if st.button("Update record"):
                set_clause = ", ".join([f"{k} = ?" for k in upd_vals.keys()])
                params = tuple(upd_vals.values()) + (sel_id,)
                ok = exec_sql(conn, f"UPDATE {table_choice} SET {set_clause} WHERE {pk} = ?", params)
                if ok:
                    st.success("Record updated.")
                    st.experimental_rerun()

        st.markdown("---")
        if not df.empty:
            st.subheader("Delete record")
            pk = df.columns[0]
            del_id = st.selectbox("Select id to delete", df[pk].tolist(), key="del_id")
            if st.button("Delete record"):
                ok = exec_sql(conn, f"DELETE FROM {table_choice} WHERE {pk} = ?", (del_id,))
                if ok:
                    st.success("Deleted.")
                    st.experimental_rerun()

# -----------------------
# Data page
# -----------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for t in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        st.subheader(t)
        if table_exists(conn, t):
            df = run_sql(conn, f"SELECT * FROM {t}")
            st.dataframe(df, use_container_width=True)
            st.download_button(f"Download {t}.csv", df.to_csv(index=False).encode("utf-8"), file_name=f"{t}.csv")
        else:
            st.info(f"Table {t} not found.")

# -----------------------
# About
# -----------------------
elif page == "About":
    st.header("About")
    st.markdown(
        """
        **Local Food Wastage Management System**

        Features:
        - Interactive EDA dashboard (6+ reports) with filters (city, provider, food type, date)
        - Donations Explorer for searching & contacting providers
        - 15 prebuilt SQL queries + downloadable CSVs
        - CRUD interface to add/update/delete records directly in SQLite DB

        Data sources expected in repo root:
        - food_wastage.db (preferred), or:
        - providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv (CSV fallback)

        Next steps you can ask me to implement:
        - Geolocation map layer (if lat/lon available)
        - Authentication & role-based CRUD
        - Deployment tuning for Streamlit Cloud
        """
    )
