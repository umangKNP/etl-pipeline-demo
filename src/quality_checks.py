"""
Data quality validation layer.
Runs configurable checks before loading — raises on critical failures,
logs warnings on soft failures.
"""
from dataclasses import dataclass, field

import pandas as pd
import yaml

from logger import get_logger

log = get_logger("quality")


@dataclass
class QualityReport:
    passed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.failures) == 0

    def summarise(self) -> None:
        log.info("── Quality Report ─────────────────────────────────")
        for msg in self.passed:
            log.info("  ✓ %s", msg)
        for msg in self.warnings:
            log.warning("  ⚠ %s", msg)
        for msg in self.failures:
            log.error("  ✗ %s", msg)
        status = "PASSED" if self.ok else "FAILED"
        log.info("── %s (%d checks, %d warnings, %d failures) ───",
                 status, len(self.passed), len(self.warnings), len(self.failures))


def run_quality_checks(df: pd.DataFrame, config: dict) -> QualityReport:
    cfg = config["quality"]
    report = QualityReport()

    # ── Check 1: Non-empty dataframe ──────────────────────────────────────────
    if len(df) == 0:
        report.failures.append("DataFrame is empty — nothing to load.")
        return report
    report.passed.append(f"DataFrame has {len(df):,} rows")

    # ── Check 2: Required columns present ─────────────────────────────────────
    required = {"indicator_name", "year", "metric_value", "country_name"}
    missing = required - set(df.columns)
    if missing:
        report.failures.append(f"Missing required columns: {missing}")
    else:
        report.passed.append("All required columns present")

    # ── Check 3: Null % in metric_value ───────────────────────────────────────
    null_pct = df["metric_value"].isna().mean() * 100
    if null_pct > cfg["max_null_pct"]:
        report.failures.append(
            f"metric_value null rate {null_pct:.1f}% exceeds threshold {cfg['max_null_pct']}%"
        )
    elif null_pct > cfg["max_null_pct"] / 2:
        report.warnings.append(f"metric_value null rate is {null_pct:.1f}% (threshold: {cfg['max_null_pct']}%)")
    else:
        report.passed.append(f"metric_value null rate OK: {null_pct:.1f}%")

    # ── Check 4: Year coverage per indicator ──────────────────────────────────
    min_coverage = cfg["min_year_coverage"]
    coverage = df.groupby("indicator_name")["year"].nunique()
    under = coverage[coverage < min_coverage]
    if not under.empty:
        report.warnings.append(
            f"Low year coverage (<{min_coverage} years): {under.to_dict()}"
        )
    else:
        report.passed.append(f"All indicators have ≥{min_coverage} years of data")

    # ── Check 5: Value bounds per indicator ───────────────────────────────────
    bounds = cfg.get("value_bounds", {})
    for ind_name, (lo, hi) in bounds.items():
        subset = df[df["indicator_name"] == ind_name]["metric_value"].dropna()
        if subset.empty:
            continue
        out_of_range = subset[(subset < lo) | (subset > hi)]
        if not out_of_range.empty:
            report.warnings.append(
                f"{ind_name}: {len(out_of_range)} values outside bounds [{lo}, {hi}] "
                f"(min={subset.min():.2f}, max={subset.max():.2f})"
            )
        else:
            report.passed.append(
                f"{ind_name}: all values within [{lo}, {hi}]"
            )

    # ── Check 6: Duplicate upsert keys ────────────────────────────────────────
    upsert_keys = config["load"]["upsert_key"]
    key_cols = [c for c in upsert_keys if c in df.columns]
    if len(key_cols) == len(upsert_keys):
        dupes = df.duplicated(subset=key_cols).sum()
        if dupes > 0:
            report.warnings.append(f"{dupes} duplicate rows on upsert keys {key_cols}")
        else:
            report.passed.append("No duplicate upsert keys")

    # ── Check 7: Year range sanity ────────────────────────────────────────────
    if "year" in df.columns:
        yr_min, yr_max = df["year"].min(), df["year"].max()
        expected_min, expected_max = config["transform"]["expected_year_range"]
        if yr_min < expected_min or yr_max > expected_max:
            report.warnings.append(
                f"Year range {yr_min}–{yr_max} outside expected {expected_min}–{expected_max}"
            )
        else:
            report.passed.append(f"Year range OK: {yr_min:.0f}–{yr_max:.0f}")

    report.summarise()
    return report


if __name__ == "__main__":
    import os
    from pathlib import Path
    os.chdir(Path(__file__).parent.parent)
    from transform import run_transform
    with open("config/config.yaml") as f:
        cfg = yaml.safe_load(f)
    df = run_transform(config=cfg)
    report = run_quality_checks(df, cfg)
    if not report.ok:
        raise SystemExit("Quality checks failed — see logs above.")
