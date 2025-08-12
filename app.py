import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Connect to SQLite DB
@st.cache_resource(ttl=600)
def get_connection():
    conn = sqlite3.connect('food_wastage.db', check_same_thread=False)
    return conn

conn = get_connection()
cursor = conn.cursor()

# Helper function to run query and return df
def run_query(sql, params=None):
    params = params or []
    return pd.read_sql(sql, conn, params=params)

# --- Sidebar: Filters for Food Listings ---
st.sidebar.title("Filter Food Listings")

# Fetch filter options dynamically from DB
def get_unique_values(table, column):
    df = run_query(f"SELECT DISTINCT {column} FROM {table} ORDER BY {column} ASC")
    return ["All"] + df[column].dropna().tolist()

city_options = get_unique_values("Providers", "City")
provider_type_options = get_unique_values("Providers", "Type")
food_type_options = get_unique_values("Food_Listings", "Food_Type")
meal_type_options = get_unique_values("Food_Listings", "Meal_Type")

city_filter = st.sidebar.selectbox("City", city_options)
provider_type_filter = st.sidebar.selectbox("Provider Type", provider_type_options)
food_type_filter = st.sidebar.selectbox("Food Type", food_type_options)
meal_type_filter = st.sidebar.selectbox("Meal Type", meal_type_options)

# Build dynamic filter query for Food Listings
def get_filtered_food_listings():
    query = """
    SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, 
           p.Name as Provider_Name, p.Contact as Provider_Contact, 
           f.Food_Type, f.Meal_Type, f.Location
    FROM Food_Listings f
    JOIN Providers p ON f.Provider_ID = p.Provider_ID
    WHERE 1=1
    """
    params = []
    if city_filter != "All":
        query += " AND p.City = ?"
        params.append(city_filter)
    if provider_type_filter != "All":
        query += " AND p.Type = ?"
        params.append(provider_type_filter)
    if food_type_filter != "All":
        query += " AND f.Food_Type = ?"
        params.append(food_type_filter)
    if meal_type_filter != "All":
        query += " AND f.Meal_Type = ?"
        params.append(meal_type_filter)
    
    query += " ORDER BY f.Expiry_Date ASC"
    return run_query(query, params)

# --- Main App Layout ---
st.title("🍲 Local Food Wastage Management System")

st.markdown("### Available Food Listings")
food_listings_df = get_filtered_food_listings()
st.dataframe(food_listings_df)

# Show contact info for providers in filtered results
st.markdown("### Contact Food Providers")
providers_in_listings = food_listings_df[['Provider_Name', 'Provider_Contact']].drop_duplicates().reset_index(drop=True)
st.dataframe(providers_in_listings)

# --- CRUD Operations Section ---
st.markdown("---")
st.header("Manage Food Listings & Claims")

tab1, tab2 = st.tabs(["Food Listings", "Claims"])

