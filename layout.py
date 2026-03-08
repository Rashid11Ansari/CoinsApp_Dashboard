from __future__ import annotations

from dash import dcc, html, dash_table


def build_layout(app_title: str, origin_options: list[dict]):
    origin_default = origin_options[0]["value"] if origin_options else None

    # helper styles
    SIDEBAR = {
        "width": "380px",
        "padding": "16px",
        "borderRight": "1px solid #ddd",
        "backgroundColor": "#fafafa",
        "boxSizing": "border-box",
        "height": "100vh",
        "position": "sticky",
        "top": "0",
        "overflowY": "auto",
    }
    MAIN = {
        "flex": "1",
        "padding": "12px",
        "overflowX": "hidden",
        "minWidth": 0,
        "boxSizing": "border-box",
    }
    HIDE = {"display": "none"}
    SHOW = {"display": "block"}

    return html.Div(
        style={
            "display": "flex",
            "minHeight": "100vh",
            "alignItems": "stretch",
            "gap": "12px",
            "maxWidth": "1650px",
            "margin": "0 auto",
            "padding": "10px",
        },
        children=[
            # ===================== LEFT SIDEBAR =====================
            html.Div(
                style=SIDEBAR,
                children=[
                    html.H3(app_title, style={"marginTop": 0}),
                    html.H4("Global filters", style={"marginBottom": "6px"}),

                    html.Label("Final product"),
                    dcc.Dropdown(
                        id="product",
                        options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]],
                        value="Hepar",
                        searchable=False,
                        clearable=False,
                    ),

                    html.Div(style={"height": "20px"}),

                    html.Label("Search feature ID (optional)"),
                    dcc.Input(
                        id="feature_search",
                        type="text",
                        placeholder="e.g., N_10036",
                        style={"width": "100%"},
                    ),

                    html.Div(style={"height": "10px"}),

                    dcc.Checklist(
                        id="only_pubchem",
                        options=[{"label": "Only features with PubChem CID(s)", "value": "only"}],
                        value=[],
                    ),

                    html.Div(style={"height": "6px"}),

                    dcc.Checklist(
                        id="global_use_log",
                        options=[{"label": "Use log10(intensity)", "value": "log"}],
                        value=["log"],
                    ),

                    html.Div(style={"height": "12px"}),

                    html.Label("Product intensity filter (global)"),
                    dcc.RangeSlider(
                        id="global_intensity_log_range",
                        min=2,
                        max=7,
                        step=0.3,
                        value=[2, 7],
                        marks={},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                    html.Div(
                        id="global_intensity_range_label",
                        style={"fontSize": "12px", "color": "#666", "marginTop": "6px"},
                    ),

                    html.Hr(),
                    html.H4("Navigation", style={"marginBottom": "6px"}),

                    html.Label("Choose view"),
                    dcc.Dropdown(
                        id="page_select",
                        options=[
                            {"label": "Explore: Shared between Hepar & Hepeel", "value": "explore::Shared between Hepar & Hepeel"},
                            {"label": "Q1: Product features & origin", "value": "q1"},
                            {"label": "Q3: Plant vs animal signal", "value": "q3"},
                            {"label": "Q4: Component-only", "value": "q4"},
                            {"label": "Q5: Product-only", "value": "q5"},
                            {"label": "Q6: Ingredient contribution", "value": "q6"},
                            {"label": "Q7: Enriched features", "value": "q7"},                           
                            {"label": "Q8: Selective amplification/attenuation", "value": "q8"},
                            {"label": "Q10: Hepar - Hepeel (plant vs animal driver)", "value": "q10"},
                        ],
                        value="explore::Shared between Hepar & Hepeel",
                        maxHeight=720,
                        searchable=False,
                        clearable=False,
                    ),

                    # Hidden controls – driven by page_select; kept for existing callbacks
                    dcc.Dropdown(
                        id="origin_filter",
                        options=origin_options,
                        value=origin_default,
                        searchable=False,
                        clearable=False,
                        style={"display": "none"},
                    ),
                ],
            ),

            # ===================== MAIN CONTENT =====================
            html.Div(
                style=MAIN,
                children=[
                    # ---------- Explore view ----------
                    html.Div(
                        id="view_explore",
                        style=SHOW,
                        children=[
                            html.H3("Explore product", style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Chart type"),
                                            dcc.Dropdown(
                                                id="chart_type",
                                                options=[
                                                    {"label": "Top-N bar (intensity)", "value": "bar"},
                                                    {"label": "Scatter (intensity vs RT)", "value": "scatter"},
                                                ],
                                                value="scatter",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
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
                                ],
                            ),
                            dcc.Graph(id="main_graph", style={"height": "650px", "marginTop": "10px"}),
                            html.Div(id="stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),
                    # ---------- Q1 view ----------
                    html.Div(
                        id="view_q1",
                        style=HIDE,
                        children=[
                            html.H3("Q1: What is in the product & where does it come from?", style={"marginTop": 0}),

                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "360px"},
                                        children=[
                                            html.Label("Origin bucket"),
                                            dcc.Dropdown(
                                                id="q1_bucket",
                                                options=[
                                                    {"label": "Plant-only", "value": "Plant-only"},
                                                    {"label": "Animal-only", "value": "Animal-only"},
                                                    {"label": "Common (plant + animal)", "value": "Common (plant+animal)"},
                                                    {"label": "Product-only (vs components)", "value": "Product-only (vs components)"},
                                                ],
                                                value="Plant-only",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Chart type"),
                                            dcc.Dropdown(
                                                id="q1_chart_type",
                                                options=[
                                                    {"label": "Top-N bar (intensity)", "value": "bar"},
                                                    {"label": "Scatter (intensity vs RT)", "value": "scatter"},
                                                ],
                                                value="scatter",
                                                clearable=False,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "220px"},
                                        children=[
                                            html.Label("Top-N (bar only)"),
                                            dcc.Slider(
                                                id="q1_top_n",
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

                            dcc.Graph(id="q1_graph", style={"height": "650px", "marginTop": "10px"}),
                            html.Div(id="q1_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ---------- Q3 view ----------
                    html.Div(
                        id="view_q3",
                        style=HIDE,
                        children=[
                            html.H3("Q3: What proportion of total signal intensity in the final product originates from plant- and animal-derived features?",
                                        style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Dominance threshold (x)"),
                                            dcc.Slider(
                                                id="q3_dom_ratio",
                                                min=1.0,
                                                max=10.0,
                                                step=0.25,
                                                value=1.5,
                                                marks={1: "1x", 1.5: "1.5x", 2: "2x", 3: "3x", 5: "5x", 10: "10x"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Include categories"),
                                            dcc.Checklist(
                                                id="q3_cats",
                                                options=[
                                                    {"label": "Plant-dominant", "value": "Plant-dominant"},
                                                    {"label": "Animal-dominant", "value": "Animal-dominant"},
                                                    {"label": "Mixed", "value": "Mixed"},
                                                    {"label": "Product-only", "value": "Product-only"},
                                                ],
                                                value=["Plant-dominant", "Animal-dominant", "Mixed"],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                style={"display": "flex", "flexDirection": "column", "gap": "14px", "marginTop": "10px"},
                                children=[
                                    html.Div(
                                        children=[
                                            html.H4("Signal proportion (answers Q3)", style={"margin": "0 0 6px 0"}),
                                            dcc.Graph(id="q3_prop_bar", style={"height": "420px"}),
                                        ]
                                    ),
                                    html.Div(
                                        children=[
                                            html.H4("Feature view (Intensity vs RT)", style={"margin": "0 0 6px 0"}),
                                            dcc.Graph(id="q3_scatter", style={"height": "520px"}),
                                        ]
                                    ),
                                ],
                            ),
                            html.Div(id="q3_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                        ],
                    ),

                    # ---------- Q4 view ----------
                    html.Div(
                        id="view_q4",
                        style=HIDE,
                        children=[
                            html.H3("Q4: Component-only features (in components, missing in product)", style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "240px"},
                                        children=[
                                            html.Label("Component source"),
                                            dcc.Dropdown(
                                                id="q4_source",
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
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Presence threshold (log10 component intensity)"),
                                            dcc.Slider(
                                                id="q4_presence_log_thr",
                                                min=-2,
                                                max=6,
                                                step=0.25,
                                                value=0,
                                                marks={-2: "1e-2", 0: "1", 2: "1e2", 4: "1e4", 6: "1e6"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Max rows"),
                                            dcc.Slider(
                                                id="q4_max_rows",
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
                            html.Div(id="q4_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q4_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ---------- Q5 view ----------
                    html.Div(
                        id="view_q5",
                        style=HIDE,
                        children=[
                            html.H3("Q5: Product-only features (in product, missing in components)", style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Max rows"),
                                            dcc.Slider(
                                                id="q5_max_rows",
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
                            html.Div(id="q5_stats", style={"marginTop": "8px", "fontSize": "14px"}),
                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q5_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ---------- Q6 view ----------
                    html.Div(
                        id="view_q6",
                        style=HIDE,
                        children=[
                            html.H3("Q6: Which ingredients dominate the final product?", style={"marginTop": 0}),

                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Feature ID (optional)"),
                                            dcc.Input(
                                                id="q6_feature_id",
                                                type="text",
                                                placeholder="e.g., P_15781",
                                                debounce=True,
                                                style={"width": "100%"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Top ingredients"),
                                            dcc.Slider(
                                                id="q6_top_n",
                                                min=5,
                                                max=40,
                                                step=1,
                                                value=15,
                                                marks={5: "5", 15: "15", 25: "25", 40: "40"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            html.Div(id="q6_stats", style={"marginTop": "10px", "fontSize": "14px"}),

                            dcc.Graph(id="q6_dom_bar", style={"height": "360px"}),
                            dcc.Graph(id="q6_contrib_bar", style={"height": "420px"}),

                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q6_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ---------- Q7 view ----------
                    html.Div(
                        id="view_q7",
                        style=HIDE,
                        children=[
                            html.H3("Q7: Enriched features (Final − sum(ingredients))", style={"marginTop": 0}),

                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Top enriched features"),
                                            dcc.Slider(
                                                id="q7_top_n",
                                                min=25,
                                                max=1000,
                                                step=25,
                                                value=300,
                                                marks={25: "25", 100: "100", 300: "300", 600: "600", 1000: "1000"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            html.Div(id="q7_stats", style={"marginTop": "10px", "fontSize": "14px"}),

                            dcc.Graph(id="q7_graph", style={"height": "420px"}),

                            html.Div(
                                id="q7_pubchem",
                                style={
                                    "marginTop": "10px",
                                    "marginBottom": "10px",
                                    "fontSize": "14px",
                                    "fontWeight": "bold",
                                    "color": "black",
                                    "backgroundColor": "#f5f5f5",
                                    "padding": "10px",
                                    "borderRadius": "5px",
                                },
                                children="Click a feature bar to see PubChem ID(s)",
                            ),

                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q7_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ---------- Q8 view ----------
                    html.Div(
                        id="view_q8",
                        style=HIDE,
                        children=[
                            html.H3("Q8: Selective amplification & attenuation", style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "300px"},
                                        children=[
                                            html.Label("Amplification threshold (x)"),
                                            dcc.Slider(
                                                id="q8_amp_threshold",
                                                min=1.0,
                                                max=10.0,
                                                step=0.25,
                                                value=3.0,
                                                marks={1: "1x", 2: "2x", 3: "3x", 5: "5x", 10: "10x"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Show categories"),
                                            dcc.Checklist(
                                                id="q8_cats",
                                                options=[
                                                    {"label": "Selective amplification", "value": "selective_amplification"},
                                                    {"label": "Selective attenuation", "value": "selective_attenuation"},
                                                ],
                                                value=["selective_amplification", "selective_attenuation"],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(id="q8_stats", style={"marginTop": "10px", "fontSize": "14px"}),
                            dcc.Graph(id="q8_hist", style={"height": "320px"}),

                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q8_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        tooltip_delay=0,
                                        tooltip_duration=None,
                                        hidden_columns=["hepar_comp_max", "hepeel_comp_max"],
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ---------- Q10 view ----------
                    html.Div(
                        id="view_q10",
                        style=HIDE,
                        children=[
                            html.H3("Q10: (Q10  )", style={"marginTop": 0}),

                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Top rows"),
                                            dcc.Slider(
                                                id="q10_top_n",
                                                min=25,
                                                max=1000,
                                                step=25,
                                                value=300,
                                                marks={25: "25", 100: "100", 300: "300", 600: "600", 1000: "1000"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            html.Div(id="q10_stats", style={"marginTop": "10px", "fontSize": "14px"}),

                            dcc.Graph(id="q10_graph", style={"height": "420px"}),
                            # Move threshold slider between the two graphs
                            html.Div(
                                style={"minWidth": "320px"},
                                children=[
                                    html.Label("Significance threshold (log10 |Hepar_final − Hepeel_final|)"),
                                    dcc.Slider(
                                        id="q10_diff_log_thr",
                                        min=-2,
                                        max=8,
                                        step=0.25,
                                        value=0,  # 10^0 = 1
                                        marks={-2: "1e-2", 0: "1", 2: "1e2", 4: "1e4", 6: "1e6", 8: "1e8"},
                                    ),
                                ],
                            ),
                            dcc.Graph(id="q10_breakdown", style={"height": "320px"}),
                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q10_table",
                                        page_size=25,
                                        sort_action="native",
                                        filter_action="none",
                                        style_table={"minWidth": "100%"},
                                        style_cell={
                                            "textAlign": "left",
                                            "padding": "6px",
                                            "fontFamily": "Arial",
                                            "fontSize": 12,
                                            "whiteSpace": "nowrap",
                                        },
                                        style_header={"fontWeight": "bold"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )