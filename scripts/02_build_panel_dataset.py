"""
Builds a balanced company-category-year panel from cleaned BHRC event data.

Input:
- company_ids.csv
- events_clean.csv

Output:
- panel_by_company_category_year.csv
"""

from pathlib import Path
import pandas as pd


# ============================================================
# PATHS
# ============================================================

COMPANY_FILE = Path("data/output/company_ids.csv")
EVENTS_FILE = Path("data/output/events_clean.csv")
OUTPUT_FILE = Path("data/output/panel_by_company_category_year.csv")


# ============================================================
# LOAD DATA
# ============================================================

companies = pd.read_csv(COMPANY_FILE)
events = pd.read_csv(EVENTS_FILE)

companies.columns = companies.columns.str.strip().str.lower()
events.columns = events.columns.str.strip().str.lower()


# ============================================================
# CLEAN YEAR
# ============================================================

events["year"] = pd.to_numeric(events["year"], errors="coerce")
events = events.dropna(subset=["year"]).copy()
events["year"] = events["year"].astype(int)

first_year = int(events["year"].min())
last_year = int(events["year"].max())
years = list(range(first_year, last_year + 1))

print(f"First recorded event year: {first_year}")
print(f"Last recorded event year: {last_year}")


# ============================================================
# BUILD BALANCED COMPANY-CATEGORY-YEAR GRID
# ============================================================

categories = ["hrd_attacks", "lawsuits", "other_allegations"]

base = companies.merge(
    pd.DataFrame({"category": categories}),
    how="cross"
)

full_grid = base.merge(
    pd.DataFrame({"year": years}),
    how="cross"
)


# ============================================================
# COUNT EVENTS
# ============================================================

counts = (
    events
    .groupby(["ric", "category", "year"])
    .size()
    .reset_index(name="n_events")
)

panel_long = full_grid.merge(
    counts,
    on=["ric", "category", "year"],
    how="left"
)

panel_long["n_events"] = panel_long["n_events"].fillna(0).astype(int)


# ============================================================
# WIDE PANEL
# ============================================================

panel = (
    panel_long
    .pivot_table(
        index=[
            "ric",
            "company_name",
            "name_bhrc",
            "company_id",
            "url_bhrc",
            "category"
        ],
        columns="year",
        values="n_events",
        aggfunc="sum",
        fill_value=0
    )
    .reset_index()
)

fixed_cols = [
    "ric",
    "company_name",
    "name_bhrc",
    "company_id",
    "url_bhrc",
    "category"
]

panel = panel[fixed_cols + years]
panel.columns = [str(col) for col in panel.columns]


# ============================================================
# SAVE
# ============================================================

panel.to_csv(OUTPUT_FILE, index=False)

print(f"Panel saved to: {OUTPUT_FILE}")
print(f"Companies: {len(companies)}")
print(f"Categories: {len(categories)}")
print(f"Expected rows: {len(companies) * len(categories)}")
print(f"Actual rows: {len(panel)}")
