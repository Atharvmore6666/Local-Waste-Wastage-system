# app.py - Full Local Food Wastage System with All Pages & 15 Queries

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

# -----------------------
# PAGE CONFIG
# -----------------------
st.set_page_config(
    page_title="Local Food Wastage System",
    layout="wide",
    page_icon="🌿"
)

# -----------------------
# CUSTOM CSS
# -----------------------
st.markdown(
    """
    <style>
        body { background-color: #f5f0e1; color: #2e7d32; }
        h1, h2, h3, h4 { color: #2e7d32; }
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------
# LOAD DATA
# -----------------------
@st.cache_data
def load_data():
    df = pd.read_csv("wastage_data.csv")  # Replace with your CSV path
    df.fillna("", inplace=True)
    if "Timestamp" in df.columns:
        df["Timestamp_dt"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    if "Days_to_Expiry" in df.columns:
        df["Days_to_Expiry"] = df["Days_to_Expiry"].abs()
    return df

c = load_data()

# -----------------------
# SIDEBAR NAVIGATION
# -----------------------
page = st.sidebar.selectbox(
    "Navigation",
    ["Dashboard", "Donations Explorer", "Queries", "CRUD", "Data", "About"]
)

# -----------------------
# COMMON FILTERS
# -----------------------
st.sidebar.header("Filters")
c_filtered = c.copy()

# Category filter
if "Category" in c.columns:
    categories = st.sidebar.multiselect(
        "Select Category", options=c["Category"].unique(), default=c["Category"].unique()
    )
    c_filtered = c_filtered[c_filtered["Category"].isin(categories)]

# Days to expiry filter
if "Days_to_Expiry" in c_filtered.columns:
    days_to_expiry = st.sidebar.slider(
        "Days to Expiry",
        int(c_filtered["Days_to_Expiry"].min()),
        int(c_filtered["Days_to_Expiry"].max()),
        (int(c_filtered["Days_to_Expiry"].min()), int(c_filtered["Days_to_Expiry"].max()))
    )
    c_filtered = c_filtered[
        (c_filtered["Days_to_Expiry"] >= days_to_expiry[0]) &
        (c_filtered["Days_to_Expiry"] <= days_to_expiry[1])
    ]

# Date range filter
if "Timestamp_dt" in c_filtered.columns:
    min_date = c_filtered["Timestamp_dt"].min()
    max_date = c_filtered["Timestamp_dt"].max()
    date_range = st.sidebar.date_input(
        "Select Date Range",
        [min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )
    if len(date_range) == 2:
        start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        c_filtered = c_filtered[
            (c_filtered["Timestamp_dt"] >= start_date) &
            (c_filtered["Timestamp_dt"] <= end_date)
        ]

# -----------------------
# DASHBOARD PAGE
# -----------------------
if page == "Dashboard":
    st.title("🌿 Local Food Wastage Dashboard")
    st.subheader("Overview")
    st.write("Total Records:", len(c_filtered))
    st.write("Total Categories:", c_filtered["Category"].nunique() if "Category" in c_filtered.columns else "N/A")
    st.write("Date Range:", c_filtered["Timestamp_dt"].min(), "to", c_filtered["Timestamp_dt"].max())

    # Example monthly aggregation chart
    if "Timestamp_dt" in c_filtered.columns and "Quantity" in c_filtered.columns:
        monthly_data = c_filtered.dropna(subset=["Timestamp_dt"]).groupby(
            pd.Grouper(key="Timestamp_dt", freq="M")
        )["Quantity"].sum().reset_index().rename(columns={"Timestamp_dt": "Period"})
        chart = alt.Chart(monthly_data).mark_line(point=True).encode(
            x="Period:T",
            y="Quantity:Q",
            tooltip=["Period", "Quantity"]
        ).properties(height=400)
        st.altair_chart(chart, use_container_width=True)

# -----------------------
# DONATIONS EXPLORER PAGE
# -----------------------
elif page == "Donations Explorer":
    st.title("💝 Donations Explorer")
    if "Donor" in c_filtered.columns and "Quantity" in c_filtered.columns:
        donor_agg = c_filtered.groupby("Donor")["Quantity"].sum().reset_index().sort_values("Quantity", ascending=False)
        st.dataframe(donor_agg)
        chart = alt.Chart(donor_agg).mark_bar().encode(
            x="Donor:N",
            y="Quantity:Q",
            tooltip=["Donor", "Quantity"]
        ).properties(height=400)
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Donor or Quantity columns not found.")

# -----------------------
# QUERIES PAGE WITH 15 PREDEFINED QUERIES
# -----------------------
elif page == "Queries":
    st.title("🔍 Predefined Queries")

    queries = {
        "1. Total Quantity per Category": "c_filtered.groupby('Category')['Quantity'].sum()",
        "2. Average Days to Expiry": "c_filtered['Days_to_Expiry'].mean()",
        "3. Total Donations by Donor": "c_filtered.groupby('Donor')['Quantity'].sum()",
        "4. Monthly Wastage Trend": "c_filtered.dropna(subset=['Timestamp_dt']).groupby(pd.Grouper(key='Timestamp_dt', freq='M'))['Quantity'].sum()",
        "5. Items Close to Expiry (<=3 days)": "c_filtered[c_filtered['Days_to_Expiry'] <= 3]",
        "6. Top 10 Donors": "c_filtered.groupby('Donor')['Quantity'].sum().sort_values(ascending=False).head(10)",
        "7. Categories with Zero Quantity": "c_filtered[c_filtered['Quantity'] == 0]['Category'].unique()",
        "8. Average Quantity per Donation": "c_filtered['Quantity'].mean()",
        "9. Total Records per Category": "c_filtered['Category'].value_counts()",
        "10. Oldest Donations": "c_filtered.sort_values('Timestamp_dt').head(10)",
        "11. Most Recent Donations": "c_filtered.sort_values('Timestamp_dt', ascending=False).head(10)",
        "12. Total Quantity per Donor per Month": "c_filtered.dropna(subset=['Timestamp_dt']).groupby([pd.Grouper(key='Timestamp_dt', freq='M'),'Donor'])['Quantity'].sum()",
        "13. Donations with Missing Donor": "c_filtered[c_filtered['Donor']=='']",
        "14. Categories with Maximum Wastage": "c_filtered.groupby('Category')['Quantity'].sum().sort_values(ascending=False).head(5)",
        "15. Summary Statistics": "c_filtered.describe()"
    }

    selected_query = st.selectbox("Select Query", list(queries.keys()))
    if st.button("Run Query"):
        try:
            result = eval(queries[selected_query])
            st.dataframe(result)
        except Exception as e:
            st.error(f"Error executing query: {e}")

# -----------------------
# CRUD PAGE
# -----------------------
elif page == "CRUD":
    st.title("🛠 CRUD Operations")
    st.write("You can add or remove records here.")
    if st.checkbox("Add New Record"):
        new_data = {}
        for col in c.columns:
            new_data[col] = st.text_input(f"{col}")
        if st.button("Add Record"):
            c_filtered.loc[len(c_filtered)] = new_data
            st.success("Record added!")

    if st.checkbox("Delete Record by Index"):
        idx = st.number_input("Enter Row Index", min_value=0, max_value=len(c_filtered)-1)
        if st.button("Delete"):
            c_filtered.drop(index=idx, inplace=True)
            st.success(f"Deleted row {idx}")

# -----------------------
# DATA PAGE
# -----------------------
elif page == "Data":
    st.title("🗂 View Data")
    st.dataframe(c_filtered)

# -----------------------
# ABOUT PAGE
# -----------------------
elif page == "About":
    st.title("ℹ️ About")
    st.markdown("""
    **Local Food Wastage System**  
    - Built with Streamlit & pandas  
    - Allows tracking, exploring, and analyzing food wastage  
    - Supports Donations tracking, CRUD operations, and predefined queries  
    - Filters applied across all pages
    """)
