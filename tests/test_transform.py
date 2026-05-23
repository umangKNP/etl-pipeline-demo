"""Unit tests for the transform layer."""
import sys
from pathlib import Path
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from transform import flatten_record, clean_dataframe


MOCK_CONFIG = {
    "transform": {
        "drop_null_value_rows": True,
        "rename_columns": {
            "countryiso3code": "iso3_code",
            "country.value": "country_name",
            "indicator.id": "indicator_id",
            "indicator.value": "indicator_description",
            "date": "year",
            "value": "metric_value",
        },
        "expected_year_range": [1990, 2024],
        "numeric_columns": ["year", "metric_value"],
    }
}


def test_flatten_record_nested():
    record = {
        "country": {"id": "AU", "value": "Australia"},
        "indicator": {"id": "SL.UEM.TOTL.ZS", "value": "Unemployment rate"},
        "date": "2020",
        "value": 6.5,
    }
    flat = flatten_record(record)
    assert flat["country.id"] == "AU"
    assert flat["country.value"] == "Australia"
    assert flat["indicator.id"] == "SL.UEM.TOTL.ZS"
    assert flat["date"] == "2020"


def test_flatten_record_already_flat():
    record = {"year": 2020, "metric_value": 5.1, "country": "AU"}
    flat = flatten_record(record)
    assert flat == record


def test_clean_dataframe_renames_and_types():
    raw = pd.DataFrame([{
        "country": {"id": "AU", "value": "Australia"},
        "indicator": {"id": "SL.UEM.TOTL.ZS", "value": "Unemployment"},
        "countryiso3code": "AUS",
        "date": "2020",
        "value": 6.5,
        "decimal": 1,
        "_indicator_name": "unemployment_rate_pct",
    }])
    df = clean_dataframe(raw, MOCK_CONFIG)
    assert "year" in df.columns
    assert "metric_value" in df.columns
    assert df["year"].dtype in (int, float)
    assert df["metric_value"].dtype == float


def test_clean_dataframe_drops_nulls():
    raw = pd.DataFrame([
        {"country": {"id": "AU", "value": "Australia"},
         "indicator": {"id": "X", "value": "Test"},
         "countryiso3code": "AUS", "date": "2020", "value": None,
         "decimal": 0, "_indicator_name": "test"},
        {"country": {"id": "AU", "value": "Australia"},
         "indicator": {"id": "X", "value": "Test"},
         "countryiso3code": "AUS", "date": "2019", "value": 5.0,
         "decimal": 0, "_indicator_name": "test"},
    ])
    df = clean_dataframe(raw, MOCK_CONFIG)
    assert len(df) == 1
    assert df.iloc[0]["metric_value"] == 5.0


def test_clean_dataframe_filters_year_range():
    raw = pd.DataFrame([
        {"country": {"id": "AU", "value": "AU"}, "indicator": {"id": "X", "value": "T"},
         "countryiso3code": "AUS", "date": "1985", "value": 4.0,
         "decimal": 0, "_indicator_name": "test"},
        {"country": {"id": "AU", "value": "AU"}, "indicator": {"id": "X", "value": "T"},
         "countryiso3code": "AUS", "date": "2020", "value": 5.0,
         "decimal": 0, "_indicator_name": "test"},
    ])
    df = clean_dataframe(raw, MOCK_CONFIG)
    assert len(df) == 1
    assert int(df.iloc[0]["year"]) == 2020
