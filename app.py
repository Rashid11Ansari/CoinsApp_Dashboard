from __future__ import annotations
from layout import build_layout

from pathlib import Path

import math
import pandas as pd
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px
import plotly.io as pio

# Guard against bad/unsupported default templates causing px.bar() to crash
pio.templates.default = "plotly"
import re

from data_loader import load_all


APP_TITLE = "MS Feature Explorer (Origin-aware)"

_PUBCHEM_RE = re.compile(r"\d+")

def extract_pubchem_cids(val) -> list[str]:
    """Extract PubChem CIDs from a cell value (supports comma/semicolon/text)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    cids = _PUBCHEM_RE.findall(s)
    # de-duplicate while preserving order
    seen = set()
    out = []
    for cid in cids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out

def has_pubchem(val) -> bool:
    return len(extract_pubchem_cids(val)) > 0


def present_in_any(summary_df: pd.DataFrame, feature_ids: set[str], cols: list[str], threshold: float = 0) -> set[str]:
    """Return features (subset of feature_ids) present in ANY of the given columns above threshold."""
    if not cols:
        return set()
    sub = summary_df[summary_df["feature"].isin(feature_ids)]
    mask = (sub[cols] > threshold).any(axis=1)
    return set(sub.loc[mask, "feature"].astype(str))


def compute_origin_sets(product_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict, threshold: float = 0) -> dict[str, set[str]]:
    """Classify product features into meaningful evidence-based sets (non-zero presence)."""
    prod_ids = set(product_df["feature"].astype(str).dropna())

    plant_ids = present_in_any(summary_df, prod_ids, groups["plant_cols"], threshold=threshold)
    animal_ids = present_in_any(summary_df, prod_ids, groups["animal_cols"], threshold=threshold)

    common = plant_ids.intersection(animal_ids)
    unique = prod_ids.difference(plant_ids.union(animal_ids))

    return {
        "All product features": prod_ids,
        "Common (plant+animal)": common,
        "Unique to product": unique,
    }


def build_product_only_df(prod_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """Q5: Features present in final product but absent in all plant+animal components."""
    origin_sets = compute_origin_sets(prod_df, summary_df, groups, threshold=0)
    ids = origin_sets["Unique to product"]

    dff = prod_df[prod_df["feature"].astype(str).isin(ids)].copy()

    annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in summary_df.columns]
    if annot_cols:
        annot = summary_df[annot_cols].drop_duplicates("feature")
        dff = dff.merge(annot, on="feature", how="left")

    keep = [c for c in ["feature", "intensity", "Average.Rt.min.", "Average.Mz", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in dff.columns]
    return dff[keep].sort_values("intensity", ascending=False)


def build_component_only_df(prod_feature_ids: set[str], summary_df: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """Q4: Features present in raw components but absent in the final product."""
    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    if not comp_cols:
        return pd.DataFrame(columns=["feature", "source", "max_component_intensity"])

    # component present if ANY component column > 0
    comp_present_mask = (summary_df[comp_cols] > 0).any(axis=1)
    comp_present = summary_df.loc[comp_present_mask, "feature"].astype(str)

    comp_only_ids = set(comp_present) - set(map(str, prod_feature_ids))
    sdf = summary_df[summary_df["feature"].astype(str).isin(comp_only_ids)].copy()

    # classify source
    plant_present = (sdf[plant_cols] > 0).any(axis=1) if plant_cols else False
    animal_present = (sdf[animal_cols] > 0).any(axis=1) if animal_cols else False

    def _src(p, a):
        if p and a:
            return "Common (plant+animal)"
        if p:
            return "Plant"
        if a:
            return "Animal"
        return "Unknown"

    sdf["source"] = [ _src(bool(p), bool(a)) for p, a in zip(plant_present, animal_present) ]

    # max component intensity across plant+animal component cols
    sdf["max_component_intensity"] = sdf[comp_cols].max(axis=1)

    keep = [c for c in ["feature", "source", "max_component_intensity", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in sdf.columns]
    return sdf[keep].sort_values("max_component_intensity", ascending=False)


def build_component_contribution_df(prod_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """
    Q6 helper:
    Estimate how much each component (plant/animal column) contributes to the
    final product signal by summing product intensities for features that are
    also present in the given component column (> 0).
    """
    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    if not comp_cols or "feature" not in summary_df.columns:
        return pd.DataFrame(columns=["component", "source", "product_intensity_sum", "fraction_of_total"])

    # Merge product intensities with component columns on feature id.
    merged = prod_df[["feature", "intensity"]].merge(
        summary_df[["feature"] + comp_cols], on="feature", how="left"
    )

    rows: list[dict] = []
    for col in comp_cols:
        if col not in merged.columns:
            continue
        mask = merged[col] > 0
        contrib = float(merged.loc[mask, "intensity"].sum())
        if contrib <= 0:
            continue
        source = "Plant" if col in plant_cols else "Animal"
        rows.append(
            {
                "component": str(col),
                "source": source,
                "product_intensity_sum": contrib,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["component", "source", "product_intensity_sum", "fraction_of_total"])

    df = pd.DataFrame(rows)
    total = float(df["product_intensity_sum"].sum())
    if total > 0:
        df["fraction_of_total"] = df["product_intensity_sum"] / total
    else:
        df["fraction_of_total"] = 0.0

    return df.sort_values("product_intensity_sum", ascending=False)


def build_enrichment_df(
    prod_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    groups: dict,
    min_component_intensity: float = 0.0,
) -> pd.DataFrame:
    """
    Q7 helper:
    For each product feature that is also present in at least one component,
    compute an enrichment ratio:

        enrichment_ratio = product_intensity / max_component_intensity

    where max_component_intensity is the maximum intensity across all
    plant/animal component columns.
    """
    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    if "feature" not in summary_df.columns or not comp_cols:
        return pd.DataFrame(
            columns=[
                "feature",
                "intensity",
                "max_component_intensity",
                "enrichment_ratio",
                "source",
                "name",
                "molecularFormula",
                "pubchemids",
            ]
        )

    annot_cols = [
        c
        for c in ["feature", "name", "molecularFormula", "pubchemids"]
        if c in summary_df.columns
    ]

    merged = prod_df[["feature", "intensity"]].merge(
        summary_df[["feature"] + comp_cols + [c for c in annot_cols if c != "feature"]],
        on="feature",
        how="left",
    )

    if not comp_cols:
        return merged.iloc[0:0].copy()

    merged["max_component_intensity"] = merged[comp_cols].max(axis=1)
    dff = merged[merged["max_component_intensity"] > float(min_component_intensity)].copy()
    if dff.empty:
        return dff

    # classify source (plant / animal / common)
    plant_present = (dff[plant_cols] > 0).any(axis=1) if plant_cols else False
    animal_present = (dff[animal_cols] > 0).any(axis=1) if animal_cols else False

    def _src(p, a):
        if p and a:
            return "Common (plant+animal)"
        if p:
            return "Plant"
        if a:
            return "Animal"
        return "Unknown"

    dff["source"] = [
        _src(bool(p), bool(a)) for p, a in zip(plant_present, animal_present)
    ]

    dff["enrichment_ratio"] = dff["intensity"] / dff["max_component_intensity"]

    keep = [
        c
        for c in [
            "feature",
            "intensity",
            "max_component_intensity",
            "enrichment_ratio",
            "source",
            "name",
            "molecularFormula",
            "pubchemids",
        ]
        if c in dff.columns
    ]
    return dff[keep].sort_values("enrichment_ratio", ascending=False)


def build_amplification_df(
    prod_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    groups: dict,
    min_component_intensity: float = 0.0,
    amp_ratio: float = 3.0,
    att_ratio: float = 3.0,
) -> pd.DataFrame:
    """
    Q8 helper:
    Classify product features (that are present in components) into:
      - Amplified   : enrichment_ratio >= amp_ratio
      - Attenuated  : enrichment_ratio <= 1 / att_ratio
      - Neutral     : everything else
    """
    df = build_enrichment_df(
        prod_df,
        summary_df,
        groups,
        min_component_intensity=min_component_intensity,
    ).copy()
    if df.empty or "enrichment_ratio" not in df.columns:
        return df

    er = df["enrichment_ratio"]
    amp_mask = er >= float(amp_ratio)
    att_mask = er <= 1.0 / float(att_ratio) if float(att_ratio) > 0 else False

    state = pd.Series("Neutral", index=df.index)
    state[amp_mask] = "Amplified"
    state[att_mask] = "Attenuated"
    df["state"] = state

    # order_value brings strongest changes (amplified or attenuated) to the top
    order_val = er.copy()
    order_val[att_mask] = 1.0 / er[att_mask].replace(0, pd.NA)
    df["order_value"] = order_val

    return df.sort_values("order_value", ascending=False)


def build_product_overlap_df(
    hepar_df: pd.DataFrame,
    hepeel_df: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Q9 helper:
    Compare the two products (Hepar vs Hepeel) and classify features into:
      - Hepar only
      - Hepeel only
      - Shared (both products)
    Also attach per-product intensities and basic annotations.
    """
    if "feature" not in hepar_df.columns or "feature" not in hepeel_df.columns:
        return pd.DataFrame(
            columns=[
                "feature",
                "group",
                "Hepar_intensity",
                "Hepeel_intensity",
                "name",
                "molecularFormula",
                "pubchemids",
            ]
        )

    hepar_ids = set(hepar_df["feature"].astype(str).dropna())
    hepeel_ids = set(hepeel_df["feature"].astype(str).dropna())

    shared_ids = hepar_ids.intersection(hepeel_ids)
    hepar_only_ids = hepar_ids.difference(hepeel_ids)
    hepeel_only_ids = hepeel_ids.difference(hepar_ids)

    rows: list[dict] = []
    for fid in hepar_only_ids:
        rows.append({"feature": fid, "group": "Hepar only"})
    for fid in hepeel_only_ids:
        rows.append({"feature": fid, "group": "Hepeel only"})
    for fid in shared_ids:
        rows.append({"feature": fid, "group": "Shared"})

    if not rows:
        return pd.DataFrame(
            columns=[
                "feature",
                "group",
                "Hepar_intensity",
                "Hepeel_intensity",
                "name",
                "molecularFormula",
                "pubchemids",
            ]
        )

    df = pd.DataFrame(rows)

    # Aggregate per-product intensities (max per feature as a simple summary).
    hepar_int = (
        hepar_df.groupby("feature")["intensity"].max().rename("Hepar_intensity")
        if "intensity" in hepar_df.columns
        else None
    )
    hepeel_int = (
        hepeel_df.groupby("feature")["intensity"].max().rename("Hepeel_intensity")
        if "intensity" in hepeel_df.columns
        else None
    )

    if hepar_int is not None:
        df = df.merge(hepar_int, left_on="feature", right_index=True, how="left")
    if hepeel_int is not None:
        df = df.merge(hepeel_int, left_on="feature", right_index=True, how="left")

    # Attach basic annotations from summary_df where available.
    annot_cols = [
        c
        for c in ["feature", "name", "molecularFormula", "pubchemids"]
        if c in summary_df.columns
    ]
    if annot_cols:
        annot = summary_df[annot_cols].drop_duplicates("feature")
        df = df.merge(annot, on="feature", how="left")

    return df


