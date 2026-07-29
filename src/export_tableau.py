"""Export processed pipeline output to Tableau-ready flat CSVs.

Tableau (and Tableau Public in particular) wants tidy, flat, one-row-per-thing
tables. The processed JSON has nested list fields (therapeutic_categories,
companies, all_reasons) which Tableau cannot read, so those are exploded into
separate bridge tables and ALSO kept as pipe-joined strings for tooltips.

Outputs land in data/tableau/. Run: python -m src.export_tableau
"""

import csv
import json
import os
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(BASE, "data", "processed")
OUT = os.path.join(BASE, "data", "tableau")

# Cause severity lookup, mirrored from the risk scoring methodology so the
# Tableau workbook can show the weight table without recomputing it.
CAUSE_SEVERITY = {
    "Raw Material / API Shortage": 100,
    "Manufacturing / Quality": 85,
    "Discontinuation": 80,
    "Regulatory": 70,
    "Shipping / Logistics Delay": 50,
    "Demand Increase": 40,
    "Other / Unspecified": 30,
}

SCORE_WEIGHTS = [
    ("Recurrence Frequency", 0.30, "recurrence_score", "recurrence_count"),
    ("Shortage Duration", 0.25, "duration_score", "avg_duration_days"),
    ("Cause Severity", 0.25, "cause_severity_score", None),
    ("Current Status", 0.20, "status_score", None),
]


def load(name):
    with open(os.path.join(PROCESSED, name)) as f:
        return json.load(f)


def write_csv(name, rows, fieldnames):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  {name:<38} {len(rows):>6,} rows")
    return path


