"""Dash callback wiring separated from the main app entrypoint."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, html

from dashboard.analysis.plots import PlotFactory
from dashboard.analysis.queries import QueryRegistry
from dashboard.data.context import DataContext
from dashboard.utils.identifiers import has_pubchem


class CallbackBinder:
    """Registers all Dash callbacks (encapsulation + clearer responsibilities)."""

    def __init__(self, app, data_ctx: DataContext, queries: QueryRegistry):
        self.app = app
        self.data_ctx = data_ctx
        self.queries = queries
        self.summary_df = data_ctx.summary
        self.groups = data_ctx.groups

    def register_all(self) -> None:
        self._register_mode_visibility()
        self._register_sidebar_visibility()
        self._register_main_graph()
        self._register_q6()
        self._register_q7()
        self._register_q8()
        self._register_q9()
        self._register_q10()
        self._register_q4_q5()

    # ---- small helpers ----
    def _apply_pubchem_filter(self, df, only_vals):
        return self.queries.filter_pubchem(df, only_vals)

    # ---- callbacks ----
    def _register_mode_visibility(self):
        @self.app.callback(
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

    def _register_sidebar_visibility(self):
        @self.app.callback(
            Output("sidebar_final_product_block", "style"),
            Output("sidebar_origin_block", "style"),
            Output("sidebar_search_block", "style"),
            Input("analysis_mode", "value"),
        )
        def _toggle_final_product(mode):
            final_style = {"display": "none"} if mode in ("q9", "q10") else {"display": "block"}
            aux_style = {"display": "block"} if mode == "explore" else {"display": "none"}
            return final_style, aux_style, aux_style

    def _register_main_graph(self):
        @self.app.callback(
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
            prod_df = self.data_ctx.product(product).copy()
            origin_sets = self.queries.origin_sets.run(prod_df)
            allowed_ids = origin_sets.get(origin_filter, origin_sets["All product features"])

            dff = prod_df[prod_df["feature"].astype(str).isin(allowed_ids)].copy()

            if feature_search and feature_search.strip():
                fs = feature_search.strip()
                dff = dff[dff["feature"].astype(str).str.contains(fs, case=False, na=False)].copy()

            annot_cols = [
                c
                for c in [
                    "feature",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                    "NPC.pathway",
                ]
                if c in self.summary_df.columns
            ]
            if annot_cols:
                annot = self.summary_df[annot_cols].drop_duplicates("feature")
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

            dff = self._apply_pubchem_filter(dff, only_pubchem_vals)
            use_log = "log" in (use_log_vals or [])

            if chart_type == "bar":
                fig = PlotFactory.make_bar_topN(dff, use_log=use_log, top_n=int(top_n))
            else:
                fig = PlotFactory.make_scatter(dff, use_log=use_log)

            stats = (
                f"{product} | {origin_filter} | shown: {len(dff):,} "
                f"| plant cols: {len(self.groups['plant_cols'])} | animal cols: {len(self.groups['animal_cols'])}"
            )
            return fig, stats

    def _register_q6(self):
        @self.app.callback(
            Output("q6_contrib_graph", "figure"),
            Output("q6_contrib_stats", "children"),
            Output("q6_source_breakdown", "children"),
            Input("product", "value"),
            Input("q6_top_k", "value"),
        )
        def update_q6_contrib(product: str, q6_top_k: int):
            prod_key = product or "Hepar"
            try:
                top_k = int(q6_top_k) if q6_top_k is not None else 8
            except (TypeError, ValueError):
                top_k = 8

            prod_df = self.data_ctx.product(prod_key)
            contrib_df = self.queries.component_contrib.run(prod_df)

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
            plant_frac = contrib_df.loc[contrib_df["source"] == "Plant", "fraction_of_total"].sum()
            animal_frac = contrib_df.loc[contrib_df["source"] == "Animal", "fraction_of_total"].sum()
            other_frac = max(0.0, 1.0 - plant_frac - animal_frac)

            parts = [f"Plant: {plant_frac:.1%}", f"Animal: {animal_frac:.1%}"]
            if other_frac > 0.005:
                parts.append(f"Other: {other_frac:.1%}")
            breakdown = "Total product intensity by source (all components) → " + " | ".join(parts)

            return fig, stats, breakdown

    def _register_q7(self):
        @self.app.callback(
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
            prod_df = self.data_ctx.product(q7_product)
            min_comp = float(q7_min_comp or 0.0)
            df = self.queries.enrichment.run(
                prod_df,
                min_component_intensity=min_comp,
            )

            df = self._apply_pubchem_filter(df, only_pubchem_vals)

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

    def _register_q8(self):
        @self.app.callback(
            Output("q8_amp_graph", "figure"),
            Output("q8_amp_stats", "children"),
            Output("q8_selected_feature", "children"),
            Input("product", "value"),
            Input("q8_feature_search", "value"),
            Input("q8_top_n", "value"),
            Input("q8_states", "value"),
            Input("only_pubchem", "value"),
            Input("q8_use_log", "value"),
            Input("q8_amp_graph", "clickData"),
        )
        def update_q8_amp(
            q8_product: str,
            q8_feature_search,
            q8_top_n: int,
            q8_states,
            only_pubchem_vals,
            q8_use_log,
            q8_click,
        ):
            AMP_RATIO = 3.0
            ATT_RATIO = 3.0
            COLOR_MAP = {"Amplified": "#1f77b4", "Attenuated": "#d62728", "Neutral": "#7f7f7f"}

            prod_df = self.data_ctx.product(q8_product)
            df = self.queries.amplification.run(
                prod_df,
                min_component_intensity=0.0,
                amp_ratio=AMP_RATIO,
                att_ratio=ATT_RATIO,
            )

            if q8_feature_search and str(q8_feature_search).strip():
                term = str(q8_feature_search).strip()
                df = df[df["feature"].astype(str).str.contains(term, case=False, na=False)].copy()

            df = self._apply_pubchem_filter(df, only_pubchem_vals)

            if df.empty:
                fig = px.bar(title="No features with sufficient component signal")
                stats = f"{q8_product}: no features after component-intensity filter."
                return fig, stats, ""

            state_val = q8_states or "All"
            if state_val != "All":
                df = df[df["state"] == state_val].copy()

            if df.empty:
                fig = px.bar(title="No amplified/attenuated features for current thresholds")
                stats = (
                    f"{q8_product}: 0 features classified as "
                    f"{state_val if state_val != 'All' else 'Amplified/Attenuated/Neutral'} "
                    f"(amp >= {AMP_RATIO:.1f}x, att <= 1/{ATT_RATIO:.1f}x)."
                )
                return fig, stats, ""

            top_n_int = int(q8_top_n)

            if state_val == "All":
                parts = []
                for st in ["Amplified", "Attenuated", "Neutral"]:
                    subset = df[df["state"] == st].head(top_n_int)
                    if not subset.empty:
                        parts.append(subset)
                if parts:
                    dff = (
                        pd.concat(parts)
                        .sort_values("order_value", ascending=False)
                        .reset_index(drop=True)
                    )
                else:
                    dff = df.head(top_n_int)
            else:
                dff = df.head(top_n_int)
            fig = px.bar(
                dff,
                x="feature",
                y="enrichment_ratio",
                color="state",
                category_orders={"state": ["Amplified", "Attenuated", "Neutral"]},
                color_discrete_map=COLOR_MAP,
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
                autosize=True,
            )
            if q8_use_log and "log" in q8_use_log:
                fig.update_yaxes(type="log", rangemode="nonnegative", minexponent=1)
            else:
                fig.update_yaxes(type="linear")

            selected_feature = None
            if q8_click and "points" in q8_click and q8_click["points"]:
                selected_feature = q8_click["points"][0].get("x")

            # Apply outline only to the selected bar (per-trace to avoid bleed to other states).
            line_widths_by_state: dict[str, list[int]] = {}
            for state in COLOR_MAP:
                feats = dff.loc[dff["state"] == state, "feature"]
                line_widths_by_state[state] = [3 if f == selected_feature else 0 for f in feats]

            for trace in fig.data:
                state_name = trace.name
                widths = line_widths_by_state.get(state_name)
                if widths is not None:
                    trace.marker.line.color = "#111"
                    trace.marker.line.width = widths

            # Ensure legend always shows all three states (even if not present in data).
            present_states = set(dff["state"].unique())
            for state in ["Amplified", "Attenuated", "Neutral"]:
                if state not in present_states:
                    fig.add_trace(
                        go.Scatter(
                            x=[None],
                            y=[None],
                            mode="markers",
                            marker=dict(color=COLOR_MAP[state], symbol="square", size=10),
                            name=state,
                            showlegend=True,
                            legendgroup=state,
                            hoverinfo="skip",
                        )
                    )

            selected_label = ""
            if selected_feature and selected_feature in dff["feature"].values:
                sel_state = dff.loc[dff["feature"] == selected_feature, "state"].iloc[0]
                point = (q8_click or {}).get("points", [{}])[0]
                cd = point.get("customdata") or []
                # hover_data order defines customdata order
                (intensity, max_comp, source, name, formula, pubchemids, *_) = (
                    list(cd) + [None] * 6
                )
                enr = point.get("y", None)
                # truncate very long PubChem lists to avoid layout overflow
                def fmt_pubchem(ids):
                    if not ids:
                        return ""
                    parts = str(ids).replace(",", ";").split(";")
                    parts = [p.strip() for p in parts if p.strip()]
                    if not parts:
                        return ""
                    head = parts[:5]
                    more = len(parts) - len(head)
                    return "; ".join(head) + (f" (+{more} more)" if more > 0 else "")

                selected_label = html.Div(
                    [
                        html.Div(
                            f"{selected_feature}",
                            style={"fontWeight": "600", "marginBottom": "4px"},
                        ),
                        html.Div(
                            f"State: {sel_state}",
                            style={"color": COLOR_MAP.get(sel_state, "#111")},
                        ),
                        html.Div(
                            f"Enrichment (product / max component): "
                            f"{enr:.3g}" if enr is not None else "Enrichment: n/a"
                        ),
                        html.Div(
                            f"Product intensity: {intensity}"
                            if intensity is not None
                            else ""
                        ),
                        html.Div(
                            f"Max component intensity: {max_comp}"
                            if max_comp is not None
                            else ""
                        ),
                        html.Div(f"Source: {source}" if source else ""),
                        html.Div(f"Name: {name}" if name else ""),
                        html.Div(f"Formula: {formula}" if formula else ""),
                        html.Div(
                            f"PubChem IDs: {fmt_pubchem(pubchemids)}"
                            if pubchemids
                            else ""
                        ),
                    ],
                    style={
                        "marginTop": "6px",
                        "lineHeight": "20px",
                        "maxHeight": "140px",
                        "overflow": "auto",
                        "padding": "6px 0",
                    },
                )

            n_amp = int((dff["state"] == "Amplified").sum())
            n_att = int((dff["state"] == "Attenuated").sum())
            n_neu = int((dff["state"] == "Neutral").sum()) if "Neutral" in dff["state"].values else 0
            stats = (
                f"{q8_product} | shown features: {len(dff):,} "
                f"(Amplified: {n_amp}, Attenuated: {n_att}, Neutral: {n_neu}) | "
                f"amp >= {AMP_RATIO:.1f}x, att <= 1/{ATT_RATIO:.1f}x"
            )
            return fig, stats, selected_label

    def _register_q9(self):
        @self.app.callback(
            Output("q9_overlap_graph", "figure"),
            Output("q9_overlap_table", "data"),
            Output("q9_overlap_table", "columns"),
            Output("q9_overlap_stats", "children"),
            Output("q9_overlap_scatter", "figure"),
            Input("q9_groups", "value"),
            Input("only_pubchem", "value"),
            Input("q9_overlap_graph", "clickData"),
        )
        def update_q9_overlap(
            q9_groups, only_pubchem_vals, q9_click
        ):
            hepar_df = self.data_ctx.product("Hepar")
            hepeel_df = self.data_ctx.product("Hepeel")
            df = self.queries.product_overlap.run(hepar_df, hepeel_df)

            if df.empty:
                fig = px.bar(title="No overlap data available")
                empty_columns = [{"name": c, "id": c} for c in df.columns]
                return fig, [], empty_columns, "No overlap data available."

            df = self._apply_pubchem_filter(df, only_pubchem_vals)

            selected_groups = set(q9_groups or ["Hepar only", "Hepeel only", "Shared"])
            df = df[df["group"].isin(selected_groups)].copy()

            if df.empty:
                fig = px.bar(title="No features in selected groups")
                empty_columns = [{"name": c, "id": c} for c in df.columns]
                stats = "No features for selected groups and filters."
                return fig, [], empty_columns, stats

            for col in ["Hepar_intensity", "Hepeel_intensity"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            df["combined_intensity"] = df.get("Hepar_intensity", 0) + df.get("Hepeel_intensity", 0)

            desired_order = ["Hepar only", "Hepeel only", "Shared"]
            count_series = df.groupby("group")["feature"].nunique()
            count_df = (
                count_series.reindex(desired_order, fill_value=0)
                .reset_index()
                .rename(columns={"index": "group", "feature": "n_features"})
            )
            fig = px.bar(
                count_df,
                x="group",
                y="n_features",
                labels={"group": "Group", "n_features": "Number of features"},
                title="Hepar vs Hepeel: feature counts per group",
            )
            fig.update_layout(
                margin=dict(l=20, r=20, t=40, b=40),
                bargap=0.25,
                bargroupgap=0.05,
                width=600,
                height=320,
            )
            # Highlight selected bar (click)
            selected_group = None
            if q9_click and "points" in q9_click and q9_click["points"]:
                selected_group = q9_click["points"][0].get("x")
            widths = [3 if g == selected_group else 0 for g in count_df["group"]]
            fig.update_traces(marker_line_color="#111", marker_line_width=widths)

            # Show all selected features in the table (no Top-N cap for table data).
            dff = df.sort_values("combined_intensity", ascending=False)
            columns = [{"name": c, "id": c} for c in dff.columns if c != "combined_intensity"]
            stats = (
                f"Features shown: {len(dff):,} "
                f"(Hepar only: {int((df['group'] == 'Hepar only').sum())}, "
                f"Hepeel only: {int((df['group'] == 'Hepeel only').sum())}, "
                f"Shared: {int((df['group'] == 'Shared').sum())})"
            )
            # Scatter: feature-level view
            scatter = px.scatter(
                dff,
                x="Hepar_intensity",
                y="Hepeel_intensity",
                color="group",
                labels={
                    "Hepar_intensity": "Hepar intensity",
                    "Hepeel_intensity": "Hepeel intensity",
                    "group": "Group",
                },
                hover_data=[
                    "feature",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                ],
            )
            scatter.update_layout(
                margin=dict(l=20, r=20, t=40, b=60),
                legend_title="Group",
            )

            return fig, dff.to_dict("records"), columns, stats, scatter

    def _register_q10(self):
        @self.app.callback(
            Output("q10_diff_graph", "figure"),
            Output("q10_diff_table", "data"),
            Output("q10_diff_table", "columns"),
            Output("q10_diff_stats", "children"),
            Output("q10_selected_feature", "children"),
            Input("q10_min_total_int", "value"),
            Input("q10_min_abs_diff", "value"),
            Input("q10_top_n", "value"),
            Input("q10_dirs", "value"),
            Input("only_pubchem", "value"),
            Input("q10_chart_type", "value"),
            Input("q10_diff_graph", "clickData"),
        )
        def update_q10_diff(
            q10_min_total_int,
            q10_min_abs_diff: float,
            q10_top_n: int,
            q10_dirs,
            only_pubchem_vals,
            q10_chart_type,
            q10_click,
        ):
            hepar_df = self.data_ctx.product("Hepar")
            hepeel_df = self.data_ctx.product("Hepeel")

            # --- New logic: use raw intensity difference (Hepar - Hepeel) and plant/suis sums ---
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

            df[["Hepar_intensity", "Hepeel_intensity"]] = df[["Hepar_intensity", "Hepeel_intensity"]].fillna(0.0)
            df["total_intensity"] = df["Hepar_intensity"] + df["Hepeel_intensity"]

            min_total = float(q10_min_total_int or 0.0)
            if min_total > 0:
                df = df[df["total_intensity"] >= min_total].copy()
                if df.empty:
                    fig = px.bar(title="No features above combined intensity threshold")
                    empty_columns = [{"name": c, "id": c} for c in df.columns]
                    return fig, [], empty_columns, "No features above combined intensity threshold.", ""

            df["intensity_diff"] = df["Hepar_intensity"] - df["Hepeel_intensity"]
            min_diff = float(q10_min_abs_diff or 0.0)
            df = df[df["intensity_diff"].abs() >= min_diff].copy()
            if df.empty:
                fig = px.bar(title="No features above intensity difference threshold")
                empty_columns = [{"name": c, "id": c} for c in df.columns]
                return fig, [], empty_columns, "No features above intensity difference threshold.", ""

            def _direction(v: float) -> str:
                if v > 0:
                    return "Hepar higher"
                if v < 0:
                    return "Hepeel higher"
                return "Similar"

            df["direction"] = df["intensity_diff"].apply(_direction)

            # Plant vs. suis sums (Hepar component columns)
            plant_cols = [
                "Avena.sativa",
                "Chelidonium.majus",
                "Cinchona.pubescens",
                "Cynara.scolymus",
                "Lycopodium.clavatum",
                "Silybum.marianum.",
                "Taraxacum.officinale",
                "Veratrum.album",
            ]
            suis_cols = [
                "Colon.Suis.D4",
                "Duodenum.Suis.D4",
                "Hepar.Suis.D4",
                "Pankreas.Suis.D4",
                "Thymus.Suis.D4",
                "Vesica.Fellea.Suis.D4",
            ]

            comp_agg = (
                self.summary_df[["feature"] + plant_cols + suis_cols]
                .drop_duplicates("feature")
                .set_index("feature")
            )
            comp_agg = comp_agg.reindex(df.index).fillna(0.0)
            plant_sum = comp_agg[plant_cols].sum(axis=1)
            suis_sum = comp_agg[suis_cols].sum(axis=1)

            def _detail(row, cols):
                items = []
                for c in cols:
                    v = row.get(c, 0.0)
                    try:
                        v_float = float(v)
                    except Exception:
                        v_float = 0.0
                    if v_float and v_float != 0.0:
                        items.append((c, v_float))
                items = sorted(items, key=lambda x: x[1], reverse=True)[:7]
                return "; ".join([f"{k}={int(v) if v.is_integer() else round(v,2)}" for k, v in items])

            df["plant_sum"] = plant_sum
            df["suis_sum"] = suis_sum
            df["plant_detail"] = [_detail(comp_agg.loc[idx], plant_cols) for idx in comp_agg.index]
            df["suis_detail"] = [_detail(comp_agg.loc[idx], suis_cols) for idx in comp_agg.index]
            df["plant_minus_suis"] = df["plant_sum"] - df["suis_sum"]

            def _driver(p, a) -> str:
                if p <= 0 and a <= 0:
                    return "Unknown"
                if p > a * 1.5:
                    return "Plant-dominated"
                if a > p * 1.5:
                    return "Animal-dominated"
                return "Mixed"

            df["driver"] = [_driver(p, a) for p, a in zip(df["plant_sum"], df["suis_sum"])]

            dirs = set(q10_dirs or ["Hepar higher", "Hepeel higher"])
            df = df[df["direction"].isin(dirs)].copy()
            if df.empty:
                fig = px.bar(title="No features for selected directions")
                empty_columns = [{"name": c, "id": c} for c in df.columns]
                stats = "No features for selected directions."
                return fig, [], empty_columns, stats, ""

            df = df.sort_values("intensity_diff", ascending=False)
            dff = df.head(int(q10_top_n or 100))

            # choose chart type
            chart = q10_chart_type or "bar"
            if chart == "dot":
                fig = px.scatter(
                    dff,
                    x="intensity_diff",
                    y="total_intensity",
                    color="driver",
                    symbol="direction",
                    custom_data=["feature"],
                    hover_data=[
                        "Hepar_intensity",
                        "Hepeel_intensity",
                        "direction",
                        "plant_sum",
                        "suis_sum",
                        "plant_minus_suis",
                        "name",
                        "molecularFormula",
                        "pubchemids",
                    ],
                    labels={
                        "intensity_diff": "Hepar - Hepeel",
                        "total_intensity": "Total intensity",
                        "driver": "Driver",
                    },
                )
                fig.update_layout(
                    autosize=True,
                    height=380,
                    margin=dict(l=20, r=20, t=40, b=60),
                    dragmode=False,
                    xaxis=dict(tickfont=dict(size=10), zeroline=True, zerolinecolor="rgba(150,150,150,0.6)"),
                    yaxis=dict(tickfont=dict(size=10)),
                )
                selected_feature = None
                if q10_click and "points" in q10_click and q10_click["points"]:
                    selected_feature = (q10_click["points"][0].get("customdata") or [None])[0]
                # we won't outline on scatter for simplicity
            elif chart == "stack":
                summary = (
                    dff.groupby(["direction", "driver"])["feature"]
                    .nunique()
                    .reset_index(name="n_features")
                )
                fig = px.bar(
                    summary,
                    x="direction",
                    y="n_features",
                    color="driver",
                    barmode="stack",
                    labels={
                        "direction": "Direction",
                        "n_features": "# features",
                        "driver": "Driver",
                    },
                )
                fig.update_layout(
                    autosize=True,
                    height=320,
                    margin=dict(l=20, r=20, t=40, b=60),
                )
            elif chart == "sankey":
                # Build Sankey from driver -> direction
                summary = (
                    dff.groupby(["driver", "direction"])["feature"]
                    .nunique()
                    .reset_index(name="n_features")
                )
                drivers = summary["driver"].unique().tolist()
                directions = summary["direction"].unique().tolist()
                labels = drivers + directions
                src = []
                tgt = []
                vals = []
                for _, row in summary.iterrows():
                    src.append(labels.index(row["driver"]))
                    tgt.append(labels.index(row["direction"]))
                    vals.append(row["n_features"])
                fig = go.Figure(
                    data=[
                        go.Sankey(
                            arrangement="snap",
                            node=dict(label=labels, pad=15, thickness=15),
                            link=dict(source=src, target=tgt, value=vals),
                        )
                    ]
                )
                fig.update_layout(
                    autosize=True,
                    height=360,
                    margin=dict(l=20, r=20, t=40, b=60),
                )
            else:
                # default bar
                fig = px.bar(
                    dff,
                    x="feature",
                    y="intensity_diff",
                    color="driver",
                    hover_data=[
                        "Hepar_intensity",
                        "Hepeel_intensity",
                        "direction",
                        "plant_sum",
                        "suis_sum",
                        "plant_minus_suis",
                        "name",
                        "molecularFormula",
                        "pubchemids",
                    ],
                    labels={
                        "feature": "Feature ID",
                        "intensity_diff": "Hepar - Hepeel",
                        "driver": "Driver",
                    },
                )
                fig.update_layout(
                    autosize=True,
                    height=380,
                    margin=dict(l=20, r=20, t=40, b=60),
                    dragmode=False,
                    xaxis=dict(
                        tickangle=45,
                        tickfont=dict(size=10),
                    ),
                    yaxis=dict(tickfont=dict(size=10)),
                    shapes=[
                        dict(
                            type="line",
                            x0=-0.5,
                            x1=len(dff) - 0.5,
                            y0=0,
                            y1=0,
                            line=dict(color="rgba(150,150,150,0.6)", width=1, dash="dash"),
                        )
                    ],
                )
                # highlight selected bar
                selected_feature = None
                if q10_click and "points" in q10_click and q10_click["points"]:
                    selected_feature = q10_click["points"][0].get("x")
                line_widths = [3 if f == selected_feature else 0 for f in dff["feature"]]
                fig.update_traces(marker_line_color="#111", marker_line_width=line_widths)

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
                f"| min |intensity diff|: {min_diff:.1f}"
            )
            # Selected feature details
            selected_feature = None
            if q10_click and "points" in q10_click and q10_click["points"]:
                point = q10_click["points"][0]
                selected_feature = point.get("x") or (
                    (point.get("customdata") or [None])[0] if "customdata" in point else None
                )
            detail = ""
            if selected_feature and selected_feature in dff["feature"].values:
                row = dff.loc[dff["feature"] == selected_feature].iloc[0]
                def fmt(v):
                    try:
                        return f"{float(v):,.3f}"
                    except Exception:
                        return str(v)
                pubchem = row.get("pubchemids", "")
                detail = html.Div(
                    [
                        html.Div(f"{selected_feature}", style={"fontWeight": "600", "marginBottom": "4px"}),
                        html.Div(f"Direction: {row.get('direction','')}"),
                        html.Div(f"Driver: {row.get('driver','')}"),
                        html.Div(f"log2FC (Hepar/Hepeel): {fmt(row.get('log2_fc',''))}"),
                        html.Div(f"Hepar intensity: {fmt(row.get('Hepar_intensity',''))}"),
                        html.Div(f"Hepeel intensity: {fmt(row.get('Hepeel_intensity',''))}"),
                        html.Div(f"Plant sum: {fmt(row.get('plant_sum',''))}"),
                        html.Div(f"Animal sum: {fmt(row.get('animal_sum',''))}"),
                        html.Div(f"Plant detail: {row.get('plant_detail','')}"),
                        html.Div(f"Animal detail: {row.get('animal_detail','')}"),
                        html.Div(f"Name: {row.get('name','')}"),
                        html.Div(f"Formula: {row.get('molecularFormula','')}"),
                        html.Div(f"PubChem IDs: {pubchem}"),
                    ],
                    style={"marginTop": "6px", "lineHeight": "18px"},
                )

            return fig, dff.to_dict("records"), columns, stats, detail

    def _register_q4_q5(self):
        @self.app.callback(
            Output("q45_graph", "figure"),
            Output("set_table", "data"),
            Output("set_table", "columns"),
            Output("set_stats", "children"),
            Input("product", "value"),
            Input("set_mode", "value"),
            Input("set_source", "value"),
            Input("set_search", "value"),
            Input("set_max_rows", "value"),
            Input("only_pubchem", "value"),
            Input("q45_chart_type", "value"),
        )
        def update_set_table(
            set_product: str,
            set_mode: str,
            set_source: str,
            set_search: str,
            set_max_rows: int,
            only_pubchem_vals,
            q45_chart_type: str,
        ):
            prod_df = self.data_ctx.product(set_product)
            prod_ids = set(prod_df["feature"].astype(str).dropna())

            if set_mode == "product_only":
                df = self.queries.product_only.run(prod_df)
                title = "Q5: Product-only features"
            else:
                df = self.queries.component_only.run(prod_ids)
                title = "Q4: Component-only features"
                if set_source != "all" and "source" in df.columns:
                    df = df[df["source"] == set_source]

            df = self._apply_pubchem_filter(df, only_pubchem_vals)

            if set_search and str(set_search).strip():
                s = str(set_search).strip()
                df = df[df["feature"].astype(str).str.contains(s, case=False, na=False)]

            df = df.head(int(set_max_rows))

            if q45_chart_type == "scatter" and "Average.Rt.min." in df.columns:
                if "intensity" in df.columns:
                    ycol = "intensity"
                elif "max_component_intensity" in df.columns:
                    ycol = "max_component_intensity"
                else:
                    ycol = None

                if ycol is not None:
                    hover_cols = [
                        c
                        for c in [
                            "feature",
                            ycol,
                            "Average.Mz",
                            "name",
                            "molecularFormula",
                            "pubchemids",
                            "source",
                        ]
                        if c in df.columns
                    ]
                    fig = px.scatter(
                        df,
                        x="Average.Rt.min.",
                        y=ycol,
                        color="source" if "source" in df.columns else None,
                        hover_data=hover_cols,
                        labels={
                            "Average.Rt.min.": "RT (min)",
                            ycol: "intensity",
                        },
                        title=f"{title} – RT vs intensity",
                    )
                    fig.update_layout(
                        margin=dict(l=20, r=20, t=40, b=60),
                    )
                else:
                    fig = px.bar(title="No numeric intensity column for scatter")
            else:
                fig = px.bar(title="Scatter disabled (table only)")

            columns = [{"name": c, "id": c} for c in df.columns]
            stats = f"{title} | rows shown: {len(df):,} | product: {set_product}"
            return fig, df.to_dict("records"), columns, stats