def build_hepar_hepeel_diff_df(
    hepar_df: pd.DataFrame,
    hepeel_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    groups: dict,
    min_total_intensity: float = 0.0,
) -> pd.DataFrame:
    """
    Q10 helper:
    For each feature present in at least one product, compute:
      - Hepar_intensity (max per feature)
      - Hepeel_intensity (max per feature)
      - log2 fold-change (Hepar / Hepeel)
      - direction: which product is higher
      - driver: Plant / Animal / Mixed / Unknown
    """
    if "feature" not in hepar_df.columns or "feature" not in hepeel_df.columns:
        return pd.DataFrame(
            columns=[
                "feature",
                "Hepar_intensity",
                "Hepeel_intensity",
                "log2_fc",
                "direction",
                "driver",
                "name",
                "molecularFormula",
                "pubchemids",
            ]
        )

    hepar_int = (
        hepar_df.groupby("feature")["intensity"].max().rename("Hepar_intensity")
        if "intensity" in hepar_df.columns
        else None
    )
    hepeel_int = (
        hepeel_df.groupby("feature")["intensity"].max().rename("Hepeel_intensity")
        if "intensity" in hepeel_df.columns
        else None
    )

    all_features = set(hepar_df["feature"].astype(str).dropna()).union(
        set(hepeel_df["feature"].astype(str).dropna())
    )
    df = pd.DataFrame({"feature": list(all_features)}).set_index("feature")

    if hepar_int is not None:
        df = df.join(hepar_int, how="left")
    else:
        df["Hepar_intensity"] = 0.0
    if hepeel_int is not None:
        df = df.join(hepeel_int, how="left")
    else:
        df["Hepeel_intensity"] = 0.0

    df[["Hepar_intensity", "Hepeel_intensity"]] = df[
        ["Hepar_intensity", "Hepeel_intensity"]
    ].fillna(0.0)

    df["total_intensity"] = df["Hepar_intensity"] + df["Hepeel_intensity"]
    if min_total_intensity is not None and float(min_total_intensity) > 0:
        df = df[df["total_intensity"] >= float(min_total_intensity)].copy()
        if df.empty:
            df = df.reset_index()
            return df

    # log2 fold-change (add small epsilon to avoid division by zero)
    eps = 1e-6
    ratio = (df["Hepar_intensity"] + eps) / (df["Hepeel_intensity"] + eps)
    df["log2_fc"] = ratio.apply(lambda v: math.log2(v))

    def _direction(v: float) -> str:
        if v > 0:
            return "Hepar higher"
        if v < 0:
            return "Hepeel higher"
        return "Similar"

    df["direction"] = df["log2_fc"].apply(_direction)

    # Plant/animal driver using component columns in summary_df
    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    driver_series = pd.Series("Unknown", index=df.index)
    if comp_cols:
        comp_agg = (
            summary_df[["feature"] + comp_cols]
            .drop_duplicates("feature")
            .set_index("feature")
        )
        comp_agg = comp_agg.reindex(df.index).fillna(0.0)

        if plant_cols:
            plant_sum = comp_agg[plant_cols].sum(axis=1)
        else:
            plant_sum = pd.Series(0.0, index=comp_agg.index)

        if animal_cols:
            animal_sum = comp_agg[animal_cols].sum(axis=1)
        else:
            animal_sum = pd.Series(0.0, index=comp_agg.index)

        def _driver(p, a) -> str:
            if p <= 0 and a <= 0:
                return "Unknown"
            if p > a * 1.5:
                return "Plant-dominated"
            if a > p * 1.5:
                return "Animal-dominated"
            return "Mixed"

        driver_series = pd.Series(
            [_driver(float(p), float(a)) for p, a in zip(plant_sum, animal_sum)],
            index=df.index,
        )

    df["driver"] = driver_series

    df = df.reset_index()

    # Attach basic annotations
    annot_cols = [
        c
        for c in ["feature", "name", "molecularFormula", "pubchemids"]
        if c in summary_df.columns
    ]
    if annot_cols:
        annot = summary_df[annot_cols].drop_duplicates("feature")
        df = df.merge(annot, on="feature", how="left")

    return df

