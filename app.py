import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
import os
from datetime import datetime
from PIL import Image

# -----------------------
# CONFIG + THEME STYLING
# -----------------------
st.set_page_config(page_title="Local Food Wastage System", layout="wide", page_icon="🌿")

st.markdown("""
    <style>
    :root {
        --beige: #E8E2D0;  /* darker beige for better contrast */
        --dark-green: #2E5339;
        --accent-green: #4F8F4F;
        --text-dark: #1A1A1A; /* near-black for readability */
    }
    .stApp {
        background-color: var(--beige);
        color: var(--accent-green);
        font-family: 'Segoe UI', sans-serif;
    }
    h1, h2, h3, h4, h5, h6 {
        color: var(--dark-green) !important;
        font-weight: 700;
    }
    section[data-testid="stSidebar"] {
        background-color: var(--dark-green);
        color: var(--beige);
    }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2 {
        color: var(--beige) !important;
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
        color: var(--accent-green);
        font-size: 16px;
    }
    .dataframe th {
        background-color: var(--accent-green);
        color: var(--beige) !important;
        font-size: 14px;
    }
    .dataframe td {
        background-color: white;
        color: var(--dark-green) !important;
        font-size: 13px;
    }
    .stButton>button {
        background-color: var(--accent-green);
        color: var(--beige);
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        border: none;
        font-size: 15px;
    }
    .stButton>button:hover {
        background-color: var(--dark-green);
        color: var(--beige);
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------
# DB Helpers
# -----------------------
DB_PATH = "food_wastage.db"

@st.cache_resource
def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    return conn

def initialize_db_from_csv(conn):
    required_files = ["providers_data.csv", "receivers_data.csv", "food_listings_data.csv", "claims_data.csv"]
    missing = [f for f in required_files if not os.path.exists(f)]
    if missing:
        return False, f"CSV files missing in repo root: {', '.join(missing)}"

    providers = pd.read_csv("providers_data.csv", dtype=str)
    receivers = pd.read_csv("receivers_data.csv", dtype=str)
    food = pd.read_csv("food_listings_data.csv", dtype=str)
    claims = pd.read_csv("claims_data.csv", dtype=str)

    for df in (providers, receivers, food, claims):
        for c in df.select_dtypes(include=['object']).columns:
            df[c] = df[c].astype(str).str.strip().replace({'nan':'', 'None':''})

    if "City" in providers.columns:
        providers["City"] = providers["City"].str.title().fillna("Unknown City")
    if "City" in receivers.columns:
        receivers["City"] = receivers["City"].str.title().fillna("Unknown City")
    if "Location" in food.columns:
        food["Location"] = food["Location"].str.title().fillna("Unknown Location")

    for col in ["Provider_ID","Receiver_ID","Food_ID","Quantity","Claim_ID"]:
        for df in (providers, receivers, food, claims):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

    if "Expiry_Date" in food.columns:
        food["Expiry_Date"] = pd.to_datetime(food["Expiry_Date"], errors="coerce")
    if "Timestamp" in claims.columns:
        claims["Timestamp"] = pd.to_datetime(claims["Timestamp"], errors="coerce")

    providers.to_sql("Providers", conn, index=False, if_exists="replace")
    receivers.to_sql("Receivers", conn, index=False, if_exists="replace")
    food.to_sql("Food_Listings", conn, index=False, if_exists="replace")
    claims.to_sql("Claims", conn, index=False, if_exists="replace")

    try:
        conn.commit()
    except Exception as e:
        return False, f"Error committing DB: {e}"

    return True, "DB created from CSVs."

if not os.path.exists(DB_PATH):
    temp_conn = sqlite3.connect(DB_PATH)
    ok, msg = initialize_db_from_csv(temp_conn)
    temp_conn.close()
    if not ok:
        st.warning("Database not found and couldn't build from CSVs: " + msg)
        st.info("Place cleaned CSVs in the repo root (providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv) and refresh.")
    else:
        st.success("Database created from CSVs.")

conn = get_conn(DB_PATH)

# -----------------------
# Header with logos
# -----------------------
LOGO_LEFT = "logo.png"
LOGO_RIGHT = "recycle.png"

left_img = None
right_img = None
try:
    if os.path.exists(LOGO_LEFT):
        left_img = Image.open(LOGO_LEFT)
    if os.path.exists(LOGO_RIGHT):
        right_img = Image.open(LOGO_RIGHT)
except Exception:
    left_img = None
    right_img = None

c1, c2, c3 = st.columns([1, 6, 1])
with c1:
    if left_img:
        st.image(left_img, width=100)
with c2:
    st.markdown(
        "<div style='text-align:center'><h1 style='margin:0; color:#2f6f3a;'>🌿 Local Food Wastage Management System</h1>"
        "<div class='small-muted'>Reduce waste — connect surplus food providers with people in need.</div></div>", 
        unsafe_allow_html=True
    )
with c3:
    if right_img:
        st.image(right_img, width=80)

st.markdown("---")

# -----------------------
# SQL Queries dictionary
# -----------------------
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

def run_sql(sql, params=None):
    try:
        if params:
            df = pd.read_sql(sql, conn, params=params)
        else:
            df = pd.read_sql(sql, conn)
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()
    return df

st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Queries", "CRUD", "Data", "About"])

def table_exists(name):
    try:
        t = pd.read_sql(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';", conn)
        return not t.empty
    except Exception:
        return False

# -----------------------
# Dashboard Page (Updated)
# -----------------------
if page == "Dashboard":
    st.header("Dashboard")

    # Load Food_Listings for filtering
    if table_exists("Food_Listings"):
        food_df = run_sql(
            """
            SELECT Food_ID, Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type
            FROM Food_Listings
            WHERE Expiry_Date IS NOT NULL
            """
        )
        # convert Expiry_Date to datetime
        food_df["Expiry_Date"] = pd.to_datetime(food_df["Expiry_Date"], errors='coerce')

        # Calculate absolute positive days to expiry
        food_df["Days_to_Expiry"] = (food_df["Expiry_Date"] - pd.Timestamp.now().normalize()).dt.days.abs()

        # Filters
        st.markdown("### Filters")

        # Food_Type filter
        food_types = ["All"] + sorted(food_df["Food_Type"].dropna().unique().tolist())
        selected_type = st.selectbox("Filter by Food Type", food_types)

        # Days to expiry slider
        max_days = int(food_df["Days_to_Expiry"].max()) if not food_df.empty else 30
        days_filter = st.slider("Max Days to Expiry", min_value=0, max_value=max_days, value=max_days)

        # Apply filters
        filtered = food_df.copy()
        if selected_type != "All":
            filtered = filtered[filtered["Food_Type"] == selected_type]
        filtered = filtered[filtered["Days_to_Expiry"] <= days_filter]

        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        total_providers = int(run_sql("SELECT COUNT(*) FROM Providers;").iloc[0,0]) if table_exists("Providers") else 0
        total_receivers = int(run_sql("SELECT COUNT(*) FROM Receivers;").iloc[0,0]) if table_exists("Receivers") else 0
        total_quantity = int(run_sql("SELECT IFNULL(SUM(Quantity),0) FROM Food_Listings;").iloc[0,0]) if table_exists("Food_Listings") else 0
        total_claims = int(run_sql("SELECT COUNT(*) FROM Claims;").iloc[0,0]) if table_exists("Claims") else 0

        col1.metric("Providers", total_providers)
        col2.metric("Receivers", total_receivers)
        col3.metric("Total Food Quantity", total_quantity)
        col4.metric("Total Claims", total_claims)

        # Show filtered listings
        st.markdown("### Food Listings Matching Filters")
        if filtered.empty:
            st.info("No food listings match your filters.")
        else:
            st.dataframe(
                filtered[["Food_ID", "Food_Name", "Quantity", "Expiry_Date", "Days_to_Expiry", "Provider_Type", "Location", "Food_Type"]],
                use_container_width=True,
                height=300
            )

        # Chart Type selector for Top Providers
        st.markdown("### Top Providers by Donated Quantity")
        chart_type = st.radio("Select Chart Type", options=["Bar Chart", "Pie Chart"], horizontal=True)

        if table_exists("Food_Listings") and table_exists("Providers"):
            top_providers = run_sql(QUERIES["Q13: Total quantity donated by each provider"])
            if not top_providers.empty:
                top_providers = top_providers.head(10)
                if chart_type == "Bar Chart":
                    bar = alt.Chart(top_providers).mark_bar(color="#4F8F4F").encode(
                        x=alt.X("Total_Donated:Q", title="Total Donated"),
                        y=alt.Y("Name:N", sort='-x', title="Provider"),
                        tooltip=[alt.Tooltip("Name"), alt.Tooltip("Total_Donated")]
                    ).properties(height=350).configure_axis(
                        labelFontSize=14,
                        titleFontSize=16,
                        labelColor="#2E5339",
                        titleColor="#2E5339"
                    ).configure_title(
                        fontSize=20,
                        color="#2E5339"
                    )
                    st.altair_chart(bar, use_container_width=True)
                else:
                    pie = alt.Chart(top_providers).mark_arc().encode(
                        theta=alt.Theta(field="Total_Donated", type="quantitative"),
                        color=alt.Color(field="Name", type="nominal"),
                        tooltip=[alt.Tooltip("Name"), alt.Tooltip("Total_Donated")]
                    ).properties(height=350)
                    st.altair_chart(pie, use_container_width=True)
            else:
                st.info("No donation data available.")
        else:
            st.info("Tables Food_Listings or Providers missing.")

        # Claims Status Distribution chart with type selector
        st.markdown("### Claims Status Distribution")
        claims_chart_type = st.radio("Select Chart Type", options=["Bar Chart", "Pie Chart"], horizontal=True, key="claims_chart_type")

        if table_exists("Claims"):
            claims_status = run_sql(QUERIES["Q10: Claims status distribution (%)"])
            if not claims_status.empty:
                if claims_chart_type == "Bar Chart":
                    bar = alt.Chart(claims_status).mark_bar().encode(
                        x=alt.X("Percentage:Q", title="Percentage (%)"),
                        y=alt.Y("Status:N", sort='-x', title="Status"),
                        color=alt.Color("Status:N", legend=None),
                        tooltip=[alt.Tooltip("Status"), alt.Tooltip("Count"), alt.Tooltip("Percentage", format=".2f")]
                    ).properties(height=300).configure_axis(
                        labelFontSize=14,
                        titleFontSize=16,
                        labelColor="#2E5339",
                        titleColor="#2E5339"
                    )
                    st.altair_chart(bar, use_container_width=True)
                else:
                    pie = alt.Chart(claims_status).mark_arc().encode(
                        theta=alt.Theta(field="Count", type="quantitative"),
                        color=alt.Color("Status:N", legend=None),
                        tooltip=[alt.Tooltip("Status"), alt.Tooltip("Count"), alt.Tooltip("Percentage", format=".2f")]
                    ).properties(height=300)
                    st.altair_chart(pie, use_container_width=True)

                st.table(claims_status.style.set_properties(**{'color': '#4F8F4F', 'font-weight': 'bold'}))
            else:
                st.info("No claims data available.")
        else:
            st.info("Claims table missing.")

    else:
        st.warning("Food_Listings table does not exist.")

# -----------------------
# Queries Page
# -----------------------
elif page == "Queries":
    st.header("SQL Queries & Outputs")
    st.markdown("Select a query to run. You will see the question, SQL, and the output (downloadable).")
    query_names = list(QUERIES.keys())
    selected_query = st.selectbox("Choose query", query_names)

    st.markdown("**Question:**")
    st.markdown(f"<span style='color:#2E5339;font-weight:600'>{selected_query}</span>", unsafe_allow_html=True)

    st.markdown("**SQL:**")
    st.code(QUERIES[selected_query])

    params = None
    if selected_query == "Q3: Contact info of providers in a city (param)":
        city = st.text_input("Enter city name for providers (case-insensitive)", "")
        if city:
            params = (city.strip(),)
        else:
            st.info("Please enter a city name to run this query.")

    if (selected_query != "Q3: Contact info of providers in a city (param)") or params:
        result_df = run_sql(QUERIES[selected_query], params)
        if not result_df.empty:
            st.dataframe(result_df.style.set_properties(**{'color': '#4F8F4F'}), use_container_width=True)
            csv_bytes = result_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv_bytes, file_name=f"{selected_query.replace(' ', '_')}.csv")
        else:
            st.warning("No data found for this query.")

# -----------------------
# CRUD Page (placeholder for your existing CRUD code)
# -----------------------
elif page == "CRUD":
    st.header("CRUD Operations")
    st.markdown("Add / Update / Delete items here. This writes directly to the SQLite DB.")
    # Implement your CRUD interface here as needed, preserving green/beige theme.

# -----------------------
# Data Page (show raw tables)
# -----------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for tbl in ["Providers", "Receivers", "Food_Listings", "Claims"]:
        st.subheader(tbl)
        if table_exists(tbl):
            df = run_sql(f"SELECT * FROM {tbl} LIMIT 500;")
            st.dataframe(df.style.set_properties(**{'color': '#4F8F4F'}), use_container_width=True)
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            st.download_button(f"Download {tbl}.csv", csv_bytes, file_name=f"{tbl}.csv")
        else:
            st.info(f"Table `{tbl}` not found in database.")

# -----------------------
# About Page
# -----------------------
elif page == "About":
    st.header("About this App")
    st.markdown("""
    **Local Food Wastage Management System** — a Streamlit app connecting surplus food providers with people in need.
    
    - Uses SQLite for backend.
    - Interactive filters and visualizations.
    - CRUD operations to manage listings.
    - Designed with accessible green-on-beige styling.
    
    **Next Steps:** Add map integration, authentication, and deployment.
    """)

# -----------------------
# END
# -----------------------
