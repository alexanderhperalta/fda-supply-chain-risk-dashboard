"""
Ingests raw shortage data from the FDA openFDA API, cleans and standardizes
fields, computes derived features, and outputs a dataset.

Data Source: https://api.fda.gov/drug/shortages.json
"""

import requests
import json
import time
import os
from datetime import datetime
from collections import Counter, defaultdict


# Configuration

API_BASE = "https://api.fda.gov/drug/shortages.json"
LIMIT = 100
OUTPUT_RAW = "data/raw/fda_shortages_raw.json"
OUTPUT_CLEAN = "data/processed/fda_shortages_cleaned.json"
RATE_LIMIT_DELAY = 0.5


# Ingestion

def fetch_all_records():
    """Pull all shortage records from the FDA openFDA API with pagination."""
    session = requests.Session()
    all_results = []
    skip = 0

    # First call to get total count
    r = session.get(f"{API_BASE}?limit=1", timeout=30)
    r.raise_for_status()
    total = r.json()["meta"]["results"]["total"]
    print(f"Total records available: {total}")

    while skip < total:
        print(f"  Fetching records {skip} to {skip + LIMIT}...")
        r = session.get(f"{API_BASE}?limit={LIMIT}&skip={skip}", timeout=30)

        if r.status_code != 200:
            print(f"  Error {r.status_code}, retrying...")
            time.sleep(2)
            continue

        data = r.json()
        results = data.get("results", [])

        if not results:
            break

        all_results.extend(results)
        skip += LIMIT
        time.sleep(RATE_LIMIT_DELAY)

    print(f"Fetched {len(all_results)} total records.")
    return all_results


# Cleaning and standardization

def parse_date(date_str):
    """Parse FDA date formats into datetime objects."""
    if not date_str:
        return None
    for fmt in ["%m/%d/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return None


# Canonical shortage reason categories
REASON_MAP = {
    "discontinu": "Discontinuation",
    "active ingredient": "Raw Material / API Shortage",
    "inactive ingredient": "Raw Material / API Shortage",
    "raw material": "Raw Material / API Shortage",
    "manufacturing": "Manufacturing / Quality",
    "good manufacturing": "Manufacturing / Quality",
    "demand": "Demand Increase",
    "shipping": "Shipping / Logistics Delay",
    "delay": "Shipping / Logistics Delay",
    "regulatory": "Regulatory",
}


def standardize_reason(shortage_reason, related_info):
    reason = (shortage_reason or "").lower().strip()
    related = (related_info or "").lower().strip()

    combined = reason + " " + related
    for keyword, category in REASON_MAP.items():
        if keyword in combined:
            return category

    # Infer from related_info patterns
    if "backorder" in related or "recovery" in related:
        return "Manufacturing / Quality"
    if "allocation" in related:
        return "Demand Increase"

    return "Other / Unspecified"


def standardize_availability(availability):
    """Normalize availability strings (includes typos in source data)."""
    av = (availability or "").lower().strip()
    if "unavailable" in av:
        return "Unavailable"
    if "limited" in av:
        return "Limited"
    if "available" in av:
        return "Available"
    if "pending" in av:
        return "Pending"
    return "Unknown"


def clean_record(raw):
    """Transform a raw FDA record into a standardized record."""
    posting_date = parse_date(raw.get("initial_posting_date"))
    update_date = parse_date(raw.get("update_date"))

    # Compute shortage duration in days
    duration_days = 0
    if posting_date and update_date:
        duration_days = max((update_date - posting_date).days, 0)

    # Extract openFDA enrichment fields
    openfda = raw.get("openfda", {})

    return {
        "generic_name": raw.get("generic_name", ""),
        "company_name": raw.get("company_name", ""),
        "status": raw.get("status", ""),
        "shortage_reason": standardize_reason(
            raw.get("shortage_reason"), raw.get("related_info")
        ),
        "shortage_reason_raw": raw.get("shortage_reason", ""),
        "availability": standardize_availability(raw.get("availability")),
        "therapeutic_categories": raw.get("therapeutic_category", []),
        "primary_category": raw.get("therapeutic_category", ["Unknown"])[0],
        "dosage_form": raw.get("dosage_form", ""),
        "presentation": raw.get("presentation", ""),
        "initial_posting_date": raw.get("initial_posting_date", ""),
        "update_date": raw.get("update_date", ""),
        "posting_year": posting_date.year if posting_date else None,
        "posting_month": posting_date.month if posting_date else None,
        "duration_days": duration_days,
        "manufacturer": openfda.get("manufacturer_name", [""])[0] if openfda else raw.get("company_name", ""),
        "route": openfda.get("route", [""])[0] if openfda else "",
        "product_type": openfda.get("product_type", [""])[0] if openfda else "",
        "package_ndc": raw.get("package_ndc", ""),
    }


def run_pipeline(raw_data=None):
    """
    Execute the full ETL pipeline.

    If raw_data is None, fetches from the FDA API.
    Returns cleaned records.
    """
    if raw_data is None:
        print("=" * 60)
        print("STEP 1: INGESTION — Fetching from FDA openFDA API")
        print("=" * 60)
        raw_data = fetch_all_records()

        os.makedirs(os.path.dirname(OUTPUT_RAW), exist_ok=True)
        with open(OUTPUT_RAW, "w") as f:
            json.dump(raw_data, f)
        print(f"Saved raw data to {OUTPUT_RAW}")

    print("\n" + "=" * 60)
    print("STEP 2: CLEANING & STANDARDIZATION")
    print("=" * 60)

    cleaned = [clean_record(r) for r in raw_data]

    # Summary statistics
    print(f"  Records processed: {len(cleaned)}")
    print(f"  Unique drugs: {len(set(r['generic_name'] for r in cleaned))}")
    print(f"  Unique companies: {len(set(r['company_name'] for r in cleaned))}")
    print(f"  Status distribution:")
    for status, count in Counter(r["status"] for r in cleaned).most_common():
        print(f"    {status}: {count}")
    print(f"  Reason distribution:")
    for reason, count in Counter(r["shortage_reason"] for r in cleaned).most_common():
        print(f"    {reason}: {count}")

    os.makedirs(os.path.dirname(OUTPUT_CLEAN), exist_ok=True)
    with open(OUTPUT_CLEAN, "w") as f:
        json.dump(cleaned, f, indent=2)
    print(f"\nSaved cleaned data to {OUTPUT_CLEAN}")

    return cleaned


if __name__ == "__main__":
    if os.path.exists(OUTPUT_RAW):
        print(f"Found existing raw data at {OUTPUT_RAW}")
        with open(OUTPUT_RAW) as f:
            raw = json.load(f)
        run_pipeline(raw)
    else:
        run_pipeline()
