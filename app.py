# app.py (UPDATED)
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

# Creative Green & Beige CSS
st.markdown(
    """
    <style>
      :root {
        --beige: #f7f4ef;
        --soft-green: #eaf3ea;
        --accent-green: #83b489;
        --dark-green: #2f6f3a;
      }

      /* Backgrounds */
      .reportview-container { background: var(--beige); }
      .stApp { background: var(--beige); }

      /* Global font color */
      html, body, [class*="css"] {
        color: var(--dark-green) !important;
      }

      /* Header styling */
      header {
        background: linear-gradient(90deg, var(--soft-green), #f0f7f0);
        padding: 12px;
        border-radius: 10px;
      }

      /* Buttons */
      .stButton>button {
        background-color: var(--accent-green);
        color: white !important;
        border-radius: 8px;
      }

      /* Card */
      .card {
        background: white;
        border-radius: 12px;
        padding: 14px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.06);
      }

      /* KPI text */
      .kpi {
        font-size: 20px;
        color: var(--dark-green);
        font-weight: 700;
      }

      /* Muted text stays grey */
      .small-muted {
        color: #6b6b6b !important;
        font-size: 12px;
      }

      /* Logo row alignment */
      .logo-row {
        display: flex;
        align-items: center;
        gap: 12px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# DB Helpers
# -----------------------
DB_PATH = "food_wastage.db"

@st.cache_resource
def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    # enable row factory for nicer column access if needed
    return conn

def initialize_db_from_csv(conn):
    """
    Create DB from CSVs in repo root if DB missing.
    Looks for: providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv
    """
    required_files = ["providers_data.csv", "receivers_data.csv", "food_listings_data.csv", "claims_data.csv"]
    missing = [f for f in required_files if not os.path.exists(f)]
    if missing:
        return False, f"CSV files missing in repo root: {', '.join(missing)}"

    # load CSVs & perform mild cleaning then write to SQLite
    providers = pd.read_csv("providers_data.csv", dtype=str)
    receivers = pd.read_csv("receivers_data.csv", dtype=str)
    food = pd.read_csv("food_listings_data.csv", dtype=str)
    claims = pd.read_csv("claims_data.csv", dtype=str)

    # Basic cleaning: trim strings and replace literal 'nan'/'None'
    for df in (providers, receivers, food, claims):
        for c in df.select_dtypes(include=['object']).columns:
            df[c] = df[c].astype(str).str.strip().replace({'nan':'', 'None':''})

    # Normalize casing for City/Location columns if present
    if "City" in providers.columns:
        providers["City"] = providers["City"].str.title().fillna("Unknown City")
    if "City" in receivers.columns:
        receivers["City"] = receivers["City"].str.title().fillna("Unknown City")
    if "Location" in food.columns:
        food["Location"] = food["Location"].str.title().fillna("Unknown Location")

    # Convert numeric columns where present
    for col in ["Provider_ID","Receiver_ID","Food_ID","Quantity","Claim_ID"]:
        for df in (providers, receivers, food, claims):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

    # Parse dates if present
    if "Expiry_Date" in food.columns:
        food["Expiry_Date"] = pd.to_datetime(food["Expiry_Date"], errors="coerce")
    if "Timestamp" in claims.columns:
        claims["Timestamp"] = pd.to_datetime(claims["Timestamp"], errors="coerce")

    # Save cleaned tables into sqlite (replace if exists)
    providers.to_sql("Providers", conn, index=False, if_exists="replace")
    receivers.to_sql("Receivers", conn, index=False, if_exists="replace")
    food.to_sql("Food_Listings", conn, index=False, if_exists="replace")
    claims.to_sql("Claims", conn, index=False, if_exists="replace")

    try:
        conn.commit()
    except Exception as e:
        return False, f"Error committing DB: {e}"

    return True, "DB created from CSVs."

# If DB not present, try to build from repo-root CSVs
if not os.path.exists(DB_PATH):
    temp_conn = sqlite3.connect(DB_PATH)
    ok, msg = initialize_db_from_csv(temp_conn)
    temp_conn.close()
    if not ok:
        st.warning("Database not found and couldn't build from CSVs: " + msg)
        st.info("Place cleaned CSVs in the repo root (providers_data.csv, receivers_data.csv, food_listings_data.csv, claims_data.csv) and refresh.")
    else:
        st.success("Database created from CSVs.")

# Acquire connection for app runtime
conn = get_conn(DB_PATH)

# -----------------------
# Header with logos
# -----------------------
LOGO_LEFT = "logo.png"        # replace with your left logo filename if different
LOGO_RIGHT = "recycle.png"    # replace with your right icon

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
    st.markdown("<div style='text-align:center'><h1 style='margin:0; color:#2f6f3a;'>🌿 Local Food Wastage Management System</h1><div class='small-muted'>Reduce waste — connect surplus food providers with people in need.</div></div>", unsafe_allow_html=True)
with c3:
    if right_img:
        st.image(right_img, width=80)

st.markdown("---")

# -----------------------
# SQL Queries dictionary (13 core + 2 extras)
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
               CAST(julianday(date(f.Expiry_Date)) - julianday(date('now')) AS INTEGER) AS days_to_expiry
        FROM Food_Listings f
        LEFT JOIN Providers p ON f.Provider_ID = p.Provider_ID
        WHERE date(f.Expiry_Date) BETWEEN date('now') AND date('now','+3 days')
        ORDER BY days_to_expiry ASC;
        """
    ),
}

