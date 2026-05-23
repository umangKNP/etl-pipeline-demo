"""
Extract layer — pulls economic indicators for Australia from the
World Bank REST API v2. Retries on failure, saves raw JSON per indicator.
"""
import json
import time
from pathlib import Path
from typing import Any

import requests
import yaml

from logger import get_logger

log = get_logger("extract")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def fetch_indicator(
    base_url: str,
    country: str,
    indicator_id: str,
    start_year: int,
    end_year: int,
    per_page: int = 100,
    timeout: int = 30,
    retries: int = 3,
    backoff: int = 2,
) -> list[dict[str, Any]]:
    """
    Fetch all pages of a single World Bank indicator for a given country.
    Returns the flat list of data records.
    """
    url = (
        f"{base_url}/country/{country}/indicator/{indicator_id}"
        f"?format=json&date={start_year}:{end_year}&per_page={per_page}"
    )
    all_records: list[dict] = []
    page = 1

    while True:
        paged_url = f"{url}&page={page}"
        log.debug("GET %s", paged_url)

        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(paged_url, timeout=timeout)
                resp.raise_for_status()
                break
            except requests.RequestException as exc:
                log.warning("Attempt %d/%d failed for %s: %s",
                            attempt, retries, indicator_id, exc)
                if attempt == retries:
                    raise
                time.sleep(backoff * attempt)

        payload = resp.json()
        # World Bank returns [metadata_dict, data_list]
        if not isinstance(payload, list) or len(payload) < 2:
            log.warning("Unexpected payload shape for %s: %s", indicator_id, payload)
            break

        meta, data = payload[0], payload[1]
        if data is None:
            break

        all_records.extend(data)
        total_pages = meta.get("pages", 1)
        log.debug("Fetched page %d/%d for %s (%d records so far)",
                  page, total_pages, indicator_id, len(all_records))

        if page >= total_pages:
            break
        page += 1

    return all_records


def run_extract(config: dict, raw_dir: str = "data/raw") -> dict[str, list]:
    """
    Extract all configured indicators. Save raw JSON and return dict
    of {indicator_name: [records]}.
    """
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    cfg_e = config["extract"]
    results: dict[str, list] = {}

    for ind in cfg_e["indicators"]:
        log.info("Extracting indicator: %s (%s)", ind["id"], ind["name"])
        try:
            records = fetch_indicator(
                base_url=cfg_e["base_url"],
                country=cfg_e["country"],
                indicator_id=ind["id"],
                start_year=cfg_e["date_range"]["start_year"],
                end_year=cfg_e["date_range"]["end_year"],
                per_page=cfg_e["per_page"],
                timeout=cfg_e["timeout_seconds"],
                retries=cfg_e["retry_attempts"],
                backoff=cfg_e["retry_backoff_seconds"],
            )
            # Attach the human-readable name for downstream use
            for r in records:
                r["_indicator_name"] = ind["name"]

            # Save raw JSON
            raw_path = Path(raw_dir) / f"{ind['name']}.json"
            with open(raw_path, "w") as f:
                json.dump(records, f, indent=2)

            log.info("  → %d records fetched, saved to %s", len(records), raw_path)
            results[ind["name"]] = records

        except Exception as exc:
            log.error("Failed to extract %s: %s", ind["id"], exc, exc_info=True)

    log.info("Extract complete. %d indicators fetched.", len(results))
    return results


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)
    cfg = load_config()
    run_extract(cfg)
