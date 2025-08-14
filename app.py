import os
import sqlite3
from datetime import date
from typing import Tuple, Optional

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

# -----------------------
# Page Config and Styling
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
# Paths & Config Maps
# -----------------------
DB_PATH = "food_wastage.db"
CSV_MAP = {
    "Providers": "providers_data.csv",
    "Receivers": "receivers_data.csv",
    "Food_Listings": "food_listings_data.csv",
    "Claims": "claims_data.csv",
}
# ✅ Defines correct primary keys for each table for safe CRUD operations.
PRIMARY_KEYS = {
    "Providers": "Provider_ID",
    "Receivers": "Receiver_ID",
    "Food_Listings": "Food_ID",
    "Claims": "Claim_ID",
}

# -----------------------
# Database Helper Functions
# -----------------------
@st.cache_resource
def get_conn(path: str = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(path, check_same_thread=False)

def ensure_db_from_csvs(conn: sqlite3.Connection) -> Tuple[bool, str]:
    missing_files = [f for f in CSV_MAP.values() if not os.path.exists(f)]
    if missing_files:
        return False, f"Missing CSV files: {', '.join(missing_files)}"
    try:
        for table, csvfile in CSV_MAP.items():
            df = pd.read_csv(csvfile, dtype=str)
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": "", "None": ""})
            df.to_sql(table, conn, index=False, if_exists="replace")
        conn.commit()
        return True, "Database created from CSVs."
    except Exception as e:
        return False, str(e)

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", conn, params=(name,))
        return not df.empty
    except Exception:
        return False

def run_sql(conn: sqlite3.Connection, sql: str, params: Optional[Tuple]=None) -> pd.DataFrame:
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

def exec_sql(conn: sqlite3.Connection, sql: str, params: Optional[Tuple]=None) -> bool:
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"DB execution error: {e}")
        return False

# -----------------------
# Initialize DB
# -----------------------
if not os.path.exists(DB_PATH):
    tmp_conn = sqlite3.connect(DB_PATH)
    ok, msg = ensure_db_from_csvs(tmp_conn)
    tmp_conn.close()
    if not ok:
        st.warning(f"Could not create DB from CSVs: {msg}")

conn = get_conn()

# -----------------------
# Load Tables
# -----------------------
@st.cache_data
def load_tables() -> dict:
    tables_dict = {}
    for table_name in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        if table_exists(conn, table_name):
            df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
            df.columns = df.columns.str.strip()
            for c in df.select_dtypes(include=["object"]).columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": "", "None": ""})
            tables_dict[table_name] = df
        else:
            tables_dict[table_name] = pd.DataFrame()
    return tables_dict

tables = load_tables()
providers = tables["Providers"]
receivers = tables["Receivers"]
food = tables["Food_Listings"]
claims = tables["Claims"]

# -----------------------
# Data Cleaning
# -----------------------
def safe_dt(series):
    return pd.to_datetime(series, errors='coerce')

def add_days_to_expiry(df):
    if df.empty or "Expiry_Date" not in df.columns:
        return df
    df = df.copy()
    df["Expiry_Date"] = safe_dt(df["Expiry_Date"])
    today = pd.to_datetime(date.today())
    # ✅ FIX: Removed .abs() to correctly show negative days for expired items.
    df["Days_To_Expiry"] = (df["Expiry_Date"] - today).dt.days
    df["Days_To_Expiry"] = df["Days_To_Expiry"].astype("Int64")
    return df

food = add_days_to_expiry(food)
if "Quantity" in food.columns:
    food["Quantity"] = pd.to_numeric(food["Quantity"], errors='coerce').fillna(0)
if "Quantity" in claims.columns:
    claims["Quantity"] = pd.to_numeric(claims["Quantity"], errors='coerce').fillna(0)

# -----------------------
# Header & Logo
# -----------------------
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None

c1, c2, c3 = st.columns([1, 6, 1])
with c1:
    if left_img:
        st.image(left_img, width=80)
