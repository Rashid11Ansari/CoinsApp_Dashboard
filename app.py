from __future__ import annotations

from itertools import product
from pathlib import Path
import re

import pandas as pd
import numpy as np
from dash import Dash, dcc, Input, Output, dash_table
import plotly.express as px
import plotly.io as pio

# Guard against bad/unsupported default templates causing px.bar() to crash
pio.templates.default = "plotly"

from data_loader import load_all
from layout import build_layout

APP_TITLE = "MS Feature Explorer (Origin-aware)"

_PUBCHEM_RE = re.compile(r"\d+")

# -----------------------------
# Q8 configuration
# -----------------------------
Q8_HEPAR_FINAL_COL = "Hepar.comp.Ampoules..Bulk.mat.52324."
Q8_HEPEEL_FINAL_COL = "Hepeel.ampoule.solution..Bulk"

Q8_HEPAR_INGREDIENTS = [
    "Avena sativa","Chelidonium majus","Cinchona pubescens","Cynara scolymus","Lycopodium clavatum","Silybum marianum","Taraxacum officinale","Veratrum album",
    "Colon suis","Duodenum suis", "Hepar suis","Pankreas suis","Thymus suis","Vesica fellea suis",
]

Q8_HEPEEL_INGREDIENTS = [
    "Chelidonium majus","Cinchona pubescens","Citrullus colocynthis","Lycopodium clavatum","Myristica fragrans","Silybum marianum","Veratrum album",
]


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


def _find_cols_for_ingredients(df: pd.DataFrame, ingredients: list[str]) -> list[str]:
    cols: list[str] = []
    for ing in ingredients:
        try:
            cols.append(_find_col(df, ing))
        except KeyError:
            # ignore missing; we'll handle with whatever we found
            pass
    return cols


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


def compute_origin_sets(product_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict, threshold: float = 0) -> dict[str, set[str]]:
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

