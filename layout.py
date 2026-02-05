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
                            {"label": "Explore: All product features", "value": "explore::All product features"},
                            {"label": "Explore: Unique to product", "value": "explore::Unique to product"},
                            {"label": "Explore: Common (plant+animal)", "value": "explore::Common (plant+animal)"},
                            {"label": "Q3: Plant vs animal signal", "value": "q3"},
                            {"label": "Q4: Component-only", "value": "q4"},
                            {"label": "Q5: Product-only", "value": "q5"},
                            {"label": "Q8: Selective amplification/attenuation", "value": "q8"},
                        ],
                        value="explore::All product features",
                        clearable=False,
                    ),

                    # Hidden controls – driven by page_select; kept for existing callbacks
                    dcc.Dropdown(
                        id="origin_filter",
                        options=origin_options,
                        value=origin_default,
                        clearable=False,
                        style={"display": "none"},
                    ),
                    dcc.Dropdown(
                        id="q4q5_select",
                        options=[
                            {"label": "Q5: Product-only", "value": "product_only"},
                            {"label": "Q4: Component-only", "value": "component_only"},
                        ],
                        value="product_only",
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

                    # ---------- Q3 view ----------
                    html.Div(
                        id="view_q3",
                        style=HIDE,
                        children=[
                            html.H3("Q3: Plant vs animal signal", style={"marginTop": 0}),
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

                    # ---------- Q4/Q5 view ----------
                    html.Div(
                        id="view_q4q5",
                        style=HIDE,
                        children=[
                            html.H3("Q4/Q5: Missing & extra", style={"marginTop": 0}),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "360px"},
                                        children=[
                                            html.Label("Question"),
                                            dcc.Dropdown(
                                                id="set_mode",
                                                options=[
                                                    {"label": "Q5: Product-only", "value": "product_only"},
                                                    {"label": "Q4: Component-only", "value": "component_only"},
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
                                        style={"minWidth": "260px"},
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

                            # table-only horizontal scroll
                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="set_table",
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