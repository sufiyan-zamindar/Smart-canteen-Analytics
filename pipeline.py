# pipeline.py
# Core engine: Pandas -> NumPy -> Excel (in-memory)

from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -------- Phase 0 — Load and normalize --------
def load_data(menu_csv, sales_csv):
    """Accepts file paths or file-like objects from Streamlit uploads."""
    menu = pd.read_csv(menu_csv)
    sales = pd.read_csv(sales_csv)

    # Normalize headers
    menu.columns = [c.strip().lower() for c in menu.columns]
    sales.columns = [c.strip().lower() for c in sales.columns]

    # Schema (matches your real data)
    need_menu = {"item_id", "item_name", "category", "price"}
    need_sales = {"item_id", "quantity", "student_count", "date"}
    miss_m = need_menu - set(menu.columns)
    miss_s = need_sales - set(sales.columns)
    if miss_m:
        raise KeyError(f"Menu missing columns: {sorted(miss_m)}")
    if miss_s:
        raise KeyError(f"Sales missing columns: {sorted(miss_s)}")

    # Types / defaults
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce").fillna(0.0)
    if "unitcost" not in menu.columns:
        menu["unitcost"] = (menu["price"] * 0.60).round(2)

    sales["quantity"] = pd.to_numeric(sales["quantity"], errors="coerce").fillna(0).astype(int)
    sales["student_count"] = pd.to_numeric(sales["student_count"], errors="coerce").fillna(0).astype(int)
    sales["date"] = pd.to_datetime(sales["date"], errors="coerce").dt.date

    return menu, sales


# -------- Phase 1 — Pandas tasks --------
def pandas_phase(menu: pd.DataFrame, sales: pd.DataFrame):
    df = sales.merge(
        menu[["item_id", "item_name", "category", "price", "unitcost"]],
        on="item_id",
        how="left",
        validate="many_to_one",
    ).rename(columns={"item_name": "Item", "category": "Category"})

    # Normalization for plotting and splits
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["Category"] = (
        df["Category"]
        .astype(str)
        .str.strip()
        .str.replace("_", "-", regex=False)
        .str.title()
        .replace({"Non-Veg": "Non-veg"})
    )

    # Financials
    df["Revenue"] = df["quantity"] * df["price"]
    df["Cost"] = df["quantity"] * df["unitcost"]
    df["Profit"] = df["Revenue"] - df["Cost"]

    # Daily KPIs
    daily = (
        df.groupby("date")
        .agg(
            Revenue=("Revenue", "sum"),
            Cost=("Cost", "sum"),
            Profit=("Profit", "sum"),
            Orders=("quantity", "sum"),
            UniqueStudents=("student_count", "sum"),
        )
        .reset_index()
        .rename(columns={"date": "Date"})
    )

    # Veg/Non-veg split
    vnv = (
        df.groupby(["date", "Category"])
        .agg(Revenue=("Revenue", "sum"), Qty=("quantity", "sum"))
        .reset_index()
        .rename(columns={"date": "Date"})
        .sort_values(["Date", "Revenue"], ascending=[True, False])
    )

    # Top-5 per day
    top_items = (
        df.groupby(["date", "Item"])
        .agg(Revenue=("Revenue", "sum"), Qty=("quantity", "sum"))
        .reset_index()
        .rename(columns={"date": "Date"})
    )
    top_items["Rank"] = top_items.groupby("Date")["Revenue"].rank(method="first", ascending=False)
    top5 = top_items[top_items["Rank"] <= 5].sort_values(["Date", "Rank"])

    return df, daily, vnv, top5


# -------- Phase 2 — NumPy tasks --------
def numpy_phase(daily: pd.DataFrame):
    rev = daily["Revenue"].to_numpy()
    students = daily["UniqueStudents"].replace(0, np.nan).to_numpy()
    daily["AvgSpendPerStudent"] = np.round(rev / students, 2)

    cost = daily["Cost"].to_numpy()
    if cost.size > 0:
        window = np.ones(3) / 3.0
        pad = np.pad(cost, (1, 1), mode="edge")
        daily["Cost_MA3"] = np.round(np.convolve(pad, window, mode="valid"), 2)
    else:
        daily["Cost_MA3"] = np.nan
    return daily


