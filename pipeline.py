# pipeline.py
# Pandas -> NumPy -> Excel (in-memory). No matplotlib import.

from io import BytesIO
import numpy as np
import pandas as pd


# ---- Phase 0: Load + normalize ----
def load_data(menu_csv, sales_csv):
    """Accepts file paths or file-like objects (Streamlit uploader)."""
    menu = pd.read_csv(menu_csv)
    sales = pd.read_csv(sales_csv)

    # Normalize headers
    menu.columns = [c.strip().lower() for c in menu.columns]
    sales.columns = [c.strip().lower() for c in sales.columns]

    # Schema checks aligned with your data
    need_menu = {"item_id", "item_name", "category", "price"}
    need_sales = {"item_id", "quantity", "student_count", "date"}
    miss_m = need_menu - set(menu.columns)
    miss_s = need_sales - set(sales.columns)
    if miss_m:
        raise KeyError(f"Menu missing columns: {sorted(miss_m)}")
    if miss_s:
        raise KeyError(f"Sales missing columns: {sorted(miss_s)}")

    # Types and defaults
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce").fillna(0.0)
    if "unitcost" not in menu.columns:
        menu["unitcost"] = (menu["price"] * 0.60).round(2)

    sales["quantity"] = pd.to_numeric(sales["quantity"], errors="coerce").fillna(0).astype(int)
    sales["student_count"] = pd.to_numeric(sales["student_count"], errors="coerce").fillna(0).astype(int)
    sales["date"] = pd.to_datetime(sales["date"], errors="coerce").dt.date

    return menu, sales


# ---- Phase 1: Pandas tasks ----
def pandas_phase(menu: pd.DataFrame, sales: pd.DataFrame):
    df = (
        sales.merge(
            menu[["item_id", "item_name", "category", "price", "unitcost"]],
            on="item_id",
            how="left",
            validate="many_to_one",
        )
        .rename(columns={"item_name": "Item", "category": "Category"})
    )

    # Normalize for consistent charts/tables
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["Category"] = (
        df["Category"].astype(str).strip().replace("_", "-", regex=False).title()
        if hasattr(str, "title") else df["Category"]
    )
    df["Category"] = (
        df["Category"].replace({"Non-Veg": "Non-veg"})
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


# ---- Phase 2: NumPy tasks ----
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


# ---- Phase 3: Excel in memory (no plotting here) ----
def build_excel(df, daily, vnv, top5) -> bytes:
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
    return xbuf.getvalue()


# ---- Entry point for the app ----
def run_pipeline(menu_csv, sales_csv):
    menu, sales = load_data(menu_csv, sales_csv)
    df, daily, vnv, top5 = pandas_phase(menu, sales)
    daily = numpy_phase(daily)
    excel_bytes = build_excel(df, daily, vnv, top5)
    return {
        "df": df,
        "daily": daily,
        "vnv": vnv,
        "top5": top5,
        "excel_bytes": excel_bytes,
    }