with c2:
    st.markdown(
        "<div style='text-align:center'><h1 style='margin:0'>🌿 Local Food Wastage Management System</h1><div class='small-muted'>Interactive dashboard · SQL queries · CRUD</div></div>",
        unsafe_allow_html=True,
    )
with c3:
    if right_img:
        st.image(right_img, width=70)
st.markdown("---")

# -----------------------
# Navigation
# -----------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Donations Explorer", "Queries", "CRUD", "Data", "About"])

# Global filters
with st.sidebar.expander("Global filters", expanded=False):
    # City filter
    city_candidates = set()
    for df, col in [(providers, "City"), (receivers, "City"), (food, "Location")]:
        if not df.empty and col in df.columns:
            city_candidates.update(df[col].dropna().astype(str).unique())
    city_list = ["All"] + sorted([c for c in city_candidates if c])
    sel_city = st.selectbox("City", city_list, index=0)

    # Provider filter
    prov_list = ["All"]
    if not providers.empty and "Name" in providers.columns:
        prov_list += sorted(providers["Name"].dropna().astype(str).unique())
    sel_provider = st.selectbox("Provider", prov_list, index=0)

    # Food Type filter
    ft_list = ["All"]
    if not food.empty and "Food_Type" in food.columns:
        ft_list += sorted(food["Food_Type"].dropna().astype(str).unique())
    sel_food_type = st.selectbox("Food Type", ft_list, index=0)

    # Date range filter
    min_date_val, max_date_val = None, None
    all_dates = []
    if "Expiry_Date" in food.columns:
        all_dates.extend(pd.to_datetime(food["Expiry_Date"], errors='coerce').dropna())
    if "Timestamp" in claims.columns:
        all_dates.extend(pd.to_datetime(claims["Timestamp"], errors='coerce').dropna())
    
    if all_dates:
        min_date_val = min(all_dates).date()
        max_date_val = max(all_dates).date()
    else:
        min_date_val, max_date_val = date.today(), date.today()

    sel_date_range = st.date_input("Date range (uses expiry or claim timestamps)", [min_date_val, max_date_val])


# Helper to apply filters
def apply_filters(food_df, claims_df):
    f = food_df.copy()
    c = claims_df.copy()

    # Filter by city
    if sel_city != "All":
        cond_loc = f.get("Location", pd.Series()).astype(str).str.lower() == sel_city.lower()
        if "Provider_ID" in f.columns and not providers.empty and "Provider_ID" in providers.columns:
            prov_map = providers[["Provider_ID", "City"]].drop_duplicates()
            prov_map["Provider_ID"] = prov_map["Provider_ID"].astype(str)
            f = f.merge(prov_map, on="Provider_ID", how="left", suffixes=("", "_prov"))
            cond_prov = f.get("City_prov", pd.Series()).astype(str).str.lower() == sel_city.lower()
            f = f[cond_loc | cond_prov]
            f = f.drop(columns=[col for col in f.columns if col.endswith("_prov")], errors='ignore')
        else:
            f = f[cond_loc]
        if "Food_ID" in c.columns:
            c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]

    # Filter by provider
    if sel_provider != "All" and "Provider_ID" in f.columns:
        if "Name" in providers.columns:
            match = providers[providers["Name"].astype(str) == sel_provider]
            if not match.empty and "Provider_ID" in match.columns:
                ids = match["Provider_ID"].astype(str).tolist()
                f = f[f["Provider_ID"].astype(str).isin(ids)]
                if "Food_ID" in c.columns:
                    c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]

    # Filter by food type
    if sel_food_type != "All" and "Food_Type" in f.columns:
        f = f[f["Food_Type"].astype(str) == sel_food_type]
        if "Food_ID" in c.columns:
            c = c[c["Food_ID"].astype(str).isin(f["Food_ID"].astype(str).unique())]

    # Date range filter
    if len(sel_date_range) == 2:
        start_d, end_d = sel_date_range
        if "Expiry_Date" in f.columns:
            f["Expiry_Date_dt"] = safe_dt(f["Expiry_Date"])
            f = f[((f["Expiry_Date_dt"].dt.date >= start_d) & (f["Expiry_Date_dt"].dt.date <= end_d)) | (f["Expiry_Date_dt"].isna())]
            f = f.drop(columns=["Expiry_Date_dt"], errors='ignore')
        if "Timestamp" in c.columns:
            c["Timestamp_dt"] = safe_dt(c["Timestamp"])
            c = c[((c["Timestamp_dt"].dt.date >= start_d) & (c["Timestamp_dt"].dt.date <= end_d)) | (c["Timestamp_dt"].isna())]
            c = c.drop(columns=["Timestamp_dt"], errors='ignore')
    return f, c