# -------- Phase 3 — Excel + charts (in-memory) --------
def build_excel_and_charts(df, daily, vnv, top5):
    """
    Returns: excel_bytes, daily_revenue_png_bytes, vnv_png_bytes
    """
    # Excel in memory
    xbuf = BytesIO()
    with pd.ExcelWriter(xbuf, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name="Full_Joined")
        daily.to_excel(w, index=False, sheet_name="Summary_Daily")
        vnv.to_excel(w, index=False, sheet_name="Veg_NonVeg_Ratio")
        top5.to_excel(w, index=False, sheet_name="Top5_Items_Per_Day")

        for d, dfx in df.groupby("date"):
            sheet = str(d)
            kpi = daily[daily["Date"] == pd.to_datetime(d).date()]
            kpi.to_excel(w, index=False, sheet_name=sheet, startrow=0)
            item_breakdown = (
                dfx.groupby(["Item", "Category"])
                .agg(Qty=("quantity", "sum"), Revenue=("Revenue", "sum"), Profit=("Profit", "sum"))
                .reset_index()
                .sort_values("Revenue", ascending=False)
            )
            item_breakdown.to_excel(w, index=False, sheet_name=sheet, startrow=5)
    xbuf.seek(0)

    # Charts in memory
    daily_png, vnv_png = None, None

    if len(daily) > 0:
        # Robust plot for 1–2 days as bars, else line
        dsorted = daily.sort_values("Date")
        fig1, ax1 = plt.subplots()
        if len(dsorted) <= 2:
            ax1.bar(dsorted["Date"].astype(str), dsorted["Revenue"])
        else:
            ax1.plot(pd.to_datetime(dsorted["Date"]), dsorted["Revenue"], marker="o", linewidth=2)
        ax1.set_title("Daily Revenue")
        ax1.set_xlabel("Date"); ax1.set_ylabel("Revenue")
        p1 = BytesIO(); plt.savefig(p1, format="png", bbox_inches="tight"); plt.close(fig1)
        p1.seek(0); daily_png = p1.read()

    if len(vnv) > 0:
        v = vnv.copy()
        v["Category"] = v["Category"].astype(str)
        pv = (
            v.pivot_table(index="Date", columns="Category", values="Revenue", aggfunc="sum")
            .fillna(0)
            .sort_index()
        )
        fig2, ax2 = plt.subplots()
        if pv.shape[0] <= 2:
            pv.plot(kind="bar", ax=ax2)
            ax2.set_xlabel("Date")
        else:
            for col in pv.columns:
                ax2.plot(pd.to_datetime(pv.index), pv[col], marker="o", linewidth=2, label=col)
        ax2.set_title("Revenue by Category (Veg vs Non-veg)")
        ax2.set_ylabel("Revenue"); ax2.legend()
        p2 = BytesIO(); plt.savefig(p2, format="png", bbox_inches="tight"); plt.close(fig2)
        p2.seek(0); vnv_png = p2.read()

    return xbuf.getvalue(), daily_png, vnv_png


# -------- Single entry for the app --------
def run_pipeline(menu_csv, sales_csv):
    menu, sales = load_data(menu_csv, sales_csv)
    df, daily, vnv, top5 = pandas_phase(menu, sales)
    daily = numpy_phase(daily)
    excel_bytes, daily_png, vnv_png = build_excel_and_charts(df, daily, vnv, top5)
    return {
        "df": df,
        "daily": daily,
        "vnv": vnv,
        "top5": top5,
        "excel_bytes": excel_bytes,
        "daily_png": daily_png,
        "vnv_png": vnv_png,
    }
