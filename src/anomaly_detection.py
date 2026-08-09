"""
Anomaly Detection Module
Identifies therapeutic categories and individual drugs with statistically
unusual shortage patterns using Z-score analysis.
"""

import json
import os
import numpy as np
from collections import Counter, defaultdict


def detect_category_anomalies(cleaned_records, z_threshold=1.5):
    """
    Z-score analysis on shortage frequency by therapeutic category.

    Identifies categories experiencing disproportionate disruption
    relative to the overall distribution.

    Parameters
    ----------
    cleaned_records : list[dict]
        Cleaned shortage records from the ETL pipeline.
    z_threshold : float
        Z-score threshold for flagging anomalies (default: 1.5).

    Returns
    -------
    list[dict]
        Category anomaly analysis results, sorted by z-score descending.
    """
    # Count shortages per therapeutic category
    category_counts = Counter()
    for r in cleaned_records:
        for cat in r["therapeutic_categories"]:
            category_counts[cat] += 1

    counts = np.array(list(category_counts.values()))
    mean_count = float(np.mean(counts))
    std_count = float(np.std(counts))

    results = []
    for cat, count in category_counts.most_common():
        z_score = (count - mean_count) / std_count if std_count > 0 else 0
        is_anomaly = abs(z_score) > z_threshold

        results.append({
            "category": cat,
            "shortage_count": int(count),
            "z_score": round(z_score, 3),
            "is_anomaly": is_anomaly,
            "direction": "over-represented" if z_score > 0 else "under-represented",
            "mean": round(mean_count, 1),
            "std": round(std_count, 1),
        })

    results.sort(key=lambda x: x["z_score"], reverse=True)
    return results


def detect_temporal_anomalies(cleaned_records, window_months=6):
    """
    Time-series trend detection to flag accelerating shortage rates.

    Computes a rolling average of monthly shortage counts and flags
    periods where the rate exceeds 2 standard deviations above the mean.

    Parameters
    ----------
    cleaned_records : list[dict]
        Cleaned shortage records.
    window_months : int
        Rolling window size for trend detection.

    Returns
    -------
    dict
        Temporal analysis with monthly counts and anomaly flags.
    """
    # Aggregate by year-month
    monthly_counts = defaultdict(int)
    for r in cleaned_records:
        if r["posting_year"] and r["posting_month"]:
            key = f"{r['posting_year']}-{r['posting_month']:02d}"
            monthly_counts[key] += 1

    sorted_months = sorted(monthly_counts.keys())
    counts = [monthly_counts[m] for m in sorted_months]

    if len(counts) < window_months:
        return {"monthly": [], "anomalies": []}

    # Compute rolling statistics
    monthly_results = []
    anomalies = []

    for i, month in enumerate(sorted_months):
        count = counts[i]

        # Rolling window stats
        if i >= window_months:
            window = counts[i - window_months : i]
            rolling_mean = np.mean(window)
            rolling_std = np.std(window)
            z_score = (count - rolling_mean) / rolling_std if rolling_std > 0 else 0
            is_anomaly = z_score > 2.0
        else:
            rolling_mean = np.mean(counts[: i + 1])
            rolling_std = np.std(counts[: i + 1])
            z_score = 0
            is_anomaly = False

        entry = {
            "period": month,
            "count": int(count),
            "rolling_mean": round(float(rolling_mean), 1),
            "rolling_std": round(float(rolling_std), 1),
            "z_score": round(float(z_score), 2),
            "is_anomaly": is_anomaly,
        }
        monthly_results.append(entry)
        if is_anomaly:
            anomalies.append(entry)

    return {"monthly": monthly_results, "anomalies": anomalies}


def detect_drug_recurrence_anomalies(drug_scores, z_threshold=2.0):
    """
    Flag individual drugs with anomalously high recurrence rates.

    Parameters
    ----------
    drug_scores : list[dict]
        Output from the risk scoring engine.
    z_threshold : float
        Z-score threshold for flagging.

    Returns
    -------
    list[dict]
        Drugs with anomalous recurrence patterns.
    """
    recurrence_counts = [d["recurrence_count"] for d in drug_scores]
    mean_r = np.mean(recurrence_counts)
    std_r = np.std(recurrence_counts)

    anomalies = []
    for d in drug_scores:
        z = (d["recurrence_count"] - mean_r) / std_r if std_r > 0 else 0
        if z > z_threshold:
            anomalies.append({
                "drug": d["drug"],
                "recurrence_count": d["recurrence_count"],
                "z_score": round(float(z), 2),
                "risk_score": d["risk_score"],
                "primary_category": d["primary_category"],
                "current_status": d["current_status"],
            })

    anomalies.sort(key=lambda x: x["z_score"], reverse=True)
    return anomalies


def print_anomaly_report(category_anomalies, temporal_result, drug_anomalies):
    """Print a formatted anomaly detection report."""
    print("\n" + "=" * 70)
    print("ANOMALY DETECTION REPORT")
    print("=" * 70)

    # Category anomalies
    flagged = [a for a in category_anomalies if a["is_anomaly"]]
    print(f"\n{'─' * 70}")
    print(f"CATEGORY ANOMALIES (|z| > 1.5)")
    print(f"{'─' * 70}")
    print(f"  Mean shortages/category: {category_anomalies[0]['mean']}")
    print(f"  Std deviation: {category_anomalies[0]['std']}")
    print(f"  Flagged categories: {len(flagged)}\n")

    for a in category_anomalies:
        flag = " ◀ ANOMALY" if a["is_anomaly"] else ""
        print(f"  {a['category']:<30} {a['shortage_count']:>5} shortages  z = {a['z_score']:>6.2f}{flag}")

    # Temporal anomalies
    if temporal_result["anomalies"]:
        print(f"\n{'─' * 70}")
        print(f"TEMPORAL ANOMALIES (z > 2.0, 6-month rolling window)")
        print(f"{'─' * 70}")
        for a in temporal_result["anomalies"]:
            print(f"  {a['period']}: {a['count']} shortages (rolling avg: {a['rolling_mean']}, z = {a['z_score']})")

    # Drug recurrence anomalies
    if drug_anomalies:
        print(f"\n{'─' * 70}")
        print(f"DRUG RECURRENCE ANOMALIES (z > 2.0)")
        print(f"{'─' * 70}")
        for a in drug_anomalies:
            print(f"  {a['drug'][:45]:<45} {a['recurrence_count']:>3}× (z = {a['z_score']}, risk = {a['risk_score']})")


if __name__ == "__main__":
    CLEAN_FILE = "data/processed/fda_shortages_cleaned.json"
    SCORES_FILE = "data/processed/drug_risk_scores.json"
    OUTPUT_FILE = "data/processed/anomaly_results.json"

    if not os.path.exists(CLEAN_FILE):
        print(f"Error: {CLEAN_FILE} not found. Run etl_pipeline.py first.")
        exit(1)

    with open(CLEAN_FILE) as f:
        cleaned = json.load(f)

    # Load drug scores if available
    drug_scores = []
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE) as f:
            drug_scores = json.load(f)

    # Run all anomaly detection
    cat_anomalies = detect_category_anomalies(cleaned)
    temporal = detect_temporal_anomalies(cleaned)
    drug_anomalies = detect_drug_recurrence_anomalies(drug_scores) if drug_scores else []

    print_anomaly_report(cat_anomalies, temporal, drug_anomalies)

    # Save results
    output = {
        "category_anomalies": cat_anomalies,
        "temporal_anomalies": temporal,
        "drug_recurrence_anomalies": drug_anomalies,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved anomaly results to {OUTPUT_FILE}")