with tab1:
    st.subheader("Add New Food Listing")
    with st.form("add_food_form"):
        food_name = st.text_input("Food Name")
        quantity = st.number_input("Quantity", min_value=1, step=1)
        expiry_date = st.date_input("Expiry Date", min_value=datetime.today())
        provider_id = st.number_input("Provider ID", min_value=1, step=1)
        provider_type = st.text_input("Provider Type")
        location = st.text_input("Location")
        food_type = st.selectbox("Food Type", options=["Vegetarian", "Non-Vegetarian", "Vegan"])
        meal_type = st.selectbox("Meal Type", options=["Breakfast", "Lunch", "Dinner", "Snacks"])
        submitted = st.form_submit_button("Add Food Listing")

        if submitted:
            days_to_expiry = (expiry_date - datetime.now().date()).days
            try:
                cursor.execute("""
                    INSERT INTO Food_Listings 
                    (Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type, days_to_expiry) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (food_name, quantity, expiry_date.strftime('%Y-%m-%d'), provider_id, provider_type, location, food_type, meal_type, days_to_expiry))
                conn.commit()
                st.success("Food listing added successfully!")
            except Exception as e:
                st.error(f"Error adding listing: {e}")

    st.markdown("### Update Existing Food Listing")
    food_ids = run_query("SELECT Food_ID FROM Food_Listings")["Food_ID"].tolist()
    update_food_id = st.selectbox("Select Food ID to Update", options=food_ids)
    
    if update_food_id:
        food_data = run_query("SELECT * FROM Food_Listings WHERE Food_ID = ?", [update_food_id])
        if not food_data.empty:
            f = food_data.iloc[0]
            with st.form("update_food_form"):
                u_food_name = st.text_input("Food Name", f.Food_Name)
                u_quantity = st.number_input("Quantity", min_value=1, step=1, value=int(f.Quantity))
                u_expiry_date = st.date_input("Expiry Date", pd.to_datetime(f.Expiry_Date))
                u_provider_id = st.number_input("Provider ID", min_value=1, step=1, value=int(f.Provider_ID))
                u_provider_type = st.text_input("Provider Type", f.Provider_Type)
                u_location = st.text_input("Location", f.Location)
                u_food_type = st.selectbox("Food Type", options=["Vegetarian", "Non-Vegetarian", "Vegan"], index=["Vegetarian", "Non-Vegetarian", "Vegan"].index(f.Food_Type) if f.Food_Type in ["Vegetarian", "Non-Vegetarian", "Vegan"] else 0)
                u_meal_type = st.selectbox("Meal Type", options=["Breakfast", "Lunch", "Dinner", "Snacks"], index=["Breakfast", "Lunch", "Dinner", "Snacks"].index(f.Meal_Type) if f.Meal_Type in ["Breakfast", "Lunch", "Dinner", "Snacks"] else 0)
                submitted_update = st.form_submit_button("Update Listing")

                if submitted_update:
                    days_to_expiry = (u_expiry_date - datetime.now().date()).days
                    try:
                        cursor.execute("""
                            UPDATE Food_Listings SET Food_Name=?, Quantity=?, Expiry_Date=?, Provider_ID=?, Provider_Type=?, Location=?, Food_Type=?, Meal_Type=?, days_to_expiry=?
                            WHERE Food_ID=?
                        """, (u_food_name, u_quantity, u_expiry_date.strftime('%Y-%m-%d'), u_provider_id, u_provider_type, u_location, u_food_type, u_meal_type, days_to_expiry, update_food_id))
                        conn.commit()
                        st.success("Food listing updated successfully!")
                    except Exception as e:
                        st.error(f"Error updating listing: {e}")

    st.markdown("### Delete Food Listing")
    delete_food_id = st.selectbox("Select Food ID to Delete", options=food_ids, key="delete_food")
    if st.button("Delete Food Listing"):
        try:
            cursor.execute("DELETE FROM Food_Listings WHERE Food_ID=?", (delete_food_id,))
            conn.commit()
            st.success(f"Food listing with ID {delete_food_id} deleted.")
        except Exception as e:
            st.error(f"Error deleting listing: {e}")

with tab2:
    st.subheader("Add New Claim")
    with st.form("add_claim_form"):
        claim_food_id = st.number_input("Food ID", min_value=1, step=1)
        receiver_id = st.number_input("Receiver ID", min_value=1, step=1)
        status = st.selectbox("Status", options=["Pending", "Completed", "Cancelled"])
        timestamp = st.date_input("Timestamp", value=datetime.today())
        submitted_claim = st.form_submit_button("Add Claim")

        if submitted_claim:
            try:
                cursor.execute("""
                    INSERT INTO Claims (Food_ID, Receiver_ID, Status, Timestamp) VALUES (?, ?, ?, ?)
                """, (claim_food_id, receiver_id, status, timestamp.strftime('%Y-%m-%d')))
                conn.commit()
                st.success("Claim added successfully!")
            except Exception as e:
                st.error(f"Error adding claim: {e}")

    st.markdown("### Update Claim Status")
    claim_ids = run_query("SELECT Claim_ID FROM Claims")["Claim_ID"].tolist()
    update_claim_id = st.selectbox("Select Claim ID to Update", options=claim_ids)
    if update_claim_id:
        claim_data = run_query("SELECT * FROM Claims WHERE Claim_ID = ?", [update_claim_id])
        if not claim_data.empty:
            c = claim_data.iloc[0]
            with st.form("update_claim_form"):
                u_status = st.selectbox("Status", options=["Pending", "Completed", "Cancelled"], index=["Pending", "Completed", "Cancelled"].index(c.Status))
                u_timestamp = st.date_input("Timestamp", pd.to_datetime(c.Timestamp))
                submitted_claim_update = st.form_submit_button("Update Claim")
                if submitted_claim_update:
                    try:
                        cursor.execute("""
                            UPDATE Claims SET Status=?, Timestamp=? WHERE Claim_ID=?
                        """, (u_status, u_timestamp.strftime('%Y-%m-%d'), update_claim_id))
                        conn.commit()
                        st.success("Claim updated successfully!")
                    except Exception as e:
                        st.error(f"Error updating claim: {e}")

    st.markdown("### Delete Claim")
    delete_claim_id = st.selectbox("Select Claim ID to Delete", options=claim_ids, key="delete_claim")
    if st.button("Delete Claim"):
        try:
            cursor.execute("DELETE FROM Claims WHERE Claim_ID=?", (delete_claim_id,))
            conn.commit()
            st.success(f"Claim with ID {delete_claim_id} deleted.")
        except Exception as e:
            st.error(f"Error deleting claim: {e}")

# --- Queries & Analysis Section ---
st.markdown("---")
st.header("SQL Queries & Analysis")

query_dict = {
    "1. Count food providers and receivers in each city": """
        SELECT City, COUNT(DISTINCT Provider_ID) AS Total_Providers, 0 AS Total_Receivers FROM Providers GROUP BY City
        UNION ALL
        SELECT City, 0 AS Total_Providers, COUNT(DISTINCT Receiver_ID) AS Total_Receivers FROM Receivers GROUP BY City;
    """,
    "2. Food provider type contributing the most food": """
        SELECT Provider_Type, SUM(Quantity) AS Total_Quantity FROM Food_Listings GROUP BY Provider_Type ORDER BY Total_Quantity DESC LIMIT 1;
    """,
    "3. Contact info of food providers in a city (example: Aguirreville)": """
        SELECT Name, Type, City, Contact FROM Providers WHERE City = 'Aguirreville';
    """,
    "4. Receivers who claimed the most food": """
        SELECT r.Name, COUNT(c.Claim_ID) AS Total_Claims FROM Receivers r JOIN Claims c ON r.Receiver_ID = c.Receiver_ID GROUP BY r.Receiver_ID ORDER BY Total_Claims DESC;
    """,
    "5. Total quantity of food available": """
        SELECT SUM(Quantity) AS Total_Food_Quantity FROM Food_Listings;
    """,
    "6. City with highest number of food listings": """
        SELECT p.City, COUNT(f.Food_ID) AS Total_Listings FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID GROUP BY p.City ORDER BY Total_Listings DESC LIMIT 1;
    """,
    "7. Most commonly available food types": """
        SELECT Food_Type, COUNT(*) AS Count FROM Food_Listings GROUP BY Food_Type ORDER BY Count DESC;
    """,
    "8. Number of food claims per food item": """
        SELECT f.Food_Name, COUNT(c.Claim_ID) AS Total_Claims FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID GROUP BY f.Food_Name ORDER BY Total_Claims DESC;
    """,
    "9. Provider with highest successful food claims": """
        SELECT p.Name, COUNT(c.Claim_ID) AS Successful_Claims FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID JOIN Providers p ON f.Provider_ID = p.Provider_ID WHERE c.Status = 'Completed' GROUP BY p.Provider_ID ORDER BY Successful_Claims DESC LIMIT 1;
    """,
    "10. Percentage of claims status": """
        SELECT Status, ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM Claims)), 2) AS Percentage FROM Claims GROUP BY Status;
    """,
    "11. Average quantity of food claimed per receiver": """
        SELECT r.Name, ROUND(AVG(f.Quantity), 2) AS Avg_Quantity FROM Claims c JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID JOIN Food_Listings f ON c.Food_ID = f.Food_ID GROUP BY r.Receiver_ID;
    """,
    "12. Most claimed meal type": """
        SELECT f.Meal_Type, COUNT(c.Claim_ID) AS Total_Claims FROM Claims c JOIN Food_Listings f ON c.Food_ID = f.Food_ID GROUP BY f.Meal_Type ORDER BY Total_Claims DESC LIMIT 1;
    """,
    "13. Total quantity of food donated by each provider": """
        SELECT p.Name, SUM(f.Quantity) AS Total_Donated FROM Food_Listings f JOIN Providers p ON f.Provider_ID = p.Provider_ID GROUP BY p.Provider_ID ORDER BY Total_Donated DESC;
    """
}

for title, sql in query_dict.items():
    with st.expander(title):
        df = run_query(sql)
        st.dataframe(df)

st.markdown("### End of Queries")

