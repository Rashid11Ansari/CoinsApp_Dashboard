from __future__ import annotations

from pathlib import Path
import re
import math


import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, State, dash_table, callback_context, no_update
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# Guard against bad/unsupported default templates causing px.bar() to crash
pio.templates.default = "plotly"

from data_loader import load_all
from layout import build_layout

APP_TITLE = "MS Feature Explorer (Origin-aware)"

_PUBCHEM_RE = re.compile(r"\d+")

# Final product columns (authoritative)
Q8_HEPAR_FINAL_COL = "Hepar.comp.Ampoules..Bulk.mat.52324."

Q8_HEPEEL_FINAL_COL = "Hepeel.ampoule.solution..Bulk"

# =============================
# App structure
# =============================
# - Helpers: column matching, PubChem parsing, origin set construction
# - Per-question helpers: Q3/Q4/Q5/Q6/Q7/Q8/Q9/Q10
# - build_app(): loads data, defines layout, and registers Dash callbacks
#
# NOTE: Component column lists come from data_loader via `groups` (populated from JSON config).
#       Hepar has plant+animal components; Hepeel is plant-only.

def _norm_col(s: str) -> str:
    s = str(s).strip().lower()
    s = s.replace(".", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_col(df: pd.DataFrame, target: str) -> str:
    """Best-effort column match: exact normalized match first, then substring match."""
    t = _norm_col(target)
    col_norm = {c: _norm_col(c) for c in df.columns}

    for c, cn in col_norm.items():
        if cn == t:
            return c

    for c, cn in col_norm.items():
        if t in cn:
            return c

    raise KeyError(f"Q8: could not find column matching '{target}'")

def _q8_state(prod: float, comp_max: float, amp_thr: float) -> str:
    if pd.isna(prod) or pd.isna(comp_max) or comp_max <= 0:
        return "unknown" if pd.isna(comp_max) or comp_max <= 0 else "unchanged"
    ratio = prod / comp_max if comp_max else float("nan")
    if ratio >= amp_thr:
        return "amplified"
    if ratio <= (1.0 / amp_thr):
        return "attenuated"
    return "unchanged"


def _q8_empty_figure(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=0.12,
        x1=0.88,
        y0=0.3,
        y1=0.7,
        line={"color": "#cbd5e1", "width": 1, "dash": "dot"},
        fillcolor="rgba(241,245,249,0.7)",
    )
    fig.add_annotation(
        text=msg,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 13, "color": "#475569"},
    )
    fig.update_layout(
        template="plotly",
        margin=dict(l=20, r=20, t=40, b=40),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _q8_log10_ratio_series(sr: pd.Series) -> np.ndarray:
    r = pd.to_numeric(sr, errors="coerce").replace(0, np.nan).clip(lower=1e-300)
    return np.log10(r.to_numpy(dtype=float))


def extract_pubchem_cids(val) -> list[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    cids = _PUBCHEM_RE.findall(s)
    seen = set()
    out: list[str] = []
    for cid in cids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def has_pubchem(val) -> bool:
    return len(extract_pubchem_cids(val)) > 0


def render_pubchem_links(val):
    cids = extract_pubchem_cids(val)
    if not cids:
        return ["NA"]
    children = []
    for i, cid in enumerate(cids):
        if i > 0:
            children.append(", ")
        children.append(
            html.A(
                cid,
                href=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                target="_blank",
                rel="noopener noreferrer",
                style={"textDecoration": "underline"},
            )
        )
    return children


def present_in_any(summary_df: pd.DataFrame, feature_ids: set[str], cols: list[str], threshold: float = 0) -> set[str]:
    if not cols:
        return set()
    sub = summary_df[summary_df["feature"].isin(feature_ids)]
    mask = (sub[cols] > threshold).any(axis=1)
    return set(sub.loc[mask, "feature"].astype(str))

def get_product_component_cols(product: str, groups: dict) -> tuple[list[str], list[str]]:
    """Return (plant_cols, animal_cols) for the selected product."""
    p = str(product).lower()
    if "hepar" in p:
        plant_cols = list(groups.get("hepar_plant_cols", []))
        animal_cols = list(groups.get("hepar_animal_cols", []))
    else:
        plant_cols = list(groups.get("hepeel_plant_cols", []))
        animal_cols = []  # Hepeel has no animal components in our data
    return plant_cols, animal_cols

def compute_origin_sets(product: str, product_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict, threshold: float = 0) -> dict[str, set[str]]:
    """Q1 origin buckets for the selected product (per-product plant/animal sources)."""
    prod_ids = set(product_df["feature"].astype(str).dropna())

    plant_cols, animal_cols = get_product_component_cols(product, groups)

    plant_ids = present_in_any(summary_df, prod_ids, plant_cols, threshold=threshold)
    animal_ids = present_in_any(summary_df, prod_ids, animal_cols, threshold=threshold)

    common = plant_ids & animal_ids
    plant_only = plant_ids - animal_ids
    animal_only = animal_ids - plant_ids
    product_only = prod_ids - (plant_ids | animal_ids)

    return {
        "All product features": prod_ids,
        "Product-only (vs components)": product_only,
        "Plant-only": plant_only,
        "Animal-only": animal_only,
        "Common (plant+animal)": common,
    }

def compute_product_sets(product: str, data: dict) -> dict[str, set[str]]:
    """
    Sets based on Hepar vs Hepeel (final products only):
      - All product features
      - Unique to product (vs other product)
      - Shared (both products)
    """
    product_names = [k for k in data.keys() if not str(k).startswith("_")]
    if product not in product_names:
        return {"All product features": set(), "Unique to product": set(), "Shared (both products)": set()}

    # assume exactly 2 products (Hepar + Hepeel)
    other = next((p for p in product_names if p != product), None)
    if other is None:
        prod_ids = set(data[product].features["feature"].astype(str).dropna())
        return {"All product features": prod_ids, "Unique to product": set(), "Shared (both products)": set()}

    prod_ids = set(data[product].features["feature"].astype(str).dropna())
    other_ids = set(data[other].features["feature"].astype(str).dropna())

    unique_vs_other = prod_ids - other_ids
    shared_both = prod_ids & other_ids

    return {
        "All product features": prod_ids,
        "Unique to product": unique_vs_other,
        "Shared (both products)": shared_both,
    }

def q6_feature_contrib(summary_df, feature_id, ingredient_cols, plant_cols, animal_cols):
    row = summary_df[summary_df["feature"].astype(str) == str(feature_id)]
    if row.empty:
        return pd.DataFrame(columns=["Ingredient", "Raw", "Log10", "Type"]), None

    contrib = row[ingredient_cols].T.reset_index()
    contrib.columns = ["Ingredient", "Raw"]
    contrib["Raw"] = pd.to_numeric(contrib["Raw"], errors="coerce").fillna(0)
    contrib["Log10"] = np.log10(contrib["Raw"].replace(0, np.nan))

    animal_set = set(animal_cols)
    contrib["Type"] = ["Animal" if c in animal_set else "Plant" for c in contrib["Ingredient"]]

    dominant = None
    if contrib["Raw"].gt(0).any():
        dominant = contrib.loc[contrib["Raw"].idxmax(), "Ingredient"]

    return contrib.sort_values("Raw", ascending=False), dominant


def q6_get_ingredient_cols_for_product(product: str, summary_df: pd.DataFrame, groups: dict) -> tuple[list[str], list[str], list[str]]:
    """Return (ingredient_cols, plant_cols, animal_cols) for Q6 using JSON config groups."""
    if "hepar" in str(product).lower():
        ingredient_cols = [c for c in groups.get("hepar_component_cols", []) if c in summary_df.columns]
        plant_cols = [c for c in groups.get("hepar_plant_cols", []) if c in summary_df.columns]
        animal_cols = [c for c in groups.get("hepar_animal_cols", []) if c in summary_df.columns]
    else:
        ingredient_cols = [c for c in groups.get("hepeel_component_cols", []) if c in summary_df.columns]
        plant_cols = [c for c in groups.get("hepeel_plant_cols", []) if c in summary_df.columns]
        animal_cols = []  # Hepeel has no animal

    return ingredient_cols, plant_cols, animal_cols


# -----------------------------
# Q5 START: Product-only features (present in final product list, absent in raw components)
# -----------------------------

def build_product_only_df(product: str, prod_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """Q5: features present in the selected final product feature list but absent in its raw component columns."""

    prod_df = prod_df.copy()
    prod_df["feature"] = prod_df["feature"].astype(str)

    origin_sets = compute_origin_sets(product, prod_df, summary_df, groups, threshold=0)
    ids = origin_sets.get("Product-only (vs components)", set())

    dff = prod_df[prod_df["feature"].isin(set(map(str, ids)))].copy()

    # merge helpful annotations
    annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in summary_df.columns]
    if annot_cols:
        annot = summary_df[annot_cols].drop_duplicates("feature").copy()
        annot["feature"] = annot["feature"].astype(str)
        dff = dff.merge(annot, on="feature", how="left")

    # ensure intensity numeric if present
    if "intensity" in dff.columns:
        dff["intensity"] = pd.to_numeric(dff["intensity"], errors="coerce").fillna(0)

    keep = [c for c in ["feature", "intensity", "log10_intensity", "Average.Mz", "Average.Rt.min.", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in dff.columns]
    if "intensity" in keep:
        dff = dff.sort_values("intensity", ascending=False)

    return dff[keep]

# -----------------------------
# Q4 START: Component-only features
# (present in raw components, absent in final product)
# -----------------------------
def build_component_only_df(product: str, prod_feature_ids: set[str], summary_df: pd.DataFrame, groups: dict, presence_thr: float = 0.0
) -> pd.DataFrame:
    """Q4: features present in raw component columns but absent in the selected product feature list."""

    # choose per-product component columns
    if "hepar" in str(product).lower():
        comp_base = list(groups.get("hepar_component_cols", []))
        plant_cols = list(groups.get("hepar_plant_cols", []))
        animal_cols = list(groups.get("hepar_animal_cols", []))
    else:
        comp_base = list(groups.get("hepeel_component_cols", []))
        plant_cols = list(groups.get("hepeel_plant_cols", []))
        animal_cols = []

    # keep only cols that exist
    comp_cols = [c for c in comp_base if c in summary_df.columns]
    plant_cols = [c for c in plant_cols if c in summary_df.columns]
    animal_cols = [c for c in animal_cols if c in summary_df.columns]

    if not comp_cols:
        return pd.DataFrame(columns=["feature", "source", "max_component_intensity"])

    # numeric safety
    sdf0 = summary_df.copy()
    for c in comp_cols:
        sdf0[c] = pd.to_numeric(sdf0[c], errors="coerce").fillna(0)

    # features present in ANY component column (threshold-aware)
    comp_present_mask = (sdf0[comp_cols] > presence_thr).any(axis=1)
    comp_present = sdf0.loc[comp_present_mask, "feature"].astype(str)

    # Q4 set = present in components but not in product feature list
    comp_only_ids = set(comp_present) - set(map(str, prod_feature_ids))
    sdf = sdf0[sdf0["feature"].astype(str).isin(comp_only_ids)].copy()

    # source labeling (threshold-aware)
    plant_present = (sdf[plant_cols] > presence_thr).any(axis=1) if plant_cols else pd.Series(False, index=sdf.index)
    animal_present = (sdf[animal_cols] > presence_thr).any(axis=1) if animal_cols else pd.Series(False, index=sdf.index)

    def _src(p: bool, a: bool) -> str:
        if p and a:
            return "Common (plant+animal)"
        if p:
            return "Plant"
        if a:
            return "Animal"
        return "Unknown"

    sdf["source"] = [_src(bool(p), bool(a)) for p, a in zip(plant_present, animal_present)]
    sdf["max_component_intensity"] = sdf[comp_cols].max(axis=1)

    keep = [c for c in ["feature", "source", "max_component_intensity", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in sdf.columns]
    return sdf[keep].sort_values("max_component_intensity", ascending=False)

# EXPLORE PLOT HELPERS START
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

# Q3 HELPERS START
def _ensure_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def add_q3_component_sums_and_dominance(
    dff: pd.DataFrame,
    summary_df: pd.DataFrame,
    groups: dict,
    product: str,
    dom_ratio: float,
    presence_thr: float = 0.0,   # <-- NEW: ignore tiny noise
) -> pd.DataFrame:
    """
    Adds per-feature:
      plant_sum, animal_sum, plant_frac, animal_frac, q3_class
    where q3_class ∈ {Plant-dominant, Animal-dominant, Mixed, Product-only}.
    """

    # ✅ per-product cols (Hepar has animal; Hepeel animal = [])
    plant_cols, animal_cols = get_product_component_cols(product, groups)
    plant_cols = [c for c in plant_cols if c in summary_df.columns]
    animal_cols = [c for c in animal_cols if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    out = dff.copy()
    out["feature"] = out["feature"].astype(str)

    if not comp_cols:
        out["plant_sum"] = 0.0
        out["animal_sum"] = 0.0
        out["plant_frac"] = 0.0
        out["animal_frac"] = 0.0
        out["q3_class"] = "Product-only"
        return out

    comp = summary_df[["feature"] + comp_cols].drop_duplicates("feature").copy()
    comp["feature"] = comp["feature"].astype(str)
    comp = _ensure_numeric_cols(comp, comp_cols)

    # ✅ Apply presence threshold to reduce noise (anything <= thr counts as 0)
    if presence_thr > 0:
        for c in comp_cols:
            comp[c] = np.where(comp[c] > presence_thr, comp[c], 0.0)

    comp["plant_sum"] = comp[plant_cols].sum(axis=1) if plant_cols else 0.0
    comp["animal_sum"] = comp[animal_cols].sum(axis=1) if animal_cols else 0.0
    comp["total_comp_sum"] = comp["plant_sum"] + comp["animal_sum"]

    comp["plant_frac"] = np.where(comp["total_comp_sum"] > 0, comp["plant_sum"] / comp["total_comp_sum"], 0.0)
    comp["animal_frac"] = np.where(comp["total_comp_sum"] > 0, comp["animal_sum"] / comp["total_comp_sum"], 0.0)

    def _label(ps: float, an: float) -> str:
        if ps <= 0 and an <= 0:
            return "Product-only"
        if an <= 0 < ps:
            return "Plant-dominant"
        if ps <= 0 < an:
            return "Animal-dominant"
        if ps >= dom_ratio * an:
            return "Plant-dominant"
        if an >= dom_ratio * ps:
            return "Animal-dominant"
        return "Mixed"

    comp["q3_class"] = [_label(float(ps), float(an)) for ps, an in zip(comp["plant_sum"], comp["animal_sum"])]

    out = out.merge(
        comp[["feature", "plant_sum", "animal_sum", "plant_frac", "animal_frac", "q3_class"]],
        on="feature",
        how="left",
    )

    for c in ["plant_sum", "animal_sum", "plant_frac", "animal_frac"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    out["q3_class"] = out["q3_class"].fillna("Product-only")

    return out


def make_q3_prop_bar(dff: pd.DataFrame):
    if dff.empty or "intensity" not in dff.columns:
        return px.bar(pd.DataFrame({"category": [], "fraction": []}), x="category", y="fraction")

    dff2 = dff.copy()
    dff2["intensity"] = pd.to_numeric(dff2["intensity"], errors="coerce").fillna(0)

    total = float(dff2["intensity"].sum())
    if total <= 0:
        return px.bar(pd.DataFrame({"category": [], "fraction": []}), x="category", y="fraction")

    cats = ["Plant-dominant", "Animal-dominant", "Mixed", "Product-only"]
    rows = []
    for c in cats:
        s = float(dff2.loc[dff2["q3_class"] == c, "intensity"].sum())
        rows.append({"category": c, "fraction": s / total, "signal_sum": s})

    dfb = pd.DataFrame(rows)

    fig = px.bar(
        dfb,
        x="category",
        y="fraction",
        color="category",
        hover_data={"signal_sum": ":.3g", "fraction": ":.3f"},
        template="plotly",
        color_discrete_map={
            "Plant-dominant": "red",
            "Animal-dominant": "green",
            "Mixed": "gold",
            "Product-only": "black",
        },
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Fraction of total product signal",
        yaxis_tickformat=".0%",
        margin=dict(l=20, r=20, t=40, b=60),
        legend_title_text="",
    )
    return fig


def make_q3_scatter(dff: pd.DataFrame, use_log: bool):
    if dff.empty:
        return px.scatter(pd.DataFrame({"Average.Rt.min.": [], "intensity": []}), x="Average.Rt.min.", y="intensity")

    ycol = "log10_intensity" if use_log and "log10_intensity" in dff.columns else "intensity"

    d = dff.dropna(subset=["Average.Rt.min.", ycol]).copy()

    hover_cols = [c for c in [
        "feature", "intensity", "Average.Mz",
        "plant_sum", "animal_sum", "plant_frac", "animal_frac"
    ] if c in d.columns]

    fig = px.scatter(
        d,
        x="Average.Rt.min.",
        y=ycol,
        color="q3_class",
        hover_data=hover_cols,
        template="plotly",
        color_discrete_map={
            "Plant-dominant": "red",
            "Animal-dominant": "green",
            "Mixed": "gold",
            "Product-only": "black",
        },
    )
    fig.update_layout(
        xaxis_title="RT (min)",
        yaxis_title=ycol,
        margin=dict(l=20, r=20, t=40, b=50),
        legend_title_text="",
    )
    return fig

def build_app() -> Dash:
    data_dir = Path(__file__).resolve().parent / "data"
    data = load_all(str(data_dir))
    summary_df = data["_summary"]
    groups = data["_groups"]
    # print("hepar_plant_cols:", groups.get("hepar_plant_cols", []))
    # print("hepar_animal_cols:", groups.get("hepar_animal_cols", []))
    # print("hepeel_plant_cols:", groups.get("hepeel_plant_cols", []))

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = APP_TITLE

    origin_options = [
        {"label": "All product features", "value": "All product features"},
        {"label": "Unique to product (vs other product)", "value": "Unique to product"},
        {"label": "Shared (both products)", "value": "Shared (both products)"},
        {"label": "Product-only (vs components)", "value": "Product-only (vs components)"},
        {"label": "Plant-only", "value": "Plant-only"},
        {"label": "Animal-only", "value": "Animal-only"},
        {"label": "Common (plant+animal components)", "value": "Common (plant+animal)"},
    ]
    app.layout = build_layout(APP_TITLE, origin_options)

    # ---- Global: sync NEW linear intensity slider/inputs and BRIDGE to legacy log10 slider ----
    @app.callback(
        Output("global_intensity_range", "value"),
        Output("global_intensity_min", "value"),
        Output("global_intensity_max", "value"),
        Output("global_intensity_range_label", "children"),
        Output("global_intensity_log_range", "value"),
        Input("global_intensity_range", "value"),
        Input("global_intensity_min", "value"),
        Input("global_intensity_max", "value"),
        Input("product", "value"),
    )
    def sync_global_intensity_linear_to_log(range_val, min_val, max_val, product):
        # defaults
        default_lo, default_hi = 1000.0, 50000.0

        # normalize product (Dash may pass list)
        if isinstance(product, (list, tuple)):
            product = product[0] if product else "Hepar"
        if not product:
            product = "Hepar"

        # start from slider range
        lo = default_lo
        hi = default_hi
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            lo = float(range_val[0]) if range_val[0] is not None else lo
            hi = float(range_val[1]) if range_val[1] is not None else hi

        # determine which input triggered
        trig = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""

        # if user typed min/max, update lo/hi
        if trig == "global_intensity_min" and min_val is not None:
            lo = float(min_val)
        if trig == "global_intensity_max" and max_val is not None:
            hi = float(max_val)

        # ensure sane bounds
        if lo < 0:
            lo = 0.0
        if hi < 0:
            hi = 0.0
        if lo > hi:
            lo, hi = hi, lo

        # label for UI
        label = f"Showing features with product intensity between {lo:,.0f} and {hi:,.0f}"

        # bridge to legacy log10 slider used throughout the app
        lo_for_log = max(lo, 1e-9)  # avoid log10(0)
        hi_for_log = max(hi, 1e-9)
        log_lo = math.log10(lo_for_log)
        log_hi = math.log10(hi_for_log)

        # old slider was 2..7; clamp so existing code doesn't break
        log_lo = max(2.0, min(7.0, log_lo))
        log_hi = max(2.0, min(7.0, log_hi))
        if log_lo > log_hi:
            log_lo, log_hi = log_hi, log_lo

        return [lo, hi], lo, hi, label, [log_lo, log_hi]
    # ---- Q10: sync linear Δ_final threshold (slider+input) to legacy log threshold ----
    @app.callback(
        Output("q10_diff_thr_slider", "value"),
        Output("q10_diff_thr_value", "value"),
        Output("q10_diff_log_thr", "value"),
        Input("q10_diff_thr_slider", "value"),
        Input("q10_diff_thr_value", "value"),
    )
    def sync_q10_threshold_linear_to_log(slider_val, box_val):
        # Which input triggered?
        trig = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""

        # Default threshold (linear)
        thr = 5000.0

        # If user typed in the box, use that; otherwise slider
        if trig == "q10_diff_thr_value" and box_val is not None:
            thr = float(box_val)
        elif slider_val is not None:
            thr = float(slider_val)

        if thr < 0:
            thr = 0.0

        # Convert to log10 threshold used by existing Q10 logic
        thr_for_log = max(thr, 1e-9)  # avoid log10(0)
        log_thr = math.log10(thr_for_log)

        # Clamp to existing Q10 log slider range (your layout uses -2..8)
        log_thr = max(-2.0, min(8.0, log_thr))

        return thr, thr, log_thr

    # ---- Navigation: show/hide views and set origin_filter ----
    @app.callback(
        Output("app_root", "style"),
        Output("view_home", "style"),
        Output("view_explore", "style"),
        Output("view_q1", "style"),
        Output("view_q3", "style"),
        Output("view_q4", "style"),
        Output("view_q5", "style"),
        Output("view_q6", "style"),
        Output("view_q7", "style"),
        Output("view_q8", "style"),
        Output("view_q9", "style"),
        Output("view_q10", "style"),
        Output("origin_filter", "value"),
        Input("page_select", "value"),
    )

    def switch_view(page_select: str):
        show = {"display": "block"}
        show_home = {"display": "block", "backgroundColor": "#0b1220", "padding": "10px", "borderRadius": "12px"}
        hide = {"display": "none"}

        analysis_root_style = {
            "display": "flex",
            "minHeight": "100vh",
            "alignItems": "stretch",
            "gap": "12px",
            "maxWidth": "1720px",
            "margin": "0 auto",
            "padding": "10px",
        }
        home_root_style = {
            "display": "flex",
            "minHeight": "100vh",
            "alignItems": "stretch",
            "gap": "0px",
            "maxWidth": "100%",
            "margin": "0",
            "padding": "0",
            "backgroundColor": "#0b1220",
        }

        origin_val = "All product features"

        def _pack(root_style, home_s, explore_s, q1_s, q3_s, q4_s, q5_s, q6_s, q7_s, q8_s, q9_s, q10_s, origin):
            return (
                root_style,
                home_s,
                explore_s,
                q1_s,
                q3_s,
                q4_s,
                q5_s,
                q6_s,
                q7_s,
                q8_s,
                q9_s,
                q10_s,
                origin,
            )

        if not page_select:
            return _pack(home_root_style, show_home, hide, hide, hide, hide, hide, hide, hide, hide, hide, hide, origin_val)

        if isinstance(page_select, str) and page_select.startswith("explore::"):
            origin_val = page_select.split("::", 1)[1]
            return _pack(analysis_root_style, hide, show, hide, hide, hide, hide, hide, hide, hide, hide, hide, origin_val)
        if page_select == "home":
            return _pack(home_root_style, show_home, hide, hide, hide, hide, hide, hide, hide, hide, hide, hide, origin_val)
        if page_select == "q1":
            return _pack(analysis_root_style, hide, hide, show, hide, hide, hide, hide, hide, hide, hide, hide, origin_val)
        if page_select == "q3":
            return _pack(analysis_root_style, hide, hide, hide, show, hide, hide, hide, hide, hide, hide, hide, origin_val)
        if page_select == "q4":
            return _pack(analysis_root_style, hide, hide, hide, hide, show, hide, hide, hide, hide, hide, hide, origin_val)
        if page_select == "q5":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, show, hide, hide, hide, hide, hide, origin_val)
        if page_select == "q6":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, hide, show, hide, hide, hide, hide, origin_val)
        if page_select == "q7":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, hide, hide, show, hide, hide, hide, origin_val)
        if page_select == "q8":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, hide, hide, hide, show, hide, hide, origin_val)
        if page_select == "q9":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, hide, hide, hide, hide, show, hide, origin_val)
        if page_select == "q10":
            return _pack(analysis_root_style, hide, hide, hide, hide, hide, hide, hide, hide, hide, hide, show, origin_val)

        return _pack(home_root_style, show_home, hide, hide, hide, hide, hide, hide, hide, hide, hide, hide, origin_val)

    @app.callback(
        Output("home_quick_stats_dynamic", "children"),
        Input("product", "value"),
    )
    def update_home_quick_stats(product):
        hepar_df = data["Hepar"].features.copy()
        hepeel_df = data["Hepeel"].features.copy()
        hepar_ids = set(hepar_df["feature"].astype(str).dropna())
        hepeel_ids = set(hepeel_df["feature"].astype(str).dropna())
        shared_n = len(hepar_ids & hepeel_ids)
        uniq_hepar_n = len(hepar_ids - hepeel_ids)
        uniq_hepeel_n = len(hepeel_ids - hepar_ids)

        current_n = 0
        if product in data and "feature" in data[product].features.columns:
            current_n = int(data[product].features["feature"].astype(str).nunique())

        stats = [
            ("Features in selection", f"{current_n:,}"),
            ("Shared features", f"{shared_n:,}"),
            ("Unique to Hepar", f"{uniq_hepar_n:,}"),
            ("Unique to Hepeel", f"{uniq_hepeel_n:,}"),
        ]

        cards = []
        for label, value in stats:
            cards.append(
                html.Div(
                    className="home-stat-card",
                    style={
                        "border": "1px solid #e5e7eb",
                        "borderRadius": "12px",
                        "padding": "12px",
                        "backgroundColor": "#ffffff",
                        "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                    },
                    children=[
                        html.Div(label, style={"fontSize": "12px", "color": "#64748b", "fontWeight": "600"}),
                        html.Div(value, style={"fontSize": "22px", "fontWeight": "700", "color": "#0f172a", "marginTop": "2px"}),
                    ],
                )
            )
        return cards

    @app.callback(
        Output("home_product_toggle_button", "children"),
        Input("product", "value"),
    )
    def update_home_product_toggle_button(product):
        product_str = str(product) if product else "Hepar"
        return [
            html.Div("Selected product", style={"fontSize": "12px", "color": "#64748b", "fontWeight": "600", "marginBottom": "6px"}),
            html.Div(product_str, style={"fontSize": "22px", "fontWeight": "700", "color": "#0f172a", "lineHeight": 1.1}),
            html.Div("Click to switch product", style={"fontSize": "11px", "fontStyle": "italic", "color": "#64748b", "marginTop": "6px"}),
        ]

    @app.callback(
        Output("home_hero_buttons", "className"),
        Output("home_toggle_analysis_menu", "children"),
        Input("home_toggle_analysis_menu", "n_clicks"),
    )
    def toggle_home_analysis_menu(n_clicks):
        is_open = bool(n_clicks and n_clicks % 2 == 1)
        if is_open:
            return "analysis-menu analysis-menu--open", "Analysis ▾"
        return "analysis-menu analysis-menu--closed", "Analysis ▸"

    @app.callback(
        Output("app_root", "className"),
        Output("home_theme_custom", "className"),
        Output("home_theme_a", "className"),
        Output("home_theme_b", "className"),
        Output("home_theme_c", "className"),
        Input("home_theme_custom", "n_clicks"),
        Input("home_theme_a", "n_clicks"),
        Input("home_theme_b", "n_clicks"),
        Input("home_theme_c", "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_home_theme(custom_clicks, theme_a_clicks, theme_b_clicks, theme_c_clicks):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        theme_map = {
            "home_theme_custom": "theme-custom",
            "home_theme_a": "theme-a",
            "home_theme_b": "theme-b",
            "home_theme_c": "theme-c",
        }
        selected = theme_map.get(trigger, "theme-custom")
        custom_cls = "theme-chip theme-chip--active" if selected == "theme-custom" else "theme-chip"
        a_cls = "theme-chip theme-chip--active" if selected == "theme-a" else "theme-chip"
        b_cls = "theme-chip theme-chip--active" if selected == "theme-b" else "theme-chip"
        c_cls = "theme-chip theme-chip--active" if selected == "theme-c" else "theme-chip"
        return selected, custom_cls, a_cls, b_cls, c_cls

    @app.callback(
        Output("product", "value"),
        Input("home_product_toggle_button", "n_clicks"),
        State("product", "value"),
        prevent_initial_call=True,
    )
    def toggle_home_product(n_clicks, current_product):
        if not n_clicks:
            return no_update
        current = str(current_product) if current_product else "Hepar"
        return "Hepeel" if current == "Hepar" else "Hepar"

    @app.callback(
        Output("analysis_sidebar", "style"),
        Input("page_select", "value"),
    )
    def toggle_analysis_back_button(page_select):
        if str(page_select) == "home":
            return {"display": "none"}
        return {"display": "block"}

    @app.callback(
        Output("analysis_chem_bg", "style"),
        Input("page_select", "value"),
    )
    def toggle_analysis_background(page_select):
        if str(page_select) == "home":
            return {"display": "none"}
        return {"display": "block"}

    @app.callback(
        Output("main_content_shell", "className"),
        Output("page_transition_state", "data"),
        Input("page_select", "value"),
        State("page_transition_state", "data"),
    )
    def update_transition_mode(page_select, transition_state):
        state = transition_state or {"prev": "home", "flip": 0}
        prev_page = str(state.get("prev", "home"))
        flip = int(state.get("flip", 0))
        current_page = str(page_select or "home")

        cls = "main-content-shell transition-none"
        if prev_page == "home" and current_page != "home":
            cls = "main-content-shell transition-zoom-in"

        return cls, {"prev": current_page, "flip": flip}

    @app.callback(
        Output("page_select", "value"),
        Input("home_go_explore", "n_clicks"),
        Input("home_go_q1", "n_clicks"),
        Input("home_go_q3", "n_clicks"),
        Input("home_go_q4", "n_clicks"),
        Input("home_go_q5", "n_clicks"),
        Input("home_go_q6", "n_clicks"),
        Input("home_go_q7", "n_clicks"),
        Input("home_go_q8", "n_clicks"),
        Input("home_go_q9", "n_clicks"),
        Input("home_go_q10", "n_clicks"),
        Input("analysis_back_home", "n_clicks"),
        prevent_initial_call=True,
    )
    def home_navigation_router(
        go_explore,
        go_q1,
        go_q3,
        go_q4,
        go_q5,
        go_q6,
        go_q7,
        go_q8,
        go_q9,
        go_q10,
        back_home,
    ):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        route_map = {
            "home_go_explore": "explore::Shared between Hepar & Hepeel",
            "home_go_q1": "q1",
            "home_go_q3": "q3",
            "home_go_q4": "q4",
            "home_go_q5": "q5",
            "home_go_q6": "q6",
            "home_go_q7": "q7",
            "home_go_q8": "q8",
            "home_go_q9": "q9",
            "home_go_q10": "q10",
            "analysis_back_home": "home",
        }
        return route_map.get(trigger, "home")

    @app.callback(
        Output("page_select", "value", allow_duplicate=True),
        Input("analysis_prev_question", "n_clicks"),
        Input("analysis_next_question", "n_clicks"),
        State("page_select", "value"),
        prevent_initial_call=True,
    )
    def sidebar_question_step(prev_clicks, next_clicks, current_page):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        question_order = ["q1", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"]

        current = str(current_page or "")
        if current not in question_order:
            if trigger == "analysis_next_question":
                return question_order[0]
            if trigger == "analysis_prev_question":
                return question_order[-1]
            return no_update

        idx = question_order.index(current)
        if trigger == "analysis_next_question":
            return question_order[(idx + 1) % len(question_order)]
        if trigger == "analysis_prev_question":
            return question_order[(idx - 1) % len(question_order)]
        return no_update


    # ---- Q6: interaction state (selected feature + closable card) ----
    @app.callback(
        Output("q6_selected_feature", "data"),
        Output("q6_card_open", "data"),
        Input("q6_dom_bar", "clickData"),
        Input("q6_feature_id", "value"),
        Input("q6_close_card", "n_clicks"),
        State("q6_selected_feature", "data"),
        State("q6_card_open", "data"),
        prevent_initial_call=True,
    )
    def update_q6_selection(q6_clickData, q6_feature_id, q6_close_clicks, current_selected, current_open):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
        if trigger == "q6_close_card":
            return no_update, False
        if trigger == "q6_feature_id":
            typed = str(q6_feature_id).strip() if q6_feature_id else ""
            if typed:
                return typed, True
            return current_selected, current_open
        if trigger == "q6_dom_bar" and q6_clickData and q6_clickData.get("points"):
            return str(q6_clickData["points"][0].get("x")), True
        return current_selected, current_open

    # ---- Q6: Feature-level ingredient contribution drilldown ----
    @app.callback(
        Output("q6_dom_bar", "figure"),
        Output("q6_contrib_bar", "figure"),
        Output("q6_table", "data"),
        Output("q6_table", "columns"),
        Output("q6_stats", "children"),
        Output("q6_card_body", "children"),
        Output("q6_feature_card", "style"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q6_top_n", "value"),
        Input("q6_selected_feature", "data"),
        Input("q6_card_open", "data"),
    )
    def update_q6(product, feature_search, only_pubchem_vals, global_intensity_log_range, q6_top_n, q6_selected_feature, q6_card_open):
        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        ingredient_cols, plant_cols, animal_cols = q6_get_ingredient_cols_for_product(product, sdf, groups)
        if not ingredient_cols:
            empty = px.bar(title="Q6: No ingredient columns matched")
            return empty, empty, [], [], "Q6: No ingredient columns matched for this product.", html.Div("No feature selected."), {"display": "none"}

        # numeric conversion for ingredient cols
        for c in ingredient_cols:
            if c in sdf.columns:
                sdf[c] = pd.to_numeric(sdf[c], errors="coerce").fillna(0)

        # restrict to features that exist in the selected product feature list
        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)
        prod_ids = set(prod_df["feature"].dropna().astype(str))
        sdf = sdf[sdf["feature"].isin(prod_ids)].copy()

        # global intensity filter uses product feature intensity (same as Explore)
        if global_intensity_log_range and "intensity" in prod_df.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            keep_ids = set(prod_df.loc[prod_df["intensity"].between(lo, hi, inclusive="both"), "feature"].astype(str))
            sdf = sdf[sdf["feature"].isin(keep_ids)].copy()

        # feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            sdf = sdf[sdf["feature"].str.contains(s, case=False, na=False)].copy()

        # only pubchem
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in sdf.columns:
                sdf = sdf[sdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                sdf = sdf.iloc[0:0].copy()

        top_n = int(q6_top_n) if q6_top_n else 15
        # ---- Feature-level total ingredient intensity (matches question6.py) ----
        mat_num = sdf[ingredient_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        total_raw = mat_num.sum(axis=1)
        total_log = np.log10(total_raw.replace(0, np.nan))

        feat_df = pd.DataFrame({
            "feature": sdf["feature"].astype(str),
            "Total_Intensityy": total_raw,
            "Total_Intensity": total_log,
        })

        # If duplicates exist per feature, aggregate like a safe version of question6
        feat_df = feat_df.groupby("feature", as_index=False)["Total_Intensityy"].sum()
        feat_df["Total_Intensity"] = np.log10(feat_df["Total_Intensityy"].replace(0, np.nan))

        # keep UI responsive
        feat_df = feat_df.sort_values("Total_Intensityy", ascending=False).head(3000)

        selected_feature = str(q6_selected_feature).strip() if q6_selected_feature else None

        q6_dom_fig = px.bar(
            feat_df,
            x="feature",
            y="Total_Intensity",
            title="Total Intensity per Feature (log10(sum of ingredient intensities))",
            template="plotly",
        )

        # highlight selected feature
        if selected_feature is not None:
            colors = ["crimson" if f == selected_feature else "lightsteelblue" for f in feat_df["feature"].astype(str)]
            q6_dom_fig.update_traces(marker_color=colors)

        q6_dom_fig.update_layout(
            xaxis=dict(showticklabels=False),
            yaxis_title="log10(sum ingredients)",
        )


        # per-feature contribution plot + table
        contrib_fig = px.bar(title="Q6: Enter a feature ID to see ingredient contributions")
        table_df = pd.DataFrame(columns=["Ingredient", "Raw", "Log10", "Type"])

        if selected_feature and str(selected_feature).strip():
            fid = str(selected_feature).strip()

            contrib_df, _dom = q6_feature_contrib(sdf, fid, ingredient_cols, plant_cols, animal_cols)

            if not contrib_df.empty:
                table_df = contrib_df.head(top_n).copy()
                contrib_fig = px.bar(
                    table_df,
                    x="Ingredient",
                    y="Log10",
                    color="Type",
                    title=f"Ingredient contributions for {fid} (log10 intensity)",
                    template="plotly",
                )
                contrib_fig.update_layout(xaxis_tickangle=-45, yaxis_title="log10(intensity)")
            else:
                contrib_fig = px.bar(title=f"Q6: Feature {fid} not found after filters")

        cols = [{"name": c, "id": c} for c in table_df.columns]
        stats = (
            f"Q6 | features after filters: {len(sdf):,} | ingredient cols matched: {len(ingredient_cols)} "
            f"(plant={len(plant_cols)}, animal={len(animal_cols)})"
        )
        card_body = html.Div("Grafikte bir feature secerek detaylarini gorebilirsiniz.")
        card_style = {"display": "none"}
        if selected_feature and bool(q6_card_open):
            selected_rows = sdf[sdf["feature"].astype(str) == selected_feature]
            if not selected_rows.empty:
                r = selected_rows.iloc[0]
                feat_total_row = feat_df[feat_df["feature"].astype(str) == selected_feature]
                total_raw = float(feat_total_row["Total_Intensityy"].iloc[0]) if not feat_total_row.empty else float("nan")
                total_log = np.log10(total_raw) if pd.notna(total_raw) and total_raw > 0 else np.nan
                dominant = table_df.iloc[0]["Ingredient"] if not table_df.empty else "NA"
                dominant_raw = float(table_df.iloc[0]["Raw"]) if not table_df.empty else np.nan
                card_body = html.Div([
                    html.H4(f"Selected feature: {selected_feature}", style={"margin": "0 0 8px 0"}),
                    html.Div(f"Total ingredient intensity (sum): {total_raw:,.0f}" if pd.notna(total_raw) else "Total ingredient intensity (sum): NA"),
                    html.Div(f"log10(total ingredient intensity): {total_log:.6f}" if pd.notna(total_log) else "log10(total ingredient intensity): NA"),
                    html.Div(f"Dominant ingredient: {dominant}"),
                    html.Div(f"Dominant raw intensity: {dominant_raw:,.0f}" if pd.notna(dominant_raw) else "Dominant raw intensity: NA"),
                    html.Div(f"Name: {r.get('name', 'NA')}"),
                    html.Div(f"Molecular Formula: {r.get('molecularFormula', 'NA')}"),
                    html.Div(["PubChem IDs: ", *render_pubchem_links(r.get("pubchemids", None))]),
                    html.Div(f"NPC Pathway: {r.get('NPC.pathway', 'NA')}"),
                ])
                card_style = {"display": "block", "marginTop": "6px"}
        return q6_dom_fig, contrib_fig, table_df.to_dict("records"), cols, stats, card_body, card_style

    # ---- Q7: Enrichment vs component sources (Final − sum(components)) ----
    # ---- Q7: Enrichment vs component sources (read DIRECTLY from Excel) ----
    HEPAR_COLS = [
        "Avena.sativa",
        "Chelidonium.majus",
        "Cinchona.pubescens",
        "Cynara.scolymus",
        "Lycopodium.clavatum",
        "Silybum.marianum.",
        "Taraxacum.officinale",
        "Veratrum.album",
        "Colon.Suis.D4",
        "Duodenum.Suis.D4",
        "Hepar.Suis.D4",
        "Pankreas.Suis.D4",
        "Thymus.Suis.D4",
        "Vesica.Fellea.Suis.D4",
    ]

    HEPEEL_COLS = [
        "Chelidonium.majus",
        "Cinchona.pubescens",
        "Citrullus.colocynthis.",
        "Lycopodium.clavatum",
        "Myristica.fragrans.",
        "Silybum.marianum.",
        "Veratrum.album",
    ]

    HEPAR_TARGET_COL = "Hepar.comp.Ampoules..Bulk.mat.52324."
    HEPEEL_BULK_COL = "Hepeel.ampoule.solution..Bulk"

    def _load_q7_excel_df() -> pd.DataFrame:
        """
        Read Excel directly for Q7.
        The workbook has a title row first, so the real header is row 2.
        """
        excel_path = Path(__file__).resolve().parent / "data" / "Product_features_summary_annotation.xlsx"

        # IMPORTANT: real header is the second row
        df = pd.read_excel(excel_path, header=1)

        df["feature"] = df["feature"].astype(str).str.strip()

        needed_cols = HEPAR_COLS + HEPEEL_COLS + [HEPAR_TARGET_COL, HEPEEL_BULK_COL]
        missing = [c for c in needed_cols if c not in df.columns]
        if missing:
            raise KeyError(f"Q7: Missing required Excel columns: {missing}")

        for c in needed_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # ingredient sums
        df["hepar_ingredient_sum"] = df[HEPAR_COLS].sum(axis=1)
        df["hepeel_ingredient_sum"] = df[HEPEEL_COLS].sum(axis=1)

        # final product values
        df["hepar_final_product"] = df[HEPAR_TARGET_COL]
        df["hepeel_final_product"] = df[HEPEEL_BULK_COL]

        # enrichment deltas
        df["hepar_enrichment_delta"] = df["hepar_final_product"] - df["hepar_ingredient_sum"]
        df["hepeel_enrichment_delta"] = df["hepeel_final_product"] - df["hepeel_ingredient_sum"]

        # enrichment flags
        df["hepar_enriched"] = df["hepar_enrichment_delta"] > 0
        df["hepeel_enriched"] = df["hepeel_enrichment_delta"] > 0

        return df

    @app.callback(
        Output("q7_selected_feature", "data"),
        Output("q7_card_open", "data"),
        Input("q7_graph", "clickData"),
        Input("q7_close_card", "n_clicks"),
        State("q7_selected_feature", "data"),
        State("q7_card_open", "data"),
        prevent_initial_call=True,
    )
    def update_q7_selection(q7_clickData, q7_close_clicks, current_selected, current_open):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
        if trigger == "q7_close_card":
            return no_update, False
        if trigger == "q7_graph" and q7_clickData and q7_clickData.get("points"):
            return str(q7_clickData["points"][0].get("x")), True
        return current_selected, current_open

    @app.callback(
        Output("q7_graph", "figure"),
        Output("q7_table", "data"),
        Output("q7_table", "columns"),
        Output("q7_stats", "children"),
        Output("q7_card_body", "children"),
        Output("q7_feature_card", "style"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q7_top_n", "value"),
        Input("q7_selected_feature", "data"),
        Input("q7_card_open", "data"),
    )
    def update_q7(product, feature_search, only_pubchem_vals, global_intensity_log_range, q7_top_n, q7_selected_feature, q7_card_open):
        try:
            dff = _load_q7_excel_df()
        except Exception as e:
            fig = px.bar(
                pd.DataFrame({"feature": [], "enrichment_delta": []}),
                x="feature",
                y="enrichment_delta",
                template="plotly",
                title=f"Q7: error loading Excel ({e})",
            )
            return fig, [], [], f"Q7 error: {e}", html.Div("No feature selected."), {"display": "none"}

        # optional filters
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            dff = dff[dff["feature"].str.contains(s, case=False, na=False)].copy()

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                dff = dff.iloc[0:0].copy()

        # apply global slider to BOTH product finals so the page stays consistent
        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            dff = dff[
                dff["hepar_final_product"].between(lo, hi, inclusive="both")
                | dff["hepeel_final_product"].between(lo, hi, inclusive="both")
            ].copy()

        top_n = int(q7_top_n) if q7_top_n else 50

        # build Hepar enriched rows
        hepar_df = dff[dff["hepar_enriched"]].copy()
        hepar_df["ingredient_sum"] = hepar_df["hepar_ingredient_sum"]
        hepar_df["final_product"] = hepar_df["hepar_final_product"]
        hepar_df["enrichment_delta"] = hepar_df["hepar_enrichment_delta"]
        hepar_df["enriched_in"] = "Hepar"

        # build Hepeel enriched rows
        hepeel_df = dff[dff["hepeel_enriched"]].copy()
        hepeel_df["ingredient_sum"] = hepeel_df["hepeel_ingredient_sum"]
        hepeel_df["final_product"] = hepeel_df["hepeel_final_product"]
        hepeel_df["enrichment_delta"] = hepeel_df["hepeel_enrichment_delta"]
        hepeel_df["enriched_in"] = "Hepeel"

        # combine both
        enriched_df = pd.concat([hepar_df, hepeel_df], ignore_index=True)

        # optional: if dropdown is selected, sort with selected product first
        if "hepar" in str(product).lower():
            enriched_df["product_priority"] = (enriched_df["enriched_in"] != "Hepar").astype(int)
        else:
            enriched_df["product_priority"] = (enriched_df["enriched_in"] != "Hepeel").astype(int)

        enriched_df = enriched_df.sort_values(
            ["product_priority", "enrichment_delta"],
            ascending=[True, False]
        ).copy()

        plot_df = enriched_df.head(top_n).copy()

        if plot_df.empty:
            fig = px.bar(
                pd.DataFrame({"feature": [], "enrichment_delta": [], "enriched_in": []}),
                x="feature",
                y="enrichment_delta",
                color="enriched_in",
                template="plotly",
                title="Q7: Hepar + Hepeel enriched features",
            )
        else:
            hover_cols = [
                c for c in [
                    "ingredient_sum",
                    "final_product",
                    "hepar_ingredient_sum",
                    "hepar_final_product",
                    "hepar_enrichment_delta",
                    "hepeel_ingredient_sum",
                    "hepeel_final_product",
                    "hepeel_enrichment_delta",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                    "NPC.pathway",
                ] if c in plot_df.columns
            ]

            if plot_df.empty:
                fig = px.bar(
                    pd.DataFrame({"feature": [], "enrichment_delta": [], "enriched_in": []}),
                    x="feature",
                    y="enrichment_delta",
                    color="enriched_in",
                    template="plotly",
                    title="Q7: Hepar + Hepeel enriched features",
                )
            else:
                hover_cols = [
                    c for c in [
                        "ingredient_sum",
                        "final_product",
                        "hepar_ingredient_sum",
                        "hepar_final_product",
                        "hepar_enrichment_delta",
                        "hepeel_ingredient_sum",
                        "hepeel_final_product",
                        "hepeel_enrichment_delta",
                        "name",
                        "molecularFormula",
                        "pubchemids",
                        "NPC.pathway",
                    ] if c in plot_df.columns
                ]

                fig = px.bar(
                    plot_df,
                    x="feature",
                    y="enrichment_delta",
                    color="enriched_in",
                    barmode="group",
                    hover_data=hover_cols,
                    template="plotly",
                    title="Q7: Enriched features in Hepar and Hepeel (read directly from Excel)",
                    log_y=True,
                )

                fig.update_layout(
                    xaxis_title="feature",
                    yaxis_title="final product - sum(ingredients) [log scale]",
                    margin=dict(l=20, r=20, t=50, b=140),
                    legend_title_text="",
                )

                fig.update_xaxes(tickangle=-35)

        selected_feature = str(q7_selected_feature).strip() if q7_selected_feature else None
        if selected_feature:
            for tr in fig.data:
                xs = [str(x) for x in tr.x] if tr.x is not None else []
                line_widths = [2 if x == selected_feature else 0 for x in xs]
                opacities = [1.0 if x == selected_feature else 0.45 for x in xs]
                tr.marker.line = {"color": "black", "width": line_widths}
                tr.marker.opacity = opacities


        out_cols = [
            "feature",
            "enriched_in",
            "ingredient_sum",
            "final_product",
            "enrichment_delta",
            "hepar_ingredient_sum",
            "hepar_final_product",
            "hepar_enrichment_delta",
            "hepeel_ingredient_sum",
            "hepeel_final_product",
            "hepeel_enrichment_delta",
        ]
        for c in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
            if c in enriched_df.columns:
                out_cols.append(c)

        out_df = enriched_df[out_cols].copy()
        cols = [{"name": c, "id": c} for c in out_df.columns]

        hepar_count = int((enriched_df["enriched_in"] == "Hepar").sum())
        hepeel_count = int((enriched_df["enriched_in"] == "Hepeel").sum())

        stats = (
            f"Q7 | Hepar enriched: {hepar_count:,} | "
            f"Hepeel enriched: {hepeel_count:,} | "
            f"total rows: {len(enriched_df):,} | source: Excel"
        )
        def _fmt_int(x):
            try:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return "NA"
                return f"{float(x):,.0f}"
            except Exception:
                return "NA"

        card_body = html.Div("Grafikte bir feature secerek detaylarini gorebilirsiniz.")
        card_style = {"display": "none"}
        if selected_feature and bool(q7_card_open):
            rows = out_df[out_df["feature"].astype(str) == selected_feature]
            if not rows.empty:
                hepar_row = rows[rows["enriched_in"] == "Hepar"]
                hepeel_row = rows[rows["enriched_in"] == "Hepeel"]
                base_row = dff[dff["feature"].astype(str) == selected_feature]
                rr = base_row.iloc[0] if not base_row.empty else None
                category = []
                if not hepar_row.empty:
                    category.append("Hepar")
                if not hepeel_row.empty:
                    category.append("Hepeel")
                if not category:
                    category.append("Not enriched")
                card_body = html.Div([
                    html.H4(f"Selected feature: {selected_feature}", style={"margin": "0 0 8px 0"}),
                    html.Div(f"Category: {', '.join(category)}"),
                    html.Div(
                        f"Hepar ratio: {_fmt_int(rr.get('hepar_final_product', np.nan))} / {_fmt_int(rr.get('hepar_ingredient_sum', np.nan))} | "
                        f"delta: {_fmt_int(rr.get('hepar_enrichment_delta', np.nan))}"
                    ) if rr is not None else html.Div("Hepar ratio: NA"),
                    html.Div(
                        f"Hepeel ratio: {_fmt_int(rr.get('hepeel_final_product', np.nan))} / {_fmt_int(rr.get('hepeel_ingredient_sum', np.nan))} | "
                        f"delta: {_fmt_int(rr.get('hepeel_enrichment_delta', np.nan))}"
                    ) if rr is not None else html.Div("Hepeel ratio: NA"),
                    html.Div(f"Hepar final: {_fmt_int(rr.get('hepar_final_product', np.nan))} | sum(comp): {_fmt_int(rr.get('hepar_ingredient_sum', np.nan))}") if rr is not None else html.Div("Hepar final: NA"),
                    html.Div(f"Hepeel final: {_fmt_int(rr.get('hepeel_final_product', np.nan))} | sum(comp): {_fmt_int(rr.get('hepeel_ingredient_sum', np.nan))}") if rr is not None else html.Div("Hepeel final: NA"),
                    html.Div(f"Name: {rr.get('name', 'NA') if rr is not None else 'NA'}"),
                    html.Div(f"Formula: {rr.get('molecularFormula', 'NA') if rr is not None else 'NA'}"),
                    html.Div(["PubChem: ", *render_pubchem_links(rr.get("pubchemids", None) if rr is not None else None)]),
                ])
                card_style = {"display": "block", "marginTop": "6px"}

        return fig, out_df.to_dict("records"), cols, stats, card_body, card_style
    # ---- Q8: click / card state ----
    @app.callback(
        Output("q8_selected_feature", "data"),
        Output("q8_card_open", "data"),
        Input("q8_graph", "clickData"),
        Input("q8_close_card", "n_clicks"),
        State("q8_selected_feature", "data"),
        State("q8_card_open", "data"),
        prevent_initial_call=True,
    )
    def update_q8_selection(q8_clickData, q8_close_clicks, current_selected, current_open):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
        if trigger == "q8_close_card":
            return no_update, False
        if trigger == "q8_graph" and q8_clickData and q8_clickData.get("points"):
            return str(q8_clickData["points"][0].get("x")), True
        return current_selected, current_open

    # ---- Q8: Selective amplification/attenuation (Final / max(component)) ----
    @app.callback(
        Output("q8_table", "data"),
        Output("q8_table", "columns"),
        Output("q8_table", "tooltip_data"),
        Output("q8_graph", "figure"),
        Output("q8_stats", "children"),
        Output("q8_card_body", "children"),
        Output("q8_feature_card", "style"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q8_amp_threshold", "value"),
        Input("q8_cats", "value"),
        Input("q8_selected_feature", "data"),
        Input("q8_card_open", "data"),
    )
    def update_q8(
        product,
        feature_search,
        only_pubchem_vals,
        global_intensity_log_range,
        q8_amp_threshold,
        q8_cats,
        q8_selected_feature,
        q8_card_open,
    ):
        empty_fig = _q8_empty_figure("Q8: no data or empty filter result")

        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        try:
            hepar_final = _find_col(sdf, Q8_HEPAR_FINAL_COL)
            hepeel_final = _find_col(sdf, Q8_HEPEEL_FINAL_COL)
        except KeyError as e:
            card = html.Div(f"Q8: missing columns. {e}")
            return [], [], [], empty_fig, str(e), card, {"display": "none"}

        hepar_ing_cols = [c for c in groups.get("hepar_component_cols", []) if c in sdf.columns]
        hepeel_ing_cols = [c for c in groups.get("hepeel_component_cols", []) if c in sdf.columns]

        if not hepar_ing_cols or not hepeel_ing_cols:
            msg = f"Q8: missing component columns. Hepar={len(hepar_ing_cols)}, Hepeel={len(hepeel_ing_cols)}."
            return [], [], [], empty_fig, msg, html.Div(msg), {"display": "none"}

        need_cols = [hepar_final, hepeel_final] + hepar_ing_cols + hepeel_ing_cols
        for c in need_cols:
            if c in sdf.columns:
                sdf[c] = pd.to_numeric(sdf[c], errors="coerce").fillna(0)

        pnorm = str(product).lower()
        is_hepar = "hepar" in pnorm
        sel_final = hepar_final if is_hepar else hepeel_final
        sel_ratio_col = "hepar_ratio" if is_hepar else "hepeel_ratio"
        sel_state_col = "hepar_state" if is_hepar else "hepeel_state"
        other_state_col = "hepeel_state" if is_hepar else "hepar_state"

        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            sdf = sdf[sdf[sel_final].between(lo, hi, inclusive="both")].copy()

        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            sdf = sdf[sdf["feature"].astype(str).str.contains(s, case=False, na=False)].copy()

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in sdf.columns:
                sdf = sdf[sdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                sdf = sdf.iloc[0:0].copy()

        amp_thr = float(q8_amp_threshold) if q8_amp_threshold else 1.0
        amp_thr = max(1.0, amp_thr)

        hepar_comp_max = sdf[hepar_ing_cols].max(axis=1)
        hepeel_comp_max = sdf[hepeel_ing_cols].max(axis=1)
        sdf["hepar_comp_max"] = hepar_comp_max
        sdf["hepeel_comp_max"] = hepeel_comp_max

        sdf["hepar_ratio"] = sdf[hepar_final] / hepar_comp_max.replace(0, pd.NA)
        sdf["hepeel_ratio"] = sdf[hepeel_final] / hepeel_comp_max.replace(0, pd.NA)

        sdf["hepar_state"] = [_q8_state(float(p), float(m), amp_thr) for p, m in zip(sdf[hepar_final], hepar_comp_max)]
        sdf["hepeel_state"] = [_q8_state(float(p), float(m), amp_thr) for p, m in zip(sdf[hepeel_final], hepeel_comp_max)]

        def cat(row) -> list[str]:
            out: list[str] = []
            hs = row["hepar_state"]
            ps = row["hepeel_state"]
            if hs == "amplified" and ps != "amplified":
                out.append("hepar_selective_amplification")
            if ps == "amplified" and hs != "amplified":
                out.append("hepeel_selective_amplification")
            if hs == "attenuated" and ps != "attenuated":
                out.append("hepar_selective_attenuation")
            if ps == "attenuated" and hs != "attenuated":
                out.append("hepeel_selective_attenuation")
            return out

        sdf["q8_category"] = sdf.apply(cat, axis=1)
        sdf = sdf.explode("q8_category").dropna(subset=["q8_category"])

        amp_cat = "hepar_selective_amplification" if is_hepar else "hepeel_selective_amplification"
        att_cat = "hepar_selective_attenuation" if is_hepar else "hepeel_selective_attenuation"

        desired = set(q8_cats or [])
        allowed = set()
        if "selective_amplification" in desired:
            allowed.add(amp_cat)
        if "selective_attenuation" in desired:
            allowed.add(att_cat)

        sdf = sdf[sdf["q8_category"].isin(allowed)].copy() if allowed else sdf.iloc[0:0].copy()

        sdf["q8_type"] = sdf["q8_category"].map({
            amp_cat: "Selective amplification",
            att_cat: "Selective attenuation",
        })

        prod_label = "Hepar" if is_hepar else "Hepeel"
        max_bars = 2000

        selected_feature = str(q8_selected_feature).strip() if q8_selected_feature else None

        show_amp = "selective_amplification" in desired and amp_cat in allowed
        show_att = "selective_attenuation" in desired and att_cat in allowed

        amp_df = sdf[sdf["q8_type"] == "Selective amplification"].copy() if show_amp else pd.DataFrame()
        att_df = sdf[sdf["q8_type"] == "Selective attenuation"].copy() if show_att else pd.DataFrame()

        if not sdf.empty:
            if not amp_df.empty:
                amp_df = amp_df.sort_values(sel_ratio_col, ascending=False).head(max_bars)
            if not att_df.empty:
                att_df = att_df.sort_values(sel_ratio_col, ascending=True).head(max_bars)

        if sdf.empty:
            fig = _q8_empty_figure("Empty filter result — relax threshold or intensity range.")
            return [], [], [], fig, f"Q8 ({prod_label}) | 0 feature", html.Div("No rows in table."), {"display": "none"}

        amp_color = "#27ae60"
        att_color = "#e67e22"

        def _add_empty_panel_message(fig_obj: go.Figure, row: int, message: str):
            # Draw an explicit empty-state card inside the subplot region.
            if row == 1:
                y0, y1, y_text = 0.58, 0.92, 0.75
            else:
                y0, y1, y_text = 0.08, 0.42, 0.25

            fig_obj.add_shape(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0.05,
                x1=0.95,
                y0=y0,
                y1=y1,
                line={"color": "#cbd5e1", "width": 1, "dash": "dot"},
                fillcolor="rgba(241,245,249,0.7)",
            )
            fig_obj.add_annotation(
                x=0.5,
                y=y_text,
                xref="paper",
                yref="paper",
                text=message,
                showarrow=False,
                font={"size": 13, "color": "#475569"},
                align="center",
            )

        def make_q8_bar_trace(df: pd.DataFrame, color: str) -> go.Bar:
            xs = df["feature"].astype(str).tolist()
            ys = _q8_log10_ratio_series(df[sel_ratio_col])
            line_w = [2.5 if selected_feature and str(x) == selected_feature else 0 for x in xs]
            opac = [1.0 if (selected_feature and str(x) == selected_feature) else 0.55 for x in xs]
            cd = np.column_stack(
                [
                    df["q8_type"].astype(str).to_numpy(),
                    pd.to_numeric(df[sel_ratio_col], errors="coerce").to_numpy(),
                ]
            )
            return go.Bar(
                x=xs,
                y=ys,
                marker_color=color,
                marker_line_color="black",
                marker_line_width=line_w,
                marker_opacity=opac,
                customdata=cd,
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    + f"{prod_label} ratio=%{{customdata[1]:.4g}}<br>"
                    + "log10(ratio)=%{y:.3f}<br>"
                    + "q8_type=%{customdata[0]}<extra></extra>"
                ),
                showlegend=False,
            )

        if show_amp and show_att:
            fig = make_subplots(
                rows=2,
                cols=1,
                vertical_spacing=0.1,
                subplot_titles=(
                    f"Selective amplification — {prod_label} (selected product amplified, other not)",
                    f"Selective attenuation — {prod_label} (selected product attenuated, other not)",
                ),
            )
            if not amp_df.empty:
                fig.add_trace(make_q8_bar_trace(amp_df, amp_color), row=1, col=1)
            else:
                _add_empty_panel_message(
                    fig,
                    row=1,
                    message=f"No selective amplification features found for {prod_label} under the current filters.",
                )
            if not att_df.empty:
                fig.add_trace(make_q8_bar_trace(att_df, att_color), row=2, col=1)
            else:
                _add_empty_panel_message(
                    fig,
                    row=2,
                    message=f"No selective attenuation features found for {prod_label} under the current filters.",
                )
            fig.update_xaxes(title_text="feature (each bar = one feature)", showticklabels=False, row=1, col=1)
            fig.update_xaxes(title_text="feature (each bar = one feature)", showticklabels=False, row=2, col=1)
            fig.update_yaxes(title_text="log10(Final / max component)", row=1, col=1)
            fig.update_yaxes(title_text="log10(Final / max component)", row=2, col=1)
            fig.update_layout(
                template="plotly",
                height=720,
                margin=dict(l=50, r=20, t=90, b=40),
                title_text=f"Q8 ({prod_label}): which features show selective amp / att?",
            )
        elif show_amp:
            fig = go.Figure(data=[make_q8_bar_trace(amp_df, amp_color)]) if not amp_df.empty else _q8_empty_figure(
                f"No selective amplification features found for {prod_label} under the current filters."
            )
            fig.update_layout(
                template="plotly",
                height=460,
                title_text=f"Q8 ({prod_label}): selective amplification (by feature)",
                xaxis=dict(title="feature (each bar = one feature)", showticklabels=False),
                yaxis=dict(title="log10(Final / max component)"),
                margin=dict(l=50, r=20, t=70, b=40),
            )
        elif show_att:
            fig = go.Figure(data=[make_q8_bar_trace(att_df, att_color)]) if not att_df.empty else _q8_empty_figure(
                f"No selective attenuation features found for {prod_label} under the current filters."
            )
            fig.update_layout(
                template="plotly",
                height=460,
                title_text=f"Q8 ({prod_label}): selective attenuation (by feature)",
                xaxis=dict(title="feature (each bar = one feature)", showticklabels=False),
                yaxis=dict(title="log10(Final / max component)"),
                margin=dict(l=50, r=20, t=70, b=40),
            )
        else:
            fig = _q8_empty_figure("No features to show for the selected categories (or filter result is empty).")

        out_cols = [
            "feature",
            "q8_type",
            "hepar_comp_max",
            "hepeel_comp_max",
            hepar_final,
            hepeel_final,
            "hepar_ratio",
            "hepeel_ratio",
            "hepar_state",
            "hepeel_state",
            sel_state_col,
            other_state_col,
        ]
        _seen: list[str] = []
        for c in out_cols:
            if c in sdf.columns and c not in _seen:
                _seen.append(c)
        out_cols = _seen
        for c in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
            if c in sdf.columns and c not in out_cols:
                out_cols.append(c)

        out = sdf[out_cols].copy()
        out = out.sort_values(["q8_type", sel_ratio_col], ascending=[True, False]).head(2000)

        def _fmt_int(x):
            try:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return "NA"
                return f"{float(x):,.0f}"
            except Exception:
                return "NA"

        def _fmt_ratio(x):
            try:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return "NA"
                return f"{float(x):.2f}"
            except Exception:
                return "NA"

        inv_thr = 1.0 / amp_thr if amp_thr else float("nan")

        tooltips = []
        for _, r in out.iterrows():
            hf = r.get(hepar_final, float("nan"))
            hm = r.get("hepar_comp_max", float("nan"))
            hr = r.get("hepar_ratio", float("nan"))
            hs = r.get("hepar_state", "")

            pf = r.get(hepeel_final, float("nan"))
            pm = r.get("hepeel_comp_max", float("nan"))
            pr = r.get("hepeel_ratio", float("nan"))
            ps = r.get("hepeel_state", "")

            hepar_tip = (
                f"**ratio = Final / max(ingredients)**\n"
                f"= {_fmt_int(hf)} / {_fmt_int(hm)} = **{_fmt_ratio(hr)}**\n\n"
                f"Amplified if ratio >= **{amp_thr:.2f}**\n"
                f"Attenuated if ratio <= **{inv_thr:.2f}**\n"
                f"-> **{hs}**"
            )

            hepeel_tip = (
                f"**ratio = Final / max(ingredients)**\n"
                f"= {_fmt_int(pf)} / {_fmt_int(pm)} = **{_fmt_ratio(pr)}**\n\n"
                f"Amplified if ratio >= **{amp_thr:.2f}**\n"
                f"Attenuated if ratio <= **{inv_thr:.2f}**\n"
                f"-> **{ps}**"
            )

            tooltips.append(
                {
                    "hepar_ratio": {"value": hepar_tip, "type": "markdown"},
                    "hepeel_ratio": {"value": hepeel_tip, "type": "markdown"},
                }
            )

        cols = [{"name": c, "id": c} for c in out.columns]
        stats = (
            f"Q8 ({prod_label}) | table rows: {len(out):,} | chart: amp≤{max_bars}, att≤{max_bars} | "
            f"threshold amp≥{amp_thr:g}x (att≤{1/amp_thr:g}x)"
        )

        card_body = html.Div("Click a bar in the chart to select a feature.")
        card_style = {"display": "none"}
        if selected_feature and q8_card_open:
            one = sdf[sdf["feature"].astype(str) == selected_feature]
            if not one.empty:
                rr = one.iloc[0]
                cats = ", ".join(one["q8_type"].dropna().astype(str).unique()) if "q8_type" in one.columns else "-"
                card_body = html.Div([
                    html.H4(f"Selected feature: {selected_feature}", style={"margin": "0 0 8px 0"}),
                    html.Div(f"Category: {cats}"),
                    html.Div(f"Hepar ratio: {_fmt_ratio(rr.get('hepar_ratio', np.nan))} | state: {rr.get('hepar_state', '-')}"),
                    html.Div(f"Hepeel ratio: {_fmt_ratio(rr.get('hepeel_ratio', np.nan))} | state: {rr.get('hepeel_state', '-')}"),
                    html.Div(f"Hepar final: {_fmt_int(rr.get(hepar_final, np.nan))} | max(comp): {_fmt_int(rr.get('hepar_comp_max', np.nan))}"),
                    html.Div(f"Hepeel final: {_fmt_int(rr.get(hepeel_final, np.nan))} | max(comp): {_fmt_int(rr.get('hepeel_comp_max', np.nan))}"),
                    html.Div(f"Name: {rr.get('name', '-')}"),
                    html.Div(f"Formula: {rr.get('molecularFormula', '-')}"),
                    html.Div(["PubChem: ", *render_pubchem_links(rr.get("pubchemids", None))]),
                ])
                card_style = {"display": "block", "marginTop": "6px"}

        return out.to_dict("records"), cols, tooltips, fig, stats, card_body, card_style

    # ---- Q9: interaction state (selected feature + closable card) ----
    @app.callback(
        Output("q9_selected_feature", "data"),
        Output("q9_card_open", "data"),
        Input("q9_graph", "clickData"),
        Input("q9_close_card", "n_clicks"),
        State("q9_selected_feature", "data"),
        State("q9_card_open", "data"),
        prevent_initial_call=True,
    )
    def update_q9_selection(q9_clickData, q9_close_clicks, current_selected, current_open):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None

        if trigger == "q9_close_card":
            return no_update, False

        if trigger == "q9_graph" and q9_clickData and "points" in q9_clickData and q9_clickData["points"]:
            selected = str(q9_clickData["points"][0].get("x"))
            return selected, True

        return current_selected, current_open

    # ---- Q9: Shared vs unique feature chemistry (Hepar vs Hepeel) ----
    @app.callback(
        Output("q9_graph", "figure"),
        Output("q9_stats", "children"),
        Output("q9_table", "data"),
        Output("q9_table", "columns"),
        Output("q9_card_body", "children"),
        Output("q9_feature_card", "style"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q9_selected_feature", "data"),
        Input("q9_card_open", "data"),
    )
    def update_q9(feature_search, only_pubchem_vals, global_intensity_log_range, q9_selected_feature, q9_card_open):
        hepar_df = data["Hepar"].features.copy()
        hepeel_df = data["Hepeel"].features.copy()
        hepar_df["feature"] = hepar_df["feature"].astype(str)
        hepeel_df["feature"] = hepeel_df["feature"].astype(str)

        hepar_ids = set(hepar_df["feature"].dropna())
        hepeel_ids = set(hepeel_df["feature"].dropna())

        union_ids = hepar_ids | hepeel_ids
        shared_ids = hepar_ids & hepeel_ids
        unique_hepar = hepar_ids - hepeel_ids
        unique_hepeel = hepeel_ids - hepar_ids

        if "intensity" in hepar_df.columns:
            hepar_df["intensity"] = pd.to_numeric(hepar_df["intensity"], errors="coerce").fillna(0)
        else:
            hepar_df["intensity"] = 0.0
        if "intensity" in hepeel_df.columns:
            hepeel_df["intensity"] = pd.to_numeric(hepeel_df["intensity"], errors="coerce").fillna(0)
        else:
            hepeel_df["intensity"] = 0.0

        hepar_int_map = hepar_df.drop_duplicates("feature").set_index("feature")["intensity"].to_dict()
        hepeel_int_map = hepeel_df.drop_duplicates("feature").set_index("feature")["intensity"].to_dict()

        rows = []
        for fid in sorted(union_ids):
            if fid in shared_ids:
                cls = "Shared (Hepar + Hepeel)"
            elif fid in unique_hepar:
                cls = "Unique to Hepar"
            else:
                cls = "Unique to Hepeel"

            h_int = float(hepar_int_map.get(fid, 0.0) or 0.0)
            p_int = float(hepeel_int_map.get(fid, 0.0) or 0.0)
            max_int = max(h_int, p_int)
            rows.append(
                {
                    "feature": str(fid),
                    "q9_class": cls,
                    "hepar_intensity": h_int,
                    "hepeel_intensity": p_int,
                    "q9_intensity": max_int,
                    "q9_log_intensity": np.log10(max_int) if max_int > 0 else np.nan,
                }
            )

        qdf = pd.DataFrame(rows)

        annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in summary_df.columns]
        if annot_cols and not qdf.empty:
            annot = summary_df[annot_cols].drop_duplicates("feature").copy()
            annot["feature"] = annot["feature"].astype(str)
            qdf = qdf.merge(annot, on="feature", how="left")

        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            qdf = qdf[qdf["feature"].str.contains(s, case=False, na=False)].copy()

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in qdf.columns:
                qdf = qdf[qdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                qdf = qdf.iloc[0:0].copy()

        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            qdf = qdf[qdf["q9_intensity"].between(lo, hi, inclusive="both")].copy()

        qdf = qdf.sort_values("q9_intensity", ascending=False).head(5000)

        color_map = {
            "Shared (Hepar + Hepeel)": "#636EFA",
            "Unique to Hepar": "#EF553B",
            "Unique to Hepeel": "#00CC96",
        }
        fig = px.bar(
            qdf,
            x="feature",
            y="q9_log_intensity",
            color="q9_class",
            color_discrete_map=color_map,
            hover_data={c: False for c in qdf.columns if c not in {"feature", "q9_class"}},
            title="Q9: Shared and unique features across Hepar vs Hepeel",
            template="plotly",
        )
        fig.update_traces(
            customdata=qdf[["q9_class"]].to_numpy() if not qdf.empty else None,
            hovertemplate="q9_class=%{customdata[0]}<br>feature=%{x}<extra></extra>",
        )

        selected_feature = str(q9_selected_feature).strip() if q9_selected_feature else None
        if selected_feature:
            for tr in fig.data:
                xs = [str(x) for x in tr.x] if tr.x is not None else []
                line_widths = [2 if x == selected_feature else 0 for x in xs]
                opacities = [1.0 if x == selected_feature else 0.45 for x in xs]
                tr.marker.line = {"color": "black", "width": line_widths}
                tr.marker.opacity = opacities

        fig.update_layout(
            xaxis=dict(showticklabels=False),
            yaxis_title="log10(max final intensity across two products)",
            legend_title_text="",
            margin=dict(l=20, r=20, t=45, b=45),
        )

        table_cols = [
            c for c in [
                "feature", "q9_class", "hepar_intensity", "hepeel_intensity",
                "q9_intensity", "q9_log_intensity", "name",
                "molecularFormula", "pubchemids", "NPC.pathway",
            ] if c in qdf.columns
        ]
        q9_table_df = qdf[table_cols].copy() if table_cols else qdf.copy()

        card_body = html.Div("Click a bar to select a feature.")
        card_style = {"display": "none"}
        if selected_feature and bool(q9_card_open):
            selected_row = q9_table_df[q9_table_df["feature"].astype(str) == selected_feature]
            if not selected_row.empty:
                r = selected_row.iloc[0]
                q9_cls = str(r.get("q9_class", ""))
                if q9_cls == "Shared (Hepar + Hepeel)":
                    card_border = "#636EFA"
                    card_bg = "rgba(99, 110, 250, 0.14)"
                elif q9_cls == "Unique to Hepar":
                    card_border = "#EF553B"
                    card_bg = "rgba(239, 85, 59, 0.14)"
                elif q9_cls == "Unique to Hepeel":
                    card_border = "#00CC96"
                    card_bg = "rgba(0, 204, 150, 0.14)"
                else:
                    card_border = "#ddd"
                    card_bg = "rgba(249, 250, 251, 1)"
                card_body = html.Div([
                    html.H4(
                        f"Selected feature: {selected_feature}",
                        style={"margin": "0 0 8px 0", "color": card_border},
                    ),
                    html.Div(f"Class: {r.get('q9_class', 'NA')}", style={"fontWeight": "600", "color": card_border}),
                    html.Div(f"Hepar intensity: {float(r.get('hepar_intensity', 0.0)):,.0f}"),
                    html.Div(f"Hepeel intensity: {float(r.get('hepeel_intensity', 0.0)):,.0f}"),
                    html.Div(f"Max intensity: {float(r.get('q9_intensity', 0.0)):,.0f}"),
                    html.Div(f"log10(max intensity): {float(r.get('q9_log_intensity', np.nan)):.6f}" if pd.notna(r.get("q9_log_intensity", np.nan)) else "log10(max intensity): NA"),
                    html.Div(f"Name: {r.get('name', 'NA')}"),
                    html.Div(f"Molecular Formula: {r.get('molecularFormula', 'NA')}"),
                    html.Div(["PubChem IDs: ", *render_pubchem_links(r.get("pubchemids", None))]),
                    html.Div(f"NPC Pathway: {r.get('NPC.pathway', 'NA')}"),
                ])
                card_style = {
                    "display": "block",
                    "marginTop": "6px",
                    "--q9-card-border": card_border,
                    "--q9-card-bg": card_bg,
                }

        shared_n = int((qdf["q9_class"] == "Shared (Hepar + Hepeel)").sum()) if not qdf.empty else 0
        hepar_n = int((qdf["q9_class"] == "Unique to Hepar").sum()) if not qdf.empty else 0
        hepeel_n = int((qdf["q9_class"] == "Unique to Hepeel").sum()) if not qdf.empty else 0
        stats = f"Q9 | shown: {len(qdf):,} | shared: {shared_n:,} | unique Hepar: {hepar_n:,} | unique Hepeel: {hepeel_n:,}"
        cols = [{"name": c, "id": c} for c in q9_table_df.columns]
        return fig, stats, q9_table_df.to_dict("records"), cols, card_body, card_style

    # ---- Q10: interaction state (selected feature + closable card) ----
    @app.callback(
        Output("q10_selected_feature", "data"),
        Output("q10_card_open", "data"),
        Input("q10_graph", "clickData"),
        Input("q10_close_card", "n_clicks"),
        State("q10_selected_feature", "data"),
        State("q10_card_open", "data"),
        prevent_initial_call=True,
    )
    def update_q10_selection(q10_clickData, q10_close_clicks, current_selected, current_open):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
        if trigger == "q10_close_card":
            return no_update, False
        if trigger == "q10_graph" and q10_clickData and q10_clickData.get("points"):
            return str(q10_clickData["points"][0].get("x")), True
        return current_selected, current_open

    # ---- Q10: Hepar vs Hepeel final difference + plant/animal driver breakdown ----
    @app.callback(
        Output("q10_graph", "figure"),
        Output("q10_breakdown", "figure"),
        Output("q10_table", "data"),
        Output("q10_table", "columns"),
        Output("q10_stats", "children"),
        Output("q10_card_body", "children"),
        Output("q10_feature_card", "style"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q10_top_n", "value"),
        Input("q10_diff_log_thr", "value"),
        Input("q10_selected_feature", "data"),
        Input("q10_card_open", "data"),
    )
    def update_q10(feature_search, only_pubchem_vals, global_intensity_log_range, q10_top_n, q10_diff_log_thr, q10_selected_feature, q10_card_open):
        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        # final product columns (Hepar vs Hepeel)
        try:
            hepar_final = _find_col(sdf, Q8_HEPAR_FINAL_COL)
            hepeel_final = _find_col(sdf, Q8_HEPEEL_FINAL_COL)
        except KeyError as e:
            fig = px.bar(title=f"Q10: Missing final columns ({e})")
            empty = px.bar(title="Q10: click a feature to see breakdown")
            return fig, empty, [], [], "Q10: missing final product columns", html.Div("Click a feature in the chart to open details."), {"display": "none"}

        # numeric conversion
        sdf[hepar_final] = pd.to_numeric(sdf[hepar_final], errors="coerce").fillna(0)
        sdf[hepeel_final] = pd.to_numeric(sdf[hepeel_final], errors="coerce").fillna(0)

        # Apply global intensity filter using product feature list intensities (same as Explore)
        # We'll filter BOTH products consistently by feature-id set from product tables.
        # Use union of hepar+hepeel feature lists then filter by whichever side is selected in global slider.
        hepar_feat = data["Hepar"].features.copy()
        hepeel_feat = data["Hepeel"].features.copy()
        hepar_feat["feature"] = hepar_feat["feature"].astype(str)
        hepeel_feat["feature"] = hepeel_feat["feature"].astype(str)

        feature_universe = set(hepar_feat["feature"]).union(set(hepeel_feat["feature"]))
        sdf = sdf[sdf["feature"].isin(feature_universe)].copy()

        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi

            # keep feature if either product intensity falls in range
            keep_ids = set(hepar_feat.loc[hepar_feat["intensity"].between(lo, hi, inclusive="both"), "feature"])
            keep_ids |= set(hepeel_feat.loc[hepeel_feat["intensity"].between(lo, hi, inclusive="both"), "feature"])
            sdf = sdf[sdf["feature"].isin(keep_ids)].copy()

        # feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            sdf = sdf[sdf["feature"].str.contains(s, case=False, na=False)].copy()

        # only pubchem
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in sdf.columns:
                sdf = sdf[sdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                sdf = sdf.iloc[0:0].copy()

        # final-product difference
        sdf["q10_diff_final"] = (sdf[hepar_final] - sdf[hepeel_final]).abs()

        # threshold (log10)
        thr_log = float(q10_diff_log_thr) if q10_diff_log_thr is not None else 0.0
        thr = 10 ** thr_log
        sdf = sdf[sdf["q10_diff_final"] >= thr].copy()

        top_n = int(q10_top_n) if q10_top_n else 300
        sdf = sdf.sort_values("q10_diff_final", ascending=False).head(top_n)

        # Main bar plot
        fig = px.bar(
            sdf,
            x="feature",
            y="q10_diff_final",
            title=f"Q10: |Hepar_final − Hepeel_final|  (threshold ≥ {thr:g})",
            template="plotly",
            log_y=True,
        )
        fig.update_layout(xaxis=dict(showticklabels=False), yaxis_title="|Δ final| (log scale)")

        # Breakdown plot (plant vs animal driver) for clicked feature
        breakdown = px.bar(title="Q10 breakdown: click a feature above")

        # Pull Q10-specific cols from groups (Option B)
        hepar_plant_cols = groups.get("hepar_plant_cols", [])
        hepar_animal_cols = groups.get("hepar_animal_cols", [])
        hepeel_plant_cols = groups.get("hepeel_plant_cols", [])
        # Hepeel animal is 0

        # Make sure ingredient cols are numeric
        for c in set(hepar_plant_cols + hepar_animal_cols + hepeel_plant_cols):
            if c in sdf.columns:
                sdf[c] = pd.to_numeric(sdf[c], errors="coerce").fillna(0)

        selected_feature = str(q10_selected_feature) if q10_selected_feature else None
        if selected_feature:
            f_clicked = selected_feature
            row = sdf[sdf["feature"] == f_clicked]
            if not row.empty:
                r = row.iloc[0]

                hepar_plant = float(r[hepar_plant_cols].sum()) if hepar_plant_cols else 0.0
                hepar_animal = float(r[hepar_animal_cols].sum()) if hepar_animal_cols else 0.0
                hepeel_plant = float(r[hepeel_plant_cols].sum()) if hepeel_plant_cols else 0.0

                delta_plant = abs(hepar_plant - hepeel_plant)
                delta_animal = abs(hepar_animal - 0.0)  # Hepeel has no animal

                bdf = pd.DataFrame({
                    "Driver": ["Plant components", "Animal components"],
                    "Delta": [delta_plant, delta_animal],
                })

                breakdown = px.bar(
                    bdf,
                    x="Driver",
                    y="Delta",
                    title=f"Q10 driver breakdown for {f_clicked}",
                    template="plotly",
                    log_y=True,
                )
                breakdown.update_layout(yaxis_title="|Δ components| (log scale)")

        # Table
        out_cols = ["feature", "q10_diff_final", hepar_final, hepeel_final]
        for c in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
            if c in sdf.columns:
                out_cols.append(c)

        out_df = sdf[out_cols].copy()
        columns = [{"name": c, "id": c} for c in out_df.columns]

        stats = f"Q10 | shown features: {len(out_df):,} | threshold: {thr:g}"
        card_body = html.Div("Click a feature in the chart to open details.")
        card_style = {"display": "none"}
        if selected_feature and bool(q10_card_open):
            rows = sdf[sdf["feature"].astype(str) == selected_feature]
            if not rows.empty:
                rr = rows.iloc[0]
                card_body = html.Div([
                    html.H4(f"Selected feature: {selected_feature}", style={"margin": "0 0 8px 0"}),
                    html.Div(f"|Hepar - Hepeel|: {float(rr.get('q10_diff_final', 0.0)):,.0f}"),
                    html.Div(f"Hepar final intensity: {float(rr.get(hepar_final, 0.0)):,.0f}"),
                    html.Div(f"Hepeel final intensity: {float(rr.get(hepeel_final, 0.0)):,.0f}"),
                    html.Div(f"Name: {rr.get('name', 'NA')}"),
                    html.Div(f"Molecular Formula: {rr.get('molecularFormula', 'NA')}"),
                    html.Div(["PubChem IDs: ", *render_pubchem_links(rr.get("pubchemids", None))]),
                    html.Div(f"NPC Pathway: {rr.get('NPC.pathway', 'NA')}"),
                ])
                card_style = {"display": "block", "marginTop": "6px"}

        return fig, breakdown, out_df.to_dict("records"), columns, stats, card_body, card_style

    # ---- Explore: main scatter/bar for selected product and origin subset ----
    @app.callback(
        Output("main_graph", "figure"),
        Output("stats", "children"),
        Input("product", "value"),
        Input("origin_filter", "value"),
        Input("chart_type", "value"),
        Input("top_n", "value"),
        Input("global_use_log", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
    )
    def update_graph(product: str, origin_filter: str, chart_type: str, top_n: int, global_use_log_vals, feature_search: str, only_pubchem_vals, global_intensity_log_range):
        prod_df = data[product].features.copy()

        # Product-vs-product sets (Hepar-only / Hepeel-only / shared)
        prod_sets = compute_product_sets(product, data)

        # Component-origin set (plant+animal common) still comes from old logic
        origin_sets = compute_origin_sets(product, prod_df, summary_df, groups, threshold=0)

        if origin_filter in prod_sets:
            allowed_ids = prod_sets[origin_filter]
        else:
            allowed_ids = origin_sets.get(origin_filter, origin_sets["All product features"])
        
        dff = prod_df[prod_df["feature"].astype(str).isin(allowed_ids)].copy()

        # Global product-intensity filter (log slider)
        if global_intensity_log_range and "intensity" in dff.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            dff = dff[dff["intensity"].between(lo, hi, inclusive="both")].copy()

        if feature_search and feature_search.strip():
            fs = feature_search.strip()
            dff = dff[dff["feature"].astype(str).str.contains(fs, case=False, na=False)].copy()

        annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in summary_df.columns]
        if annot_cols:
            annot = summary_df[annot_cols].drop_duplicates("feature")
            dff = dff.merge(annot, on="feature", how="left", suffixes=("", "_annot"))
            for col in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
                if f"{col}_annot" in dff.columns:
                    if col not in dff.columns:
                        dff[col] = dff[f"{col}_annot"]
                    else:
                        dff[col] = dff[col].where(dff[col].notna(), dff[f"{col}_annot"])
            drop_cols = [c for c in dff.columns if c.endswith("_annot")]
            if drop_cols:
                dff = dff.drop(columns=drop_cols)

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                dff = dff.iloc[0:0].copy()

        use_log = "log" in (global_use_log_vals or [])

        if chart_type == "bar":
            fig = make_bar_topN(dff, use_log=use_log, top_n=int(top_n))
        else:
            fig = make_scatter(dff, use_log=use_log)

        rng_txt = ""
        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            rng_txt = f" | intensity: {lo:,.0f}-{hi:,.0f}"

        stats = (
            f"{product} | {origin_filter} | shown: {len(dff):,}"
            f"{rng_txt} | plant cols: {len(groups['plant_cols'])} | animal cols: {len(groups['animal_cols'])}"
        )
        return fig, stats
    # ---- Q4: Component-only feature table (present in components, missing in product) ----
    @app.callback(
        Output("q4_table", "data"),
        Output("q4_table", "columns"),
        Output("q4_stats", "children"),
        Input("product", "value"),
        Input("q4_source", "value"),
        Input("q4_presence_log_thr", "value"),
        Input("q4_max_rows", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
    )
    def update_q4_table(product, q4_source, q4_presence_log_thr, q4_max_rows, feature_search, only_pubchem_vals, global_intensity_log_range):
    # Robustness: some Dash components may pass product as a list/tuple
        if isinstance(product, (list, tuple)):
            product = product[0] if len(product) > 0 else "Hepar"
        if not product:
            product = "Hepar"

        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)
        prod_ids = set(prod_df["feature"].dropna().astype(str))

        thr_log = float(q4_presence_log_thr) if q4_presence_log_thr is not None else 0.0
        presence_thr = 10 ** thr_log

        df = build_component_only_df(product, prod_ids, summary_df, groups, presence_thr=presence_thr)

        # ✅ Global intensity range filter (use product feature list intensities)
        if global_intensity_log_range and "intensity" in prod_df.columns and not prod_df.empty:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            df["max_component_intensity"] = pd.to_numeric(df["max_component_intensity"], errors="coerce").fillna(0)
            df = df[df["max_component_intensity"].between(lo, hi, inclusive="both")].copy()

        # filter by source
        if q4_source and q4_source != "all" and "source" in df.columns:
            df = df[df["source"] == q4_source].copy()

        # feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            df = df[df["feature"].astype(str).str.contains(s, case=False, na=False)].copy()

        # only pubchem
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)].copy()
            else:
                df = df.iloc[0:0].copy()

        max_rows = int(q4_max_rows) if q4_max_rows else 300
        df = df.head(max_rows)

        cols = [{"name": c, "id": c} for c in df.columns]
        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            stats = f"Q4 | rows shown: {len(df):,} | presence_thr=10^{thr_log:.2f} | global=10^{log_lo:.2f}..10^{log_hi:.2f} (component max)"
        else:
            stats = f"Q4 | rows shown: {len(df):,} | presence_thr=10^{thr_log:.2f}"
        return df.to_dict("records"), cols, stats
    # ---- Q5: Product-only feature table (present in product, missing in components) ----
    @app.callback(
        Output("q5_table", "data"),
        Output("q5_table", "columns"),
        Output("q5_stats", "children"),
        Input("product", "value"),
        Input("q5_max_rows", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
    )
    def update_q5_table(product, q5_max_rows, feature_search, only_pubchem_vals, global_intensity_log_range):
        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)

        df = build_product_only_df(product, prod_df, summary_df, groups)

        # global intensity filter
        if global_intensity_log_range and "intensity" in df.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            df = df[df["intensity"].between(lo, hi, inclusive="both")].copy()

        # feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            df = df[df["feature"].astype(str).str.contains(s, case=False, na=False)].copy()

        # only pubchem
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)].copy()
            else:
                df = df.iloc[0:0].copy()

        max_rows = int(q5_max_rows) if q5_max_rows else 300
        df = df.head(max_rows)

        cols = [{"name": c, "id": c} for c in df.columns]
        stats = f"Q5 | rows shown: {len(df):,}"
        return df.to_dict("records"), cols, stats

    # ---- Q1: Origin buckets visualization (Plant-only/Animal-only/Common/Product-only) ----
    @app.callback(
    Output("q1_graph", "figure"),
    Output("q1_stats", "children"),
    Input("product", "value"),
    Input("q1_bucket", "value"),
    Input("q1_chart_type", "value"),
    Input("q1_top_n", "value"),
    Input("feature_search", "value"),
    Input("only_pubchem", "value"),
    Input("global_use_log", "value"),
    Input("global_intensity_log_range", "value"),
)
    def update_q1(product, q1_bucket, q1_chart_type, q1_top_n, feature_search, only_pubchem_vals, global_use_log, global_intensity_log_range):
        use_log = "log" in (global_use_log or [])

        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)

        origin_sets = compute_origin_sets(product, prod_df, summary_df, groups, threshold=0)
        allowed_ids = origin_sets.get(q1_bucket, set())

        dff = prod_df[prod_df["feature"].isin(set(map(str, allowed_ids)))].copy()

        # intensity range
        if global_intensity_log_range and "intensity" in dff.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            dff = dff[dff["intensity"].between(lo, hi, inclusive="both")].copy()

        # feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            dff = dff[dff["feature"].astype(str).str.contains(s, case=False, na=False)].copy()

        # merge annotations
        annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids", "NPC.pathway"] if c in summary_df.columns]
        if annot_cols:
            annot = summary_df[annot_cols].drop_duplicates("feature").copy()
            annot["feature"] = annot["feature"].astype(str)
            dff = dff.merge(annot, on="feature", how="left")

        # only pubchem
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                dff = dff.iloc[0:0].copy()

        if dff.empty:
            fig = px.scatter(pd.DataFrame({"Average.Rt.min.": [], "intensity": []}), x="Average.Rt.min.", y="intensity", template="plotly")
            return fig, f"Q1 | product={product} | bucket={q1_bucket} | rows=0"

        if q1_chart_type == "bar":
            fig = make_bar_topN(dff, use_log=use_log, top_n=int(q1_top_n or 50))
        else:
            fig = make_scatter(dff, use_log=use_log)

        stats = f"Q1 | product={product} | bucket={q1_bucket} | rows={len(dff):,}"
        return fig, stats
    
    # ---- Q3: Proportion of product signal that is plant-/animal-dominant ----
    @app.callback(
            Output("q3_prop_bar", "figure"),
            Output("q3_scatter", "figure"),
            Output("q3_stats", "children"),
            Input("product", "value"),
            Input("origin_filter", "value"),
            Input("feature_search", "value"),
            Input("only_pubchem", "value"),
            Input("global_intensity_log_range", "value"),
            Input("q3_dom_ratio", "value"),
            Input("q3_cats", "value"),
            Input("global_use_log", "value"),
    )
    def update_q3(product, origin_filter, feature_search, only_pubchem_vals,
                  global_intensity_log_range, q3_dom_ratio, q3_cats, global_use_log_vals):

        prod_df = data[product].features.copy()

        # 1) apply origin filter (same as Explore)
        prod_sets = compute_product_sets(product, data)
        origin_sets = compute_origin_sets(product, prod_df, summary_df, groups, threshold=0)

        if origin_filter in prod_sets:
            allowed_ids = prod_sets[origin_filter]
        else:
            allowed_ids = origin_sets.get(origin_filter, origin_sets["All product features"])

        dff = prod_df[prod_df["feature"].astype(str).isin(set(map(str, allowed_ids)))].copy()

        # 2) global intensity filter (product intensity)
        if global_intensity_log_range and "intensity" in dff.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            dff = dff[dff["intensity"].between(lo, hi, inclusive="both")].copy()

        # 3) feature search
        if feature_search and str(feature_search).strip():
            fs = str(feature_search).strip()
            dff = dff[dff["feature"].astype(str).str.contains(fs, case=False, na=False)].copy()

        # 4) merge pubchemids (needed for only_pubchem)
        if "pubchemids" not in dff.columns and "pubchemids" in summary_df.columns:
            annot = summary_df[["feature", "pubchemids"]].drop_duplicates("feature").copy()
            annot["feature"] = annot["feature"].astype(str)
            dff = dff.merge(annot, on="feature", how="left")

        # 5) only_pubchem filter
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                dff = dff.iloc[0:0].copy()

        # 6) compute plant/animal sums + dominance label
        dom_ratio = float(q3_dom_ratio) if q3_dom_ratio else 1.5
        # choose a small threshold to avoid noise;
        presence_thr = 0.0
        dff = add_q3_component_sums_and_dominance(
            dff, summary_df, groups,
            product=product,
            dom_ratio=dom_ratio,
            presence_thr=presence_thr,
        )

        # 7) filter categories
        if q3_cats:
            dff = dff[dff["q3_class"].isin(q3_cats)].copy()

        # 8) build charts
        bar_fig = make_q3_prop_bar(dff)
        use_log = bool(global_use_log_vals and "log" in global_use_log_vals)
        scatter_fig = make_q3_scatter(dff, use_log=use_log)

        # 9) stats text
        total_feats = len(dff)
        total_signal = float(pd.to_numeric(dff.get("intensity", 0), errors="coerce").fillna(0).sum())
        stats = f"{product} | Q3 features used: {total_feats:,} | total filtered signal: {total_signal:,.3g} | dom≥{dom_ratio:g}x"

        return bar_fig, scatter_fig, stats
    return app


if __name__ == "__main__":
    app = build_app()
    app.run(debug=True, use_reloader=True)