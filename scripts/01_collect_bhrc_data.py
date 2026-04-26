"""
Collects company-level human rights controversy data from
Business & Human Rights Resource Centre (BHRC).

The script:
1. Loads a mapped list of companies and BHRC URLs
2. Removes companies not matched to BHRC
3. Extracts BHRC company IDs
4. Collects HRD attacks, lawsuits, and other allegations
5. Cleans and exports event-level and summary outputs
"""

import re
import time
import random
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
import requests


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = Path("data/input/stoxx_bhrc_company_mapping.csv")
OUTPUT_DIR = Path("data/output")

BASE = "https://www.business-humanrights.org"
API = f"{BASE}/en/api/internal/explore/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

N_TEST = None  # set to e.g. 30 for testing, or None for full run

PAGE_LIMIT = 50
REQUEST_TIMEOUT = 30
MAX_RETRIES = 4

MIN_SLEEP = 1.0
MAX_SLEEP = 2.0


# ============================================================
# OUTPUT FILES
# ============================================================

OUTPUT_COMPANY_IDS = OUTPUT_DIR / "company_ids.csv"
OUTPUT_EVENTS_RAW = OUTPUT_DIR / "events_raw.csv"
OUTPUT_EVENTS_CLEAN = OUTPUT_DIR / "events_clean.csv"
OUTPUT_SUMMARY = OUTPUT_DIR / "summary_by_company_category.csv"
OUTPUT_BY_YEAR = OUTPUT_DIR / "summary_by_year_long.csv"
OUTPUT_FAILED = OUTPUT_DIR / "failures.csv"


# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HELPERS
# ============================================================

def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def polite_sleep(min_s: float = MIN_SLEEP, max_s: float = MAX_SLEEP) -> None:
    time.sleep(random.uniform(min_s, max_s))


def safe_get(url: str, params: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)

            if response.status_code == 403:
                wait_time = 5 * attempt
                print(
                    f"[WARN] 403 for {url} | "
                    f"attempt {attempt}/{MAX_RETRIES} | "
                    f"sleeping {wait_time}s"
                )
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            return response

        except Exception as e:
            last_error = e

            if attempt < MAX_RETRIES:
                wait_time = 2 * attempt
                print(
                    f"[RETRY] {url} | "
                    f"attempt {attempt}/{MAX_RETRIES} | "
                    f"error: {e} | sleeping {wait_time}s"
                )
                time.sleep(wait_time)
            else:
                raise last_error

    raise last_error


def load_companies() -> pd.DataFrame:
    companies = pd.read_csv(INPUT_FILE)
    companies.columns = companies.columns.str.strip().str.lower()
    companies = companies.loc[:, ~companies.columns.str.contains("^unnamed", case=False)]

    required_cols = {"ric", "company_name", "name_bhrc", "url_bhrc"}
    missing = required_cols - set(companies.columns)

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    na_values = ["N/A", "n/a", "NA", "na", "", "None", "none"]

    companies[["name_bhrc", "url_bhrc"]] = (
        companies[["name_bhrc", "url_bhrc"]]
        .replace(na_values, pd.NA)
    )

    companies = companies.dropna(subset=["name_bhrc", "url_bhrc"]).copy()

    if N_TEST is not None:
        companies = companies.head(N_TEST).copy()

    print(f"[INFO] Companies kept for scraping: {len(companies)}")

    return companies


def fetch_all(params: dict, limit: int = PAGE_LIMIT):
    results_all = []
    offset = 0

    while True:
        params_page = dict(params)
        params_page["limit"] = limit
        params_page["offset"] = offset

        response = safe_get(API, params=params_page)
        data = response.json()

        results = data.get("results", [])
        results_all.extend(results)

        if not data.get("next") or not results:
            break

        offset += limit
        polite_sleep()

    return results_all


def extract_company_id_from_profile(url_bhrc: str) -> Optional[int]:
    response = safe_get(url_bhrc)
    html = response.text

    match = re.search(r"companies=(\d+)", html)

    if not match:
        return None

    return int(match.group(1))


def items_to_rows(items, ric, company_name, name_bhrc, company_id, category):
    rows = []

    for item in items:
        date_raw = item.get("backdate")
        year = (
            date_raw[:4]
            if isinstance(date_raw, str) and len(date_raw) >= 4
            else None
        )

        rel_url = item.get("translated_url")
        full_url = urljoin(BASE, rel_url) if rel_url else None

        rows.append({
            "ric": ric,
            "company_name": company_name,
            "name_bhrc": name_bhrc,
            "company_id": company_id,
            "category": category,
            "date_raw": date_raw,
            "year": year,
            "url": full_url,
        })

    return rows


