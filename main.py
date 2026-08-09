"""
FDA Drug Shortage Supply Chain Risk Dashboard
  1. ETL: Ingest and clean FDA shortage data
  2. Risk Scoring: Compute composite risk scores per drug
  3. Anomaly Detection: Flag statistical outliers

The dashboard is a Tableau workbook fed by src.export_tableau; see README.md.

Usage:
    python main.py              # Run full pipeline
    python main.py --pipeline   # Same, minus the closing next-steps hint

"""

import json
import os
import sys

from src.etl_pipeline import run_pipeline
from src.risk_scoring import compute_drug_scores, print_risk_report
from src.anomaly_detection import (
    detect_category_anomalies,
    detect_temporal_anomalies,
    detect_drug_recurrence_anomalies,
    print_anomaly_report,
)


def main():
    pipeline_only = "--pipeline" in sys.argv

    raw_file = "data/raw/fda_shortages_raw.json"
    if os.path.exists(raw_file):
        print(f"Found existing raw data at {raw_file}")
        with open(raw_file) as f:
            raw = json.load(f)
        cleaned = run_pipeline(raw)
    else:
        cleaned = run_pipeline()

    print("\n" + "=" * 60)
    print("STEP 3: RISK SCORING ENGINE")
    print("=" * 60)

    drug_scores = compute_drug_scores(cleaned)
    print_risk_report(drug_scores)

    os.makedirs("data/processed", exist_ok=True)
    with open("data/processed/drug_risk_scores.json", "w") as f:
        json.dump(drug_scores, f, indent=2)

    print("\n" + "=" * 60)
    print("STEP 4: ANOMALY DETECTION")
    print("=" * 60)

    cat_anomalies = detect_category_anomalies(cleaned)
    temporal = detect_temporal_anomalies(cleaned)
    drug_anomalies = detect_drug_recurrence_anomalies(drug_scores)
    print_anomaly_report(cat_anomalies, temporal, drug_anomalies)

    anomaly_output = {
        "category_anomalies": cat_anomalies,
        "temporal_anomalies": temporal,
        "drug_recurrence_anomalies": drug_anomalies,
    }
    with open("data/processed/anomaly_results.json", "w") as f:
        json.dump(anomaly_output, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Records processed: {len(cleaned)}")
    print(f"  Drugs scored: {len(drug_scores)}")
    print(f"  Critical risk drugs: {sum(1 for d in drug_scores if d['risk_level'] == 'CRITICAL')}")
    print(f"  Anomalous categories: {sum(1 for a in cat_anomalies if a['is_anomaly'])}")

    if not pipeline_only:
        print("\n  To refresh the dashboard data:")
        print("    python -m src.export_tableau")
        print("  Then open dashboard/fda-supply-chain-risk-dashboard.twbx in Tableau")


if __name__ == "__main__":
    main()
