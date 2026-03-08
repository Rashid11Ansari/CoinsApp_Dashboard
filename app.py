from __future__ import annotations

from pathlib import Path
import re


import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px
import plotly.io as pio

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
# - Per-question helpers: Q3/Q4/Q5/Q6/Q7/Q8/Q10
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
    # ---- Navigation: show/hide views and set origin_filter ----
    @app.callback(
        Output("view_explore", "style"),
        Output("view_q1", "style"),
        Output("view_q3", "style"),
        Output("view_q4", "style"),
        Output("view_q5", "style"),
        Output("view_q6", "style"),
        Output("view_q7", "style"),
        Output("view_q8", "style"),
        Output("view_q10", "style"),
        Output("origin_filter", "value"),
        Input("page_select", "value"),
    )

    def switch_view(page_select: str):
        show = {"display": "block"}
        hide = {"display": "none"}

        origin_val = "All product features"

        # order:
        # explore, q1, q3, q4, q5, q6, q7, q8, q10, origin_filter,

        if not page_select:
            return show, hide, hide, hide, hide, hide, hide, hide, hide, origin_val

        # Explore shortcut
        if isinstance(page_select, str) and page_select.startswith("explore::"):
            origin_val = page_select.split("::", 1)[1]
            return show, hide, hide, hide, hide, hide, hide, hide, hide, origin_val
        if page_select == "q1":
            return hide, show, hide, hide, hide, hide, hide, hide, hide, origin_val
        if page_select == "q3":
            return hide, hide, show, hide, hide, hide, hide, hide, hide, origin_val
        if page_select == "q4":
            return hide, hide, hide, show, hide, hide, hide, hide, hide, origin_val
        if page_select == "q5":
            return hide, hide, hide, hide, show, hide, hide, hide,  hide, origin_val
        if page_select == "q6":
            return hide, hide, hide, hide, hide, show, hide, hide,  hide, origin_val
        if page_select == "q7":
            return hide, hide, hide, hide, hide, hide, show, hide, hide, origin_val
        if page_select == "q8":
            return hide, hide, hide, hide, hide, hide, hide, show, hide, origin_val
        if page_select == "q10":
            return hide, hide, hide, hide, hide, hide, hide, hide, show, origin_val

        # fallback -> explore
        return show, hide, hide, hide, hide, hide, hide, hide, hide, origin_val


    # ---- Q6: Feature-level ingredient contribution drilldown ----
    @app.callback(
        Output("q6_dom_bar", "figure"),
        Output("q6_contrib_bar", "figure"),
        Output("q6_table", "data"),
        Output("q6_table", "columns"),
        Output("q6_stats", "children"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q6_feature_id", "value"),
        Input("q6_top_n", "value"),
        Input("q6_dom_bar", "clickData"),
    )
    def update_q6(product, feature_search, only_pubchem_vals, global_intensity_log_range, q6_feature_id, q6_top_n, q6_clickData):
        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        ingredient_cols, plant_cols, animal_cols = q6_get_ingredient_cols_for_product(product, sdf, groups)
        if not ingredient_cols:
            empty = px.bar(title="Q6: No ingredient columns matched")
            return empty, empty, [], [], "Q6: No ingredient columns matched for this product."

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

        # typed feature overrides click
        selected_feature = None
        if q6_feature_id and str(q6_feature_id).strip():
            selected_feature = str(q6_feature_id).strip()
        elif q6_clickData and "points" in q6_clickData and q6_clickData["points"]:
            selected_feature = str(q6_clickData["points"][0].get("x"))

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
        return q6_dom_fig, contrib_fig, table_df.to_dict("records"), cols, stats

    # ---- Q7: Enrichment vs component sources (Final − sum(components)) ----
    @app.callback(
        Output("q7_graph", "figure"),
        Output("q7_table", "data"),
        Output("q7_table", "columns"),
        Output("q7_pubchem", "children"),
        Output("q7_stats", "children"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q7_top_n", "value"),
        Input("q7_graph", "clickData"),
    )
    def update_q7(product, feature_search, only_pubchem_vals, global_intensity_log_range, q7_top_n, q7_clickData):
        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        # Resolve final product column for selected product
        try:
            final_col = _find_col(sdf, Q8_HEPAR_FINAL_COL) if "hepar" in str(product).lower() else _find_col(sdf, Q8_HEPEEL_FINAL_COL)
        except KeyError as e:
            fig = px.bar(title=f"Q7: Missing final product column ({e})")
            return fig, [], [], "Q7: Missing final product column.", ""

        # Ingredient columns for selected product (authoritative from data_loader groups)
        if "hepar" in str(product).lower():
            base_cols = list(groups.get("hepar_component_cols", []))
        else:
            base_cols = list(groups.get("hepeel_component_cols", []))

        # keep only those that exist in the dataframe
        ingredient_cols = [c for c in base_cols if c in sdf.columns]
        missing = [c for c in base_cols if c not in sdf.columns]

        if not ingredient_cols:
            fig = px.bar(title="Q7: No ingredient columns available for this product")
            return fig, [], [], "Q7: No ingredient columns available for this product.", ""

        # Numeric conversion
        sdf[final_col] = pd.to_numeric(sdf[final_col], errors="coerce").fillna(0)
        for c in ingredient_cols:
            if c in sdf.columns:
                sdf[c] = pd.to_numeric(sdf[c], errors="coerce").fillna(0)

        # Restrict to features in selected product feature list
        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)
        prod_ids = set(prod_df["feature"].dropna().astype(str))
        sdf = sdf[sdf["feature"].isin(prod_ids)].copy()

        # Global intensity filter based on product feature intensity
        if global_intensity_log_range and "intensity" in prod_df.columns:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            keep_ids = set(prod_df.loc[prod_df["intensity"].between(lo, hi, inclusive="both"), "feature"].astype(str))
            sdf = sdf[sdf["feature"].isin(keep_ids)].copy()

        # Feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            sdf = sdf[sdf["feature"].str.contains(s, case=False, na=False)].copy()

        # Only PubChem filter
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in sdf.columns:
                sdf = sdf[sdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                sdf = sdf.iloc[0:0].copy()

        # Enrichment = Final - sum(ingredients)
        mat_ing = sdf[ingredient_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        ing_sum = mat_ing.sum(axis=1)
        sdf["q7_ingredient_sum"] = ing_sum
        sdf["q7_enrichment"] = sdf[final_col] - ing_sum

        # Keep enriched > 0
        sdf = sdf[sdf["q7_enrichment"] > 0].copy()

        top_n = int(q7_top_n) if q7_top_n else 300
        sdf = sdf.sort_values("q7_enrichment", ascending=False).head(top_n)

        # Plot (log_y like enrichment scripts)
        fig = px.bar(
            sdf,
            x="feature",
            y="q7_enrichment",
            title="Enriched features (Final − sum(ingredients))",
            template="plotly",
            log_y=True,
        )
        fig.update_layout(xaxis=dict(showticklabels=True, tickangle=45), yaxis_title="enrichment (log scale)")

        # PubChem output on click
        pubchem_out = "Click a feature bar to see PubChem ID(s)"
        if q7_clickData and "points" in q7_clickData and q7_clickData["points"]:
            f_clicked = str(q7_clickData["points"][0].get("x"))
            row = sdf[sdf["feature"] == f_clicked]
            if not row.empty:
                pubchem_ids = row["pubchemids"].iloc[0] if "pubchemids" in row.columns else None
                cids = extract_pubchem_cids(pubchem_ids)
                if not cids:
                    pubchem_out = f"Feature {f_clicked} | PubChem ID(s): Not available"
                else:
                    pubchem_out = html.Div([
                        html.B(f"Feature: {f_clicked} | PubChem CID(s): "),
                        html.Span([
                            html.A(
                                cid,
                                href=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                                target="_blank",
                                style={"marginRight": "10px"},
                            )
                            for cid in cids
                        ])
                    ])

        # Table
        out_cols = ["feature", "q7_enrichment", final_col, "q7_ingredient_sum"]
        for c in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
            if c in sdf.columns:
                out_cols.append(c)

        out_df = sdf[out_cols].copy()
        columns = [{"name": c, "id": c} for c in out_df.columns]
        miss_txt = f" | missing cols: {len(missing)}" if 'missing' in locals() and missing else ""
        stats = f"Q7 | enriched rows: {len(out_df):,} | top_n={top_n}{miss_txt}"
        return fig, out_df.to_dict("records"), columns, pubchem_out, stats
    # ---- Q8: Selective amplification/attenuation (Final / max(component)) ----
    @app.callback(
        Output("q8_table", "data"),
        Output("q8_table", "columns"),
        Output("q8_table", "tooltip_data"),
        Output("q8_hist", "figure"),
        Output("q8_stats", "children"),
        Input("product", "value"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q8_amp_threshold", "value"),
        Input("q8_cats", "value"),
    )
    def update_q8(product, feature_search, only_pubchem_vals, global_intensity_log_range, q8_amp_threshold, q8_cats):
        empty_fig = px.histogram(pd.DataFrame({"ratio": []}), x="ratio", template="plotly")
        empty_fig.update_layout(
            xaxis_title="Final product / max ingredient (ratio)",
            yaxis_title="Feature count",
            margin=dict(l=20, r=20, t=30, b=40),
            showlegend=True,
        )

        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        # Resolve required columns (best-effort matching)
        try:
            hepar_final = _find_col(sdf, Q8_HEPAR_FINAL_COL)
            hepeel_final = _find_col(sdf, Q8_HEPEEL_FINAL_COL)
        except KeyError as e:
            return [], [], [], empty_fig, f"Q8: Missing final product columns. {e}"

        hepar_ing_cols = [c for c in groups.get("hepar_component_cols", []) if c in sdf.columns]
        hepeel_ing_cols = [c for c in groups.get("hepeel_component_cols", []) if c in sdf.columns]

        if not hepar_ing_cols or not hepeel_ing_cols:
            msg = f"Q8: Missing component columns. Hepar cols={len(hepar_ing_cols)}, Hepeel cols={len(hepeel_ing_cols)}."
            return [], [], [], empty_fig, msg

        # Numeric conversion for needed columns
        need_cols = [hepar_final, hepeel_final] + hepar_ing_cols + hepeel_ing_cols
        for c in need_cols:
            if c in sdf.columns:
                sdf[c] = pd.to_numeric(sdf[c], errors="coerce").fillna(0)

        # Decide which product is selected in the top dropdown
        pnorm = str(product).lower()
        is_hepar = "hepar" in pnorm
        sel_final = hepar_final if is_hepar else hepeel_final
        sel_ratio_col = "hepar_ratio" if is_hepar else "hepeel_ratio"
        sel_state_col = "hepar_state" if is_hepar else "hepeel_state"
        other_state_col = "hepeel_state" if is_hepar else "hepar_state"

        # Global intensity filter should behave like the rest of the app:
        # apply it to the SELECTED product final intensity only
        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            sdf = sdf[sdf[sel_final].between(lo, hi, inclusive="both")].copy()

        # Feature search
        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            sdf = sdf[sdf["feature"].astype(str).str.contains(s, case=False, na=False)].copy()

        # Only PubChem filter
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in sdf.columns:
                sdf = sdf[sdf["pubchemids"].apply(has_pubchem)].copy()
            else:
                sdf = sdf.iloc[0:0].copy()

        amp_thr = float(q8_amp_threshold) if q8_amp_threshold else 3.0
        amp_thr = max(1.0, amp_thr)

        hepar_comp_max = sdf[hepar_ing_cols].max(axis=1)
        hepeel_comp_max = sdf[hepeel_ing_cols].max(axis=1)

        # Store max values in the dataframe for tooltip use
        sdf["hepar_comp_max"] = hepar_comp_max
        sdf["hepeel_comp_max"] = hepeel_comp_max

        sdf["hepar_ratio"] = sdf[hepar_final] / hepar_comp_max.replace(0, pd.NA)
        sdf["hepeel_ratio"] = sdf[hepeel_final] / hepeel_comp_max.replace(0, pd.NA)

        sdf["hepar_state"] = [_q8_state(float(p), float(m), amp_thr) for p, m in zip(sdf[hepar_final], hepar_comp_max)]
        sdf["hepeel_state"] = [_q8_state(float(p), float(m), amp_thr) for p, m in zip(sdf[hepeel_final], hepeel_comp_max)]

        # Build selective categories (still computed using BOTH products)
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

        # Map the TWO checkboxes to the right categories depending on selected product
        amp_cat = "hepar_selective_amplification" if is_hepar else "hepeel_selective_amplification"
        att_cat = "hepar_selective_attenuation" if is_hepar else "hepeel_selective_attenuation"

        desired = set(q8_cats or [])
        allowed = set()
        if "selective_amplification" in desired:
            allowed.add(amp_cat)
        if "selective_attenuation" in desired:
            allowed.add(att_cat)

        sdf = sdf[sdf["q8_category"].isin(allowed)].copy() if allowed else sdf.iloc[0:0].copy()

        # Add a friendly type label for display
        sdf["q8_type"] = sdf["q8_category"].map({
            amp_cat: "Selective amplification",
            att_cat: "Selective attenuation",
        })

        # Histogram on selected product ratio
        if sdf.empty:
            fig = empty_fig
        else:
            fig = px.histogram(
                sdf,
                x=sel_ratio_col,
                color="q8_type",
                nbins=40,
                template="plotly",
            )
            fig.update_layout(
                xaxis_title="Final product / max ingredient (ratio)",
                yaxis_title="Feature count",
                margin=dict(l=20, r=20, t=30, b=40),
                legend_title_text="",
            )

        # Output table (show selected product columns + other product state for context)
        out_cols = [
            "feature",
            "q8_type",
            "hepar_comp_max",
            "hepeel_comp_max",
            sel_final,
            sel_ratio_col,
            sel_state_col,
            other_state_col,
        ]
        for c in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
            if c in sdf.columns:
                out_cols.append(c)

        out = sdf[out_cols].copy()
        out = out.sort_values([ "q8_type", sel_ratio_col ], ascending=[True, False]).head(2000)

        # Tooltip helpers and builder
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

        # Build per-row tooltips for the ratio cells
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
                f"Amplified if ratio ≥ **{amp_thr:.2f}**\n"
                f"Attenuated if ratio ≤ **{inv_thr:.2f}**\n"
                f"→ **{hs}**"
            )

            hepeel_tip = (
                f"**ratio = Final / max(ingredients)**\n"
                f"= {_fmt_int(pf)} / {_fmt_int(pm)} = **{_fmt_ratio(pr)}**\n\n"
                f"Amplified if ratio ≥ **{amp_thr:.2f}**\n"
                f"Attenuated if ratio ≤ **{inv_thr:.2f}**\n"
                f"→ **{ps}**"
            )

            tooltips.append(
                {
                    "hepar_ratio": {"value": hepar_tip, "type": "markdown"},
                    "hepeel_ratio": {"value": hepeel_tip, "type": "markdown"},
                }
            )

        cols = [{"name": c, "id": c} for c in out.columns]
        stats = (
            f"Q8 ({'Hepar' if is_hepar else 'Hepeel'}) | rows: {len(out):,} | "
            f"amp≥{amp_thr:g}x (att≤{1/amp_thr:g}x)"
        )
        return out.to_dict("records"), cols, tooltips, fig, stats
    # ---- Q10: Hepar vs Hepeel final difference + plant/animal driver breakdown ----
    @app.callback(
        Output("q10_graph", "figure"),
        Output("q10_breakdown", "figure"),
        Output("q10_table", "data"),
        Output("q10_table", "columns"),
        Output("q10_stats", "children"),
        Input("feature_search", "value"),
        Input("only_pubchem", "value"),
        Input("global_intensity_log_range", "value"),
        Input("q10_top_n", "value"),
        Input("q10_diff_log_thr", "value"),
        Input("q10_graph", "clickData"),
    )
    def update_q10(feature_search, only_pubchem_vals, global_intensity_log_range, q10_top_n, q10_diff_log_thr, q10_click):
        sdf = summary_df.copy()
        sdf["feature"] = sdf["feature"].astype(str)

        # final product columns (Hepar vs Hepeel)
        try:
            hepar_final = _find_col(sdf, Q8_HEPAR_FINAL_COL)
            hepeel_final = _find_col(sdf, Q8_HEPEEL_FINAL_COL)
        except KeyError as e:
            fig = px.bar(title=f"Q10: Missing final columns ({e})")
            empty = px.bar(title="Q10: click a feature to see breakdown")
            return fig, empty, [], [], "Q10: missing final product columns"

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

        if q10_click and "points" in q10_click and q10_click["points"]:
            f_clicked = str(q10_click["points"][0].get("x"))
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
        return fig, breakdown, out_df.to_dict("records"), columns, stats


    # ---- Global: sync intensity slider range to selected product ----
    @app.callback(
        Output("global_intensity_log_range", "min"),
        Output("global_intensity_log_range", "max"),
        Output("global_intensity_log_range", "value"),
        Output("global_intensity_log_range", "marks"),
        Output("global_intensity_range_label", "children"),
        Input("product", "value"),
    )
    def sync_global_intensity_slider(product: str):
        prod_df = data[product].features

        if "intensity" not in prod_df.columns or prod_df["intensity"].dropna().empty:
            return 0, 1, [0, 1], {}, ""

        # clamp min to 1 to avoid log10(0)
        mx = float(prod_df["intensity"].max())
        mx = max(1.0, mx)

        log_min = 0.0  # log10(1)
        log_max = float(np.ceil(np.log10(mx)))

        # marks at powers of 10
        marks: dict[float, str] = {}
        for i in range(int(log_min), int(log_max) + 1):
            val = 10 ** i
            if val >= 1_000_000:
                lab = f"{int(val/1_000_000)}M"
            elif val >= 1_000:
                lab = f"{int(val/1_000)}k"
            else:
                lab = f"{int(val)}"
            marks[float(i)] = lab

        label = f"Intensity filter (log10): 10^{log_min:.0f} to 10^{log_max:.0f}"
        return log_min, log_max, [log_min, log_max], marks, label

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
    )
    def update_q4_table(product, q4_source, q4_presence_log_thr, q4_max_rows, feature_search, only_pubchem_vals):
        prod_df = data[product].features.copy()
        prod_df["feature"] = prod_df["feature"].astype(str)
        prod_ids = set(prod_df["feature"].dropna().astype(str))

        thr_log = float(q4_presence_log_thr) if q4_presence_log_thr is not None else 0.0
        presence_thr = 10 ** thr_log

        df = build_component_only_df(product, prod_ids, summary_df, groups, presence_thr=presence_thr)
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