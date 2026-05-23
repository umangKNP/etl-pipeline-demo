# etl-pipeline-demo

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-2.0-150458?logo=pandas&logoColor=white)
![pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?logo=pytest)
![License](https://img.shields.io/badge/license-MIT-green)

**Production-grade ETL pipeline: World Bank API → pandas → SQLite → cron.**  
Demonstrates the core data engineering loop with proper layering, error handling, data quality validation, idempotent loading, and a configurable YAML-driven architecture.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         pipeline.py                             │
│                  (orchestrator + run logging)                   │
└──────┬──────────────┬──────────────┬──────────────┬────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
  extract.py    transform.py   quality_checks.py  load.py
       │              │              │              │
       ▼              ▼              ▼              ▼
 World Bank    pandas cleaning  12 configurable  SQLite
 REST API v2   + type coercion  quality checks   (upsert)
       │
       ▼
  data/raw/
  *.json
```

**Data flow:**
1. **Extract** — calls World Bank API for 6 Australian economic indicators (1990–2024), retries on failure, saves raw JSON
2. **Transform** — flattens nested JSON, renames columns, enforces types, filters year range, adds audit columns
3. **Quality Checks** — validates nulls, value bounds, year coverage, duplicate keys — fails pipeline if critical thresholds exceeded
4. **Load** — batch upserts into SQLite with `INSERT OR REPLACE`, logs every run to `etl_run_log` table

---

## Indicators Tracked

| Indicator | World Bank Code |
|-----------|----------------|
| Unemployment rate (%) | `SL.UEM.TOTL.ZS` |
| Employment-to-population ratio (%) | `SL.EMP.TOTL.SP.ZS` |
| Labour force participation rate (%) | `SL.TLF.CACT.ZS` |
| GDP (current USD) | `NY.GDP.MKTP.CD` |
| GDP per capita (current USD) | `NY.GDP.PCAP.CD` |
| Inflation, CPI (annual %) | `FP.CPI.TOTL.ZG` |

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline (extract + transform + quality + load)
make run
# or:
python src/pipeline.py

# Re-run transform + load from cached raw data (no API call)
make run-skip-extract

# Validate transform + quality only, skip writing to DB
make dry-run

# Run tests
make test
```

---

## Project Structure

```
etl-pipeline-demo/
├── src/
│   ├── pipeline.py         # orchestrator — runs all 4 steps in order
│   ├── extract.py          # World Bank API client with retry + pagination
│   ├── transform.py        # pandas cleaning, flattening, type coercion
│   ├── quality_checks.py   # 7 configurable data quality validations
│   ├── load.py             # SQLite upsert with batch inserts + run logging
│   └── logger.py           # structured logging (console + daily log file)
├── config/
│   └── config.yaml         # all parameters — zero hardcoding in code
├── tests/
│   ├── test_transform.py   # 5 unit tests for transform layer
│   └── test_quality_checks.py  # 6 unit tests for quality checks
├── cron/
│   └── schedule.sh         # cron setup for daily scheduled runs
├── data/
│   ├── raw/                # raw JSON from API (git-ignored)
│   └── processed/          # SQLite database (git-ignored)
├── logs/                   # daily run logs (git-ignored)
├── Makefile
├── requirements.txt
└── README.md
```

---

## SQLite Schema

```sql
CREATE TABLE economic_indicators (
    indicator_name        TEXT    NOT NULL,
    indicator_id          TEXT,
    indicator_description TEXT,
    country_name          TEXT,
    iso3_code             TEXT,
    year                  INTEGER NOT NULL,
    metric_value          REAL,
    decimal_places        INTEGER,
    loaded_at             TEXT,
    PRIMARY KEY (indicator_name, year)   -- natural upsert key
);

CREATE TABLE etl_run_log (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp  TEXT,
    rows_extracted INTEGER,
    rows_loaded    INTEGER,
    rows_skipped   INTEGER,
    status         TEXT,
    error_message  TEXT
);
```

---

## Key Engineering Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| Config-driven via YAML | `config/config.yaml` | Zero hardcoding — change behaviour without touching code |
| Retry with exponential backoff | `extract.py` | Resilient to transient API failures |
| Paginated API traversal | `extract.py` | Handles any dataset size correctly |
| Idempotent upsert | `load.py` | Run as many times as needed — no duplicate rows |
| Batch inserts | `load.py` | Memory-efficient for large datasets |
| Run audit log | `load.py` | Every pipeline run recorded — debuggable in production |
| Data quality gate | `quality_checks.py` | Pipeline aborts before load if data is corrupt |
| Structured logging | `logger.py` | Console INFO + file DEBUG — every run fully traceable |
| `--skip-extract` flag | `pipeline.py` | Faster iteration during development |

---

## Scheduling (Cron)

```bash
# Run daily at 6:00 AM
chmod +x cron/schedule.sh
crontab -e

# Add this line:
0 6 * * * /full/path/to/etl-pipeline-demo/cron/schedule.sh
```

---

*Data sourced from [World Bank Open Data](https://data.worldbank.org/). No API key required.*
