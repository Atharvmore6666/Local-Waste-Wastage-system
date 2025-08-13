# app.py
import os
import sqlite3
from datetime import date, datetime

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
:root{--beige:#E8E2D0;--dark-green:#2E5339;--accent-green:#4F8F4F;--ink:#1A1A1A;}
.stApp{background:var(--beige); color:var(--dark-green); font-family:'Segoe UI',sans-serif;}
h1,h2,h3,h4,h5{color:var(--dark-green) !important; font-weight:700;}
section[data-testid="stSidebar"]{background:var(--dark-green); color:#dbe7db;}
section[data-testid="stSidebar"] *{color:#dbe7db !important;}
.card{background:#fff; border-radius:10px; padding:12px;}
.kpi-value{font-size:26px; font-weight:800; color:var(--dark-green);}
.stButton>button{background:var(--accent-green); color:#fff; border-radius:8px;}
.dataframe th{background:var(--accent-green) !important; color:#fff !important;}
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# -----------------------
# PATHS
# -----------------------
DB_PATH = "food_wastage.db"
LOGO_LEFT = "logo.png"
LOGO_RIGHT = "recycle.png"

# -----------------------
# DB helpers
# -----------------------
@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

def table_exists(name: str) -> bool:
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", conn, params=(name,))
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
# Load images
# -----------------------
left_img = Image.open(LOGO_LEFT) if os.path.exists(LOGO_LEFT) else None
right_img = Image.open(LOGO_RIGHT) if os.path.exists(LOGO_RIGHT) else None

c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img: st.image(left_img, width=80)
with c2:
    st.markdown("<h1 style='text-align:center;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img: st.image(right_img, width=60)
st.markdown("---")

# -----------------------
# Sidebar navigation
# -----------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", [
    "Dashboard",
    "Donations Analysis",
    "Providers Insights",
    "Receivers Insights",
    "Wastage & Expiry",
    "Filter Food",
    "Queries",
    "CRUD",
    "Data",
    "About"
])

# -----------------------
# Load base tables (cached)
# -----------------------
@st.cache_data(show_spinner=False)
def load_tables():
    out = {}
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        if table_exists(t):
            df = run_sql(f"SELECT * FROM {t}")
            # normalize column names (strip whitespace)
            df.columns = df.columns.str.strip()
            out[t] = df
        else:
            out[t] = pd.DataFrame()
    return out

dfs = load_tables()
providers = dfs["Providers"]
receivers = dfs["Receivers"]
food = dfs["Food_Listings"]
claims = dfs["Claims"]

# Defensive cleaning helper
def prepare_food_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: 
        return df
    df = df.copy()
    df.columns = df.columns.str.strip()
    # Coerce numeric
    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    # Parse expiry
    if "Expiry_Date" in df.columns:
        df["Expiry_Date"] = pd.to_datetime(df["Expiry_Date"], errors="coerce")
        today = pd.to_datetime(date.today())
        df["Days_To_Expiry"] = (df["Expiry_Date"].dt.normalize() - today).dt.days.abs().astype("Int64")
    else:
        df["Days_To_Expiry"] = pd.NA
    # Strip text cols
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].astype(str).str.strip()
    return df

def prepare_claims_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = df.columns.str.strip()
    # parse timestamp if present
    for c in ["Timestamp","timestamp","Date","date","Claim_Date"]:
        if c in df.columns:
            df["Timestamp"] = pd.to_datetime(df[c], errors="coerce")
            break
    # coerce numeric fields if any
    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].astype(str).str.strip()
    return df

food = prepare_food_df(food)
claims = prepare_claims_df(claims)
# normalize providers/receivers text cols
for df in (providers, receivers):
    if not df.empty:
        df.columns = df.columns.str.strip()
        for c in df.select_dtypes(include=["object"]).columns:
            df[c] = df[c].astype(str).str.strip()

# small helper to create contact links
def make_contact_html(df: pd.DataFrame, name_col: str, contact_col: str, id_col: str):
    if df.empty:
        return ""
    out = df[[id_col, name_col, contact_col]].fillna("")
    out["ContactLink"] = out[contact_col].apply(lambda v: (f"<a href='mailto:{v}'>{v}</a>" if "@" in v else (f"<a href='tel:{v}'>{v}</a>" if v else "")))
    return out.to_html(escape=False, index=False)

# -----------------------
# PAGE: Dashboard
# -----------------------
if page == "Dashboard":
    st.header("Dashboard")

    if food.empty or providers.empty:
        st.warning("Food_Listings and Providers tables are required for the dashboard.")
        st.stop()

    # Global filter controls
    with st.expander("Filters", expanded=True):
        # city options aggregated from providers, receivers and food location
        city_opts = sorted(set(
            providers["City"].dropna().str.strip().unique().tolist() +
            receivers["City"].dropna().str.strip().unique().tolist() +
            food["Location"].dropna().str.strip().unique().tolist()
        ))
        sel_city = st.selectbox("City", ["All"] + city_opts)
        provider_opts = sorted(food["Provider_ID"].dropna().unique().tolist())
        # map provider ids to names if providers table present
        prov_map = {}
        if not providers.empty and "Provider_ID" in providers.columns and "Name" in providers.columns:
            prov_map = dict(zip(providers["Provider_ID"], providers["Name"]))
            provider_names = [prov_map.get(i, str(i)) for i in provider_opts]
        else:
            provider_names = [str(i) for i in provider_opts]
        sel_provider = st.selectbox("Provider", ["All"] + provider_names)
        food_type_opts = sorted(food["Food_Type"].dropna().unique().tolist())
        sel_food_type = st.selectbox("Food Type", ["All"] + food_type_opts)
        day_min = int(food["Days_To_Expiry"].dropna().min()) if food["Days_To_Expiry"].notna().any() else 0
        day_max = int(food["Days_To_Expiry"].dropna().max()) if food["Days_To_Expiry"].notna().any() else 30
        sel_days = st.slider("Days to Expiry (absolute)", min_value=day_min, max_value=day_max if day_max>day_min else day_min+7, value=(day_min, min(day_min+7, day_max)))

    # apply filters to food df
    wf = food.copy()
    if sel_city and sel_city != "All":
        wf = wf[(wf["Location"].str.lower() == sel_city.lower()) | (wf.get("Provider_City", "").str.lower() == sel_city.lower())]
    if sel_provider and sel_provider != "All":
        # find provider id by name
        inv_map = {v:k for k,v in prov_map.items()}
        pid = inv_map.get(sel_provider, None)
        if pid is not None:
            wf = wf[wf["Provider_ID"] == pid]
        else:
            # maybe provider selection was ID string
            try:
                pid_int = int(sel_provider)
                wf = wf[wf["Provider_ID"] == pid_int]
            except Exception:
                pass
    if sel_food_type and sel_food_type != "All":
        wf = wf[wf["Food_Type"] == sel_food_type]
    if "Days_To_Expiry" in wf.columns:
        wf = wf[(wf["Days_To_Expiry"].notna()) & (wf["Days_To_Expiry"].astype("Int64") >= sel_days[0]) & (wf["Days_To_Expiry"].astype("Int64") <= sel_days[1])]

    # KPI row
    kp1, kp2, kp3, kp4 = st.columns(4)
    kp1.metric("Providers", int(run_sql("SELECT COUNT(*) as c FROM Providers")["c"].iloc[0]) if not providers.empty else 0)
    kp2.metric("Receivers", int(run_sql("SELECT COUNT(*) as c FROM Receivers")["c"].iloc[0]) if not receivers.empty else 0)
    kp3.metric("Total Food Quantity (filtered)", int(wf["Quantity"].sum()) if "Quantity" in wf.columns else 0)
    kp4.metric("Total Claims", int(run_sql("SELECT COUNT(*) as c FROM Claims")["c"].iloc[0]) if not claims.empty else 0)

    st.markdown("---")

    # Top providers chart: ensure numeric and no malformed columns
    prov_merge = wf.merge(providers[["Provider_ID","Name"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name"})
    prov_merge["Quantity"] = pd.to_numeric(prov_merge.get("Quantity", 0), errors="coerce").fillna(0)
    top_providers = prov_merge.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(12)
    st.subheader("Top Providers by Donated Quantity (filtered)")
    if not top_providers.empty:
        ch = alt.Chart(top_providers).mark_bar().encode(
            x=alt.X("Quantity:Q", title="Quantity"),
            y=alt.Y("Provider_Name:N", sort='-x'),
            tooltip=["Provider_Name","Quantity"]
        ).properties(height=360)
        st.altair_chart(ch, use_container_width=True)
    else:
        st.info("No data for top providers under current filters.")

    # Claims status distribution
    st.subheader("Claims Status Distribution")
    if not claims.empty and "Status" in claims.columns:
        status_df = claims.groupby("Status", as_index=False).size().reset_index(name="Count") if False else claims["Status"].value_counts().reset_index().rename(columns={"index":"Status","Status":"Count"})
        # display as bar and pie
        colA, colB = st.columns(2)
        with colA:
            st.write("Status - Bar")
            st.altair_chart(alt.Chart(status_df).mark_bar().encode(x="Status:N", y="Count:Q", tooltip=["Status","Count"]), use_container_width=True)
        with colB:
            st.write("Status - Pie")
            st.altair_chart(alt.Chart(status_df).mark_arc().encode(theta="Count:Q", color="Status:N", tooltip=["Status","Count"]), use_container_width=True)
    else:
        st.info("No claims status data.")

    st.markdown("---")
    st.subheader("Listings matching filters")
    show_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Provider_ID","Food_Type","Meal_Type","Days_To_Expiry"] if c in wf.columns]
    display_df = wf[show_cols].sort_values("Days_To_Expiry", na_position="last")
    st.dataframe(display_df, use_container_width=True)

# -----------------------
# PAGE: Donations Analysis
# -----------------------
elif page == "Donations Analysis":
    st.header("Donations Analysis (EDA)")

    if food.empty:
        st.warning("No Food_Listings data.")
        st.stop()

    f = food.copy()
    f["Expiry_Date"] = pd.to_datetime(f["Expiry_Date"], errors="coerce")
    f["YearMonth"] = f["Expiry_Date"].dt.to_period("M").astype(str).fillna("Unknown")

    st.subheader("Monthly Quantity Listed")
    monthly = f.groupby("YearMonth", as_index=False)["Quantity"].sum().sort_values("YearMonth")
    st.altair_chart(alt.Chart(monthly).mark_line(point=True).encode(x="YearMonth:N", y="Quantity:Q", tooltip=["YearMonth","Quantity"]), use_container_width=True)

    st.subheader("Food Type Distribution (by Quantity)")
    ft = f.groupby("Food_Type", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
    st.altair_chart(alt.Chart(ft).mark_bar().encode(x="Quantity:Q", y=alt.Y("Food_Type:N", sort="-x"), tooltip=["Food_Type","Quantity"]), use_container_width=True)

    st.subheader("Meal Type Share")
    mt = f.groupby("Meal_Type", as_index=False)["Quantity"].sum()
    st.altair_chart(alt.Chart(mt).mark_arc().encode(theta="Quantity:Q", color="Meal_Type:N", tooltip=["Meal_Type","Quantity"]), use_container_width=True)

# -----------------------
# PAGE: Providers Insights
# -----------------------
elif page == "Providers Insights":
    st.header("Providers Insights")

    if providers.empty or food.empty:
        st.warning("Providers or Food_Listings missing.")
        st.stop()

    pf = food.merge(providers[["Provider_ID","Name","City","Type"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Type":"Provider_Type"})
    # ensure Quantity numeric
    pf["Quantity"] = pd.to_numeric(pf.get("Quantity",0), errors="coerce").fillna(0)

    st.subheader("Top Providers (by Quantity)")
    topP = pf.groupby("Provider_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    st.altair_chart(alt.Chart(topP).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Name:N", sort="-x"), tooltip=["Provider_Name","Quantity"]), use_container_width=True)

    st.subheader("Provider Type Contribution")
    if "Provider_Type" in pf.columns:
        pt = pf.groupby("Provider_Type", as_index=False)["Quantity"].sum()
        st.altair_chart(alt.Chart(pt).mark_bar().encode(x="Quantity:Q", y=alt.Y("Provider_Type:N", sort="-x"), tooltip=["Provider_Type","Quantity"]), use_container_width=True)
    else:
        st.info("No Provider_Type column available.")

    st.subheader("Providers Contact List")
    contact_html = make_contact_html(providers, name_col="Name", contact_col="Contact", id_col="Provider_ID") if not providers.empty else ""
    st.write(contact_html, unsafe_allow_html=True)

# -----------------------
# PAGE: Receivers Insights
# -----------------------
elif page == "Receivers Insights":
    st.header("Receivers Insights")

    if receivers.empty or claims.empty or food.empty:
        st.warning("Receivers, Claims, or Food_Listings missing.")
        st.stop()

    cf = claims.merge(receivers[["Receiver_ID","Name","City","Contact"]], on="Receiver_ID", how="left").merge(
        food[["Food_ID","Quantity","Meal_Type","Food_Type","Location"]], on="Food_ID", how="left"
    ).rename(columns={"Name":"Receiver_Name"})

    cf["Quantity"] = pd.to_numeric(cf.get("Quantity",0), errors="coerce").fillna(0)

    st.subheader("Top Receivers by Claimed Quantity")
    r1 = cf.groupby("Receiver_Name", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False).head(20)
    st.altair_chart(alt.Chart(r1).mark_bar().encode(x="Quantity:Q", y=alt.Y("Receiver_Name:N", sort="-x"), tooltip=["Receiver_Name","Quantity"]), use_container_width=True)

    st.subheader("Receiver Cities – Claims Count")
    r2 = cf.groupby("City", as_index=False)["Receiver_ID"].count().rename(columns={"Receiver_ID":"Claims"})
    st.altair_chart(alt.Chart(r2).mark_bar().encode(x="Claims:Q", y=alt.Y("City:N", sort="-x"), tooltip=["City","Claims"]), use_container_width=True)

    st.subheader("Receivers Contact List")
    rhtml = make_contact_html(receivers, name_col="Name", contact_col="Contact", id_col="Receiver_ID")
    st.write(rhtml, unsafe_allow_html=True)

# -----------------------
# PAGE: Wastage & Expiry
# -----------------------
elif page == "Wastage & Expiry":
    st.header("Wastage & Expiry Analysis")

    if food.empty:
        st.warning("Food_Listings missing.")
        st.stop()

    f = food.copy()
    f["Expiry_Date"] = pd.to_datetime(f["Expiry_Date"], errors="coerce")
    f["Days_To_Expiry"] = (f["Expiry_Date"].dt.normalize() - pd.to_datetime(date.today())).dt.days.abs().astype("Int64")

    st.subheader("Quantity by Days to Expiry (absolute)")
    dte = f.groupby("Days_To_Expiry", as_index=False)["Quantity"].sum().sort_values("Days_To_Expiry")
    st.altair_chart(alt.Chart(dte).mark_bar().encode(x="Days_To_Expiry:Q", y="Quantity:Q", tooltip=["Days_To_Expiry","Quantity"]), use_container_width=True)

    st.subheader("Expired Listings")
    expired = f[pd.to_datetime(f["Expiry_Date"], errors="coerce") < pd.to_datetime(date.today())]
    if not expired.empty:
        show_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Food_Type","Meal_Type","Days_To_Expiry"] if c in expired.columns]
        st.dataframe(expired[show_cols].sort_values("Expiry_Date"), use_container_width=True)
    else:
        st.info("No expired listings.")

# -----------------------
# PAGE: Filter Food (search + contact)
# -----------------------
elif page == "Filter Food":
    st.header("Filter Food Donations")

    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers table missing.")
        st.stop()

    ff = food.merge(providers[["Provider_ID","Name","Contact"]], on="Provider_ID", how="left").rename(columns={"Name":"Provider_Name","Contact":"Provider_Contact"})
    cities = ["All"] + sorted(ff["Location"].dropna().unique().tolist())
    provs = ["All"] + sorted(ff["Provider_Name"].dropna().unique().tolist())
    ftypes = ["All"] + sorted(ff["Food_Type"].dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    sel_city = col1.selectbox("City", cities)
    sel_prov = col2.selectbox("Provider", provs)
    sel_ft = col3.selectbox("Food Type", ftypes)

    res = ff.copy()
    if sel_city != "All":
        res = res[res["Location"] == sel_city]
    if sel_prov != "All":
        res = res[res["Provider_Name"] == sel_prov]
    if sel_ft != "All":
        res = res[res["Food_Type"] == sel_ft]

    if res.empty:
        st.info("No matching listings.")
    else:
        # create a safe contact column and show DataFrame normally
        res = res.assign(Provider_Contact = res["Provider_Contact"].fillna(""))
        display_cols = [c for c in ["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Provider_Name","Food_Type","Meal_Type","Provider_Contact"] if c in res.columns]
        st.dataframe(res[display_cols].sort_values("Expiry_Date"), use_container_width=True)

        st.markdown("**Contact links:**")
        # show a list of contact links (phone or mailto)
        for _, row in res[['Provider_Name','Provider_Contact']].drop_duplicates().iterrows():
            contact = str(row.get("Provider_Contact","")).strip()
            if contact:
                if "@" in contact:
                    st.markdown(f"- **{row['Provider_Name']}** — [Email]({f'mailto:{contact}'})")
                else:
                    st.markdown(f"- **{row['Provider_Name']}** — [Call]({f'tel:{contact}'})")
            else:
                st.markdown(f"- **{row['Provider_Name']}** — (no contact)")

# -----------------------
# PAGE: Queries
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

    q = st.selectbox("Select query", list(QUERIES.keys()))
    st.code(QUERIES[q], language="sql")
    params = None
    if q.startswith("Q3"):
        city = st.text_input("City (case-insensitive)").strip()
        if city:
            params = (city,)
        else:
            st.info("Enter city for Q3")
    if not q.startswith("Q3") or params:
        out = run_sql(QUERIES[q], params)
        if out.empty:
            st.info("No results")
        else:
            st.dataframe(out, use_container_width=True)
            st.download_button("Download CSV", out.to_csv(index=False).encode("utf-8"), file_name=f"{q.replace(' ','_')}.csv")

# -----------------------
# PAGE: CRUD
# -----------------------
elif page == "CRUD":
    st.header("CRUD (Create / Update / Delete)")
    table = st.selectbox("Select table", ["Providers","Receivers","Food_Listings","Claims"])
    if not table_exists(table):
        st.warning(f"Table {table} not found in DB.")
        st.stop()
    df = run_sql(f"SELECT * FROM {table}")
    st.subheader("Existing records")
    st.dataframe(df, use_container_width=True)

    st.markdown("### ➕ Add record")
    # derive columns
    cols = df.columns.tolist() if not df.empty else []
    # fallback skeletons
    fallback = {
        "Providers": ["Name","Type","Address","City","Contact"],
        "Receivers": ["Name","Type","City","Contact"],
        "Food_Listings": ["Food_Name","Quantity","Expiry_Date","Provider_ID","Provider_Type","Location","Food_Type","Meal_Type"],
        "Claims": ["Food_ID","Receiver_ID","Status","Timestamp"],
    }
    if not cols:
        cols = fallback.get(table, [])
    add_vals = {}
    pk_like = {c for c in cols if c.lower().endswith("id") and c.lower() in {"provider_id","receiver_id","food_id","claim_id"}}
    for c in cols:
        if c in pk_like:
            st.text(f"{c} (optional / autoincrement)")
            continue
        if c.lower().endswith("date") or c.lower() == "timestamp":
            d = st.date_input(c, value=date.today(), key=f"add_{c}")
            add_vals[c] = d.isoformat()
        elif c.lower() == "quantity":
            add_vals[c] = st.number_input(c, value=1, min_value=0, key=f"add_{c}")
        else:
            add_vals[c] = st.text_input(c, key=f"add_{c}")
    if st.button("Add"):
        if add_vals:
            cols_ins = ", ".join(add_vals.keys())
            placeholders = ", ".join(["?"]*len(add_vals))
            ok = exec_sql(f"INSERT INTO {table} ({cols_ins}) VALUES ({placeholders})", tuple(add_vals.values()))
            if ok: st.success("Record added")

    st.markdown("---")
    if not df.empty:
        st.subheader("✏️ Update record")
        pk = df.columns[0]
        sel = st.selectbox(f"Select {pk}", df[pk].tolist())
        row = df[df[pk]==sel].iloc[0].to_dict()
        upd = {}
        for c in df.columns:
            if c == pk:
                st.caption(f"{pk} (primary key): {sel}")
                continue
            upd[c] = st.text_input(c, value=str(row[c]), key=f"upd_{c}")
        if st.button("Update"):
            set_clause = ", ".join([f"{k}=?" for k in upd.keys()])
            ok = exec_sql(f"UPDATE {table} SET {set_clause} WHERE {pk} = ?", tuple(upd.values()) + (sel,))
            if ok: st.success("Updated")

    st.markdown("---")
    if not df.empty:
        st.subheader("🗑️ Delete record")
        pk = df.columns[0]
        did = st.selectbox(f"Select {pk} to delete", df[pk].tolist(), key="delid")
        if st.button("Delete"):
            ok = exec_sql(f"DELETE FROM {table} WHERE {pk} = ?", (did,))
            if ok: st.success("Deleted")

# -----------------------
# PAGE: Data download
# -----------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for t in ["Providers","Receivers","Food_Listings","Claims"]:
        st.subheader(t)
        if table_exists(t):
            d = run_sql(f"SELECT * FROM {t}")
            st.dataframe(d, use_container_width=True)
            st.download_button(f"Download {t}.csv", d.to_csv(index=False).encode("utf-8"), file_name=f"{t}.csv")
        else:
            st.info(f"{t} missing in DB.")

# -----------------------
# PAGE: About
# -----------------------
elif page == "About":
    st.header("About")
    st.markdown("""
    **Local Food Wastage Management System** — Streamlit app for redistributing surplus food.
    - Dashboard with interactive filters & EDA
    - CRUD and SQL queries
    - Contact providers / receivers directly
    """)
