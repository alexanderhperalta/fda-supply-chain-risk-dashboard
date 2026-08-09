# FDA Drug Shortage Supply Chain Risk Dashboard

## Overview

Healthcare supply chains are opaque. Active pharmaceutical ingredients are heavily sourced from countries representing geopolitical risk, country-of-origin labeling is inconsistent, and consolidation among generic manufacturers has reduced competition, leading to shortages and price volatility.

This project builds a **prototype healthcare supply chain risk dashboard** using publicly available FDA Drug Shortage data. It implements:

- **Composite Risk Scoring**: Weighted multi-signal scoring per drug (recurrence, duration, cause severity, current status)
- **Anomaly Detection**: Z-score analysis flagging therapeutic categories with statistically disproportionate disruption
- **Interactive Dashboard**: A six-view Tableau workbook with filterable risk leaderboards, shortage cause breakdowns, time-series trends, and supplier concentration analysis

### Key Findings

| Metric | Value |
|--------|-------|
| Total shortage records analyzed | 1,692 |
| Unique drugs scored | 248 |
| Active shortages | 1,146 |
| CRITICAL risk drugs (score ≥ 70) | 2 |
| Anomalous therapeutic categories | 3 (Anesthesia, Psychiatry, Pediatric) |
| Average shortage duration | 5.5 years |

**Highest-risk drug:** Lidocaine Hydrochloride Injection (score: 85.7); 70 shortage events, 12+ year average duration, actively unavailable from multiple suppliers.

---

## Exiger Alignment

Each component maps directly to a capability Exiger delivers in production:

| Project Component | Exiger Parallel |
|---|---|
| Composite risk score per drug | Risk scoring incorporating supplier health, geographic exposure, dependency mapping |
| Geographic/category concentration analysis | SDX geographic visualization of supply tiers and country-of-origin analysis |
| Anomaly detection on therapeutic categories | 1Exiger early-signal detection for disruption and supply chain resilience |
| Interactive Tableau workbook for stakeholders | Custom reports and dashboards for policymakers and government agencies |
| ETL pipeline from FDA API | Data ingestion and enrichment from public and proprietary data sources |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FDA openFDA API                  │
│           api.fda.gov/drug/shortages.json           │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│                  ETL Pipeline                        │
│  • Ingest 1,692 shortage records                     │
│  • Standardize 7 canonical shortage reason categories│
│  • Compute duration, availability, enrichment fields │
└──────────────────────┬───────────────────────────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│  Risk Scoring    │  │  Anomaly Detection   │
│  Engine          │  │                      │
│  • Recurrence    │  │  • Z-score by        │
│    (30%)         │  │    therapeutic       │
│  • Duration      │  │    category          │
│    (25%)         │  │  • Temporal trend    │
│  • Cause         │  │    detection         │
│    Severity      │  │  • Recurrence        │
│    (25%)         │  │    outliers          │
│  • Status (20%)  │  │                      │
└────────┬─────────┘  └──────────┬───────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
┌──────────────────────────────────────────────────────┐
│           Tableau Export Layer (flat CSVs)           │
│  • Fact + dimension tables, bridge tables            │
│  • Pre-aggregated KPI and trend tables               │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│        Tableau Workbook (6 dashboards, 23 sheets)    │
│  • Risk Leaderboard (sortable, filterable)           │
│  • Shortage Causes (donut + ranked bars)             │
│  • Category Analysis (heatmap + anomaly flags)       │
│  • Time Series (yearly trend, monthly anomalies)     │
│  • Supplier Risk (concentration, single-source)      │
│  • Methodology & Exiger Alignment                    │
└──────────────────────────────────────────────────────┘
```

---

## Risk Scoring Methodology

The composite risk score (0–100) for each drug is computed from four weighted signals:

```
Risk = 0.30 × Recurrence + 0.25 × Duration + 0.25 × CauseSeverity + 0.20 × Status
```

### Signal Definitions

**Recurrence Frequency (30%)**: Normalized count of shortage events per drug. Drugs with chronic, repeated shortages receive the highest scores.

**Shortage Duration (25%)**: Average days in shortage state, normalized against the maximum observed duration. Longer shortages indicate deeper supply chain fragility (structural, not transient).

**Cause Severity (25%)**: Highest-severity cause observed across all shortage events for a drug:

| Cause | Score | Rationale |
|-------|-------|-----------|
| Raw Material / API Shortage | 100 | Upstream dependency failure; hardest to resolve |
| Manufacturing / Quality | 85 | GMP violations, facility shutdowns |
| Discontinuation | 80 | Permanent supply loss |
| Regulatory | 70 | Compliance-driven disruption |
| Shipping / Logistics | 50 | Usually transient |
| Demand Increase | 40 | Demand-side spike, typically temporary |

**Current Status (20%)**: Active + unavailable = 100, Active only = 80, Resolved = 20.

---

## Anomaly Detection

### Category-Level Z-Scores

Z-score analysis on shortage frequency per therapeutic category identifies classes experiencing disproportionate disruption:

```
z = (count - μ) / σ
Flag if |z| > 1.5
```

**Flagged categories:**
- **Anesthesia** (z = 2.25): 341 shortage records, driven by injectable anesthetic supply chain fragility
- **Psychiatry** (z = 1.73): 288 records, reflecting stimulant medication shortages (Adderall, Vyvanse)
- **Pediatric** (z = 1.69): 284 records, cross-cutting category reflecting pediatric formulation vulnerability

---

## Quick Start

### Prerequisites
- Python 3.10+
- pip
- Tableau Desktop or Tableau Public (2022.4+) to open the workbook

### Installation

```bash
git clone https://github.com/alexanderhperalta/fda-supply-chain-risk.git
cd fda-supply-chain-risk
pip install -r requirements.txt
```

### Run the Full Pipeline

```bash
python main.py
```

This will:
1. Fetch data from the FDA openFDA API (or use cached data)
2. Clean and standardize 1,692 shortage records
3. Compute composite risk scores for 248 drugs
4. Run anomaly detection across therapeutic categories
5. Output all results to `data/processed/`

### Run Individual Components

```bash
# ETL only
python -m src.etl_pipeline

