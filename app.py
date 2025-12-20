from __future__ import annotations

from pathlib import Path

import pandas as pd
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px
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

    app = Dash(__name__)
    app.title = APP_TITLE

    origin_options = [
        {"label": "All product features", "value": "All product features"},
        {"label": "Common (plant+animal)", "value": "Common (plant+animal)"},
        {"label": "Product-only (Q5)", "value": "Unique to product"},
    ]

    app.layout = html.Div(
        style={"maxWidth": "1200px", "margin": "0 auto", "padding": "16px"},
        children=[
            html.H2(APP_TITLE),
            html.Div(
                style={"marginTop": "6px", "marginBottom": "6px"},
                children=[
                    dcc.Checklist(
                        id="only_pubchem",
                        options=[{"label": "Only features with PubChem CID(s)", "value": "only"}],
                        value=["only"],
                    )
                ],
            ),

            dcc.Tabs(
                id="main_tabs",
                value="tab_explore",
                children=[
                    dcc.Tab(
                        label="Explore product",
                        value="tab_explore",
                        children=[
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "12px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Final product"),
                                            dcc.Dropdown(
                                                id="product",
                                                options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]],
                                                value="Hepar",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Origin filter"),
                                            dcc.Dropdown(
                                                id="origin_filter",
                                                options=origin_options,
                                                value="All product features",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Chart type"),
                                            dcc.Dropdown(
                                                id="chart_type",
                                                options=[
                                                    {"label": "Top-N bar (intensity)", "value": "bar"},
                                                    {"label": "Scatter (Intensity vs RT)", "value": "scatter"},
                                                ],
                                                value="bar",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "180px"},
                                        children=[
                                            html.Label("Top-N (bar only)"),
                                            dcc.Slider(
                                                id="top_n",
                                                min=10,
                                                max=200,
                                                step=10,
                                                value=50,
                                                marks={10: "10", 50: "50", 100: "100", 200: "200"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Search feature ID"),
                                            dcc.Input(
                                                id="feature_search",
                                                type="text",
                                                placeholder="e.g., N_10036",
                                                style={"width": "100%"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "180px"},
                                        children=[
                                            dcc.Checklist(
                                                id="use_log",
                                                options=[{"label": "Use log10(intensity)", "value": "log"}],
                                                value=["log"],
                                                style={"marginTop": "22px"},
                                            )
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(id="main_graph", style={"height": "650px", "marginTop": "10px"}),
                            html.Div(id="stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),
                    dcc.Tab(
                        label="Q4/Q5: Missing & extra features",
                        value="tab_sets",
                        children=[
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "12px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Final product"),
                                            dcc.Dropdown(
                                                id="set_product",
                                                options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]],
                                                value="Hepar",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Question"),
                                            dcc.Dropdown(
                                                id="set_mode",
                                                options=[
                                                    {"label": "Q5: Product-only (present in product, absent in components)", "value": "product_only"},
                                                    {"label": "Q4: Component-only (present in components, absent in product)", "value": "component_only"},
                                                ],
                                                value="product_only",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Component source (Q4 only)"),
                                            dcc.Dropdown(
                                                id="set_source",
                                                options=[
                                                    {"label": "All", "value": "all"},
                                                    {"label": "Plant", "value": "Plant"},
                                                    {"label": "Animal", "value": "Animal"},
                                                    {"label": "Common (plant+animal)", "value": "Common (plant+animal)"},
                                                ],
                                                value="all",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Search feature ID"),
                                            dcc.Input(
                                                id="set_search",
                                                type="text",
                                                placeholder="e.g., N_10036",
                                                style={"width": "100%"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Max rows"),
                                            dcc.Slider(
                                                id="set_max_rows",
                                                min=50,
                                                max=1000,
                                                step=50,
                                                value=300,
                                                marks={50: "50", 300: "300", 600: "600", 1000: "1000"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(id="set_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                            dash_table.DataTable(
                                id="set_table",
                                page_size=25,
                                sort_action="native",
                                filter_action="none",
                                style_table={"overflowX": "auto"},
                                style_cell={"textAlign": "left", "padding": "6px", "fontFamily": "Arial", "fontSize": 12},
                                style_header={"fontWeight": "bold"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )       

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
    def update_graph(product: str, origin_filter: str, chart_type: str, top_n: int,
                     use_log_vals, feature_search: str, only_pubchem_vals):
        prod_df = data[product].features.copy()

        origin_sets = compute_origin_sets(
            product_df=prod_df,
            summary_df=summary_df,
            groups=groups,
            threshold=0,
        )
        allowed_ids = origin_sets.get(origin_filter, origin_sets["All product features"])

        dff = prod_df[prod_df["feature"].astype(str).isin(allowed_ids)].copy()


        # filter by feature id substring
        if feature_search and feature_search.strip():
            fs = feature_search.strip()
            dff = dff[dff["feature"].astype(str).str.contains(fs, case=False, na=False)].copy()

        # merge annotation (safe)
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

        # Global filter: keep only features with PubChem CID(s)
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in dff.columns:
                dff = dff[dff["pubchemids"].apply(has_pubchem)].copy()
            else:
                # if no pubchemids column exists after merge, nothing qualifies
                dff = dff.iloc[0:0].copy()

        use_log = "log" in (use_log_vals or [])

        if chart_type == "bar":
            fig = make_bar_topN(dff, use_log=use_log, top_n=int(top_n))
        elif chart_type == "scatter":
            fig = make_scatter(dff, use_log=use_log)


        stats = (
            f"{product} | {origin_filter} | shown: {len(dff):,} "
            f"| plant cols: {len(groups['plant_cols'])} | animal cols: {len(groups['animal_cols'])}"
        )
        return fig, stats

    @app.callback(
        Output("set_table", "data"),
        Output("set_table", "columns"),
        Output("set_stats", "children"),
        Input("set_product", "value"),
        Input("set_mode", "value"),
        Input("set_source", "value"),
        Input("set_search", "value"),
        Input("set_max_rows", "value"),
        Input("only_pubchem", "value"),
    )
    def update_set_table(set_product: str, set_mode: str, set_source: str, set_search: str, set_max_rows: int, only_pubchem_vals):
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