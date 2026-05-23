"""Unit tests for quality_checks.py."""
import sys
from pathlib import Path
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from quality_checks import run_quality_checks


MOCK_CONFIG = {
    "quality": {
        "max_null_pct": 5.0,
        "min_year_coverage": 3,
        "value_bounds": {
            "unemployment_rate_pct": [0, 40],
        },
    },
    "transform": {"expected_year_range": [1990, 2024]},
    "load": {"upsert_key": ["indicator_name", "year"]},
}


def make_df(**kwargs) -> pd.DataFrame:
    defaults = {
        "indicator_name": ["unemployment_rate_pct"] * 5,
        "year": [2018, 2019, 2020, 2021, 2022],
        "metric_value": [5.0, 5.2, 6.1, 5.8, 3.9],
        "country_name": ["Australia"] * 5,
        "iso3_code": ["AUS"] * 5,
    }
    defaults.update(kwargs)
    return pd.DataFrame(defaults)


def test_passes_on_clean_data():
    df = make_df()
    report = run_quality_checks(df, MOCK_CONFIG)
    assert report.ok
    assert len(report.failures) == 0


def test_fails_on_empty_dataframe():
    df = pd.DataFrame()
    report = run_quality_checks(df, MOCK_CONFIG)
    assert not report.ok
    assert any("empty" in f.lower() for f in report.failures)


def test_fails_on_missing_column():
    df = make_df().drop(columns=["metric_value"])
    report = run_quality_checks(df, MOCK_CONFIG)
    assert not report.ok


def test_warns_on_out_of_bounds_value():
    df = make_df(metric_value=[5.0, 5.2, 99.0, 5.8, 3.9])  # 99 is out of [0,40]
    report = run_quality_checks(df, MOCK_CONFIG)
    assert any("unemployment_rate_pct" in w for w in report.warnings)


def test_warns_on_duplicate_keys():
    df = make_df()
    df = pd.concat([df, df.iloc[:1]], ignore_index=True)  # duplicate one row
    report = run_quality_checks(df, MOCK_CONFIG)
    assert any("duplicate" in w.lower() for w in report.warnings)


def test_warns_on_low_year_coverage():
    df = make_df(year=[2020, 2020, 2020, 2020, 2020])  # only 1 unique year
    report = run_quality_checks(df, MOCK_CONFIG)
    assert any("coverage" in w.lower() for w in report.warnings)
