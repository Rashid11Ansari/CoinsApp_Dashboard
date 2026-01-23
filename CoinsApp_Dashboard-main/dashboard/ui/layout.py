"""Layout builder for the dashboard UI."""

from __future__ import annotations

from dash import dcc, html, dash_table


class LayoutBuilder:
    """Encapsulates Dash layout creation (encapsulation + reuse)."""

    def __init__(self, app_title: str):
        self.app_title = app_title

    def build(self, origin_options: list[dict]) -> html.Div:
        """Return the full app layout."""
        return html.Div(
            style={
                "minHeight": "100vh",
                "display": "flex",
                "backgroundColor": "#f3f4f6",
                "fontFamily": "Arial, sans-serif",
            },
            children=[
                # SIDEBAR
                html.Div(
                    id="sidebar",
                    style={
                        "flex": "0 0 260px",
                        "backgroundColor": "#f7f7f9",
                        "padding": "16px",
                        "borderRight": "1px solid #e0e0e0",
                        "display": "flex",
                        "flexDirection": "column",
                        "gap": "16px",
                    },
                    children=[
                        html.Div(
                            children=[
                                html.H2(
                                    self.app_title,
                                    style={"fontSize": "18px", "margin": "0 0 4px 0"},
                                ),
                                html.Div(
                                    "Origin-aware LC-MS dashboard",
                                    style={"fontSize": "12px", "color": "#666"},
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.Div(
                            children=[
                                html.Label("Analysis mode", style={"fontWeight": "bold"}),
                                dcc.Dropdown(
                                    id="analysis_mode",
                                    options=[
                                        {"label": "Explore product", "value": "explore"},
                                        {
                                            "label": "Q4/Q5: Missing & extra features",
                                            "value": "q4q5",
                                        },
                                        {
                                            "label": "Q6: Component contributions",
                                            "value": "q6",
                                        },
                                        {
                                            "label": "Q7: Enriched features",
                                            "value": "q7",
                                        },
                                        {
                                            "label": "Q8: Amplification vs attenuation",
                                            "value": "q8",
                                        },
                                        {
                                            "label": "Q9: Hepar vs Hepeel overlap",
                                            "value": "q9",
                                        },
                                        {
                                            "label": "Q10: Hepar vs Hepeel differential",
                                            "value": "q10",
                                        },
                                    ],
                                    value="explore",
                                    clearable=False,
                                    style={"width": "100%"},
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.Div(
                            children=[
                                dcc.Checklist(
                                    id="only_pubchem",
                                    options=[
                                        {
                                            "label": "Only features with PubChem CID(s)",
                                            "value": "only",
                                        }
                                    ],
                                    value=["only"],
                                    style={"fontSize": "13px"},
                                ),
                                html.Br(),
                                html.Div(
                                    id="sidebar_final_product_block",
                                    children=[
                                        html.Label("Final product", style={"fontWeight": "bold"}),
                                        dcc.Dropdown(
                                            id="product",
                                            options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]],
                                            value="Hepar",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                                html.Br(),
                                html.Div(
                                    id="sidebar_origin_block",
                                    children=[
                                        html.Label("Origin filter", style={"fontWeight": "bold"}),
                                        dcc.Dropdown(
                                            id="origin_filter",
                                            options=origin_options,
                                            value="All product features",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                                html.Br(),
                                html.Div(
                                    id="sidebar_search_block",
                                    children=[
                                        html.Label("Search feature ID", style={"fontWeight": "bold"}),
                                        dcc.Input(
                                            id="feature_search",
                                            type="text",
                                            placeholder="e.g., N_10036",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                ),
                            ]
                        ),
                    ],
                ),
                # MAIN CONTENT
                html.Div(
                    id="main_content",
                    style={"flex": "1 1 auto", "padding": "16px 24px"},
                    children=[
                        html.Div(
                            children=[
                                html.H2("Analysis", style={"marginBottom": "8px"}),
                                html.Div(
                                    "Use the sidebar to select an analysis mode and filters.",
                                    style={"fontSize": "13px", "color": "#666"},
                                ),
                            ]
                        ),
                        # EXPLORE PRODUCT
                        html.Div(
                            id="mode_explore",
                            children=[
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "16px",
                                        "flexWrap": "wrap",
                                        "alignItems": "center",
                                        "marginTop": "16px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Chart type"),
                                                dcc.Dropdown(
                                                    id="chart_type",
                                                    options=[
                                                        {
                                                            "label": "Top-N bar (intensity)",
                                                            "value": "bar",
                                                        },
                                                        {
                                                            "label": "Scatter (Intensity vs RT)",
                                                            "value": "scatter",
                                                        },
                                                    ],
                                                    value="bar",
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "260px"},
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
                                            style={"minWidth": "200px", "paddingTop": "18px"},
                                            children=[
                                                dcc.Checklist(
                                                    id="use_log",
                                                    options=[
                                                        {
                                                            "label": "Use log10(intensity)",
                                                            "value": "log",
                                                        }
                                                    ],
                                                    value=["log"],
                                                )
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="main_graph",
                                    style={"height": "650px", "marginTop": "10px"},
                                ),
                                html.Div(
                                    id="stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                            ],
                        ),
                        # Q4/Q5
                        html.Div(
                            id="mode_q4q5",
                            children=[
                                html.H3(
                                    "Q4/Q5: Missing & extra features",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "320px"},
                                            children=[
                                                html.Label("Question"),
                                                dcc.Dropdown(
                                                    id="set_mode",
                                                    options=[
                                                        {
                                                            "label": "Q5: Product-only (present in product, absent in components)",
                                                            "value": "product_only",
                                                        },
                                                        {
                                                            "label": "Q4: Component-only (present in components, absent in product)",
                                                            "value": "component_only",
                                                        },
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
                                                        {
                                                            "label": "Common (plant+animal)",
                                                            "value": "Common (plant+animal)",
                                                        },
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
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                        "alignItems": "center",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Chart type"),
                                                dcc.Dropdown(
                                                    id="q45_chart_type",
                                                    options=[
                                                        {"label": "Table only", "value": "none"},
                                                        {"label": "Scatter (RT vs intensity)", "value": "scatter"},
                                                    ],
                                                    value="scatter",
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q45_graph",
                                    style={"height": "450px", "marginTop": "10px"},
                                ),
                                html.Div(
                                    id="set_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                                dash_table.DataTable(
                                    id="set_table",
                                    page_size=25,
                                    sort_action="native",
                                    filter_action="none",
                                    style_table={"overflowX": "auto"},
                                    style_cell={
                                        "textAlign": "left",
                                        "padding": "6px",
                                        "fontFamily": "Arial",
                                        "fontSize": 12,
                                    },
                                    style_header={"fontWeight": "bold"},
                                ),
                            ],
                        ),
                        # Q6
                        html.Div(
                            id="mode_q6",
                            children=[
                                html.H3(
                                    "Q6: Component contributions",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Top components"),
                                                dcc.Slider(
                                                    id="q6_top_k",
                                                    min=3,
                                                    max=20,
                                                    step=1,
                                                    value=8,
                                                    marks={3: "3", 5: "5", 10: "10", 15: "15", 20: "20"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q6_contrib_graph",
                                    style={"height": "600px", "marginTop": "10px"},
                                ),
                                html.Div(
                                    id="q6_contrib_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                                html.Div(
                                    id="q6_source_breakdown",
                                    style={
                                        "marginTop": "4px",
                                        "fontSize": "13px",
                                        "color": "#555",
                                    },
                                ),
                            ],
                        ),
                        # Q7
                        html.Div(
                            id="mode_q7",
                            children=[
                                html.H3(
                                    "Q7: Enriched features",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Min component intensity"),
                                                dcc.Input(
                                                    id="q7_min_comp",
                                                    type="number",
                                                    value=0,
                                                    min=0,
                                                    step=1000,
                                                    style={"width": "100%"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Min enrichment ratio"),
                                                dcc.Slider(
                                                    id="q7_min_ratio",
                                                    min=1.0,
                                                    max=20.0,
                                                    step=0.5,
                                                    value=3.0,
                                                    marks={1: "1x", 3: "3x", 5: "5x", 10: "10x", 20: "20x"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Top-N enriched features"),
                                                dcc.Slider(
                                                    id="q7_top_n",
                                                    min=10,
                                                    max=200,
                                                    step=10,
                                                    value=50,
                                                    marks={10: "10", 50: "50", 100: "100", 200: "200"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q7_enrich_graph",
                                    style={"height": "600px", "marginTop": "10px"},
                                ),
                                html.Div(
                                    id="q7_enrich_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                            ],
                        ),
                        # Q8
                        html.Div(
                            id="mode_q8",
                            children=[
                                html.H3(
                                    "Q8: Amplification vs attenuation",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Feature search"),
                                                dcc.Input(
                                                    id="q8_feature_search",
                                                    type="text",
                                                    debounce=True,
                                                    placeholder="Search feature ID…",
                                                    style={"width": "100%"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Top-N changed features"),
                                                dcc.Slider(
                                                    id="q8_top_n",
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
                                                html.Label("Show states"),
                                                dcc.RadioItems(
                                                    id="q8_states",
                                                    options=[
                                                        {"label": "All (incl. Neutral)", "value": "All"},
                                                        {"label": "Amplified", "value": "Amplified"},
                                                        {"label": "Attenuated", "value": "Attenuated"},
                                                    ],
                                                    value="All",
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Y-axis scale"),
                                                dcc.Checklist(
                                                    id="q8_use_log",
                                                    options=[{"label": "Log scale", "value": "log"}],
                                                    value=[],
                                                    style={"marginTop": "6px"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q8_amp_graph",
                                    style={
                                        "height": "70vh",
                                        "width": "100%",
                                        "marginTop": "10px",
                                    },
                                ),
                                html.Div(
                                    id="q8_amp_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                                html.Div(
                                    id="q8_selected_feature",
                                    style={
                                        "marginTop": "6px",
                                        "fontSize": "14px",
                                        "fontWeight": "600",
                                    },
                                ),
                            ],
                        ),
                        # Q9
                        html.Div(
                            id="mode_q9",
                            children=[
                                html.H3(
                                    "Q9: Hepar vs Hepeel overlap",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Groups to show"),
                                                dcc.Checklist(
                                                    id="q9_groups",
                                                    options=[
                                                        {"label": "Hepar only", "value": "Hepar only"},
                                                        {"label": "Hepeel only", "value": "Hepeel only"},
                                                        {"label": "Shared", "value": "Shared"},
                                                    ],
                                                    value=["Hepar only", "Hepeel only", "Shared"],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q9_overlap_graph",
                                    style={"height": "400px", "marginTop": "10px"},
                                ),
                                html.Label("Scatter (feature-level)"),
                                dcc.Graph(
                                    id="q9_overlap_scatter",
                                    style={"height": "400px", "marginTop": "10px"},
                                ),
                                html.Div(
                                    id="q9_overlap_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                                dash_table.DataTable(
                                    id="q9_overlap_table",
                                    page_size=25,
                                    sort_action="native",
                                    filter_action="none",
                                    style_table={
                                        "overflowX": "auto",
                                        "marginTop": "10px",
                                        "width": "100%",
                                    },
                                    style_cell={
                                        "textAlign": "left",
                                        "padding": "6px",
                                        "fontFamily": "Arial",
                                        "fontSize": 12,
                                        "whiteSpace": "normal",
                                        "height": "auto",
                                        "lineHeight": "18px",
                                        "maxWidth": "240px",
                                    },
                                    style_header={"fontWeight": "bold"},
                                    style_data_conditional=[
                                        {
                                            "if": {"column_id": "pubchemids"},
                                            "maxWidth": "240px",
                                            "overflow": "hidden",
                                            "textOverflow": "ellipsis",
                                        }
                                    ],
                                ),
                            ],
                        ),
                        # Q10
                        html.Div(
                            id="mode_q10",
                            children=[
                                html.H3(
                                    "Q10: Hepar vs Hepeel differential",
                                    style={"marginTop": "24px"},
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "12px",
                                        "flexWrap": "wrap",
                                        "marginTop": "12px",
                                    },
                                    children=[
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Min combined product intensity"),
                                                dcc.Input(
                                                    id="q10_min_total_int",
                                                    type="number",
                                                    value=0,
                                                    min=0,
                                                    step=10000,
                                                    style={"width": "100%"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "260px"},
                                            children=[
                                        html.Label("Min |intensity difference|"),
                                                dcc.Slider(
                                            id="q10_min_abs_diff",
                                            min=0,
                                            max=20000,
                                            step=500,
                                            value=5000,
                                            marks={0: "0", 5000: "5k", 10000: "10k", 15000: "15k", 20000: "20k"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Top-N features"),
                                                dcc.Slider(
                                                    id="q10_top_n",
                                                    min=10,
                                                    max=300,
                                                    step=10,
                                                    value=100,
                                                    marks={10: "10", 50: "50", 100: "100", 200: "200", 300: "300"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"minWidth": "220px"},
                                            children=[
                                                html.Label("Direction"),
                                                dcc.Checklist(
                                                    id="q10_dirs",
                                                    options=[
                                                        {"label": "Hepar higher", "value": "Hepar higher"},
                                                        {"label": "Hepeel higher", "value": "Hepeel higher"},
                                                    ],
                                                    value=["Hepar higher", "Hepeel higher"],
                                                ),
                                            ],
                                        ),
                                html.Div(
                                    style={"minWidth": "220px"},
                                    children=[
                                        html.Label("Chart type"),
                                        dcc.Dropdown(
                                            id="q10_chart_type",
                                            options=[
                                                {"label": "Bar (current)", "value": "bar"},
                                                {"label": "Dot / volcano-like", "value": "dot"},
                                                {"label": "Stacked summary", "value": "stack"},
                                                {"label": "Sankey (driver→direction)", "value": "sankey"},
                                            ],
                                            value="bar",
                                            clearable=False,
                                            style={"width": "100%"},
                                        ),
                                    ],
                                ),
                                    ],
                                ),
                                dcc.Graph(
                                    id="q10_diff_graph",
                                    style={
                                        "height": "420px",
                                        "width": "100%",
                                        "marginTop": "10px",
                                    },
                                ),
                                html.Div(
                                    id="q10_diff_stats",
                                    style={"marginTop": "8px", "fontSize": "14px"},
                                ),
                                html.Div(
                                    id="q10_selected_feature",
                                    style={
                                        "marginTop": "6px",
                                        "fontSize": "14px",
                                        "fontWeight": "600",
                                    },
                                ),
                                dash_table.DataTable(
                                    id="q10_diff_table",
                                    page_size=25,
                                    sort_action="native",
                                    filter_action="none",
                                    style_table={
                                        "overflowX": "auto",
                                        "marginTop": "10px",
                                        "width": "100%",
                                    },
                                    style_cell={
                                        "textAlign": "left",
                                        "padding": "6px",
                                        "fontFamily": "Arial",
                                        "fontSize": 12,
                                        "whiteSpace": "normal",
                                        "height": "auto",
                                        "lineHeight": "18px",
                                        "maxWidth": "240px",
                                    },
                                    style_header={"fontWeight": "bold"},
                                    style_data_conditional=[
                                        {
                                            "if": {"column_id": "pubchemids"},
                                            "maxWidth": "240px",
                                            "overflow": "hidden",
                                            "textOverflow": "ellipsis",
                                        }
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

