"""IMF World Economic Outlook via the DBnomics mirror (no key required).

Used for fiscal variables that WDI covers poorly (gross public debt, primary balance) and for
the IMF's own growth projections, which serve as an external benchmark for our forecasts.
"""
from __future__ import annotations

import json
import time

import pandas as pd
import requests

from ..config import HTTP_TIMEOUT, RAW

API = "https://api.db.nomics.world/v22/series/IMF/WEO:latest"

SUBJECTS = {
    "GGXWDG_NGDP": "gov_debt_imf",          # General government gross debt, % GDP
    "GGXONLB_NGDP": "primary_balance",      # General government primary net lending/borrowing, % GDP
    "GGXCNL_NGDP": "fiscal_balance",        # General government net lending/borrowing, % GDP
    "NGDP_RPCH": "imf_gdp_growth",          # Real GDP growth, % (actuals + IMF projections)
    "PCPIPCH": "imf_inflation",             # Inflation, average CPI, % change
}

CACHE = RAW / "imf_weo.csv"
WEO_CODE = {"PSE": "WBG"}  # IMF codes West Bank & Gaza as WBG
FROM_WEO = {v: k for k, v in WEO_CODE.items()}


def fetch(iso3: list[str], refresh: bool = False, log=print) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_csv(CACHE)
    rows, offset = [], 0
    dims = json.dumps({"weo-country": [WEO_CODE.get(i, i) for i in iso3], "weo-subject": list(SUBJECTS)})
    while True:
        for attempt in range(3):
            try:
                r = requests.get(API, params={"dimensions": dims, "observations": 1, "limit": 500, "offset": offset},
                                 timeout=HTTP_TIMEOUT)
                r.raise_for_status()
                payload = r.json()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        docs = payload["series"]["docs"]
        for d in docs:
            iso = FROM_WEO.get(d["dimensions"]["weo-country"], d["dimensions"]["weo-country"])
            key = SUBJECTS.get(d["dimensions"]["weo-subject"])
            for p, v in zip(d["period"], d["value"]):
                if v in (None, "NA") or key is None:
                    continue
                rows.append({"iso3": iso, "year": int(str(p)[:4]), "key": key, "value": float(v)})
        offset += len(docs)
        if not docs or offset >= payload["series"]["num_found"]:
            break
    df = pd.DataFrame(rows, columns=["iso3", "year", "key", "value"])
    df.to_csv(CACHE, index=False)
    log(f"  ✓ IMF WEO (DBnomics)      {len(df):>5} obs  {df.iso3.nunique()} economies  {df.key.nunique()} series")
    return df
