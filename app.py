import os
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, timedelta
from PIL import Image

# ---------------
# CONFIG + THEME
# ---------------
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

st.markdown(r"""
<style>
:root {
    --beige: #E8E2D0;  /* darker beige for contrast */
    --dark-green: #2E5339;
    --accent-green: #4F8F4F;
    --text-dark: #1A1A1A;
}
.stApp {
    background-color: var(--beige);
    color: var(--dark-green);
    font-family: 'Segoe UI', sans-serif;
}
h1, h2, h3, h4, h5, h6 {
    color: var(--dark-green) !important;
    font-weight: 700;
}
section[data-testid="stSidebar"] {
    background-color: var(--dark-green);
    color: white;
}
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2 {
    color: white !important;
}
.block-container {
    background: var(--beige);
    padding: 1rem;
}
.css-1d391kg, .css-12oz5g7 {
    background-color: white;
    padding: 1rem;
    border-radius: 10px;
    box-shadow: 0px 3px 8px rgba(0,0,0,0.15);
    color: var(--dark-green);
}
.dataframe th {
    background-color: var(--accent-green);
    color: white !important;
}
.dataframe td {
    background-color: white;
    color: var(--dark-green) !important;
}
.stButton>button {
    background-color: var(--accent-green);
    color: white;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-weight: bold;
    border: none;
}
.stButton>button:hover {
    background-color: var(--dark-green);
    color: white;
}
</style>
""", unsafe_allow_html=True)


# ---------------
# DB Setup
# ---------------
DB_PATH = "food_wastage.db"

def initialize_db_from_csv(conn):
    required_files = ["providers_data.csv", "receivers_data.csv", "food_listings_data.csv", "claims_data.csv"]
    missing = [f for f in required_files if not os.path.exists(f)]
    if missing:
        st.warning(f"Missing CSV files: {', '.join(missing)}. Place them in repo root and refresh.")
        return False

    try:
        providers = pd.read_csv("providers_data.csv", dtype=str)
        receivers = pd.read_csv("receivers_data.csv", dtype=str)
        food = pd.read_csv("food_listings_data.csv", dtype=str)
        claims = pd.read_csv("claims_data.csv", dtype=str)

        # Clean string columns
        for df in (providers, receivers, food, claims):
            for c in df.select_dtypes(include=['object']).columns:
                df[c] = df[c].str.strip().replace({'nan':'', 'None':''})

        # Normalize City/Location casing
        if "City" in providers.columns:
            providers["City"] = providers["City"].str.title().fillna("Unknown City")
        if "City" in receivers.columns:
            receivers["City"] = receivers["City"].str.title().fillna("Unknown City")
        if "Location" in food.columns:
            food["Location"] = food["Location"].str.title().fillna("Unknown Location")

        # Convert numeric columns
        for col in ["Provider_ID","Receiver_ID","Food_ID","Quantity","Claim_ID"]:
            for df in (providers, receivers, food, claims):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

        # Parse dates
        if "Expiry_Date" in food.columns:
            food["Expiry_Date"] = pd.to_datetime(food["Expiry_Date"], errors="coerce")
        if "Timestamp" in claims.columns:
            claims["Timestamp"] = pd.to_datetime(claims["Timestamp"], errors="coerce")

        # Write tables
        providers.to_sql("Providers", conn, index=False, if_exists="replace")
        receivers.to_sql("Receivers", conn, index=False, if_exists="replace")
        food.to_sql("Food_Listings", conn, index=False, if_exists="replace")
        claims.to_sql("Claims", conn, index=False, if_exists="replace")

        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error initializing DB from CSV: {e}")
        return False

# If DB missing, create from CSVs
if not os.path.exists(DB_PATH):
    conn_tmp = sqlite3.connect(DB_PATH)
    ok = initialize_db_from_csv(conn_tmp)
    conn_tmp.close()
    if ok:
        st.success("Database created from CSV files.")
    else:
        st.warning("Could not create DB. Place all CSV files in repo root and refresh.")

# Connect to DB
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

def table_exists(name):
    try:
        df = pd.read_sql(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';", conn)
        return not df.empty
    except:
        return False

def run_query(sql, params=None):
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        else:
            return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

# ---------------
# SQL Queries
# ---------------
QUERIES = {
    "Q1: Providers & Receivers per City": (
        """
        SELECT City, SUM(Providers) AS Providers_Count, SUM(Receivers) AS Receivers_Count
        FROM (
            SELECT City, COUNT(Provider_ID) AS Providers, 0 AS Receivers FROM Providers GROUP BY City
            UNION ALL
            SELECT City, 0 AS Providers, COUNT(Receiver_ID) AS Receivers FROM Receivers GROUP BY City
        )
        GROUP BY City
        ORDER BY Providers_Count DESC;
        """
    ),
    "Q2: Top contributing provider type (by quantity)": (
        """
        SELECT Provider_Type, SUM(Quantity) AS Total_Quantity
        FROM Food_Listings
        GROUP BY Provider_Type
        ORDER BY Total_Quantity DESC;
        """
    ),
    "Q3: Contact info of providers in a city (param)": (
        """
        SELECT Name, Type, City, Contact
        FROM Providers
        WHERE LOWER(City) = LOWER(?);
        """
    ),
    "Q4: Receivers with most claims": (
        """
        SELECT r.Receiver_ID, r.Name, r.City, COUNT(c.Claim_ID) AS Total_Claims
        FROM Claims c
        JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
        GROUP BY r.Receiver_ID, r.Name
        ORDER BY Total_Claims DESC;
        """
    ),
    "Q5: Total quantity of food available": (
        """
        SELECT IFNULL(SUM(Quantity),0) AS Total_Quantity FROM Food_Listings;
        """
    ),
    "Q6: City with highest number of listings": (
        """
        SELECT Location AS City, COUNT(*) AS Listings_Count
        FROM Food_Listings
        GROUP BY Location
        ORDER BY Listings_Count DESC
        LIMIT 10;
        """
    ),
    "Q7: Most commonly available food types": (
        """
        SELECT Food_Type, COUNT(*) AS Occurrences, SUM(Quantity) AS Total_Quantity
        FROM Food_Listings
        GROUP BY Food_Type
        ORDER BY Occurrences DESC;
        """
    ),
    "Q8: Claims made per food item": (
        """
        SELECT f.Food_ID, f.Food_Name, COUNT(c.Claim_ID) AS Claims_Count
        FROM Food_Listings f
        LEFT JOIN Claims c ON f.Food_ID = c.Food_ID
        GROUP BY f.Food_ID, f.Food_Name
        ORDER BY Claims_Count DESC;
        """
    ),
    "Q9: Provider with highest successful claims": (
        """
        SELECT p.Provider_ID, p.Name, p.City, COUNT(c.Claim_ID) AS Completed_Claims
        FROM Claims c
        JOIN Food_Listings f ON c.Food_ID = f.Food_ID
        JOIN Providers p ON f.Provider_ID = p.Provider_ID
        WHERE LOWER(c.Status) = 'completed'
        GROUP BY p.Provider_ID, p.Name
        ORDER BY Completed_Claims DESC
        LIMIT 10;
        """
    ),
    "Q10: Claims status distribution (%)": (
        """
        SELECT Status, COUNT(*) AS Count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Claims),2) AS Percentage
        FROM Claims
        GROUP BY Status;
        """
    ),
    "Q11: Average quantity claimed per receiver": (
        """
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
        """
    ),
    "Q12: Most claimed meal type": (
        """
        SELECT f.Meal_Type, COUNT(c.Claim_ID) AS Claims_Count, SUM(f.Quantity) AS Total_Quantity
        FROM Claims c
        JOIN Food_Listings f ON c.Food_ID = f.Food_ID
        GROUP BY f.Meal_Type
        ORDER BY Claims_Count DESC;
        """
    ),
    "Q13: Total quantity donated by each provider": (
        """
        SELECT p.Provider_ID, p.Name, p.City, SUM(f.Quantity) AS Total_Donated
        FROM Food_Listings f
        JOIN Providers p ON f.Provider_ID = p.Provider_ID
        GROUP BY p.Provider_ID, p.Name
        ORDER BY Total_Donated DESC
        LIMIT 50;
        """
    ),
    "Q14: Expired food listings": (
        """
        SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location
        FROM Food_Listings f
        LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
        WHERE date(f.Expiry_Date) < date('now')
        ORDER BY f.Expiry_Date ASC;
        """
    ),
    "Q15: Listings expiring within next 3 days": (
        """
        SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location,
               ABS(CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER)) AS days_to_expiry
        FROM Food_Listings f
        LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
        WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now','+3 days')
        ORDER BY days_to_expiry ASC;
        """
    ),
}

# ---------------
# Load Images for header
# ---------------
LOGO_LEFT = "logo.png"
LOGO_RIGHT = "recycle.png"

left_img = None
right_img = None
try:
    if os.path.exists(LOGO_LEFT):
        left_img = Image.open(LOGO_LEFT)
    if os.path.exists(LOGO_RIGHT):
        right_img = Image.open(LOGO_RIGHT)
except:
    pass

c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img:
        st.image(left_img, width=100)
with c2:
    st.markdown("<div style='text-align:center'><h1 style='margin:0; color:#2f6f3a;'>🌿 Local Food Wastage Management System</h1><div class='small-muted'>Reduce waste — connect surplus food providers with people in need.</div></div>", unsafe_allow_html=True)
with c3:
    if right_img:
        st.image(right_img, width=80)
st.markdown("---")

# ---------------
# Sidebar & Navigation
# ---------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Queries", "CRUD", "Data", "EDA", "About"])

# ---------------
# DASHBOARD
# ---------------
if page == "Dashboard":
    st.header("Dashboard")

    # Basic KPIs
    total_providers = run_query("SELECT COUNT(*) as count FROM Providers").iloc[0,0] if table_exists("Providers") else 0
    total_receivers = run_query("SELECT COUNT(*) as count FROM Receivers").iloc[0,0] if table_exists("Receivers") else 0
    total_food_qty = run_query("SELECT IFNULL(SUM(Quantity),0) as total FROM Food_Listings").iloc[0,0] if table_exists("Food_Listings") else 0
    total_claims = run_query("SELECT COUNT(*) as count FROM Claims").iloc[0,0] if table_exists("Claims") else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Providers", total_providers)
    col2.metric("Receivers", total_receivers)
    col3.metric("Total Food Quantity", total_food_qty)
    col4.metric("Total Claims", total_claims)

    st.markdown("### Top Providers by Donated Quantity")
    if table_exists("Food_Listings") and table_exists("Providers"):
        df_top_prov = run_query(QUERIES["Q13: Total quantity donated by each provider"])
        if not df_top_prov.empty:
            chart = alt.Chart(df_top_prov.head(10)).mark_bar().encode(
                x=alt.X("Total_Donated:Q", title="Total Donated"),
                y=alt.Y("Name:N", sort='-x', title="Provider"),
                tooltip=["Name", "Total_Donated"]
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No donation data available.")

    st.markdown("### Claims Status Distribution")
    if table_exists("Claims"):
        df_status = run_query(QUERIES["Q10: Claims status distribution (%)"])
        if not df_status.empty:
            chart = alt.Chart(df_status).mark_arc().encode(
                theta=alt.Theta("Count:
