"""Paths, environment and global settings."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
LEGACY = DATA / "legacy"

for _p in (RAW, PROCESSED):
    _p.mkdir(parents=True, exist_ok=True)

try:  # load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

START_YEAR = 2000
LAST_ACTUAL_YEAR = 2024        # last year we expect broad WDI coverage
FORECAST_END = 2035
HTTP_TIMEOUT = 60


def secret(name: str, default: str | None = None) -> str | None:
    """Read a setting from env vars, then Streamlit secrets (when deployed)."""
    val = os.getenv(name)
    if val:
        return val
    try:
        import streamlit as st

        return st.secrets.get(name, default)  # type: ignore[attr-defined]
    except Exception:
        return default


def qwen_settings() -> dict:
    """LLM settings. Any OpenAI-compatible endpoint serving a Qwen model works
    (Alibaba Cloud Model Studio / DashScope recommended; Groq also hosts Qwen)."""
    return {
        "api_key": secret("DASHSCOPE_API_KEY"),
        "base_url": secret("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        "model": secret("QWEN_MODEL", "qwen/qwen3-32b"),
        "max_tokens": int(secret("QWEN_MAX_TOKENS", "800") or 800),
    }
