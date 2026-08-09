"""
Risk Scoring Engine
====================
Computes composite risk scores for each drug based on four weighted signals:
  - Recurrence Frequency (30%): How often has this drug experienced shortages?
  - Shortage Duration (25%): Average days in shortage state.
  - Cause Severity (25%): Severity of the underlying shortage cause.
  - Current Status (20%): Active shortages receive a multiplier.

"""

import json
import os
from collections import Counter, defaultdict


# CAUSE SEVERITY
# Higher scores = deeper structural risk to supply chain

CAUSE_SEVERITY = {
    "Raw Material / API Shortage": 1.0,     # Upstream dependency failure
    "Manufacturing / Quality": 0.85,        # GMP violations, facility issues
    "Discontinuation": 0.80,                # Permanent supply loss
    "Regulatory": 0.70,                     # Compliance-driven disruption
    "Shipping / Logistics Delay": 0.50,     # Transient logistics issue
    "Demand Increase": 0.40,                # Demand-side spike (usually temporary)
    "Other / Unspecified": 0.50,            # Insufficient signal
}


def compute_drug_scores(cleaned_records):
    """
    Compute composite risk scores for all unique drugs.

    Parameters
    ----------
    cleaned_records : list[dict]
        Output from the ETL pipeline.

    Returns
    -------
    list[dict]
        Sorted list of drug risk profiles (highest risk first).
    """
    # Group records by drug
    drug_records = defaultdict(list)
    for r in cleaned_records:
        drug_records[r["generic_name"]].append(r)

    # Global normalization parameters
    all_recurrence = [len(recs) for recs in drug_records.values()]
    all_durations = [r["duration_days"] for r in cleaned_records if r["duration_days"] > 0]
    max_recurrence = max(all_recurrence)
    max_duration = max(all_durations) if all_durations else 1

    drug_scores = []

    for drug, recs in drug_records.items():
        n = len(recs)

        # Signal 1: Recurrence Frequency (30%)
        recurrence_score = min(n / max_recurrence, 1.0)

        #  Signal 2: Shortage Duration (25%)
        durations = [r["duration_days"] for r in recs if r["duration_days"] > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0
        duration_score = min(avg_duration / max_duration, 1.0)

        # ── Signal 3: Cause Severity (25%) 
        # Take maximum severity observed across all shortage events
        severities = [CAUSE_SEVERITY.get(r["shortage_reason"], 0.5) for r in recs]
        cause_score = max(severities)

        # ── Signal 4: Current Status (20%) 
        has_current = any(r["status"] == "Current" for r in recs)
        has_unavailable = any(r["availability"] == "Unavailable" for r in recs)

        if has_current and has_unavailable:
            status_score = 1.0      # Active + unavailable = maximum urgency
        elif has_current:
            status_score = 0.8      # Active but partially available
        else:
            status_score = 0.2      # Resolved/Discontinued

        # Composite Score
        composite = (
            0.30 * recurrence_score
            + 0.25 * duration_score
            + 0.25 * cause_score
            + 0.20 * status_score
        ) * 100  # Scale to 0-100

        # Metadata
        categories = []
        for r in recs:
            categories.extend(r["therapeutic_categories"])
        top_category = Counter(categories).most_common(1)[0][0] if categories else "Unknown"

        drug_scores.append({
            "drug": drug,
            "risk_score": round(composite, 1),
            "risk_level": _risk_level(composite),
            "recurrence_count": n,
            "recurrence_score": round(recurrence_score * 100, 1),
            "avg_duration_days": int(avg_duration),
            "duration_score": round(duration_score * 100, 1),
            "max_cause_severity": round(cause_score * 100, 1),
            "cause_severity_score": round(cause_score * 100, 1),
            "primary_reason": Counter(r["shortage_reason"] for r in recs).most_common(1)[0][0],
            "all_reasons": list(set(r["shortage_reason"] for r in recs)),
            "status_score": round(status_score * 100, 1),
            "current_status": "Active Shortage" if has_current else "Resolved/Discontinued",
            "primary_category": top_category,
            "all_categories": list(set(categories)),
            "companies": list(set(r["company_name"] for r in recs)),
            "num_companies": len(set(r["company_name"] for r in recs)),
            "dosage_form": recs[0]["dosage_form"],
        })

    # Sort by risk score descending
    drug_scores.sort(key=lambda x: x["risk_score"], reverse=True)

    return drug_scores


def _risk_level(score):
    """Map composite score to categorical risk level."""
    if score >= 70:
        return "CRITICAL"
    elif score >= 50:
        return "HIGH"
    elif score >= 30:
        return "MODERATE"
    return "LOW"


def print_risk_report(drug_scores, top_n=20):
    """Print a formatted risk leaderboard to stdout."""
    print("\n" + "=" * 80)
    print("RISK LEADERBOARD — Top {} Highest-Risk Drugs".format(top_n))
    print("=" * 80)
    print(f"{'Rank':<5} {'Risk':>5} {'Level':<10} {'Recur':>6} {'AvgDur':>8} {'Status':<12} Drug")
    print("-" * 80)

    for i, d in enumerate(drug_scores[:top_n]):
        print(
            f"{i+1:<5} {d['risk_score']:>5.1f} {d['risk_level']:<10} "
            f"{d['recurrence_count']:>5}× {d['avg_duration_days']:>6}d "
            f"{'●' if d['current_status'] == 'Active Shortage' else '○':<1} "
            f"{d['current_status']:<12} {d['drug'][:50]}"
        )

    # Summary stats
    critical = sum(1 for d in drug_scores if d["risk_level"] == "CRITICAL")
    high = sum(1 for d in drug_scores if d["risk_level"] == "HIGH")
    active = sum(1 for d in drug_scores if d["current_status"] == "Active Shortage")

    print(f"\n  Total drugs scored: {len(drug_scores)}")
    print(f"  CRITICAL risk: {critical}")
    print(f"  HIGH risk: {high}")
    print(f"  Active shortages: {active}")


if __name__ == "__main__":
    INPUT_FILE = "data/processed/fda_shortages_cleaned.json"
    OUTPUT_FILE = "data/processed/drug_risk_scores.json"

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run etl_pipeline.py first.")
        exit(1)

    with open(INPUT_FILE) as f:
        cleaned = json.load(f)

    scores = compute_drug_scores(cleaned)
    print_risk_report(scores)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(scores, f, indent=2)
    print(f"\nSaved risk scores to {OUTPUT_FILE}")