# -----------------------
# Utility to run queries (uses cached conn)
# -----------------------
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

# -----------------------
# Sidebar & Navigation
# -----------------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Queries", "CRUD", "Data", "About"])

# Small helper to check table existence
def table_exists(name):
    try:
        t = pd.read_sql(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';", conn)
        return not t.empty
    except Exception:
        return False

# -----------------------
# Dashboard Page
# -----------------------
if page == "Dashboard":
    st.header("Dashboard")
    # Filters
    city_options = ["All"]
    if table_exists("Providers"):
        try:
            provs = run_sql("SELECT DISTINCT City FROM Providers;")["City"].dropna().tolist()
            city_options += sorted([c for c in provs if c])
        except Exception:
            pass
    selected_city = st.selectbox("Filter by City", city_options)

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    if table_exists("Providers"):
        total_providers = int(run_sql("SELECT COUNT(*) AS cnt FROM Providers;").iloc[0,0])
    else:
        total_providers = 0
    if table_exists("Receivers"):
        total_receivers = int(run_sql("SELECT COUNT(*) AS cnt FROM Receivers;").iloc[0,0])
    else:
        total_receivers = 0
    if table_exists("Food_Listings"):
        total_food_qty = int(run_sql("SELECT IFNULL(SUM(Quantity),0) AS total FROM Food_Listings;").iloc[0,0])
    else:
        total_food_qty = 0
    if table_exists("Claims"):
        total_claims = int(run_sql("SELECT COUNT(*) AS cnt FROM Claims;").iloc[0,0])
    else:
        total_claims = 0

    col1.metric("Providers", total_providers)
    col2.metric("Receivers", total_receivers)
    col3.metric("Total Food Quantity", total_food_qty)
    col4.metric("Total Claims", total_claims)

    st.markdown("### Top providers by donated quantity")
    if table_exists("Food_Listings") and table_exists("Providers"):
        top_providers = run_sql(QUERIES["Q13: Total quantity donated by each provider"])
        if not top_providers.empty:
            chart = alt.Chart(top_providers.head(10)).mark_bar().encode(
                x=alt.X("Total_Donated:Q", title="Total Donated"),
                y=alt.Y("Name:N", sort='-x', title="Provider")
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No donation data available.")
    else:
        st.info("Food listings or providers table missing.")

    st.markdown("### Claims status distribution")
    if table_exists("Claims"):
        status_df = run_sql(QUERIES["Q10: Claims status distribution (%)"])
        if not status_df.empty:
            pie = alt.Chart(status_df).mark_arc().encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color("Status:N")
            )
            st.altair_chart(pie, use_container_width=True)
            st.table(status_df)
        else:
            st.info("No claims data.")
    else:
        st.info("Claims table missing.")

    st.markdown("### Listings expiring soon")
    if table_exists("Food_Listings"):
        expiring = run_sql(QUERIES["Q15: Listings expiring within next 3 days"])
        if not expiring.empty:
            st.dataframe(expiring)
        else:
            st.info("No listings expiring in the next 3 days.")
    else:
        st.info("Food_Listings table missing.")

# -----------------------
# Queries Page
# -----------------------
elif page == "Queries":
    st.header("SQL Queries & Outputs")
    st.markdown("Select a query to run. You will see the question, SQL, and the output (downloadable).")
    q_list = list(QUERIES.keys())
    choice = st.selectbox("Choose query", q_list)

    st.markdown("**Question:**")
    st.write(choice)

    st.markdown("**SQL:**")
    st.code(QUERIES[choice])

    params = None
    if choice.startswith("Q3"):
        city = st.text_input("Enter city name for provider contacts (case-insensitive)", value="")
        if city:
            params = (city,)

    df = run_sql(QUERIES[choice], params)
    if df.empty:
        st.warning("No results for this query. Check your data or filters.")
    else:
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), file_name=f"{choice.replace(' ','_')}.csv")