# Risk scoring only (requires ETL output)
python -m src.risk_scoring

# Anomaly detection only (requires ETL + scoring output)
python -m src.anomaly_detection
```

### Export the Tableau Data Layer

```bash
python -m src.export_tableau
```

Writes 14 Tableau-ready flat CSVs to `data/tableau/`, including a shortage-event fact table, 
drug-level risk scores, exploded bridge tables for the multi-value fields (categories, 
suppliers, reasons), anomaly output, and pre-aggregated helper tables.

### Open the Dashboard

```
dashboard/fda-supply-chain-risk-dashboard.twbx
```

The packaged workbook bundles extracts of the exported data, so it opens standalone; no live
connection to `data/tableau/` is required. To refresh it against newly exported CSVs, re-run
`src.export_tableau`, then **Data → Refresh All Extracts** in Tableau.

**Dashboards:** Risk Leaderboard · Shortage Causes · Category Analysis · Time Series ·
Supplier Risk · Methodology (23 underlying worksheets).

---

## Project Structure

```
fda-supply-chain-risk/
├── main.py                          # Full pipeline orchestration
├── requirements.txt                 # Python dependencies
├── README.md                        # This file
├── src/
│   ├── etl_pipeline.py              # Data ingestion, cleaning, standardization
│   ├── risk_scoring.py              # Composite risk scoring engine
│   ├── anomaly_detection.py         # Z-score anomaly detection
│   └── export_tableau.py            # Flatten processed data into Tableau CSVs
├── data/
│   ├── raw/                         # Raw FDA API responses
│   ├── processed/                   # Cleaned data, risk scores, anomaly results
│   └── tableau/                     # Flat CSVs + extracts for Tableau
└── dashboard/
    ├── fda-supply-chain-risk-dashboard.twbx  # Packaged Tableau workbook
    └── fda_supply_chain_risk_dashboard.jsx   # React prototype of the same views
```

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Data Ingestion | Python (requests, pandas) | Standard DS stack |
| Risk Scoring | NumPy, SciPy | Statistical computation, normalization |
| Anomaly Detection | NumPy (Z-scores) | Statistical outlier detection |
| Visualization | Tableau (packaged .twbx) | Interactive dashboards for non-technical stakeholders |
| BI Data Layer | Flat CSV star schema + bridge tables | Clean, extract-friendly model for Tableau |
| Data Source | FDA openFDA API | Public drug shortage data |

---

## Data Source

**FDA Drug Shortage Database** via the openFDA API (`api.fda.gov/drug/shortages.json`)

- 1,692 shortage records (current + resolved + discontinued)
- 248 unique drugs, 130 companies
- Therapeutic categories, shortage reasons, availability status, temporal data
- Updated daily by the FDA

---

## Author

**Alexander Peralta**
- Email: ahperalt@gmail.com
- [LinkedIn](http://linkedin.com/in/alexander--peralta)
- [GitHub](https://github.com/alexanderhperalta)