def make_bar_topN(df: pd.DataFrame, use_log: bool, top_n: int):
    ycol = "log10_intensity" if use_log and "log10_intensity" in df.columns else "intensity"
    dff = df.dropna(subset=[ycol, "feature"]).sort_values(ycol, ascending=False).head(top_n)

    hover_cols = [c for c in ["Average.Mz", "Average.Rt.min.", "name", "molecularFormula", "pubchemids"] if c in dff.columns]
    fig = px.bar(dff, x="feature", y=ycol, hover_data=hover_cols)
    fig.update_layout(xaxis_title="feature", yaxis_title=ycol, margin=dict(l=20, r=20, t=40, b=80))
    return fig


def make_scatter(df: pd.DataFrame, use_log: bool):
    ycol = "log10_intensity" if use_log and "log10_intensity" in df.columns else "intensity"
    dff = df.dropna(subset=["Average.Rt.min.", ycol]).copy()

    hover_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "Average.Mz"] if c in dff.columns]
    fig = px.scatter(dff, x="Average.Rt.min.", y=ycol, hover_data=hover_cols)
    fig.update_layout(xaxis_title="RT (min)", yaxis_title=ycol, margin=dict(l=20, r=20, t=40, b=40))
    return fig


def build_app() -> Dash:
    data_dir = Path(__file__).resolve().parent / "data"
    data = load_all(str(data_dir))
    summary_df = data["_summary"]
    groups = data["_groups"]

    # ✅ PERFORMANCE: convert component columns to numeric ONCE (not every callback)
    for c in set(groups["plant_cols"] + groups["animal_cols"]):
        if c in summary_df.columns:
            summary_df[c] = pd.to_numeric(summary_df[c], errors="coerce").fillna(0)

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = APP_TITLE

    origin_options = [
        {"label": "All product features", "value": "All product features"},
        {"label": "Common (plant+animal)", "value": "Common (plant+animal)"},
        {"label": "Product-only (Q5)", "value": "Unique to product"},
    ]

    # ==== GLOBAL LAYOUT: SIDEBAR + MAIN CONTENT (moved to layout.py) ====
    app.layout = build_layout(APP_TITLE, origin_options)

    # ==== MODE VISIBILITY VIA DROPDOWN ====
    @app.callback(
        Output("mode_explore", "style"),
        Output("mode_q4q5", "style"),
        Output("mode_q6", "style"),
        Output("mode_q7", "style"),
        Output("mode_q8", "style"),
        Output("mode_q9", "style"),
        Output("mode_q10", "style"),
        Input("analysis_mode", "value"),
    )
    def _switch_mode(mode):
        def s(name: str) -> dict:
            return {"display": "block"} if mode == name else {"display": "none"}

        return s("explore"), s("q4q5"), s("q6"), s("q7"), s("q8"), s("q9"), s("q10")

    # Hide "Final product" selector for modes that compare both products (Q9/Q10).
    @app.callback(
        Output("sidebar_final_product_block", "style"),
        Output("sidebar_origin_block", "style"),
        Output("sidebar_search_block", "style"),
        Input("analysis_mode", "value"),
    )
    def _toggle_final_product(mode):
        # Final product selector is not meaningful for Q9/Q10 (both products used).
        final_style = {"display": "none"} if mode in ("q9", "q10") else {"display": "block"}

        # Origin filter + global feature search are only relevant for Explore mode;
        # other modes have their own specific filters or aggregate across products.
        aux_style = {"display": "block"} if mode == "explore" else {"display": "none"}

        return final_style, aux_style, aux_style

    # ==== EXISTING CALLBACK LOGIC (re-wired to new layout) ====

    @app.callback(
        Output("main_graph", "figure"),
        Output("stats", "children"),
        Input("product", "value"),
        Input("origin_filter", "value"),
        Input("chart_type", "value"),
        Input("top_n", "value"),
        Input("use_log", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
    )
    def update_graph(
        product: str,
        origin_filter: str,
        chart_type: str,
        top_n: int,
        use_log_vals,
        feature_search: str,
        only_pubchem_vals,
    ):
        prod_df = data[product].features.copy()

        origin_sets = compute_origin_sets(
            product_df=prod_df,
            summary_df=summary_df,
            groups=groups,
            threshold=0,
        )
        allowed_ids = origin_sets.get(
            origin_filter, origin_sets["All product features"]
        )

        dff = prod_df[prod_df["feature"].astype(str).isin(allowed_ids)].copy()

        # filter by feature id substring
        if feature_search and feature_search.strip():
            fs = feature_search.strip()
            dff = dff[
                dff["feature"].astype(str).str.contains(
                    fs, case=False, na=False
                )
            ].copy()

        # merge annotation (safe)
        annot_cols = [
            c
            for c in [
                "feature",
                "name",
                "molecularFormula",
                "pubchemids",
                "NPC.pathway",
            ]
            if c in summary_df.columns
        ]
        if annot_cols:
            annot = summary_df[annot_cols].drop_duplicates("feature")
            dff = dff.merge(
                annot, on="feature", how="left", suffixes=("", "_annot")
            )
            for col in [
                "name",
                "molecularFormula",
                "pubchemids",
                "NPC.pathway",
            ]:
                if f"{col}_annot" in dff.columns:
                    if col not in dff.columns:
                        dff[col] = dff[f"{col}_annot"]
                    else:
                        dff[col] = dff[col].where(
                            dff[col].notna(), dff[f"{col}_annot"]
                        )
            drop_cols = [c for c in dff.columns if c.endswith("_annot")]
            if drop_cols:
                dff = dff.drop(columns=drop_cols)

        # Global filter: keep only features with PubChem CID(s)
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                dff = dff.iloc[0:0].copy()

        use_log = "log" in (use_log_vals or [])

        if chart_type == "bar":
            fig = make_bar_topN(dff, use_log=use_log, top_n=int(top_n))
        else:
            fig = make_scatter(dff, use_log=use_log)

        stats = (
            f"{product} | {origin_filter} | shown: {len(dff):,} "
            f"| plant cols: {len(groups['plant_cols'])} | animal cols: {len(groups['animal_cols'])}"
        )
        return fig, stats

    @app.callback(
        Output("q6_contrib_graph", "figure"),
        Output("q6_contrib_stats", "children"),
        Output("q6_source_breakdown", "children"),
        Input("product", "value"),
        Input("q6_top_k", "value"),
    )
    def update_q6_contrib(product: str, q6_top_k: int):
        """Q6: Which ingredients dominate the final product?"""
        # Robust defaults in case Dash sends None on initial render
        prod_key = product or "Hepar"
        try:
            top_k = int(q6_top_k) if q6_top_k is not None else 8
        except (TypeError, ValueError):
            top_k = 8

        prod_df = data[prod_key].features
        contrib_df = build_component_contribution_df(
            prod_df, summary_df, groups
        )

        if contrib_df.empty:
            fig = px.bar(title="No component contribution data available")
            stats = f"{prod_key}: no component contribution data available."
            breakdown = "Plant vs animal breakdown: n/a"
            return fig, stats, breakdown

        dff = contrib_df.head(top_k)
        fig = px.bar(
            dff,
            x="component",
            y="fraction_of_total",
            color="source",
            hover_data=["product_intensity_sum"],
            template="plotly",
            labels={
                "component": "Component column",
                "fraction_of_total": "Fraction of total product intensity",
                "source": "Source",
            },
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=40, b=80),
            xaxis_tickangle=45,
        )

        shown_fraction = dff["fraction_of_total"].sum()
        stats = (
            f"{prod_key} | top {len(dff)} components shown | "
            f"fraction of total intensity captured: {shown_fraction:.2%}"
        )
        # Overall plant vs animal fractions across all components
        plant_frac = contrib_df.loc[contrib_df["source"] == "Plant", "fraction_of_total"].sum()
        animal_frac = contrib_df.loc[contrib_df["source"] == "Animal", "fraction_of_total"].sum()
        other_frac = max(0.0, 1.0 - plant_frac - animal_frac)

        parts = [
            f"Plant: {plant_frac:.1%}",
            f"Animal: {animal_frac:.1%}",
        ]
        if other_frac > 0.005:
            parts.append(f"Other: {other_frac:.1%}")
        breakdown = "Total product intensity by source (all components) → " + " | ".join(parts)

        return fig, stats, breakdown

    @app.callback(
        Output("q7_enrich_graph", "figure"),
        Output("q7_enrich_stats", "children"),
        Input("product", "value"),
        Input("q7_min_comp", "value"),
        Input("q7_min_ratio", "value"),
        Input("q7_top_n", "value"),
        Input("only_pubchem", "value"),
    )
    def update_q7_enrich(
        q7_product: str,
        q7_min_comp,
        q7_min_ratio: float,
        q7_top_n: int,
        only_pubchem_vals,
    ):
        """Q7: Which features are enriched in the final product vs components?"""
        prod_df = data[q7_product].features
        min_comp = float(q7_min_comp or 0.0)
        df = build_enrichment_df(
            prod_df,
            summary_df,
            groups,
            min_component_intensity=min_comp,
        )

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        if df.empty:
            fig = px.bar(title="No enriched features found")
            stats = f"{q7_product}: no enriched features (after filters)."
            return fig, stats

        df = df[df["enrichment_ratio"] >= float(q7_min_ratio or 1.0)].copy()
        if df.empty:
            fig = px.bar(title="No enriched features above threshold")
            stats = (
                f"{q7_product}: no features with enrichment >= {q7_min_ratio:.1f}x "
                f"(min component intensity {min_comp})."
            )
            return fig, stats

        dff = df.head(int(q7_top_n))
        fig = px.bar(
            dff,
            x="feature",
            y="enrichment_ratio",
            color="source",
            hover_data=[
                "intensity",
                "max_component_intensity",
                "name",
                "molecularFormula",
                "pubchemids",
            ],
            labels={
                "feature": "Feature ID",
                "enrichment_ratio": "Enrichment (product / max component)",
                "source": "Source",
            },
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=40, b=80),
            xaxis_tickangle=45,
        )

        stats = (
            f"{q7_product} | enriched features shown: {len(dff):,} "
            f"| min component intensity: {min_comp:.1f} | min enrichment: {float(q7_min_ratio or 1.0):.1f}x"
        )
        return fig, stats

    @app.callback(
        Output("q8_amp_graph", "figure"),
        Output("q8_amp_stats", "children"),
        Input("product", "value"),
        Input("q8_min_comp", "value"),
        Input("q8_amp_ratio", "value"),
        Input("q8_att_ratio", "value"),
        Input("q8_top_n", "value"),
        Input("q8_states", "value"),
        Input("only_pubchem", "value"),
    )
    def update_q8_amp(
        q8_product: str,
        q8_min_comp,
        q8_amp_ratio: float,
        q8_att_ratio: float,
        q8_top_n: int,
        q8_states,
        only_pubchem_vals,
    ):
        """Q8: Which features show selective amplification or attenuation?"""
        prod_df = data[q8_product].features
        min_comp = float(q8_min_comp or 0.0)
        df = build_amplification_df(
            prod_df,
            summary_df,
            groups,
            min_component_intensity=min_comp,
            amp_ratio=float(q8_amp_ratio or 1.0),
            att_ratio=float(q8_att_ratio or 1.0),
        )

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        if df.empty:
            fig = px.bar(title="No features with sufficient component signal")
            stats = f"{q8_product}: no features after component-intensity filter."
            return fig, stats

        states = set(q8_states or [])
        if states:
            df = df[df["state"].isin(states)].copy()

        if df.empty:
            fig = px.bar(
                title="No amplified/attenuated features for current thresholds"
            )
            stats = (
                f"{q8_product}: 0 features classified as {', '.join(sorted(states))} "
                f"(amp >= {float(q8_amp_ratio or 1.0):.1f}x, att <= 1/{float(q8_att_ratio or 1.0):.1f}x)."
            )
            return fig, stats

        dff = df.head(int(q8_top_n))
        fig = px.bar(
            dff,
            x="feature",
            y="enrichment_ratio",
            color="state",
            hover_data=[
                "intensity",
                "max_component_intensity",
                "source",
                "name",
                "molecularFormula",
                "pubchemids",
            ],
            labels={
                "feature": "Feature ID",
                "enrichment_ratio": "Enrichment (product / max component)",
                "state": "State",
            },
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=40, b=80),
            xaxis_tickangle=45,
        )

        n_amp = int((dff["state"] == "Amplified").sum())
        n_att = int((dff["state"] == "Attenuated").sum())
        stats = (
            f"{q8_product} | shown features: {len(dff):,} "
            f"(Amplified: {n_amp}, Attenuated: {n_att}) | "
            f"min component intensity: {min_comp:.1f}, "
            f"amp >= {float(q8_amp_ratio or 1.0):.1f}x, att <= 1/{float(q8_att_ratio or 1.0):.1f}x"
        )
        return fig, stats

    @app.callback(
        Output("q9_overlap_graph", "figure"),
        Output("q9_overlap_table", "data"),
        Output("q9_overlap_table", "columns"),
        Output("q9_overlap_stats", "children"),
        Input("q9_groups", "value"),
        Input("q9_top_n", "value"),
        Input("only_pubchem", "value"),
    )
    def update_q9_overlap(q9_groups, q9_top_n: int, only_pubchem_vals):
        """Q9: How are Hepar and Hepeel chemically different / overlapping?"""
        hepar_df = data["Hepar"].features
        hepeel_df = data["Hepeel"].features
        df = build_product_overlap_df(hepar_df, hepeel_df, summary_df)

        if df.empty:
            fig = px.bar(title="No overlap data available")
            empty_columns = [{"name": c, "id": c} for c in df.columns]
            return fig, [], empty_columns, "No overlap data available."

        # Apply PubChem filter if requested.
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        selected_groups = set(q9_groups or ["Hepar only", "Hepeel only", "Shared"])
        df = df[df["group"].isin(selected_groups)].copy()

        if df.empty:
            fig = px.bar(title="No features in selected groups")
            empty_columns = [{"name": c, "id": c} for c in df.columns]
            stats = "No features for selected groups and filters."
            return fig, [], empty_columns, stats

        # Combined intensity for Top-N ranking (treat NaNs as 0).
        for col in ["Hepar_intensity", "Hepeel_intensity"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["combined_intensity"] = df.get("Hepar_intensity", 0) + df.get(
            "Hepeel_intensity", 0
        )

        # Prepare counts per group for the bar chart.
        count_series = df.groupby("group")["feature"].nunique()
        count_df = count_series.reset_index(name="n_features")
        fig = px.bar(
            count_df,
            x="group",
            y="n_features",
            labels={"group": "Group", "n_features": "Number of features"},
            title="Hepar vs Hepeel: feature counts per group",
        )
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=40))

        # Table: Top-N features by combined intensity.
        dff = df.sort_values("combined_intensity", ascending=False).head(
            int(q9_top_n or 100)
        )
        columns = [
            {"name": c, "id": c} for c in dff.columns if c != "combined_intensity"
        ]
        stats = (
            f"Features shown: {len(dff):,} "
            f"(Hepar only: {int((df['group'] == 'Hepar only').sum())}, "
            f"Hepeel only: {int((df['group'] == 'Hepeel only').sum())}, "
            f"Shared: {int((df['group'] == 'Shared').sum())})"
        )
        return fig, dff.to_dict("records"), columns, stats

    @app.callback(
        Output("q10_diff_graph", "figure"),
        Output("q10_diff_table", "data"),
        Output("q10_diff_table", "columns"),
        Output("q10_diff_stats", "children"),
        Input("q10_min_total_int", "value"),
        Input("q10_min_abs_log2", "value"),
        Input("q10_top_n", "value"),
        Input("q10_dirs", "value"),
        Input("only_pubchem", "value"),
    )
    def update_q10_diff(
        q10_min_total_int,
        q10_min_abs_log2: float,
        q10_top_n: int,
        q10_dirs,
        only_pubchem_vals,
    ):
        """Q10: Features with differential intensities between Hepar and Hepeel."""
        hepar_df = data["Hepar"].features
        hepeel_df = data["Hepeel"].features

        df = build_hepar_hepeel_diff_df(
            hepar_df,
            hepeel_df,
            summary_df,
            groups,
            min_total_intensity=float(q10_min_total_int or 0.0),
        )

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        if df.empty:
            fig = px.bar(title="No differential features (after intensity filter)")
            empty_columns = [{"name": c, "id": c} for c in df.columns]
            return fig, [], empty_columns, "No differential features available."

        # Filter by direction
        dirs = set(q10_dirs or ["Hepar higher", "Hepeel higher"])
        df = df[df["direction"].isin(dirs)].copy()
        if df.empty:
            fig = px.bar(title="No features for selected directions")
            empty_columns = [{"name": c, "id": c} for c in df.columns]
            stats = "No features for selected directions."
            return fig, [], empty_columns, stats

        # Filter by absolute log2 fold-change
        min_abs = float(q10_min_abs_log2 or 0.0)
        df = df[df["log2_fc"].abs() >= min_abs].copy()
        if df.empty:
            fig = px.bar(title="No features above |log2 fold-change| threshold")
            empty_columns = [{"name": c, "id": c} for c in df.columns]
            stats = f"No features with |log2FC| >= {min_abs:.2f}."
            return fig, [], empty_columns, stats

        # Sort by absolute log2 fold-change and limit Top-N
        df["abs_log2_fc"] = df["log2_fc"].abs()
        dff = df.sort_values("abs_log2_fc", ascending=False).head(
            int(q10_top_n or 100)
        )
        import plotly.graph_objects as go
        import numpy as np

        # Dense x positions starting at 0 (very close spacing)
        x_pos = np.arange(len(dff)) * 0.25  # smaller factor = closer sticks

        fig = go.Figure()

        # Vertical sticks (from 0 to log2_fc)
        fig.add_trace(
            go.Scatter(
                x=x_pos,
                y=dff["log2_fc"],
                mode="lines",
                line=dict(width=2, color="rgba(120,120,120,0.8)"),
                hoverinfo="skip",
                showlegend=False,
            )
        )

        # Dots at the end of each stick
        fig.add_trace(
            go.Scatter(
                x=x_pos,
                y=dff["log2_fc"],
                mode="markers",
                marker=dict(
                    size=7,
                    color=dff["log2_fc"],
                    colorscale="RdBu",
                    cmin=-abs(dff["log2_fc"]).max(),
                    cmax=abs(dff["log2_fc"]).max(),
                    showscale=True,
                    colorbar=dict(title="log2FC"),
                ),
                text=dff["feature"],
                customdata=dff[
                    [
                        "Hepar_intensity",
                        "Hepeel_intensity",
                        "direction",
                        "name",
                    ]
                ].values,
                hovertemplate=
                "<b>%{text}</b><br>" +
                "log2FC: %{y:.2f}<br>" +
                "Hepar intensity: %{customdata[0]}<br>" +
                "Hepeel intensity: %{customdata[1]}<br>" +
                "Direction: %{customdata[2]}<br>" +
                "Name: %{customdata[3]}<extra></extra>",
                showlegend=False,
            )
        )

        # Zero reference line
        fig.add_hline(
            y=0,
            line_width=1,
            line_dash="dash",
            line_color="rgba(150,150,150,0.6)",
        )

        # Layout: origin-aligned, compact, auto-fit
        fig.update_layout(
            autosize=True,
            height=520,
            margin=dict(l=20, r=20, t=40, b=40),
            xaxis=dict(
                title="Features (ranked by |log2FC|)",
                showticklabels=False,  # hide crowded labels
                range=[-0.1, x_pos[-1] + 0.3],
                zeroline=False,
            ),
            yaxis=dict(
                title="log2(Hepar / Hepeel)",
                zeroline=False,
            ),
        )

        columns = [
            {"name": c, "id": c}
            for c in dff.columns
            if c not in {"abs_log2_fc", "total_intensity"}
        ]
        n_hepar = int((dff["direction"] == "Hepar higher").sum())
        n_hepeel = int((dff["direction"] == "Hepeel higher").sum())
        stats = (
            f"Features shown: {len(dff):,} "
            f"(Hepar higher: {n_hepar}, Hepeel higher: {n_hepeel}) | "
            f"min combined intensity: {float(q10_min_total_int or 0.0):.1f} "
            f"| min |log2FC|: {min_abs:.2f}"
        )
        return fig, dff.to_dict("records"), columns, stats

    @app.callback(
        Output("set_table", "data"),
        Output("set_table", "columns"),
        Output("set_stats", "children"),
        Input("product", "value"),
        Input("set_mode", "value"),
        Input("set_source", "value"),
        Input("set_search", "value"),
        Input("set_max_rows", "value"),
        Input("only_pubchem", "value"),
    )
    def update_set_table(
        set_product: str,
        set_mode: str,
        set_source: str,
        set_search: str,
        set_max_rows: int,
        only_pubchem_vals,
    ):
        prod_df = data[set_product].features
        prod_ids = set(prod_df["feature"].astype(str).dropna())

        if set_mode == "product_only":
            df = build_product_only_df(prod_df, summary_df, groups)
            title = "Q5: Product-only features"
        else:
            df = build_component_only_df(prod_ids, summary_df, groups)
            title = "Q4: Component-only features"
            if set_source != "all" and "source" in df.columns:
                df = df[df["source"] == set_source]

        # Global filter: keep only features with PubChem CID(s)
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        if set_search and str(set_search).strip():
            s = str(set_search).strip()
            df = df[df["feature"].astype(str).str.contains(s, case=False, na=False)]

        df = df.head(int(set_max_rows))

        columns = [{"name": c, "id": c} for c in df.columns]
        stats = f"{title} | rows shown: {len(df):,} | product: {set_product}"
        return df.to_dict("records"), columns, stats

    return app


if __name__ == "__main__":
    app = build_app()
    app.run(debug=True, use_reloader=False)