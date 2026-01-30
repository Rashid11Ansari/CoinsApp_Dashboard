"""Utilities for working with feature identifiers."""

from __future__ import annotations

import re
from typing import Iterable, List

import pandas as pd

_PUBCHEM_RE = re.compile(r"\d+")


def extract_pubchem_cids(val) -> List[str]:
    """Extract PubChem CIDs from a cell value (supports comma/semicolon/text)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    cids = _PUBCHEM_RE.findall(s)
    # de-duplicate while preserving order
    seen = set()
    out: list[str] = []
    for cid in cids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def has_pubchem(val) -> bool:
    """Return True when PubChem CIDs are present."""
    return len(extract_pubchem_cids(val)) > 0


def require_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    """Return dataframe containing only required columns that exist."""
    cols = [c for c in required if c in df.columns]
    return df[cols].copy()