def clean_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events

    events = events.copy()

    events["date"] = pd.to_datetime(events["date_raw"], errors="coerce")
    events["year"] = events["date"].dt.year.astype("Int64")

    events = events.drop_duplicates(
        subset=["ric", "company_id", "category", "url", "date_raw"]
    )

    category_counts = (
        events
        .groupby(["ric", "company_id", "url"])["category"]
        .nunique()
        .reset_index(name="n_categories_for_event")
    )

    events = events.merge(
        category_counts,
        on=["ric", "company_id", "url"],
        how="left"
    )

    events["overlap_flag"] = events["n_categories_for_event"] > 1
    events["exclusive_category"] = events["category"]

    overlap_keys = set(
        events.loc[
            events["category"].isin(["hrd_attacks", "lawsuits"]),
            ["ric", "company_id", "url"]
        ].itertuples(index=False, name=None)
    )

    def make_exclusive_category(row):
        key = (row["ric"], row["company_id"], row["url"])

        if (
            row["category"] == "other_allegations"
            and key in overlap_keys
        ):
            return "overlap_with_specific_category"

        return row["category"]

    events["exclusive_category"] = events.apply(
        make_exclusive_category,
        axis=1
    )

    return events.sort_values(
        ["ric", "category", "date"],
        ascending=[True, True, False]
    )


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_output_dir()

    companies = load_companies()

    company_ids = []
    failed_company_id = []

    print("[INFO] Extracting BHRC company IDs")

    for i, (_, row) in enumerate(companies.iterrows(), start=1):
        url = row["url_bhrc"]
        name_bhrc = row["name_bhrc"]

        try:
            company_id = extract_company_id_from_profile(url)

            if company_id is None:
                print(f"[WARN] [{i}/{len(companies)}] No company_id found for {name_bhrc}")
                failed_company_id.append({
                    "ric": row["ric"],
                    "company_name": row["company_name"],
                    "name_bhrc": name_bhrc,
                    "url_bhrc": url,
                    "stage": "extract_company_id",
                    "error": "No company_id found"
                })
            else:
                print(f"[OK] [{i}/{len(companies)}] {name_bhrc}: {company_id}")

        except Exception as e:
            print(f"[FAIL] [{i}/{len(companies)}] Could not extract ID for {name_bhrc}: {e}")
            company_id = None

            failed_company_id.append({
                "ric": row["ric"],
                "company_name": row["company_name"],
                "name_bhrc": name_bhrc,
                "url_bhrc": url,
                "stage": "extract_company_id",
                "error": str(e)
            })

        company_ids.append(company_id)
        polite_sleep()

    companies["company_id"] = company_ids
    companies.to_csv(OUTPUT_COMPANY_IDS, index=False)

    matched = companies.dropna(subset=["company_id"]).copy()
    matched["company_id"] = matched["company_id"].astype(int)

    print(f"[INFO] Companies in input: {len(companies)}")
    print(f"[INFO] Companies matched to BHRC ID: {len(matched)}")
    print(f"[INFO] Companies missing BHRC ID: {len(companies) - len(matched)}")

    all_rows = []
    failed_scrapes = []

    print("[INFO] Collecting controversy records")

    for i, (_, row) in enumerate(matched.iterrows(), start=1):
        ric = row["ric"]
        company_name = row["company_name"]
        name_bhrc = row["name_bhrc"]
        url_bhrc = row["url_bhrc"]
        company_id = row["company_id"]

        try:
            attacks = fetch_all({
                "companies": company_id,
                "content_types": ["attacks", "slapp"]
            })
            all_rows += items_to_rows(
                attacks,
                ric,
                company_name,
                name_bhrc,
                company_id,
                "hrd_attacks"
            )
            polite_sleep()

            lawsuits = fetch_all({
                "companies": company_id,
                "content_types": ["lawsuits"]
            })
            all_rows += items_to_rows(
                lawsuits,
                ric,
                company_name,
                name_bhrc,
                company_id,
                "lawsuits"
            )
            polite_sleep()

            allegations = fetch_all({
                "companies": company_id,
                "contains_allegations": "YES"
            })
            all_rows += items_to_rows(
                allegations,
                ric,
                company_name,
                name_bhrc,
                company_id,
                "other_allegations"
            )
            polite_sleep()

            print(
                f"[OK] [{i}/{len(matched)}] {ric} | {name_bhrc}: "
                f"{len(attacks)} attacks, "
                f"{len(lawsuits)} lawsuits, "
                f"{len(allegations)} allegations"
            )

        except Exception as e:
            print(f"[FAIL] [{i}/{len(matched)}] Scrape failed for {ric} | {name_bhrc}: {e}")

            failed_scrapes.append({
                "ric": ric,
                "company_name": company_name,
                "name_bhrc": name_bhrc,
                "company_id": company_id,
                "url_bhrc": url_bhrc,
                "stage": "scrape_events",
                "error": str(e)
            })

        polite_sleep()

    events_raw = pd.DataFrame(all_rows)
    events_raw.to_csv(OUTPUT_EVENTS_RAW, index=False)

    events_clean = clean_events(events_raw)
    events_clean.to_csv(OUTPUT_EVENTS_CLEAN, index=False)

    if not events_clean.empty:
        summary = (
            events_clean
            .groupby([
                "ric",
                "company_name",
                "name_bhrc",
                "company_id",
                "category"
            ])
            .size()
            .reset_index(name="n_items")
        )

        summary.to_csv(OUTPUT_SUMMARY, index=False)

        by_year = (
            events_clean
            .groupby([
                "ric",
                "company_name",
                "name_bhrc",
                "company_id",
                "category",
                "year"
            ])
            .size()
            .reset_index(name="n_items")
        )

        by_year.to_csv(OUTPUT_BY_YEAR, index=False)

    else:
        pd.DataFrame().to_csv(OUTPUT_SUMMARY, index=False)
        pd.DataFrame().to_csv(OUTPUT_BY_YEAR, index=False)

    failures = pd.DataFrame(failed_company_id + failed_scrapes)
    failures.to_csv(OUTPUT_FAILED, index=False)

    print("\n[DONE] Saved:")
    print(f" - Company IDs:   {OUTPUT_COMPANY_IDS}")
    print(f" - Raw events:    {OUTPUT_EVENTS_RAW}")
    print(f" - Clean events:  {OUTPUT_EVENTS_CLEAN}")
    print(f" - Summary:       {OUTPUT_SUMMARY}")
    print(f" - By year:       {OUTPUT_BY_YEAR}")
    print(f" - Failures:      {OUTPUT_FAILED}")


if __name__ == "__main__":
    main()