#Q4/Q5 HELPERS START
def build_product_only_df(prod_df: pd.DataFrame, summary_df: pd.DataFrame, groups: dict) -> pd.DataFrame:
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
    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    if not comp_cols:
        return pd.DataFrame(columns=["feature", "source", "max_component_intensity"])

    comp_present_mask = (summary_df[comp_cols] > 0).any(axis=1)
    comp_present = summary_df.loc[comp_present_mask, "feature"].astype(str)

    comp_only_ids = set(comp_present) - set(map(str, prod_feature_ids))
    sdf = summary_df[summary_df["feature"].astype(str).isin(comp_only_ids)].copy()

    plant_present = (sdf[plant_cols] > 0).any(axis=1) if plant_cols else False
    animal_present = (sdf[animal_cols] > 0).any(axis=1) if animal_cols else False

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
    dom_ratio: float,
) -> pd.DataFrame:
    """
    Adds per-feature:
      plant_sum, animal_sum, plant_frac, animal_frac, q3_class
    where q3_class ∈ {Plant-dominant, Animal-dominant, Mixed, Product-only}.
    """

    plant_cols = [c for c in groups.get("plant_cols", []) if c in summary_df.columns]
    animal_cols = [c for c in groups.get("animal_cols", []) if c in summary_df.columns]
    comp_cols = plant_cols + animal_cols

    out = dff.copy()
    out["feature"] = out["feature"].astype(str)

    # If no component columns exist, everything becomes Product-only
    if not comp_cols:
        out["plant_sum"] = 0.0
        out["animal_sum"] = 0.0
        out["plant_frac"] = 0.0
        out["animal_frac"] = 0.0
        out["q3_class"] = "Product-only"
        return out

    # Pull only needed component intensities for these features
    comp = summary_df[["feature"] + comp_cols].drop_duplicates("feature").copy()
    comp["feature"] = comp["feature"].astype(str)
    comp = _ensure_numeric_cols(comp, comp_cols)

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

    comp["q3_class"] = [
        _label(float(ps), float(an)) for ps, an in zip(comp["plant_sum"], comp["animal_sum"])
    ]

    out = out.merge(comp[["feature", "plant_sum", "animal_sum", "plant_frac", "animal_frac", "q3_class"]],
                    on="feature", how="left")

    # Missing merges => treat as Product-only
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

    for c in set(groups["plant_cols"] + groups["animal_cols"]):
        if c in summary_df.columns:
            summary_df[c] = pd.to_numeric(summary_df[c], errors="coerce").fillna(0)

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = APP_TITLE

    origin_options = [
    {"label": "All product features", "value": "All product features"},
    {"label": "Unique to product (vs other product)", "value": "Unique to product"},
    {"label": "Shared (both products)", "value": "Shared (both products)"},
    {"label": "Common (plant+animal components)", "value": "Common (plant+animal)"},
    ]

    app.layout = build_layout(APP_TITLE, origin_options)

    @app.callback(
        Output("view_explore", "style"),
        Output("view_q3", "style"),
        Output("view_q4q5", "style"),
        Output("view_q8", "style"),
        Output("set_mode", "value"),
        Output("origin_filter", "value"),
        Output("q4q5_select", "value"),
        Input("page_select", "value"),
    )
    def switch_view(page_select: str):
        show = {"display": "block"}
        hide = {"display": "none"}

        # defaults
        origin_val = "All product features"
        q4q5_val = "product_only"
        set_mode_val = q4q5_val

        if not page_select:
            return show, hide, hide, hide, set_mode_val, origin_val, q4q5_val

        # Explore modes
        if page_select.startswith("explore::"):
            origin_val = page_select.split("::", 1)[1]
            return show, hide, hide, hide, set_mode_val, origin_val, q4q5_val

        # Q3
        if page_select == "q3":
            return hide, show, hide, hide, set_mode_val, origin_val, q4q5_val

        # Q8
        if page_select == "q8":
            return hide, hide, hide, show, set_mode_val, origin_val, q4q5_val

        # Q4 / Q5
        if page_select == "q4":
            q4q5_val = "component_only"
        else:  # q5
            q4q5_val = "product_only"

        set_mode_val = q4q5_val
        return hide, hide, show, hide, set_mode_val, origin_val, q4q5_val
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

        hepar_ing_cols = _find_cols_for_ingredients(sdf, Q8_HEPAR_INGREDIENTS)
        hepeel_ing_cols = _find_cols_for_ingredients(sdf, Q8_HEPEEL_INGREDIENTS)

        if not hepar_ing_cols or not hepeel_ing_cols:
            msg = (
                f"Q8: Missing ingredient columns. "
                f"Hepar matched {len(hepar_ing_cols)}/{len(Q8_HEPAR_INGREDIENTS)}, "
                f"Hepeel matched {len(hepeel_ing_cols)}/{len(Q8_HEPEEL_INGREDIENTS)}."
            )
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

    @app.callback(
        Output("set_source", "disabled"),
        Input("set_mode", "value"),
    )
    def disable_component_source_when_q5(set_mode: str):
        return set_mode == "product_only"


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
        origin_sets = compute_origin_sets(prod_df, summary_df, groups, threshold=0)

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

    @app.callback(
    Output("set_table", "data"),
    Output("set_table", "columns"),
    Output("set_stats", "children"),
    Input("product", "value"),              # global product
    Input("set_mode", "value"),
    Input("set_source", "value"),
    Input("feature_search", "value"),       # global search
    Input("set_max_rows", "value"),
    Input("only_pubchem", "value"),
    Input("global_intensity_log_range", "value"),
)
    
    def update_set_table(product, set_mode, set_source,feature_search, set_max_rows,only_pubchem_vals, global_intensity_log_range):
        prod_df = data[product].features
        prod_ids = set(prod_df["feature"].astype(str).dropna())

        if set_mode == "product_only":
            df = build_product_only_df(prod_df, summary_df, groups)
            title = "Q5: Product-only features"
        else:
            df = build_component_only_df(prod_ids, summary_df, groups)
            title = "Q4: Component-only features"
            if set_source != "all" and "source" in df.columns:
                df = df[df["source"] == set_source]

        # Global intensity filter (log slider) applies differently depending on mode
        if global_intensity_log_range:
            log_lo, log_hi = map(float, global_intensity_log_range)
            lo = 10 ** log_lo
            hi = 10 ** log_hi
            if set_mode == "product_only" and "intensity" in df.columns:
                df = df[df["intensity"].between(lo, hi, inclusive="both")].copy()
            elif set_mode != "product_only" and "max_component_intensity" in df.columns:
                df = df[df["max_component_intensity"].between(lo, hi, inclusive="both")].copy()

        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                df = df[df["pubchemids"].apply(has_pubchem)]
            else:
                df = df.iloc[0:0]

        if feature_search and str(feature_search).strip():
            s = str(feature_search).strip()
            df = df[df["feature"].astype(str).str.contains(s, case=False, na=False)]

        df = df.head(int(set_max_rows))
        columns = [{"name": c, "id": c} for c in df.columns]
        stats = f"{title} | rows shown: {len(df):,} | product: {product}"
        return df.to_dict("records"), columns, stats
    
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
        origin_sets = compute_origin_sets(prod_df, summary_df, groups, threshold=0)
        allowed_ids = origin_sets.get(origin_filter, origin_sets["All product features"])
        dff = prod_df[prod_df["feature"].astype(str).isin(allowed_ids)].copy()

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
        dff = add_q3_component_sums_and_dominance(dff, summary_df, groups, dom_ratio=dom_ratio)

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