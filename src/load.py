"""
Load layer — upserts cleaned DataFrame into SQLite with idempotent logic,
batch inserts, and run metadata tracking.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from logger import get_logger

log = get_logger("load")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def ensure_tables(con: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    con.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE IF NOT EXISTS economic_indicators (
        indicator_name        TEXT    NOT NULL,
        indicator_id          TEXT,
        indicator_description TEXT,
        country_name          TEXT,
        iso3_code             TEXT,
        year                  INTEGER NOT NULL,
        metric_value          REAL,
        decimal_places        INTEGER,
        loaded_at             TEXT,
        PRIMARY KEY (indicator_name, year)
    );

    CREATE TABLE IF NOT EXISTS etl_run_log (
        run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_timestamp TEXT    NOT NULL,
        rows_extracted INTEGER,
        rows_loaded    INTEGER,
        rows_skipped   INTEGER,
        status        TEXT    NOT NULL,
        error_message TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_indicator_year
        ON economic_indicators (indicator_name, year);
    CREATE INDEX IF NOT EXISTS idx_year
        ON economic_indicators (year);
    """)
    con.commit()


def upsert_batch(
    con: sqlite3.Connection,
    df: pd.DataFrame,
    table: str,
    batch_size: int = 500,
) -> tuple[int, int]:
    """
    Upsert rows in batches using INSERT OR REPLACE.
    Returns (rows_inserted_or_replaced, rows_skipped).
    """
    cols = list(df.columns)
    placeholders = ", ".join(["?"] * len(cols))
    sql = (
        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({placeholders})"
    )
    loaded = 0
    skipped = 0

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i : i + batch_size]
        rows = [tuple(r) for r in batch.itertuples(index=False)]
        try:
            con.executemany(sql, rows)
            con.commit()
            loaded += len(rows)
            log.debug("Loaded batch %d–%d (%d rows)", i, i + len(rows), len(rows))
        except sqlite3.Error as exc:
            log.error("Batch %d failed: %s — skipping", i, exc)
            skipped += len(rows)

    return loaded, skipped


def log_run(
    con: sqlite3.Connection,
    rows_extracted: int,
    rows_loaded: int,
    rows_skipped: int,
    status: str,
    error_message: str | None = None,
) -> None:
    con.execute(
        "INSERT INTO etl_run_log "
        "(run_timestamp, rows_extracted, rows_loaded, rows_skipped, status, error_message) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), rows_extracted,
         rows_loaded, rows_skipped, status, error_message),
    )
    con.commit()


def run_load(df: pd.DataFrame, config: dict) -> int:
    """
    Load cleaned DataFrame into SQLite. Returns number of rows loaded.
    """
    cfg_l = config["load"]
    db_path = Path(cfg_l["db_path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Connecting to %s", db_path)
    con = sqlite3.connect(db_path)
    ensure_tables(con)

    # Only send columns that exist in the target schema
    target_cols = [
        "indicator_name", "indicator_id", "indicator_description",
        "country_name", "iso3_code", "year", "metric_value",
        "decimal_places", "loaded_at",
    ]
    df_load = df[[c for c in target_cols if c in df.columns]].copy()
    # Fill missing target cols with None
    for col in target_cols:
        if col not in df_load.columns:
            df_load[col] = None

    log.info("Loading %d rows to table '%s'", len(df_load), cfg_l["table_name"])
    rows_loaded, rows_skipped = upsert_batch(
        con, df_load, cfg_l["table_name"], cfg_l["batch_size"]
    )

    log_run(con, rows_extracted=len(df), rows_loaded=rows_loaded,
            rows_skipped=rows_skipped, status="SUCCESS")
    con.close()

    log.info("Load complete. Loaded: %d | Skipped: %d", rows_loaded, rows_skipped)
    return rows_loaded


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)
    from transform import run_transform
    cfg = load_config()
    df = run_transform(config=cfg)
    run_load(df, cfg)
