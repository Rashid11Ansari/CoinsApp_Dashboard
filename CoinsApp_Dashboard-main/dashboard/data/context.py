"""Data access layer for the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from data_loader import load_all, ProductData


class DataContext:
    """Encapsulates all loaded data and helpers."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._data: Dict[str, ProductData | pd.DataFrame | dict] = {}
        self._summary_df: pd.DataFrame | None = None
        self._groups: dict | None = None

    def load(self) -> None:
        self._data = load_all(self.data_dir)
        self._summary_df = self._data["_summary"]
        self._groups = self._data["_groups"]

    @property
    def summary(self) -> pd.DataFrame:
        assert self._summary_df is not None, "Call load() before accessing summary."
        return self._summary_df

    @property
    def groups(self) -> dict:
        assert self._groups is not None, "Call load() before accessing groups."
        return self._groups

    def product(self, name: str) -> pd.DataFrame:
        assert self._data, "Call load() before accessing products."
        return self._data[name].features

    @property
    def products(self) -> list[str]:
        return [k for k in self._data.keys() if not k.startswith("_")]

