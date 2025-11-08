# app.py
# Streamlit UI. Runs Pandas -> NumPy -> Excel and serves charts + workbook.
# Run: streamlit run app.py

import streamlit as st
import pandas as pd
from io import BytesIO
from pipeline import run_pipeline

st.set_page_config(page_title="Smart Canteen Analytics", page_icon="🍽️", layout="wide")

st.title("🍽️ Smart Canteen Analytics — Auto Reports")
st.caption("Upload new menu and sales CSVs. The app runs Pandas → NumPy → Excel and returns dashboards + a downloadable workbook.")

with st.sidebar:
    st.header("Upload files")
    menu_file = st.file_uploader("Menu CSV (item_id,item_name,category,price)", type=["csv"])
    sales_file = st.file_uploader("Sales CSV (item_id,quantity,student_count,date)", type=["csv"])
    run_btn = st.button("Generate Reports", type="primary")

if run_btn:
    if not menu_file or not sales_file:
        st.error("Upload both Menu and Sales CSVs.")
        st.stop()

    try:
        result = run_pipeline(menu_file, sales_file)
    except Exception as e:
        st.error(f"Processing error: {e}")
        st.stop()

    daily = result["daily"]
    vnv = result["vnv"]
    top5 = result["top5"]

    # KPIs for latest day if present
    if len(daily) > 0:
        latest = daily.sort_values("Date").iloc[-1]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Revenue (latest day)", f"{latest['Revenue']:.0f}")
        c2.metric("Profit (latest day)", f"{latest['Profit']:.0f}")
        c3.metric("Orders (latest day)", f"{latest['Orders']}")
        c4.metric("Students (latest day)", f"{int(latest['UniqueStudents'])}")
        c5.metric("Avg Spend / Student", f"{latest['AvgSpendPerStudent']:.2f}")

    # Tables
    st.subheader("Daily KPIs")
    st.dataframe(daily, use_container_width=True)

    st.subheader("Top 5 Items per Day")
    st.dataframe(top5, use_container_width=True)

    # Charts (bytes from pipeline)
    st.subheader("Charts")
    ch1, ch2 = st.columns(2)
    if result["daily_png"]:
        ch1.image(BytesIO(result["daily_png"]), caption="Daily Revenue", use_container_width=True)
    if result["vnv_png"]:
        ch2.image(BytesIO(result["vnv_png"]), caption="Veg vs Non-veg Revenue", use_container_width=True)

    # Download Excel
    st.subheader("Download")
    st.download_button(
        label="Download Excel Dashboard",
        data=result["excel_bytes"],
        file_name="Canteen_Summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Optional: show first rows of the joined table for quick QA
    with st.expander("Preview joined data"):
        st.dataframe(result["df"].head(50), use_container_width=True)

else:
    st.info("Upload menu and sales CSVs, then click Generate Reports.")
