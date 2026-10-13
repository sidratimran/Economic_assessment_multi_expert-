"""World Bank Indicators API client (no key required) with on-disk caching."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import HTTP_TIMEOUT, RAW, START_YEAR
from ..indicators import Indicator

API = "https://api.worldbank.org/v2/country/{countries}/indicator/{code}"


def _cache_path(ind: Indicator):
    return RAW / f"wb_{ind.code.replace('.', '_')}.csv"


def fetch_indicator(ind: Indicator, iso3: list[str], end_year: int, refresh: bool = False,
                    retries: int = 3) -> pd.DataFrame:
    """Return long frame [iso3, year, key, value] for one indicator."""
    path = _cache_path(ind)
    if path.exists() and not refresh:
        return pd.read_csv(path)

    url = API.format(countries=";".join(iso3), code=ind.code)
    params = {"format": "json", "date": f"{START_YEAR}:{end_year}", "per_page": 20000, "source": ind.source}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
                msg = payload[0].get("message") if isinstance(payload, list) and payload else payload
                raise ValueError(f"No data returned: {msg}")
            rows = [
                {"iso3": r["countryiso3code"], "year": int(r["date"]), "key": ind.key, "value": r["value"]}
                for r in payload[1]
                if r.get("value") is not None and r.get("countryiso3code")
            ]
            df = pd.DataFrame(rows, columns=["iso3", "year", "key", "value"])
            df.to_csv(path, index=False)
            return df
        except Exception as ex:  # network / API hiccup
            last_err = ex
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{ind.code}: {last_err}")


def fetch_all(indicators: list[Indicator], iso3: list[str], end_year: int,
              refresh: bool = False, log=print) -> tuple[pd.DataFrame, list[dict]]:
    frames, manifest = [], []
    for ind in indicators:
        try:
            df = fetch_indicator(ind, iso3, end_year, refresh=refresh)
            frames.append(df)
            manifest.append({
                "key": ind.key, "code": ind.code, "source": "World Bank WDI" if ind.source == 2 else "World Bank WGI",
                "rows": int(len(df)), "countries": int(df.iso3.nunique()) if len(df) else 0,
                "latest_year": int(df.year.max()) if len(df) else None, "status": "ok",
            })
            log(f"  ✓ {ind.code:<22} {len(df):>5} obs  {df.iso3.nunique() if len(df) else 0:>2} economies")
        except Exception as ex:
            manifest.append({"key": ind.key, "code": ind.code, "status": f"failed: {ex}"})
            log(f"  ✗ {ind.code:<22} {ex}")
    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["iso3", "year", "key", "value"])
    for m in manifest:
        m["retrieved_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return long, manifest
