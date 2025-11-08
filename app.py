# app.py
# Streamlit UI: uploads -> Pandas -> NumPy -> Excel, plus Altair charts
# Run locally: streamlit run app.py

import streamlit as st
import pandas as pd
from io import BytesIO
import altair as alt

from pipeline import run_pipeline

st.set_page_config(page_title="Smart Canteen Analytics", page_icon="🍽️", layout="wide")

st.title("🍽️ Smart Canteen Analytics — Auto Reports")
st.caption("Upload Menu and Sales CSVs. The app runs Pandas → NumPy → Excel and returns dashboards + a downloadable workbook.")

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

    df = result["df"]
    daily = result["daily"]
    vnv = result["vnv"]
    top5 = result["top5"]

    # KPIs
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

    # Charts via Altair (no matplotlib dependency)
    st.subheader("Charts")
    ch1, ch2 = st.columns(2)

    if len(daily) > 0:
        d_sorted = daily.sort_values("Date").copy()
        d_sorted["Date"] = pd.to_datetime(d_sorted["Date"])

        # Fallback to bar when there are <= 2 dates
        if len(d_sorted) <= 2:
            chart1 = alt.Chart(d_sorted).mark_bar().encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Revenue:Q", title="Revenue"),
                tooltip=["Date:T", "Revenue:Q", "Profit:Q", "Orders:Q", "UniqueStudents:Q"]
            )
        else:
            chart1 = alt.Chart(d_sorted).mark_line(point=True).encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Revenue:Q", title="Revenue"),
                tooltip=["Date:T", "Revenue:Q", "Profit:Q", "Orders:Q", "UniqueStudents:Q"]
            )
        ch1.altair_chart(chart1.properties(title="Daily Revenue").interactive(), use_container_width=True)

    if len(vnv) > 0:
        v2 = vnv.copy()
        v2["Date"] = pd.to_datetime(v2["Date"])
        # Pivot-like layered lines, fallback to grouped bars for small N
        if v2["Date"].nunique() <= 2:
            chart2 = alt.Chart(v2).mark_bar().encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Revenue:Q", title="Revenue"),
                color=alt.Color("Category:N", title="Category"),
                column=alt.Column("Category:N", title=None)
            )
        else:
            chart2 = alt.Chart(v2).mark_line(point=True).encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Revenue:Q", title="Revenue"),
                color=alt.Color("Category:N", title="Category"),
                tooltip=["Date:T", "Category:N", "Revenue:Q"]
            )
        ch2.altair_chart(chart2.properties(title="Revenue by Category (Veg vs Non-veg)").interactive(),
                         use_container_width=True)

    # Download Excel
    st.subheader("Download")
    st.download_button(
        label="Download Excel Dashboard",
        data=result["excel_bytes"],
        file_name="Canteen_Summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    with st.expander("Preview joined data"):
        st.dataframe(df.head(50), use_container_width=True)

else:
    st.info("Upload menu and sales CSVs, then click Generate Reports.")
