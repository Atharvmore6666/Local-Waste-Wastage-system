import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, date

st.set_page_config(page_title="Local Food Wastage Management System", layout="wide", page_icon="🌿")

# Theme styling
st.markdown("""
<style>
:root {
    --beige: #E8E2D0;
    --dark-green: #2E5339;
    --accent-green: #4F8F4F;
    --text-dark: #1A1A1A;
    --font-base: 16px;
}
.stApp {
    background-color: var(--beige);
    color: var(--text-dark);
    font-family: 'Segoe UI', sans-serif;
    font-size: var(--font-base);
}
h1, h2, h3 {
    color: var(--dark-green) !important;
    font-weight: 700;
}
section[data-testid="stSidebar"] {
    background-color: var(--dark-green);
    color: white;
}
.stButton>button {
    background-color: var(--accent-green);
    color: white;
    border-radius: 8px;
}
.stButton>button:hover {
    background-color: var(--dark-green);
}
</style>
""", unsafe_allow_html=True)

# Database connection
DB_PATH = "food.db"

@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

# Run SQL query helper
def run_query(query, params=()):
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"SQL error: {e}")
        return pd.DataFrame()

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Food Listings CRUD", "Providers CRUD", "Receivers CRUD", "Claims CRUD", "SQL Queries", "EDA", "About"])

