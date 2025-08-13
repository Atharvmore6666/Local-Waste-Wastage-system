import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# -------------------------------
# CONFIG & PAGE SETUP
# -------------------------------
st.set_page_config(
    page_title="Local Food Wastage System",
    layout="wide",
    page_icon="🌿"
)

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Donations Explorer", "Queries", "CRUD", "Data", "About"])

# -------------------------------
# DATA LOADING
# -------------------------------
@st.cache_data
def load_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        df.fillna("", inplace=True)
        if "Timestamp" in df.columns:
            df["Timestamp_dt"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        return df
    except FileNotFoundError:
        st.error(f"{file_path} not found!")
        return pd.DataFrame()

claims_df = load_csv("claims_data.csv")
providers_df = load_csv("providers_data.csv")
receivers_df = load_csv("receivers_data.csv")
food_listings_df = load_csv("food_listings_data.csv")

# SQLite connection
conn = sqlite3.connect("food_wastage.db")
c = conn.cursor()

# -------------------------------
# DASHBOARD PAGE
# -------------------------------
if page == "Dashboard":
    st.title("Dashboard")
    st.image("logo.png", width=150)

    st.subheader("Monthly Food Quantity")
    if not food_listings_df.empty and "Timestamp_dt" in food_listings_df.columns:
        monthly_data = food_listings_df.groupby(pd.Grouper(key="Timestamp_dt", freq="M"))["Quantity"].sum().reset_index()
        monthly_data.rename(columns={"Timestamp_dt": "Period"}, inplace=True)
        st.line_chart(monthly_data.set_index("Period"))
    else:
        st.warning("No food listings data available.")

# -------------------------------
# DONATIONS EXPLORER PAGE
# -------------------------------
elif page == "Donations Explorer":
    st.title("Donations Explorer")
    st.dataframe(food_listings_df)

    provider_filter = st.selectbox("Filter by Provider", ["All"] + list(providers_df["Name"].unique()))
    if provider_filter != "All":
        st.dataframe(food_listings_df[food_listings_df["Provider"] == provider_filter])

# -------------------------------
# QUERIES PAGE
# -------------------------------
elif page == "Queries":
    st.title("Queries")
    query = st.selectbox("Select Query", list(range(1,16)))

    # Example query logic
    if query == 1:
        st.write("Query 1: Total food quantity per provider")
        if not food_listings_df.empty:
            q1 = food_listings_df.groupby("Provider")["Quantity"].sum().reset_index()
            st.dataframe(q1)
    elif query == 2:
        st.write("Query 2: Total claims per receiver")
        if not claims_df.empty:
            q2 = claims_df.groupby("Receiver")["Claim_ID"].count().reset_index().rename(columns={"Claim_ID": "Total_Claims"})
            st.dataframe(q2)
    # Add all queries up to 15 following this pattern
    else:
        st.info(f"Query {query} will be added.")

# -------------------------------
# CRUD PAGE
# -------------------------------
elif page == "CRUD":
    st.title("CRUD Operations")
    st.subheader("Add new food listing")
    with st.form("add_listing"):
        provider = st.selectbox("Provider", providers_df["Name"].unique())
        food_item = st.text_input("Food Item")
        quantity = st.number_input("Quantity", min_value=1)
        timestamp = st.date_input("Timestamp", value=datetime.today())
        submitted = st.form_submit_button("Add Listing")
        if submitted:
            c.execute("INSERT INTO food_listings (Provider, Food_Item, Quantity, Timestamp) VALUES (?, ?, ?, ?)",
                      (provider, food_item, quantity, timestamp))
            conn.commit()
            st.success("Listing added successfully!")

# -------------------------------
# DATA PAGE
# -------------------------------
elif page == "Data":
    st.title("Raw Data")
    st.subheader("Claims Data")
    st.dataframe(claims_df)
    st.subheader("Providers Data")
    st.dataframe(providers_df)
    st.subheader("Receivers Data")
    st.dataframe(receivers_df)
    st.subheader("Food Listings Data")
    st.dataframe(food_listings_df)

# -------------------------------
# ABOUT PAGE
# -------------------------------
elif page == "About":
    st.title("About")
    st.image("logo.png", width=200)
    st.markdown("""
    ## Local Food Wastage System
    This Streamlit app helps manage and visualize food donations, providers, receivers, and claims.
    
    Developed with ❤️ using Python, Streamlit, Pandas, and SQLite.
    """)
