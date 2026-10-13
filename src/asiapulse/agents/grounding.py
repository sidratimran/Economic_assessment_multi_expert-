"""Grounding check: every number in the AI's answer must be traceable to a tool output.

We extract numeric tokens from the answer and look for a match (allowing for rounding) in
the numbers returned by the expert tools during that conversation. Years and list markers
are ignored. The result is shown to the user as a "grounded: x / y numbers verified" badge,
with the unverified numbers listed — turning the anti-hallucination claim into evidence.
"""
from __future__ import annotations

import json
import re

NUM = re.compile(r"(?<![A-Za-z_])[-−+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z_])[-−+]?\d+(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    out = []
    for m in NUM.findall(text):
        try:
            out.append(float(m.replace(",", "").replace("−", "-")))
        except ValueError:
            pass
    return out


def _source_numbers(tool_outputs: list) -> set[float]:
    nums: set[float] = set()
    for o in tool_outputs:
        s = o if isinstance(o, str) else json.dumps(o, default=str)
        for v in _numbers(s):
            nums.add(v)
            nums.add(abs(v))
    return nums


def _is_ignorable(tok: str, v: float) -> bool:
    if tok.isdigit() and 1990 <= v <= 2100:  # years
        return True
    if tok.isdigit() and v <= 10 and "." not in tok:  # list markers, small counts ("3 pillars")
        return True
    if tok == "100":  # scale references ("/100", "per 100")
        return True
    return False


def _match(v: float, decimals: int, sources: set[float]) -> bool:
    tol = 0.5 * 10 ** (-decimals) + 1e-9          # rounding tolerance implied by how it was written
    for s in sources:
        if abs(abs(v) - s) <= max(tol, 0.005 * abs(s)):
            return True
        if s and abs(abs(v) - s / 1e9) <= max(tol, 0.005 * abs(s / 1e9)):  # US$ → US$ bn
            return True
    return False


def verify(answer: str, tool_outputs: list, question: str = "") -> dict:
    sources = _source_numbers(tool_outputs) | set(_numbers(question))
    checked, unverified = 0, []
    for tok in NUM.findall(answer):
        clean = tok.replace(",", "").replace("−", "-").lstrip("+")
        try:
            v = float(clean)
        except ValueError:
            continue
        if _is_ignorable(clean.lstrip("-"), abs(v)):
            continue
        checked += 1
        decimals = len(clean.split(".")[1]) if "." in clean else 0
        if not _match(v, decimals, sources):
            unverified.append(tok)
    verified = checked - len(unverified)
    return {"checked": checked, "verified": verified, "unverified": sorted(set(unverified)),
            "ratio": (verified / checked) if checked else 1.0}