# -------------------
# Dashboard page
# -------------------
if page == "Dashboard":
    st.title("🌿 Local Food Wastage Dashboard")

    # KPIs
    total_providers = run_query("SELECT COUNT(*) as count FROM Providers").iloc[0,0]
    total_receivers = run_query("SELECT COUNT(*) as count FROM Receivers").iloc[0,0]
    total_food_items = run_query("SELECT COUNT(*) as count FROM Food_Listings").iloc[0,0]
    total_claims = run_query("SELECT COUNT(*) as count FROM Claims").iloc[0,0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Providers", total_providers)
    col2.metric("Total Receivers", total_receivers)
    col3.metric("Food Listings", total_food_items)
    col4.metric("Claims Made", total_claims)

    st.markdown("---")

    # Food listings by city
    food_by_city = run_query("""
        SELECT Location as City, COUNT(*) as Listings
        FROM Food_Listings
        GROUP BY Location
        ORDER BY Listings DESC
        LIMIT 10
    """)

    chart = alt.Chart(food_by_city).mark_bar(color="#4F8F4F").encode(
        x=alt.X('City:N', sort='-y'),
        y='Listings:Q',
        tooltip=['City', 'Listings']
    ).properties(width=700, height=400, title="Top 10 Cities by Food Listings")

    st.altair_chart(chart, use_container_width=True)

    # Food type distribution
    food_type_dist = run_query("""
        SELECT Food_Type, COUNT(*) as Count
        FROM Food_Listings
        GROUP BY Food_Type
        ORDER BY Count DESC
    """)

    pie = alt.Chart(food_type_dist).mark_arc().encode(
        theta='Count:Q',
        color='Food_Type:N',
        tooltip=['Food_Type', 'Count']
    ).properties(title="Food Type Distribution")

    st.altair_chart(pie, use_container_width=True)

# -------------------
# CRUD: Food Listings
# -------------------
elif page == "Food Listings CRUD":
    st.title("Food Listings - Manage Surplus Food")

    st.subheader("Add New Food Listing")
    with st.form("add_food_form", clear_on_submit=True):
        food_name = st.text_input("Food Name", max_chars=50)
        quantity = st.number_input("Quantity", min_value=1, step=1)
        expiry = st.date_input("Expiry Date", min_value=date.today())
        provider_id = st.number_input("Provider ID", min_value=1, step=1)
        provider_type = st.text_input("Provider Type")
        location = st.text_input("Location (City)")
        food_type = st.selectbox("Food Type", options=["Vegetarian", "Non-Vegetarian", "Vegan", "Other"])
        meal_type = st.selectbox("Meal Type", options=["Breakfast", "Lunch", "Dinner", "Snacks"])

        submitted = st.form_submit_button("Add Food Listing")
        if submitted:
            try:
                query = """
                INSERT INTO Food_Listings (Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(query, (food_name, quantity, expiry.strftime("%Y-%m-%d"), provider_id, provider_type, location, food_type, meal_type))
                conn.commit()
                st.success("Food listing added successfully!")
            except Exception as e:
                st.error(f"Failed to add food listing: {e}")

    st.markdown("---")
    st.subheader("View & Update Food Listings")

    listings = run_query("SELECT * FROM Food_Listings ORDER BY Expiry_Date ASC LIMIT 100")
    selected_id = st.selectbox("Select Food ID to Update/Delete", options=listings["Food_ID"].tolist())

    if selected_id:
        selected_food = listings[listings["Food_ID"] == selected_id].iloc[0]

        with st.form("update_food_form"):
            uf_name = st.text_input("Food Name", value=selected_food["Food_Name"])
            uf_quantity = st.number_input("Quantity", min_value=1, value=int(selected_food["Quantity"]))
            uf_expiry = st.date_input("Expiry Date", value=pd.to_datetime(selected_food["Expiry_Date"]))
            uf_provider_id = st.number_input("Provider ID", min_value=1, value=int(selected_food["Provider_ID"]))
            uf_provider_type = st.text_input("Provider Type", value=selected_food["Provider_Type"])
            uf_location = st.text_input("Location (City)", value=selected_food["Location"])
            uf_food_type = st.selectbox("Food Type", options=["Vegetarian", "Non-Vegetarian", "Vegan", "Other"], index=["Vegetarian", "Non-Vegetarian", "Vegan", "Other"].index(selected_food["Food_Type"]) if selected_food["Food_Type"] in ["Vegetarian", "Non-Vegetarian", "Vegan", "Other"] else 0)
            uf_meal_type = st.selectbox("Meal Type", options=["Breakfast", "Lunch", "Dinner", "Snacks"], index=["Breakfast", "Lunch", "Dinner", "Snacks"].index(selected_food["Meal_Type"]) if selected_food["Meal_Type"] in ["Breakfast", "Lunch", "Dinner", "Snacks"] else 0)

            update_submitted = st.form_submit_button("Update Food Listing")
            if update_submitted:
                try:
                    conn.execute("""
                        UPDATE Food_Listings SET Food_Name=?, Quantity=?, Expiry_Date=?, Provider_ID=?, Provider_Type=?, Location=?, Food_Type=?, Meal_Type=?
                        WHERE Food_ID=?
                    """, (uf_name, uf_quantity, uf_expiry.strftime("%Y-%m-%d"), uf_provider_id, uf_provider_type, uf_location, uf_food_type, uf_meal_type, selected_id))
                    conn.commit()
                    st.success("Food listing updated!")
                except Exception as e:
                    st.error(f"Update failed: {e}")

            if st.button("Delete Food Listing"):
                try:
                    conn.execute("DELETE FROM Food_Listings WHERE Food_ID=?", (selected_id,))
                    conn.commit()
                    st.success("Food listing deleted.")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

# -------------------
# CRUD: Providers
# -------------------
elif page == "Providers CRUD":
    st.title("Food Providers - Manage Providers")

    st.subheader("Add New Provider")
    with st.form("add_provider_form", clear_on_submit=True):
        pname = st.text_input("Provider Name")
        ptype = st.text_input("Provider Type (Restaurant, Grocery, etc.)")
        paddress = st.text_area("Address")
        pcity = st.text_input("City")
        pcontact = st.text_input("Contact Number / Email")

        psubmit = st.form_submit_button("Add Provider")
        if psubmit:
            try:
                conn.execute("""
                    INSERT INTO Providers (Name, Type, Address, City, Contact) VALUES (?, ?, ?, ?, ?)
                """, (pname, ptype, paddress, pcity, pcontact))
                conn.commit()
                st.success("Provider added!")
            except Exception as e:
                st.error(f"Failed to add provider: {e}")

    st.markdown("---")
    st.subheader("View & Update Providers")

    providers = run_query("SELECT * FROM Providers ORDER BY Provider_ID ASC LIMIT 100")
    selected_pid = st.selectbox("Select Provider ID to Update/Delete", options=providers["Provider_ID"].tolist())

    if selected_pid:
        provider = providers[providers["Provider_ID"] == selected_pid].iloc[0]

        with st.form("update_provider_form"):
            up_name = st.text_input("Provider Name", value=provider["Name"])
            up_type = st.text_input("Provider Type", value=provider["Type"])
            up_address = st.text_area("Address", value=provider["Address"])
            up_city = st.text_input("City", value=provider["City"])
            up_contact = st.text_input("Contact", value=provider["Contact"])

            up_submitted = st.form_submit_button("Update Provider")
            if up_submitted:
                try:
                    conn.execute("""
                        UPDATE Providers SET Name=?, Type=?, Address=?, City=?, Contact=? WHERE Provider_ID=?
                    """, (up_name, up_type, up_address, up_city, up_contact, selected_pid))
                    conn.commit()
                    st.success("Provider updated!")
                except Exception as e:
                    st.error(f"Update failed: {e}")

            if st.button("Delete Provider"):
                try:
                    conn.execute("DELETE FROM Providers WHERE Provider_ID=?", (selected_pid,))
                    conn.commit()
                    st.success("Provider deleted.")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

# -------------------
# CRUD: Receivers
# -------------------
elif page == "Receivers CRUD":
    st.title("Food Receivers - Manage Receivers")

    st.subheader("Add New Receiver")
    with st.form("add_receiver_form", clear_on_submit=True):
        rname = st.text_input("Receiver Name")
        rtype = st.text_input("Receiver Type (NGO, Individual, etc.)")
        rcity = st.text_input("City")
        rcontact = st.text_input("Contact Number / Email")

        rsubmit = st.form_submit_button("Add Receiver")
        if rsubmit:
            try:
                conn.execute("""
                    INSERT INTO Receivers (Name, Type, City, Contact) VALUES (?, ?, ?, ?)
                """, (rname, rtype, rcity, rcontact))
                conn.commit()
                st.success("Receiver added!")
            except Exception as e:
                st.error(f"Failed to add receiver: {e}")

    st.markdown("---")
    st.subheader("View & Update Receivers")

    receivers = run_query("SELECT * FROM Receivers ORDER BY Receiver_ID ASC LIMIT 100")
    selected_rid = st.selectbox("Select Receiver ID to Update/Delete", options=receivers["Receiver_ID"].tolist())

    if selected_rid:
        receiver = receivers[receivers["Receiver_ID"] == selected_rid].iloc[0]

        with st.form("update_receiver_form"):
            ur_name = st.text_input("Receiver Name", value=receiver["Name"])
            ur_type = st.text_input("Receiver Type", value=receiver["Type"])
            ur_city = st.text_input("City", value=receiver["City"])
            ur_contact = st.text_input("Contact", value=receiver["Contact"])

            ur_submitted = st.form_submit_button("Update Receiver")
            if ur_submitted:
                try:
                    conn.execute("""
                        UPDATE Receivers SET Name=?, Type=?, City=?, Contact=? WHERE Receiver_ID=?
                    """, (ur_name, ur_type, ur_city, ur_contact, selected_rid))
                    conn.commit()
                    st.success("Receiver updated!")
                except Exception as e:
                    st.error(f"Update failed: {e}")

            if st.button("Delete Receiver"):
                try:
                    conn.execute("DELETE FROM Receivers WHERE Receiver_ID=?", (selected_rid,))
                    conn.commit()
                    st.success("Receiver deleted.")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

# -------------------
# CRUD: Claims
# -------------------
elif page == "Claims CRUD":
    st.title("Food Claims - Manage Food Claims")

    st.subheader("Add New Claim")
    with st.form("add_claim_form", clear_on_submit=True):
        food_id = st.number_input("Food ID", min_value=1)
        receiver_id = st.number_input("Receiver ID", min_value=1)
        status = st.selectbox("Status", ["Pending", "Completed", "Cancelled"])

        claim_submitted = st.form_submit_button("Add Claim")
        if claim_submitted:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("""
                    INSERT INTO Claims (Food_ID, Receiver_ID, Status, Timestamp) VALUES (?, ?, ?, ?)
                """, (food_id, receiver_id, status, timestamp))
                conn.commit()
                st.success("Claim added!")
            except Exception as e:
                st.error(f"Failed to add claim: {e}")

    st.markdown("---")
    st.subheader("View & Update Claims")

    claims = run_query("""
        SELECT Claim_ID, Food_ID, Receiver_ID, Status, Timestamp
        FROM Claims ORDER BY Timestamp DESC LIMIT 100
    """)
    selected_cid = st.selectbox("Select Claim ID to Update/Delete", options=claims["Claim_ID"].tolist())

    if selected_cid:
        claim = claims[claims["Claim_ID"] == selected_cid].iloc[0]

        with st.form("update_claim_form"):
            uc_food_id = st.number_input("Food ID", min_value=1, value=int(claim["Food_ID"]))
            uc_receiver_id = st.number_input("Receiver ID", min_value=1, value=int(claim["Receiver_ID"]))
            uc_status = st.selectbox("Status", ["Pending", "Completed", "Cancelled"], index=["Pending", "Completed", "Cancelled"].index(claim["Status"]))

            uc_submitted = st.form_submit_button("Update Claim")
            if uc_submitted:
                try:
                    conn.execute("""
                        UPDATE Claims SET Food_ID=?, Receiver_ID=?, Status=? WHERE Claim_ID=?
                    """, (uc_food_id, uc_receiver_id, uc_status, selected_cid))
                    conn.commit()
                    st.success("Claim updated!")
                except Exception as e:
                    st.error(f"Update failed: {e}")

            if st.button("Delete Claim"):
                try:
                    conn.execute("DELETE FROM Claims WHERE Claim_ID=?", (selected_cid,))
                    conn.commit()
                    st.success("Claim deleted.")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

# -------------------
# SQL Queries page
# -------------------
elif page == "SQL Queries":
    st.title("SQL Queries & Reports")

    query_names = [
        "Q1: Providers & Receivers per City",
        "Q2: Top contributing provider type (by quantity)",
        "Q3: Contact info of providers in a city (param)",
        "Q4: Receivers with most claims",
        "Q5: Total quantity of food available",
        "Q6: City with highest number of listings",
        "Q7: Most commonly available food types",
        "Q8: Claims made per food item",
        "Q9: Provider with highest successful claims",
        "Q10: Claims status distribution (%)",
        "Q11: Average quantity claimed per receiver",
        "Q12: Most claimed meal type",
        "Q13: Total quantity donated by each provider",
        "Q14: Expired food listings",
        "Q15: Listings expiring within next 3 days"
    ]

    selected_query = st.selectbox("Choose Query", query_names)

    # Params input for Q3 only
    param = None
    if selected_query == "Q3: Contact info of providers in a city (param)":
        param = st.text_input("Enter City Name (case insensitive)")

    if st.button("Run Query"):
        sql_query = QUERIES[selected_query]
        try:
            if param:
                df = run_query(sql_query, (param,))
            else:
                df = run_query(sql_query)
            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Results as CSV",
                data=csv,
                file_name=f"{selected_query.split(':')[0]}_results.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"Error running query: {e}")

# -------------------
# EDA page
# -------------------
elif page == "EDA":
    st.title("Exploratory Data Analysis")

    # Load tables as dataframes
    df_providers = run_query("SELECT * FROM Providers")
    df_receivers = run_query("SELECT * FROM Receivers")
    df_food = run_query("SELECT * FROM Food_Listings")
    df_claims = run_query("SELECT * FROM Claims")

    st.subheader("Basic Dataset Info")
    st.markdown(f"- Total Providers: {len(df_providers)}")
    st.markdown(f"- Total Receivers: {len(df_receivers)}")
    st.markdown(f"- Total Food Listings: {len(df_food)}")
    st.markdown(f"- Total Claims: {len(df_claims)}")

    # Food listings by expiry status
    today = pd.to_datetime(date.today())
    df_food['Expiry_Date'] = pd.to_datetime(df_food['Expiry_Date'], errors='coerce')
    df_food['Days_to_Expiry']
