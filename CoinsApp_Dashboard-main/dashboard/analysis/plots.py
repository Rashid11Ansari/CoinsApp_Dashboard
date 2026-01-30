"""Plotting helpers."""

from __future__ import annotations

import plotly.express as px
import pandas as pd


class PlotFactory:
    """Factory for chart generation (polymorphic use in callbacks)."""

    @staticmethod
    def make_bar_topN(df: pd.DataFrame, use_log: bool, top_n: int):
        ycol = "log10_intensity" if use_log and "log10_intensity" in df.columns else "intensity"
        dff = df.dropna(subset=[ycol, "feature"]).sort_values(ycol, ascending=False).head(top_n)
        hover_cols = [c for c in ["Average.Mz", "Average.Rt.min.", "name", "molecularFormula", "pubchemids"] if c in dff.columns]
        fig = px.bar(dff, x="feature", y=ycol, hover_data=hover_cols)
        fig.update_layout(xaxis_title="feature", yaxis_title=ycol, margin=dict(l=20, r=20, t=40, b=80))
        return fig

    @staticmethod
    def make_scatter(df: pd.DataFrame, use_log: bool):
        ycol = "log10_intensity" if use_log and "log10_intensity" in df.columns else "intensity"
        dff = df.dropna(subset=["Average.Rt.min.", ycol]).copy()
        hover_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "Average.Mz"] if c in dff.columns]
        fig = px.scatter(dff, x="Average.Rt.min.", y=ycol, hover_data=hover_cols)
        fig.update_layout(xaxis_title="RT (min)", yaxis_title=ycol, margin=dict(l=20, r=20, t=40, b=40))
        return fig

