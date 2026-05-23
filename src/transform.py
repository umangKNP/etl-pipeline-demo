"""
Transform layer — flattens nested World Bank JSON, cleans types,
enforces schema, adds derived columns.
"""
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from logger import get_logger

log = get_logger("transform")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    The World Bank API returns nested dicts for country and indicator.
    Flatten them to simple key-value pairs.
    """
    flat = {}
    for k, v in record.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v
    return flat


def clean_dataframe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    cfg = config["transform"]

    # ── 1. Flatten if columns still nested ────────────────────────────────────
    if "country" in df.columns and df["country"].dtype == object:
        flat_records = [flatten_record(r) for r in df.to_dict("records")]
        df = pd.DataFrame(flat_records)

    # ── 2. Rename columns ─────────────────────────────────────────────────────
    rename_map = cfg.get("rename_columns", {})
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # ── 3. Select and order relevant columns ──────────────────────────────────
    keep = ["indicator_id", "indicator_description", "_indicator_name",
            "iso3_code", "country_name", "year", "metric_value", "decimal_places"]
    df = df[[c for c in keep if c in df.columns]].copy()

    # ── 4. Type coercion ──────────────────────────────────────────────────────
    df["year"]         = pd.to_numeric(df["year"],         errors="coerce")
    df["metric_value"] = pd.to_numeric(df["metric_value"], errors="coerce")

    # ── 5. Drop rows with null metric_value if configured ─────────────────────
    before = len(df)
    if cfg.get("drop_null_value_rows", True):
        df = df.dropna(subset=["metric_value"])
    log.debug("Dropped %d null-value rows (retained %d)", before - len(df), len(df))

    # ── 6. Filter year range ──────────────────────────────────────────────────
    yr_min, yr_max = cfg["expected_year_range"]
    df = df[(df["year"] >= yr_min) & (df["year"] <= yr_max)]

    # ── 7. Derived columns ────────────────────────────────────────────────────
    df["loaded_at"] = pd.Timestamp.utcnow().isoformat()

    # Normalise indicator_name from _indicator_name col (may not exist for
    # records loaded from raw JSON rather than direct extract output)
    if "_indicator_name" in df.columns:
        df = df.rename(columns={"_indicator_name": "indicator_name"})
    elif "indicator_name" not in df.columns:
        df["indicator_name"] = df["indicator_id"].apply(
            lambda x: re.sub(r"[^a-z0-9]", "_", x.lower()) if isinstance(x, str) else x
        )

    df = df.sort_values(["indicator_name", "year"]).reset_index(drop=True)
    return df


def run_transform(
    raw_data: dict[str, list] | None = None,
    raw_dir: str = "data/raw",
    config: dict | None = None,
) -> pd.DataFrame:
    """
    Transform raw indicator data.
    Accepts either a dict from the extract step OR reads JSON from raw_dir.
    """
    if config is None:
        config = load_config()

    if raw_data is None:
        # Load from disk (supports re-running transform independently)
        raw_data = {}
        for jf in Path(raw_dir).glob("*.json"):
            with open(jf) as f:
                records = json.load(f)
            raw_data[jf.stem] = records
        log.info("Loaded %d indicator files from %s", len(raw_data), raw_dir)

    frames: list[pd.DataFrame] = []
    for indicator_name, records in raw_data.items():
        if not records:
            log.warning("No records for %s — skipping", indicator_name)
            continue
        df_raw = pd.DataFrame(records)
        df_clean = clean_dataframe(df_raw, config)
        frames.append(df_clean)
        log.info("Transformed %-35s → %d rows", indicator_name, len(df_clean))

    if not frames:
        raise ValueError("No data to transform — check extract step.")

    combined = pd.concat(frames, ignore_index=True)
    log.info("Transform complete. Total rows: %d", len(combined))
    return combined


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)
    df = run_transform()
    print(df.head(10).to_string())
    print(f"\nShape: {df.shape}")
    print(df.dtypes)