# -----------------------
# CRUD Page
# -----------------------
elif page == "CRUD":
    st.header("CRUD Operations")
    st.markdown("Add / Update / Delete items. Changes write directly to the SQLite DB in repo root.")
    # Add Provider
    with st.expander("➕ Add new provider"):
        with st.form("add_provider"):
            pname = st.text_input("Name")
            ptype = st.text_input("Type")
            paddr = st.text_area("Address")
            pcity = st.text_input("City")
            pcontact = st.text_input("Contact")
            submit = st.form_submit_button("Add Provider")
            if submit:
                try:
                    conn.execute("INSERT INTO Providers (Name, Type, Address, City, Contact) VALUES (?,?,?,?,?)",
                                 (pname, ptype, paddr, pcity, pcontact))
                    conn.commit()
                    st.success("Provider added.")
                except Exception as e:
                    st.error("Error adding provider: " + str(e))

    # Add Food Listing
    with st.expander("➕ Add new food listing"):
        with st.form("add_listing"):
            fname = st.text_input("Food name")
            fqty = st.number_input("Quantity", min_value=1, value=1)
            fexp = st.date_input("Expiry date", value=datetime.today())
            provider_id = st.text_input("Provider_ID (existing)")
            fptype = st.text_input("Provider_Type")
            floc = st.text_input("Location (City)")
            ftype = st.selectbox("Food type", ["Vegetarian","Non-Vegetarian","Vegan","Unknown"])
            mtype = st.selectbox("Meal type", ["Breakfast","Lunch","Dinner","Snacks","Other"])
            submit2 = st.form_submit_button("Add Listing")
            if submit2:
                try:
                    conn.execute(
                        "INSERT INTO Food_Listings (Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type) VALUES (?,?,?,?,?,?,?,?)",
                        (fname, int(fqty), fexp.isoformat(), int(provider_id) if provider_id else None, fptype, floc, ftype, mtype)
                    )
                    conn.commit()
                    st.success("Food listing added.")
                except Exception as e:
                    st.error("Error adding listing: " + str(e))

    # Create Claim
    with st.expander("➕ Create claim (Pending)"):
        with st.form("make_claim"):
            claim_food_id = st.text_input("Food_ID to claim")
            claim_receiver_id = st.text_input("Receiver_ID")
            submit_claim = st.form_submit_button("Create Claim (Pending)")
            if submit_claim:
                try:
                    timestamp = datetime.now().isoformat()
                    conn.execute("INSERT INTO Claims (Food_ID, Receiver_ID, Status, Timestamp) VALUES (?,?,?,?)",
                                 (int(claim_food_id), int(claim_receiver_id), "Pending", timestamp))
                    conn.commit()
                    st.success("Claim created with status Pending.")
                except Exception as e:
                    st.error("Error creating claim: " + str(e))

    st.markdown("### Update / Delete Listings & Claims")
    listings = run_sql("SELECT Food_ID, Food_Name, Quantity, Expiry_Date, Location FROM Food_Listings ORDER BY Food_ID DESC LIMIT 200;")
    st.dataframe(listings)
    with st.form("update_delete"):
        sel_id = st.text_input("Food_ID to update/delete")
        new_qty = st.number_input("New quantity (leave 0 to skip)", value=0)
        do_delete = st.checkbox("Delete this Food listing")
        claim_id_for_status = st.text_input("Claim_ID to update status (if updating status)")
        new_status = st.text_input("New status for claim (e.g., Completed, Cancelled)")
        do_update = st.form_submit_button("Apply changes")
        if do_update:
            try:
                if do_delete and sel_id:
                    conn.execute("DELETE FROM Food_Listings WHERE Food_ID=?", (int(sel_id),))
                    conn.commit()
                    st.success("Listing deleted.")
                else:
                    if new_qty > 0 and sel_id:
                        conn.execute("UPDATE Food_Listings SET Quantity=? WHERE Food_ID=?", (int(new_qty), int(sel_id)))
                        conn.commit()
                        st.success("Quantity updated.")
                    if claim_id_for_status and new_status:
                        conn.execute("UPDATE Claims SET Status=? WHERE Claim_ID=?", (new_status, int(claim_id_for_status)))
                        conn.commit()
                        st.success("Claim status updated.")
            except Exception as e:
                st.error("Error applying changes: " + str(e))

# -----------------------
# Data Page
# -----------------------
elif page == "Data":
    st.header("Raw Data & Downloads")
    for tbl in ["Providers","Receivers","Food_Listings","Claims"]:
        st.subheader(tbl)
        if table_exists(tbl):
            df = run_sql(f"SELECT * FROM {tbl} LIMIT 500;")
            st.dataframe(df)
            st.download_button(f"Download {tbl}.csv", df.to_csv(index=False).encode('utf-8'), file_name=f"{tbl}.csv")
        else:
            st.info(f"No table named `{tbl}` found in DB.")

# -----------------------
# About Page
# -----------------------
elif page == "About":
    st.header("About this app")
    st.markdown("""
    **Local Food Wastage Management System** — Streamlit app for redistributing surplus food.
    - Filters & queries powered by SQLite.
    - CRUD operations to add listings, providers, and claims.
    - Visual analytics for data-driven distribution.
    """)
    st.markdown("**Project deliverables:** Cleaned DB, 15 SQL queries, Streamlit app with CRUD and visualizations.")
    st.markdown("**Next steps:** Add map geolocation (lat/lon), add authentication, deploy to Streamlit Cloud.")

# -----------------------
# End
# -----------------------
