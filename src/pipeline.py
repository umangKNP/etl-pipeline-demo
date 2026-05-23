"""
Pipeline orchestrator — runs Extract → Quality Check → Transform → Load
in sequence, with structured logging, timing, and error handling.

Usage:
    python src/pipeline.py                    # full run
    python src/pipeline.py --skip-extract     # use cached raw data
    python src/pipeline.py --dry-run          # transform only, no load
"""
import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from logger import get_logger

log = get_logger("pipeline")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="World Bank AU Employment ETL Pipeline")
    p.add_argument("--skip-extract", action="store_true",
                   help="Skip extract, use existing raw JSON files")
    p.add_argument("--dry-run", action="store_true",
                   help="Run extract + transform + quality checks, skip load")
    p.add_argument("--config", default="config/config.yaml",
                   help="Path to config file (default: config/config.yaml)")
    return p.parse_args()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_pipeline(skip_extract: bool = False, dry_run: bool = False,
                 config_path: str = "config/config.yaml") -> None:
    # Change CWD to project root so relative paths work
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Lazy imports (so individual modules can be tested independently)
    from extract       import run_extract
    from transform     import run_transform
    from quality_checks import run_quality_checks
    from load          import run_load

    config = load_config(config_path)
    pipeline_start = time.perf_counter()

    log.info("=" * 60)
    log.info("ETL PIPELINE START — %s", config["pipeline"]["name"])
    log.info("  skip_extract=%s  dry_run=%s", skip_extract, dry_run)
    log.info("=" * 60)

    # ── EXTRACT ────────────────────────────────────────────────────────────────
    raw_data = None
    if not skip_extract:
        t0 = time.perf_counter()
        log.info("STEP 1/4 — EXTRACT")
        try:
            raw_data = run_extract(config)
            total_records = sum(len(v) for v in raw_data.values())
            log.info("Extract done in %.1fs — %d total records across %d indicators",
                     time.perf_counter() - t0, total_records, len(raw_data))
        except Exception as exc:
            log.error("Extract failed: %s", exc, exc_info=True)
            sys.exit(1)
    else:
        log.info("STEP 1/4 — EXTRACT (skipped — using cached raw data)")

    # ── TRANSFORM ─────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    log.info("STEP 2/4 — TRANSFORM")
    try:
        df = run_transform(raw_data=raw_data, config=config)
        log.info("Transform done in %.1fs — %d rows, %d columns",
                 time.perf_counter() - t0, len(df), len(df.columns))
    except Exception as exc:
        log.error("Transform failed: %s", exc, exc_info=True)
        sys.exit(1)

    # ── QUALITY CHECKS ────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    log.info("STEP 3/4 — QUALITY CHECKS")
    try:
        report = run_quality_checks(df, config)
        log.info("Quality checks done in %.1fs", time.perf_counter() - t0)
        if not report.ok:
            log.error("Quality checks FAILED — aborting load.")
            sys.exit(1)
    except Exception as exc:
        log.error("Quality check error: %s", exc, exc_info=True)
        sys.exit(1)

    # ── LOAD ──────────────────────────────────────────────────────────────────
    if dry_run:
        log.info("STEP 4/4 — LOAD (skipped — dry run)")
    else:
        t0 = time.perf_counter()
        log.info("STEP 4/4 — LOAD")
        try:
            rows_loaded = run_load(df, config)
            log.info("Load done in %.1fs — %d rows upserted",
                     time.perf_counter() - t0, rows_loaded)
        except Exception as exc:
            log.error("Load failed: %s", exc, exc_info=True)
            sys.exit(1)

    elapsed = time.perf_counter() - pipeline_start
    log.info("=" * 60)
    log.info("PIPELINE COMPLETE in %.1fs", elapsed)
    log.info("=" * 60)


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        skip_extract=args.skip_extract,
        dry_run=args.dry_run,
        config_path=args.config,
    )
