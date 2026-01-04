
# layout.py
from __future__ import annotations

from dash import dcc, html, dash_table


def _section_title(text: str):
    return html.H3(text, style={"margin": "18px 0 8px 0"})


def build_layout(app_title: str, origin_options: list[dict]):
    """Pure layout/UI. Callbacks live in app.py."""

    return html.Div(
        style={
            "minHeight": "100vh",
            "display": "flex",
            "backgroundColor": "#f3f4f6",
            "fontFamily": "Arial, sans-serif",
        },
        children=[
            # ===== Sidebar =====
            html.Div(
                id="sidebar",
                style={
                    "flex": "0 0 280px",
                    "backgroundColor": "#f7f7f9",
                    "padding": "16px",
                    "borderRight": "1px solid #e0e0e0",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "14px",
                },
                children=[
                    html.Div(
                        children=[
                            html.H2(app_title, style={"fontSize": "18px", "margin": "0 0 4px 0"}),
                            html.Div(
                                "Origin-aware LC–MS dashboard",
                                style={"fontSize": "12px", "color": "#666"},
                            ),
                        ]
                    ),
                    html.Hr(style={"margin": "4px 0"}),
                    html.Div(
                        children=[
                            html.Label("Analysis mode", style={"fontWeight": "bold"}),
                            dcc.Dropdown(
                                id="analysis_mode",
                                options=[
                                    {"label": "Explore product", "value": "explore"},
                                    {"label": "Q4/Q5: Missing & extra features", "value": "q4q5"},
                                    {"label": "Q6: Component contributions", "value": "q6"},
                                    {"label": "Q7: Enriched features", "value": "q7"},
                                    {"label": "Q8: Amplification vs attenuation", "value": "q8"},
                                    {"label": "Q9: Hepar vs Hepeel overlap", "value": "q9"},
                                    {"label": "Q10: Hepar vs Hepeel differential", "value": "q10"},
                                ],
                                value="explore",
                                clearable=False,
                            ),
                        ]
                    ),
                    html.Hr(style={"margin": "4px 0"}),
                    dcc.Checklist(
                        id="only_pubchem",
                        options=[{"label": "Only features with PubChem CID(s)", "value": "only"}],
                        value=[],
                        style={"fontSize": "13px"},
                    ),
                    html.Div(
                        children=[
                            html.Label("Final product", style={"fontWeight": "bold"}),
                            dcc.Dropdown(
                                id="product",
                                options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]],
                                value="Hepar",
                                clearable=False,
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Label("Origin filter", style={"fontWeight": "bold"}),
                            dcc.Dropdown(
                                id="origin_filter",
                                options=origin_options,
                                value="All product features",
                                clearable=False,
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Label("Search feature ID", style={"fontWeight": "bold"}),
                            dcc.Input(
                                id="feature_search",
                                type="text",
                                placeholder="e.g., N_10036",
                                style={"width": "100%"},
                            ),
                        ]
                    ),
                ],
            ),

            # ===== Main content =====
            html.Div(
                id="main_content",
                style={"flex": "1 1 auto", "padding": "16px 24px"},
                children=[
                    html.Div(
                        children=[
                            html.H2("Analysis", style={"marginBottom": "6px"}),
                            html.Div(
                                "Use the sidebar to select an analysis mode and filters.",
                                style={"fontSize": "13px", "color": "#666"},
                            ),
                        ]
                    ),

                    # ===== Explore product =====
                    html.Div(
                        id="mode_explore",
                        children=[
                            _section_title("Explore product"),
                            html.Div(
                                style={
                                    "display": "flex",
                                    "gap": "16px",
                                    "flexWrap": "wrap",
                                    "alignItems": "center",
                                    "marginTop": "10px",
                                },
                                children=[
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
                                                options=[{"label": "Use log10(intensity)", "value": "log"}],
                                                value=["log"],
                                            )
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(id="main_graph", style={"height": "650px", "marginTop": "10px"}),
                            html.Div(id="stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ===== Q4 / Q5 =====
                    html.Div(
                        id="mode_q4q5",
                        children=[
                            _section_title("Q4/Q5: Missing & extra features"),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "10px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "360px"},
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
                                        style={"minWidth": "240px"},
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
                                            dcc.Input(id="set_search", type="text", placeholder="e.g., N_10036", style={"width": "100%"}),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "240px"},
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

                    # ===== Q6 =====
                    html.Div(
                        id="mode_q6",
                        children=[
                            _section_title("Q6: Which ingredients dominate the final product?"),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "10px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Top-K components"),
                                            dcc.Slider(
                                                id="q6_top_k",
                                                min=5,
                                                max=30,
                                                step=1,
                                                value=10,
                                                marks={5: "5", 10: "10", 20: "20", 30: "30"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(id="q6_contrib_graph", style={"height": "520px", "marginTop": "10px"}),
                            html.Div(id="q6_contrib_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                            html.Div(id="q6_source_breakdown", style={"marginTop": "6px", "fontSize": "14px"}),
                        ],
                    ),

                    # ===== Q7 =====
                    html.Div(
                        id="mode_q7",
                        children=[
                            _section_title("Q7: Which features are enriched in the final product?"),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "10px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
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
                            dcc.Graph(id="q7_graph", style={"height": "520px", "marginTop": "10px"}),
                            html.Div(id="q7_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ===== Q8 =====
                    html.Div(
                        id="mode_q8",
                        children=[
                            _section_title("Q8: Amplification vs attenuation"),
                            dcc.Graph(id="q8_graph", style={"height": "520px", "marginTop": "10px"}),
                            html.Div(id="q8_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ===== Q9 =====
                    html.Div(
                        id="mode_q9",
                        children=[
                            _section_title("Q9: Hepar vs Hepeel overlap"),
                            dcc.Graph(id="q9_graph", style={"height": "520px", "marginTop": "10px"}),
                            html.Div(id="q9_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ===== Q10 =====
                    html.Div(
                        id="mode_q10",
                        children=[
                            _section_title("Q10: Hepar vs Hepeel differential"),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "10px"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "240px"},
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
                                        style={"minWidth": "280px"},
                                        children=[
                                            html.Label("Min |log2 fold-change|"),
                                            dcc.Slider(
                                                id="q10_min_abs_log2",
                                                min=0.0,
                                                max=8.0,
                                                step=0.25,
                                                value=1.0,
                                                marks={0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 6: "6", 8: "8"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "280px"},
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
                                        style={"minWidth": "260px"},
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
                                ],
                            ),
                            dcc.Graph(id="q10_diff_graph", style={"height": "420px", "marginTop": "10px"}),
                            html.Div(id="q10_diff_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                            dash_table.DataTable(
                                id="q10_diff_table",
                                page_size=25,
                                sort_action="native",
                                filter_action="none",
                                style_table={"overflowX": "auto", "marginTop": "10px"},
                                style_cell={"textAlign": "left", "padding": "6px", "fontFamily": "Arial", "fontSize": 12},
                                style_header={"fontWeight": "bold"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )