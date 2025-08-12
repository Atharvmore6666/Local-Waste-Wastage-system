import os
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime
from PIL import Image

# --- Config & Styling ---
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

st.markdown("""
<style>
    :root {
        --beige: #E8E2D0;
        --dark-green: #2E5339;
        --accent-green: #4F8F4F;
    }
    .stApp {
        background-color: var(--beige);
        color: var(--dark-green);
        font-family: 'Segoe UI', sans-serif;
    }
    h1,h2,h3 {
        color: var(--dark-green);
        font-weight: 700;
    }
    section[data-testid="stSidebar"] {
        background-color: var(--dark-green);
        color: white;
    }
    .css-1d391kg, .css-12oz5g7 {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 3px 8px rgba(0,0,0,0.15);
        color: var(--dark-green);
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
    }
</style>
""", unsafe_allow_html=True)

# --- Database Setup ---
DB_PATH = "food_wastage.db"

def load_csvs_to_db(conn):
    csv_files = {
        "Providers": "providers_data.csv",
        "Receivers": "receivers_data.csv",
        "Food_Listings": "food_listings_data.csv",
        "Claims": "claims_data.csv",
    }
    for table, csv_file in csv_files.items():
        if not os.path.exists(csv_file):
            st.error(f"Missing CSV file: {csv_file}. Please add it to repo root.")
            return False
    try:
        for table, csv_file in csv_files.items():
            df = pd.read_csv(csv_file)
            # Strip whitespace
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].str.strip()
            # Convert dates and numeric types explicitly
            if table == "Food_Listings" and "Expiry_Date" in df.columns:
                df["Expiry_Date"] = pd.to_datetime(df["Expiry_Date"], errors='coerce')
            if table == "Claims" and "Timestamp" in df.columns:
                df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')
            df.to_sql(table, conn, index=False, if_exists="replace")
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error loading CSVs to DB: {e}")
        return False

if not os.path.exists(DB_PATH):
    conn_tmp = sqlite3.connect(DB_PATH)
    if load_csvs_to_db(conn_tmp):
        st.success("Database created from CSV files.")
    else:
        st.warning("Failed to create database. Check CSV files.")
    conn_tmp.close()

conn = sqlite3.connect(DB_PATH, check_same_thread=False)

def table_exists(name):
    df = pd.read_sql(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';", conn)
    return not df.empty

def run_query(sql, params=None):
    try:
        if params:
            return pd.read_sql(sql, conn, params=params)
        else:
            return pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

def run_command(sql, params=None):
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

# --- Load images ---
left_img = Image.open("logo.png") if os.path.exists("logo.png") else None
right_img = Image.open("recycle.png") if os.path.exists("recycle.png") else None

# --- Header ---
c1, c2, c3 = st.columns([1,6,1])
with c1:
    if left_img:
        st.image(left_img, width=100)
with c2:
    st.markdown("<h1 style='text-align:center; color:#2E5339;'>🌿 Local Food Wastage Management System</h1>", unsafe_allow_html=True)
with c3:
    if right_img:
        st.image(right_img, width=80)
st.markdown("---")

# --- Sidebar Navigation ---
page = st.sidebar.radio("Navigation", [
    "Dashboard", "Filter Food Donations", "Queries", "CRUD", "About"
])

# --- Dashboard ---
if page == "Dashboard":
    st.header("Dashboard")

    if all(table_exists(t) for t in ["Providers", "Receivers", "Food_Listings", "Claims"]):
        total_providers = run_query("SELECT COUNT(*) AS count FROM Providers").iloc[0,0]
        total_receivers = run_query("SELECT COUNT(*) AS count FROM Receivers").iloc[0,0]
        total_food_qty = run_query("SELECT IFNULL(SUM(Quantity),0) AS total FROM Food_Listings").iloc[0,0]
        total_claims = run_query("SELECT COUNT(*) AS count FROM Claims").iloc[0,0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Providers", total_providers)
        c2.metric("Receivers", total_receivers)
        c3.metric("Total Food Quantity", total_food_qty)
        c4.metric("Total Claims", total_claims)

        st.subheader("Top Providers by Donated Quantity")
        top_providers = run_query("""
            SELECT p.Name, SUM(f.Quantity) AS Total_Donated 
            FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.Name ORDER BY Total_Donated DESC LIMIT 10
        """)
        if not top_providers.empty:
            bar_chart = alt.Chart(top_providers).mark_bar().encode(
                x=alt.X('Total_Donated:Q', title='Quantity Donated'),
                y=alt.Y('Name:N', sort='-x', title='Provider'),
                tooltip=['Name', 'Total_Donated']
            ).properties(height=350)
            st.altair_chart(bar_chart, use_container_width=True)

        st.subheader("Claims Status Distribution")
        claims_status = run_query("""
            SELECT Status, COUNT(*) AS Count 
            FROM Claims GROUP BY Status
        """)
        if not claims_status.empty:
            pie_chart = alt.Chart(claims_status).mark_arc().encode(
                theta=alt.Theta('Count:Q'),
                color=alt.Color('Status:N'),
                tooltip=['Status', 'Count']
            ).properties(width=350, height=350)
            st.altair_chart(pie_chart)
    else:
        st.warning("Database tables are missing. Please check CSV import.")

# --- Filter Food Donations Page ---
elif page == "Filter Food Donations":
    st.header("Filter Food Donations")

    # Load data for filtering
    food_df = run_query("SELECT f.*, p.Name AS Provider_Name, p.Contact AS Provider_Contact FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID")
    if food_df.empty:
        st.warning("No food listings found.")
    else:
        # Filters
        locations = sorted(food_df["Location"].dropna().unique())
        providers = sorted(food_df["Provider_Name"].dropna().unique())
        food_types = sorted(food_df["Food_Type"].dropna().unique())

        sel_location = st.selectbox("Select Location (City)", options=["All"] + locations)
        sel_provider = st.selectbox("Select Provider", options=["All"] + providers)
        sel_food_type = st.selectbox("Select Food Type", options=["All"] + food_types)

        filtered_df = food_df.copy()
        if sel_location != "All":
            filtered_df = filtered_df[filtered_df["Location"] == sel_location]
        if sel_provider != "All":
            filtered_df = filtered_df[filtered_df["Provider_Name"] == sel_provider]
        if sel_food_type != "All":
            filtered_df = filtered_df[filtered_df["Food_Type"] == sel_food_type]

        st.write(f"Showing {len(filtered_df)} matching food listings:")
        if len(filtered_df) > 0:
            st.dataframe(filtered_df[["Food_ID","Food_Name","Quantity","Expiry_Date","Location","Provider_Name","Provider_Contact","Food_Type","Meal_Type"]])

# --- Queries Page ---
elif page == "Queries":
    st.header("Predefined SQL Queries & Insights")

    QUERIES = {
        "1. Providers & Receivers per City": """
            SELECT City, SUM(Providers) AS Providers_Count, SUM(Receivers) AS Receivers_Count
            FROM (
                SELECT City, COUNT(Provider_ID) AS Providers, 0 AS Receivers FROM Providers GROUP BY City
                UNION ALL
                SELECT City, 0 AS Providers, COUNT(Receiver_ID) AS Receivers FROM Receivers GROUP BY City
            )
            GROUP BY City ORDER BY Providers_Count DESC;
        """,
        "2. Top Contributing Provider Type (by quantity)": """
            SELECT Provider_Type, SUM(Quantity) AS Total_Quantity
            FROM Food_Listings
            GROUP BY Provider_Type
            ORDER BY Total_Quantity DESC;
        """,
        "3. Contact Info of Providers in a City": """
            SELECT Name, Type, City, Contact FROM Providers WHERE LOWER(City) = LOWER(?);
        """,
        "4. Receivers with Most Claims": """
            SELECT r.Name, r.City, COUNT(c.Claim_ID) AS Total_Claims
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID, r.Name ORDER BY Total_Claims DESC;
        """,
        "5. Total Quantity of Food Available": """
            SELECT IFNULL(SUM(Quantity),0) AS Total_Quantity FROM Food_Listings;
        """,
        "6. City with Highest Number of Listings": """
            SELECT Location AS City, COUNT(*) AS Listings_Count
            FROM Food_Listings GROUP BY Location ORDER BY Listings_Count DESC LIMIT 10;
        """,
        "7. Most Commonly Available Food Types": """
            SELECT Food_Type, COUNT(*) AS Occurrences, SUM(Quantity) AS Total_Quantity
            FROM Food_Listings GROUP BY Food_Type ORDER BY Occurrences DESC;
        """,
        "8. Claims Made per Food Item": """
            SELECT f.Food_Name, COUNT(c.Claim_ID) AS Claims_Count
            FROM Food_Listings f LEFT JOIN Claims c ON f.Food_ID = c.Food_ID
            GROUP BY f.Food_ID ORDER BY Claims_Count DESC;
        """,
        "9. Provider with Highest Successful Claims": """
            SELECT p.Name, p.City, COUNT(c.Claim_ID) AS Completed_Claims
            FROM Claims c
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE LOWER(c.Status) = 'completed'
            GROUP BY p.Provider_ID ORDER BY Completed_Claims DESC LIMIT 10;
        """,
        "10. Claims Status Distribution (%)": """
            SELECT Status, COUNT(*) AS Count,
                   ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Claims),2) AS Percentage
            FROM Claims GROUP BY Status;
        """,
        "11. Average Quantity Claimed per Receiver": """
            SELECT r.Name, ROUND(AVG(f.Quantity),2) AS Avg_Quantity, SUM(f.Quantity) AS Total_Quantity, COUNT(c.Claim_ID) AS Claim_Count
            FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            GROUP BY r.Receiver_ID ORDER BY Total_Quantity DESC LIMIT 50;
        """,
        "12. Most Claimed Meal Type": """
            SELECT f.Meal_Type, COUNT(c.Claim_ID) AS Claims_Count, SUM(f.Quantity) AS Total_Quantity
            FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            GROUP BY f.Meal_Type ORDER BY Claims_Count DESC;
        """,
        "13. Total Quantity Donated by Each Provider": """
            SELECT p.Name, p.City, SUM(f.Quantity) AS Total_Donated
            FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.Provider_ID ORDER BY Total_Donated DESC LIMIT 50;
        """,
        "14. Expired Food Listings": """
            SELECT f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location
            FROM Food_Listings f LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) < date('now') ORDER BY f.Expiry_Date ASC;
        """,
        "15. Listings Expiring Within Next 3 Days": """
            SELECT f.Food_Name, f.Quantity, f.Expiry_Date, p.Name AS Provider_Name, f.Location,
                   CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER) AS Days_To_Expiry
            FROM Food_Listings f LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
            WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now', '+3 days')
            ORDER BY Days_To_Expiry ASC;
        """,
    }

    selected_query = st.selectbox("Select Query", list(QUERIES.keys()))

    if selected_query:
        sql = QUERIES[selected_query]
        params = None
        # For query 3, get city input
        if selected_query == "3. Contact Info of Providers in a City":
            city = st.text_input("Enter city name").strip()
            if city:
                params = (city,)
            else:
                st.info("Enter city to run this query.")
        if params or selected_query != "3. Contact Info of Providers in a City":
            result_df = run_query(sql, params)
            if not result_df.empty:
                st.dataframe(result_df)
            else:
                st.info("No results found.")

# --- CRUD Page ---
elif page == "CRUD":
    st.header("Manage Records (CRUD Operations)")

    table_options = ["Providers", "Receivers", "Food_Listings", "Claims"]
    selected_table = st.selectbox("Select Table to Manage", table_options)

    if selected_table:
        df = run_query(f"SELECT * FROM {selected_table}")
        st.subheader(f"Existing records in {selected_table}")
        st.dataframe(df)

        st.markdown("---")
        st.subheader(f"Add New Record to {selected_table}")

        def add_record(table):
            # Dynamically create input fields based on table columns
            df_empty = run_query(f"SELECT * FROM {table} LIMIT 0")
            new_data = {}
            for col in df_empty.columns:
                if col.lower() in ["id", "provider_id", "receiver_id", "food_id", "claim_id"]:
                    # For PK, skip or let DB autoincrement if possible
                    continue
                if col.lower().endswith("date") or col.lower() == "timestamp":
                    val = st.date_input(f"{col}", key=f"add_{col}")
                    new_data[col] = val.strftime("%Y-%m-%d")
                else:
                    val = st.text_input(f"{col}", key=f"add_{col}")
                    new_data[col] = val.strip()
            if st.button("Add Record"):
                # Prepare insert SQL
                cols = ", ".join(new_data.keys())
                placeholders = ", ".join("?" for _ in new_data)
                values = tuple(new_data.values())
                sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
                if run_command(sql, values):
                    st.success(f"Record added to {table}")
                else:
                    st.error("Failed to add record.")

        add_record(selected_table)

        st.markdown("---")
        st.subheader(f"Update Record in {selected_table}")

        if not df.empty:
            record_ids = df.iloc[:,0].tolist()
            selected_id = st.selectbox(f"Select {selected_table[:-1]} ID to update", record_ids)
            if selected_id:
                row = df[df.iloc[:,0] == selected_id].iloc[0]
                update_data = {}
                for col in df.columns:
                    if col == df.columns[0]:
                        st.write(f"**{col} (primary key):** {row[col]}")
                        continue
                    val = st.text_input(f"{col}", value=str(row[col]), key=f"upd_{col}")
                    update_data[col] = val.strip()

                if st.button("Update Record"):
                    set_clause = ", ".join(f"{k} = ?" for k in update_data)
                    values = tuple(update_data.values()) + (selected_id,)
                    sql = f"UPDATE {selected_table} SET {set_clause} WHERE {df.columns[0]} = ?"
                    if run_command(sql, values):
                        st.success("Record updated.")
                    else:
                        st.error("Failed to update record.")

        st.markdown("---")
        st.subheader(f"Delete Record from {selected_table}")

        if not df.empty:
            del_id = st.selectbox(f"Select {selected_table[:-1]} ID to delete", record_ids, key="del_select")
            if st.button("Delete Record"):
                sql = f"DELETE FROM {selected_table} WHERE {df.columns[0]} = ?"
                if run_command(sql, (del_id,)):
                    st.success("Record deleted.")
                else:
                    st.error("Failed to delete record.")

# --- About Page ---
elif page == "About":
    st.header("About")
    st.markdown("""
    This Local Food Wastage Management System connects surplus food providers with receivers in need,
    helping reduce food waste and hunger.

    **Features:**  
    - Filter food donations by location, provider, and food type  
    - Contact providers & receivers  
    - Full CRUD operations for all records  
    - 15 SQL-powered analysis queries to gain insights  
    - User-friendly Streamlit interface with interactive charts  

    **Data Source:** CSV files imported to SQLite database.  
    Developed using Streamlit, SQLite, Pandas, Altair.
    """)