# -----------------------
# Main Pages
# -----------------------
if page == "Dashboard":
    st.header("Dashboard — Interactive Analytics")
    f_filtered, c_filtered = apply_filters(food, claims)

    st.subheader("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    total_providers = int(providers.shape[0]) if not providers.empty else 0
    total_receivers = int(receivers.shape[0]) if not receivers.empty else 0
    total_food_qty = int(f_filtered["Quantity"].sum()) if "Quantity" in f_filtered.columns else 0
    total_claims = int(c_filtered.shape[0]) if not c_filtered.empty else 0
    col1.metric("Total Providers", total_providers)
    col2.metric("Total Receivers", total_receivers)
    col3.metric("Filtered Food Quantity", total_food_qty)
    col4.metric("Filtered Claims", total_claims)

    st.markdown("---")

    st.subheader("Visualizations")
    colA, colB = st.columns(2)
    
    with colA:
        st.write("Food Quantity by Type")
        if not f_filtered.empty and "Food_Type" in f_filtered.columns:
            chart_data = f_filtered.groupby("Food_Type")["Quantity"].sum().reset_index()
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('Food_Type', sort='-y', title='Food Type'),
                y=alt.Y('Quantity', title='Total Quantity'),
                tooltip=['Food_Type', 'Quantity']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No data to display for food quantity by type.")

    with colB:
        st.write("Claims Over Time")
        if not c_filtered.empty and "Timestamp" in c_filtered.columns:
            c_filtered['Claim_Date'] = pd.to_datetime(c_filtered['Timestamp']).dt.date
            chart_data = c_filtered.groupby('Claim_Date').size().reset_index(name='count')
            chart = alt.Chart(chart_data).mark_line(point=True).encode(
                x=alt.X('Claim_Date', title='Date'),
                y=alt.Y('count', title='Number of Claims'),
                tooltip=['Claim_Date', 'count']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No data to display for claims over time.")

elif page == "Donations Explorer":
    st.header("Donations Explorer — Search, Filter, and Contact")
    if food.empty or providers.empty:
        st.warning("Food_Listings or Providers table missing or empty.")
    else:
        merged = food.merge(providers[["Provider_ID", "Name", "Contact"]], on="Provider_ID", how="left").rename(
            columns={"Name": "Provider_Name", "Contact": "Provider_Contact"}
        )

        col1, col2, col3 = st.columns([1, 1, 1])
        city_opts = ["All"] + sorted(merged.get("Location", pd.Series()).dropna().astype(str).unique().tolist())
        prov_opts = ["All"] + sorted(merged.get("Provider_Name", pd.Series()).dropna().astype(str).unique().tolist())
        ft_opts = ["All"] + sorted(merged.get("Food_Type", pd.Series()).dropna().astype(str).unique().tolist())

        sel_city_e = col1.selectbox("Filter by City", city_opts, index=0, key="exp_city")
        sel_provider_e = col2.selectbox("Filter by Provider", prov_opts, index=0, key="exp_prov")
        sel_ft_e = col3.selectbox("Filter by Food Type", ft_opts, index=0, key="exp_ft")

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
            display_cols = [c for c in ["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Days_To_Expiry", "Location", "Provider_Name", "Provider_Contact", "Food_Type", "Meal_Type"] if c in res.columns]
            st.dataframe(res[display_cols].sort_values("Days_To_Expiry", na_position="last"), use_container_width=True)
            st.markdown("#### Contact Details for Matched Providers")
            for _, r in res[["Provider_Name", "Provider_Contact"]].drop_duplicates().iterrows():
                contact = r.get("Provider_Contact", "")
                name = r.get("Provider_Name", "(no name)")
                if contact and "@" in str(contact):
                    st.markdown(f"- **{name}**: [{contact}](mailto:{contact})")
                elif contact:
                    st.markdown(f"- **{name}**: {contact}")

# ✅ FIX: This page is no longer blank. The query logic has been moved here.
elif page == "Queries":
    st.header("Database Queries")
    st.markdown("Run predefined SQL queries directly against the database.")
    queries = {
        "Q1: Providers & Receivers per City": """
            WITH ProviderCounts AS (
                SELECT City, COUNT(Provider_ID) AS Providers_Count
                FROM Providers GROUP BY City
            ),
            ReceiverCounts AS (
                SELECT City, COUNT(Receiver_ID) AS Receivers_Count
                FROM Receivers GROUP BY City
            )
            SELECT
                t.City,
                IFNULL(p.Providers_Count, 0) AS Providers_Count,
                IFNULL(r.Receivers_Count, 0) AS Receivers_Count
            FROM
                (SELECT DISTINCT City FROM Providers UNION SELECT DISTINCT City FROM Receivers) t
            LEFT JOIN ProviderCounts p ON t.City = p.City
            LEFT JOIN ReceiverCounts r ON t.City = r.City;
        """,
        "Q2: Top Provider Types by Quantity": """
            SELECT p.Type, SUM(f.Quantity) AS Total_Quantity
            FROM Food_Listings f
            JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.Type
            ORDER BY Total_Quantity DESC;
        """,
        "Q3: Contact info of Providers in a City": """
            SELECT Name, Type, City, Contact FROM Providers WHERE LOWER(City) = LOWER(?);
        """,
        "Q4: Receivers with Most Claims": """
            SELECT r.Name, r.City, COUNT(c.Claim_ID) AS Claims_Count
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID, r.Name, r.City
            ORDER BY Claims_Count DESC;
        """,
        "Q5: Total Quantity of All Food Listed": "SELECT IFNULL(SUM(Quantity), 0) AS Total_Food_Quantity FROM Food_Listings;",
        "Q6: Food Listings by Food_Type": """
            SELECT Food_Type, SUM(Quantity) AS Total_Quantity FROM Food_Listings
            GROUP BY Food_Type ORDER BY Total_Quantity DESC;
        """,
        "Q7: Food Expiry Summary (Past)": """
            SELECT strftime('%Y-%m', Expiry_Date) AS Month, SUM(Quantity) AS Total_Expired
            FROM Food_Listings WHERE Expiry_Date < date('now')
            GROUP BY Month ORDER BY Month DESC;
        """,
        "Q8: Top 10 Food Items by Quantity": """
            SELECT Food_Name, SUM(Quantity) AS Total_Quantity FROM Food_Listings
            GROUP BY Food_Name ORDER BY Total_Quantity DESC LIMIT 10;
        """,
        "Q9: Claims per Receiver": """
            SELECT r.Name, COUNT(c.Claim_ID) AS Claims_Count
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID, r.Name ORDER BY Claims_Count DESC;
        """,
        "Q10: Providers with Expired Food": """
            SELECT p.Name, p.Type, p.City, COUNT(f.Food_ID) AS Expired_Listings
            FROM Providers p JOIN Food_Listings f ON p.Provider_ID = f.Provider_ID
            WHERE f.Expiry_Date < date('now')
            GROUP BY p.Provider_ID, p.Name ORDER BY Expired_Listings DESC;
        """,
        "Q11: Food Listings Expiring in Next 7 Days": """
            SELECT Food_Name, Expiry_Date, Quantity, Location
            FROM Food_Listings
            WHERE Expiry_Date BETWEEN date('now') AND date('now', '+7 days')
            ORDER BY Expiry_Date ASC;
        """,
        "Q12: Food Quantity by Location": """
            SELECT Location, SUM(Quantity) AS Total_Quantity FROM Food_Listings
            GROUP BY Location ORDER BY Total_Quantity DESC;
        """,
        "Q13: Top 10 Receivers by Claims": """
            SELECT r.Name, COUNT(c.Claim_ID) AS Claims_Count
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID, r.Name ORDER BY Claims_Count DESC LIMIT 10;
        """,
        "Q14: Provider Type Counts": """
            SELECT Type, COUNT(*) AS Count FROM Providers
            GROUP BY Type ORDER BY Count DESC;
        """,
        "Q15: Food Listings by Meal Type": """
            SELECT Meal_Type, SUM(Quantity) AS Total_Quantity FROM Food_Listings
            GROUP BY Meal_Type ORDER BY Total_Quantity DESC;
        """,
    }

    q_choice = st.selectbox("Select a Query to Run", list(queries.keys()))
    selected_sql = queries[q_choice]
    params = None

    if q_choice == "Q3: Contact info of Providers in a City":
        city_inp = st.text_input("Enter city name (case-insensitive)")
        if not city_inp:
            st.info("Please enter a city to run this query.")
            st.stop()
        params = (city_inp,)

    st.code(selected_sql, language='sql')
    if st.button(f"Run Query: {q_choice}"):
        df_q = run_sql(conn, selected_sql, params)
        if df_q.empty:
            st.info("Query executed, but no results were returned.")
        else:
            st.dataframe(df_q, use_container_width=True)
            st.download_button(
                "Download as CSV",
                df_q.to_csv(index=False).encode('utf-8'),
                file_name=f"{q_choice.replace(':', '').replace(' ', '_')}.csv",
                mime="text/csv",
            )

elif page == "CRUD":
    st.header("CRUD — Add, Update, or Delete Records")
    table_name = st.selectbox("Select Table", list(PRIMARY_KEYS.keys()))
    
    if not table_exists(conn, table_name):
        st.warning(f"Table '{table_name}' does not exist in the database.")
    else:
        df = run_sql(conn, f"SELECT * FROM {table_name}")
        pk = PRIMARY_KEYS[table_name]

        if pk not in df.columns:
            st.error(f"Configuration Error: Primary key '{pk}' not found in table '{table_name}'. Update/Delete operations are disabled.")
        else:
            st.subheader(f"Manage Records in '{table_name}'")
            st.dataframe(df.head(200), use_container_width=True)

            # --- Add Record ---
            with st.expander("Add a New Record"):
                columns = df.columns.tolist() if not df.empty else []
                add_vals = {}
                with st.form("add_form", clear_on_submit=True):
                    for col in columns:
                        if col == pk:
                             st.caption(f"{pk} will be auto-generated or should be unique.")
                             add_vals[col] = st.text_input(f"{col} (Primary Key)", key=f"add_{col}")
                        elif "date" in col.lower() or "timestamp" in col.lower():
                            add_vals[col] = st.date_input(f"{col}", value=date.today(), key=f"add_{col}").isoformat()
                        elif col.lower() == "quantity":
                             # ✅ FIX: Using 'col' as the label, not undefined 'c'.
                            add_vals[col] = st.number_input(col, min_value=0, value=1, key=f"add_{col}")
                        else:
                             # ✅ FIX: Using 'col' as the label, not undefined 'c'.
                            add_vals[col] = st.text_input(col, key=f"add_{col}")

                    submitted = st.form_submit_button("Add Record")
                    if submitted:
                        cols_str = ", ".join(add_vals.keys())
                        placeholders = ", ".join(["?"] * len(add_vals))
                        values = tuple(v if v != "" else None for v in add_vals.values())
                        success = exec_sql(conn, f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})", values)
                        if success:
                            st.success("Record added successfully.")
                            st.cache_data.clear() # Clear cache to reload data
                            st.rerun() # ✅ FIX: Using modern st.rerun()
                        else:
                            st.error("Failed to add record. Check for unique key violations.")

            # --- Update & Delete ---
            st.markdown("---")
            st.subheader("Update or Delete an Existing Record")
            id_list = df[pk].astype(str).tolist()
            if not id_list:
                 st.warning(f"No records in '{table_name}' to update or delete.")
            else:
                sel_id_for_mod = st.selectbox(f"Select Record by '{pk}' to Modify/Delete", id_list, key="mod_id")
                
                # --- Update Record ---
                with st.expander("Update Selected Record"):
                    row_to_update = df[df[pk].astype(str) == sel_id_for_mod].iloc[0]
                    update_vals = {}
                    for col in df.columns:
                        if col == pk:
                            continue
                        update_vals[col] = st.text_input(col, value=str(row_to_update[col]), key=f"upd_{col}")

                    if st.button("Update Record"):
                        set_clause = ", ".join([f'"{k}" = ?' for k in update_vals])
                        params = tuple(update_vals.values()) + (sel_id_for_mod,)
                        success = exec_sql(conn, f"UPDATE {table_name} SET {set_clause} WHERE \"{pk}\" = ?", params)
                        if success:
                            st.success("Record updated.")
                            st.cache_data.clear()
                            st.rerun() # ✅ FIX: Using modern st.rerun()

                # --- Delete Record ---
                with st.expander("Delete Selected Record"):
                    st.warning(f"You are about to delete the record where **{pk} = {sel_id_for_mod}**.")
                    if st.button("Confirm and Delete Record", type="primary"):
                        success = exec_sql(conn, f"DELETE FROM {table_name} WHERE \"{pk}\" = ?", (sel_id_for_mod,))
                        if success:
                            st.success("Record deleted.")
                            st.cache_data.clear()
                            st.rerun() # ✅ FIX: Using modern st.rerun()

elif page == "Data":
    st.header("Raw Data Tables & Downloads")
    for t in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        if table_exists(conn, t):
            with st.expander(f"Data for: {t}", expanded=(t=="Providers")):
                df_raw = run_sql(conn, f"SELECT * FROM {t}")
                st.dataframe(df_raw, use_container_width=True)
                st.download_button(
                    f"Download {t}.csv", 
                    df_raw.to_csv(index=False).encode('utf-8'), 
                    file_name=f"{t}.csv",
                    mime="text/csv"
                )
        else:
            st.warning(f"Table '{t}' does not exist.")

elif page == "About":
    st.header("About This System")
    st.markdown(
        """
        **The Local Food Wastage Management System is an interactive tool designed to connect food providers with receivers, aiming to reduce local food waste.**

        ### Core Features:
        - **Dashboard**: Get a high-level overview of operations with key metrics and visualizations.
        - **Donations Explorer**: Actively search for available food donations, filter by location or food type, and find contact information for providers.
        - **Queries**: Run powerful, predefined SQL queries against the database to extract specific insights. Results can be downloaded as CSV files.
        - **CRUD Interface**: Directly manage the database records for all tables (Create, Read, Update, Delete).
        - **Data Viewer**: Inspect the raw data in each table and download it for offline analysis.

        ### Data Source:
        The application is powered by a `SQLite` database (`food_wastage.db`). If the database file is not found, it will be automatically created from the following CSV files if they are present in the root directory:
        - `providers_data.csv`
        - `receivers_data.csv`
        - `food_listings_data.csv`
        - `claims_data.csv`
        """
    )