def iso_date(value):
    """FDA dates arrive as MM/DD/YYYY. Emit ISO so Tableau parses them
    regardless of the workbook locale."""
    if not value:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def truthy(value):
    """anomaly_results.json mixes real bools with the strings 'True'/'False'."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def risk_band(score):
    if score >= 70:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 30:
        return "MODERATE"
    return "LOW"


def pipe(values):
    return " | ".join(values) if values else ""


# ── 1. Fact table: one row per FDA shortage event ────────────────────────

def export_events(events):
    rows, bridge = [], []
    for i, e in enumerate(events, start=1):
        year, month = e.get("posting_year"), e.get("posting_month")
        month_date = f"{year:04d}-{month:02d}-01" if year and month else ""
        cats = e.get("therapeutic_categories") or []
        duration = e.get("duration_days") or 0
        status = e.get("status") or ""

        rows.append({
            "event_id": i,
            "generic_name": e.get("generic_name", ""),
            "company_name": e.get("company_name", ""),
            "manufacturer": e.get("manufacturer", ""),
            "status": status,
            "is_active": "TRUE" if "current" in status.lower() or "active" in status.lower() else "FALSE",
            "availability": e.get("availability", ""),
            "shortage_reason": e.get("shortage_reason", ""),
            "cause_severity": CAUSE_SEVERITY.get(e.get("shortage_reason", ""), ""),
            "primary_category": e.get("primary_category", ""),
            "therapeutic_categories": pipe(cats),
            "category_count": len(cats),
            "dosage_form": e.get("dosage_form", ""),
            "route": e.get("route", ""),
            "product_type": e.get("product_type", ""),
            "initial_posting_date": iso_date(e.get("initial_posting_date")),
            "update_date": iso_date(e.get("update_date")),
            "posting_year": year or "",
            "posting_month": month or "",
            "posting_month_date": month_date,
            "duration_days": duration,
            "duration_years": round(duration / 365.0, 2),
            "package_ndc": e.get("package_ndc", ""),
            "presentation": e.get("presentation", ""),
        })
        for c in cats:
            bridge.append({"event_id": i, "therapeutic_category": c})

    write_csv("shortage_events.csv", rows, list(rows[0].keys()))
    write_csv("event_categories.csv", bridge, ["event_id", "therapeutic_category"])
    return rows


# ── 2. Drug-level risk scores + bridges + score decomposition ────────────

def export_drug_scores(scores):
    rows, cat_bridge, co_bridge, reason_bridge, components = [], [], [], [], []

    for d in scores:
        drug = d["drug"]
        score = d["risk_score"]
        cats = d.get("all_categories") or []
        cos = d.get("companies") or []
        reasons = d.get("all_reasons") or []
        avg_days = d.get("avg_duration_days") or 0
        n_co = d.get("num_companies") or 0

        rows.append({
            "drug": drug,
            "risk_score": score,
            "risk_level": d.get("risk_level", risk_band(score)),
            "risk_band_calc": risk_band(score),
            "recurrence_count": d.get("recurrence_count", 0),
            "recurrence_score": d.get("recurrence_score", 0),
            "avg_duration_days": avg_days,
            "avg_duration_years": round(avg_days / 365.0, 2),
            "duration_score": d.get("duration_score", 0),
            "max_cause_severity": d.get("max_cause_severity", 0),
            "cause_severity_score": d.get("cause_severity_score", 0),
            "primary_reason": d.get("primary_reason", ""),
            "all_reasons": pipe(reasons),
            "status_score": d.get("status_score", 0),
            "current_status": d.get("current_status", ""),
            "is_active": "TRUE" if d.get("current_status") == "Active Shortage" else "FALSE",
            "primary_category": d.get("primary_category", ""),
            "all_categories": pipe(cats),
            "category_count": len(cats),
            "companies": pipe(cos),
            "num_companies": n_co,
            "is_single_source": "TRUE" if n_co <= 1 else "FALSE",
            "dosage_form": d.get("dosage_form", ""),
        })

        for c in cats:
            cat_bridge.append({"drug": drug, "therapeutic_category": c})
        for c in cos:
            co_bridge.append({"drug": drug, "company_name": c})
        for r in reasons:
            reason_bridge.append({"drug": drug, "shortage_reason": r})

        # Long format: one row per scoring component. This is the shape the
        # "score decomposition" stacked bar needs in Tableau.
        for label, weight, score_key, detail_key in SCORE_WEIGHTS:
            raw = d.get(score_key, 0)
            components.append({
                "drug": drug,
                "risk_score": score,
                "component": label,
                "weight": weight,
                "weight_label": f"{int(weight * 100)}%",
                "component_score": raw,
                "weighted_contribution": round(raw * weight, 2),
                "detail_value": d.get(detail_key, "") if detail_key else "",
            })

    write_csv("drug_risk_scores.csv", rows, list(rows[0].keys()))
    write_csv("drug_categories.csv", cat_bridge, ["drug", "therapeutic_category"])
    write_csv("drug_companies.csv", co_bridge, ["drug", "company_name"])
    write_csv("drug_reasons.csv", reason_bridge, ["drug", "shortage_reason"])
    write_csv("drug_score_components.csv", components, list(components[0].keys()))
    return rows


# ── 3. Anomaly detection output ──────────────────────────────────────────

def export_anomalies(anom):
    cats = [{
        "therapeutic_category": a["category"],
        "shortage_count": a["shortage_count"],
        "z_score": a["z_score"],
        "abs_z_score": abs(a["z_score"]),
        "is_anomaly": "TRUE" if truthy(a["is_anomaly"]) else "FALSE",
        "direction": a.get("direction", ""),
        "mean": a.get("mean", ""),
        "std": a.get("std", ""),
    } for a in anom.get("category_anomalies", [])]
    write_csv("category_anomalies.csv", cats, list(cats[0].keys()))

    recur = [{
        "drug": a["drug"],
        "recurrence_count": a["recurrence_count"],
        "z_score": a["z_score"],
        "risk_score": a["risk_score"],
        "primary_category": a.get("primary_category", ""),
        "current_status": a.get("current_status", ""),
    } for a in anom.get("drug_recurrence_anomalies", [])]
    write_csv("drug_recurrence_anomalies.csv", recur, list(recur[0].keys()))

    monthly = []
    for a in anom.get("temporal_anomalies", {}).get("monthly", []):
        period = a.get("period", "")
        monthly.append({
            "period": period,
            "period_date": f"{period}-01" if len(period) == 7 else "",
            # Named shortage_count, not count — "Count" shadows Tableau's
            # built-in aggregate and reads ambiguously in the field list.
            "shortage_count": a.get("count", 0),
            "rolling_mean": a.get("rolling_mean", ""),
            "rolling_std": a.get("rolling_std", ""),
            "z_score": a.get("z_score", 0),
            "is_anomaly": "TRUE" if truthy(a.get("is_anomaly")) else "FALSE",
        })
    if monthly:
        write_csv("temporal_anomalies.csv", monthly, list(monthly[0].keys()))


# ── 4. Pre-aggregated helper tables + KPI tiles ──────────────────────────

def export_aggregates(events, drugs):
    reasons = Counter(e["shortage_reason"] for e in events if e["shortage_reason"])
    total = sum(reasons.values())
    rows = [{
        "shortage_reason": r,
        "shortage_count": n,
        "pct_of_total": round(100.0 * n / total, 2),
        "cause_severity": CAUSE_SEVERITY.get(r, ""),
    } for r, n in reasons.most_common()]
    write_csv("reason_distribution.csv", rows, list(rows[0].keys()))

    companies = Counter(e["company_name"] for e in events if e["company_name"])
    rows = [{
        "company_name": c,
        "shortage_count": n,
        "pct_of_total": round(100.0 * n / len(events), 2),
        "concentration_rank": i,
    } for i, (c, n) in enumerate(companies.most_common(), start=1)]
    write_csv("company_concentration.csv", rows, list(rows[0].keys()))

    monthly = Counter(e["posting_month_date"] for e in events if e["posting_month_date"])
    rows = [{"period_date": p, "period": p[:7], "shortage_count": n}
            for p, n in sorted(monthly.items())]
    write_csv("shortages_by_month.csv", rows, list(rows[0].keys()))

    active = sum(1 for e in events if e["is_active"] == "TRUE")
    disc = sum(1 for e in events if "discontinu" in e["status"].lower())
    # Mean over events that actually recorded a duration, truncated — matches
    # the figure the pipeline and README report (2,018 days).
    durations = [e["duration_days"] for e in events if e["duration_days"]]
    avg_dur = int(sum(durations) / len(durations)) if durations else 0

    kpis = [
        ("Total Records", f"{len(events):,}", "FDA shortage events", 1),
        ("Unique Drugs", f"{len(drugs):,}", "Scored & ranked", 2),
        ("Active Shortages", f"{active:,}", f"{disc:,} discontinued", 3),
        ("Companies", f"{len(companies):,}", "Suppliers tracked", 4),
        ("Avg Duration", f"{avg_dur // 365}y {round((avg_dur % 365) / 30)}m", f"{avg_dur:,} days", 5),
        ("Max Risk Score", f"{max(d['risk_score'] for d in drugs)}", "Highest-risk drug", 6),
    ]
    rows = [{"metric": m, "value": v, "subtitle": s, "sort_order": o}
            for m, v, s, o in kpis]
    write_csv("kpi_summary.csv", rows, ["metric", "value", "subtitle", "sort_order"])


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"Exporting Tableau CSVs to {OUT}\n")

    events_raw = load("fda_shortages_cleaned.json")
    scores_raw = load("drug_risk_scores.json")
    anomalies = load("anomaly_results.json")

    events = export_events(events_raw)
    drugs = export_drug_scores(scores_raw)
    export_anomalies(anomalies)
    export_aggregates(events, drugs)

    print("\nDone.")


if __name__ == "__main__":
    main()
