from __future__ import annotations

from dash import dcc, html, dash_table


def build_layout(app_title: str, origin_options: list[dict]):
    origin_default = origin_options[0]["value"] if origin_options else None

    SIDEBAR = {
        "width": "360px",
        "padding": "16px",
        "borderRight": "1px solid #e2e8f0",
        "backgroundColor": "#f8fafc",
        "boxSizing": "border-box",
        "height": "100vh",
        "position": "sticky",
        "top": "0",
        "overflowY": "auto",
    }
    MAIN = {"flex": "1", "padding": "12px", "overflowX": "hidden", "minWidth": 0, "boxSizing": "border-box"}
    HIDE = {"display": "none"}
    SHOW = {"display": "block"}

    return html.Div(
        id="app_root",
        style={
            "display": "flex",
            "minHeight": "100vh",
            "alignItems": "stretch",
            "gap": "12px",
            "maxWidth": "1720px",
            "margin": "0 auto",
            "padding": "10px",
        },
        children=[
            # ===================== LEFT SIDEBAR (analysis only) =====================
            html.Div(
                id="analysis_sidebar",
                style={"display": "none"},
                children=[
                    html.Div(
                        style=SIDEBAR,
                        children=[
                            html.H3(app_title, style={"marginTop": 0}),
                            html.Button(
                                "Back to Homepage",
                                id="analysis_back_home",
                                n_clicks=0,
                                style={
                                    "margin": "8px 0 14px 0",
                                    "padding": "9px 14px",
                                    "borderRadius": "10px",
                                    "border": "1px solid rgba(15,23,42,0.15)",
                                    "backgroundColor": "#ffffff",
                                    "color": "#0f172a",
                                    "cursor": "pointer",
                                    "fontWeight": "600",
                                    "width": "100%",
                                },
                            ),
                            html.H4("Global filters", style={"marginBottom": "6px"}),
                            html.Label("Final product"),
                            dcc.Dropdown(id="product", options=[{"label": k, "value": k} for k in ["Hepar", "Hepeel"]], value="Hepar", searchable=False, clearable=False),
                            html.Div(style={"height": "20px"}),
                            html.Label("Search feature ID (optional)"),
                            dcc.Input(id="feature_search", type="text", placeholder="e.g., N_10036", style={"width": "100%"}),
                            html.Div(style={"height": "10px"}),
                            dcc.Checklist(id="only_pubchem", options=[{"label": "Only features with PubChem CID(s)", "value": "only"}], value=[]),
                            html.Div(style={"height": "6px"}),
                            dcc.Checklist(id="global_use_log", options=[{"label": "Use log10(intensity)", "value": "log"}], value=["log"]),
                            html.Div(style={"height": "12px"}),
                            html.Label("Product intensity filter (global)"),
                            dcc.RangeSlider(id="global_intensity_log_range", min=2, max=7, step=0.3, value=[2, 7], marks={}, tooltip={"placement": "bottom", "always_visible": False}),
                            html.Div(id="global_intensity_range_label", style={"fontSize": "12px", "color": "#666", "marginTop": "6px"}),
                            html.Hr(),
                            html.H4("Navigation", style={"marginBottom": "6px"}),
                            html.Label("Choose view"),
                            dcc.Dropdown(
                                id="page_select",
                                options=[
                                    {"label": "Home", "value": "home"},
                                    {"label": "Explore", "value": "explore::Shared between Hepar & Hepeel"},
                                    {"label": "Q1: Product features & origin", "value": "q1"},
                                    {"label": "Q3: Plant vs animal signal", "value": "q3"},
                                    {"label": "Q4: Component-only", "value": "q4"},
                                    {"label": "Q5: Product-only", "value": "q5"},
                                    {"label": "Q6: Ingredient contribution", "value": "q6"},
                                    {"label": "Q7: Enriched features", "value": "q7"},
                                    {"label": "Q8: Selective amp/att", "value": "q8"},
                                    {"label": "Q9: Shared vs unique", "value": "q9"},
                                    {"label": "Q10: Hepar–Hepeel driver", "value": "q10"},
                                ],
                                value="home",
                                maxHeight=420,
                                optionHeight=38,
                                searchable=False,
                                clearable=False,
                                style={"width": "100%"},
                            ),
                            dcc.Dropdown(id="origin_filter", options=origin_options, value=origin_default, searchable=False, clearable=False, style={"display": "none"}),
                        ],
                    )
                ],
            ),

            # ===================== MAIN CONTENT =====================
            html.Div(
                style=MAIN,
                children=[
                    # ---------- Home / Landing view ----------
                    html.Div(
                        id="view_home",
                        className="page-view",
                        style={"display": "block", "backgroundColor": "#0b1220", "padding": "8px", "borderRadius": "12px", "position": "relative", "overflow": "hidden"},
                        children=[
                            html.Div(
                                style={
                                    "background": "linear-gradient(125deg, #0f172a 0%, #1e293b 45%, #2563eb 100%)",
                                    "borderRadius": "16px",
                                    "padding": "22px 22px 20px 22px",
                                    "boxShadow": "0 12px 34px rgba(15,23,42,0.25)",
                                    "color": "#f8fafc",
                                    "position": "relative",
                                    "zIndex": 1,
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "display": "inline-block",
                                            "padding": "5px 10px",
                                            "borderRadius": "999px",
                                            "fontSize": "12px",
                                            "fontWeight": "600",
                                            "backgroundColor": "rgba(255,255,255,0.18)",
                                            "marginBottom": "10px",
                                        },
                                        children="MS Metabolomics Intelligence",
                                    ),
                                    html.H1(
                                        "COINS-App Dashboard",
                                        style={"margin": "0 0 8px 0", "fontSize": "36px", "lineHeight": "1.1"},
                                    ),
                                    html.P(
                                        [
                                            "Explore feature chemistry across ",
                                            html.Span("Hepar", style={"textDecoration": "underline"}),
                                            " and ",
                                            html.Span("Hepeel", style={"textDecoration": "underline"}),
                                            " using interactive analysis modules (Q1–Q10) with origin-aware filters and click-through scientific detail cards.",
                                        ],
                                        style={"margin": "0 0 14px 0", "fontSize": "16px", "maxWidth": "920px", "opacity": 0.95},
                                    ),
                                    html.Div(
                                        style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"},
                                        children=[
                                            html.Button("Start Analysis (Explore)", id="home_go_explore", n_clicks=0, style={"padding": "10px 16px", "borderRadius": "10px", "border": "none", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "#f8fafc", "color": "#0f172a"}),
                                            html.Button("Open Q1", id="home_go_q1", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q3", id="home_go_q3", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q4", id="home_go_q4", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q5", id="home_go_q5", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q6", id="home_go_q6", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q7", id="home_go_q7", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q8", id="home_go_q8", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q9", id="home_go_q9", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                            html.Button("Open Q10", id="home_go_q10", n_clicks=0, style={"padding": "10px 14px", "borderRadius": "10px", "border": "1px solid rgba(255,255,255,0.4)", "fontWeight": "600", "cursor": "pointer", "backgroundColor": "transparent", "color": "#f8fafc"}),
                                        ],
                                        id="home_hero_buttons",
                                    ),
                                ],
                            ),
                            html.Div(
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))",
                                    "gap": "10px",
                                    "marginTop": "14px",
                                    "position": "relative",
                                    "zIndex": 1,
                                },
                                children=[
                                    html.Div(id="home_quick_stats_dynamic", style={"display": "contents"}),
                                    html.Button(
                                        id="home_product_toggle_button",
                                        n_clicks=0,
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "12px 14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "width": "100%",
                                            "textAlign": "left",
                                        },
                                        children=[
                                            html.Div("Selected product", style={"fontSize": "12px", "color": "#64748b", "fontWeight": "600", "marginBottom": "6px"}),
                                            html.Div("Hepar", style={"fontSize": "22px", "fontWeight": "700", "color": "#0f172a", "lineHeight": 1.1}),
                                            html.Div("Click to switch product", style={"fontSize": "11px", "fontStyle": "italic", "color": "#64748b", "marginTop": "6px"}),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(auto-fit, minmax(280px, 1fr))",
                                    "gap": "10px",
                                    "marginTop": "12px",
                                    "position": "relative",
                                    "zIndex": 1,
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Product Features & Origin", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Analyze feature composition by origin groups and inspect distribution patterns.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Plant vs Animal Signal", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Measure dominance and mixed signatures across plant and animal contributions.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Component-only Features", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "List features found in ingredients but missing in the selected final product.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Product-only Features", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Highlight product features not detected in raw component profiles.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Ingredient Contribution", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Drill into per-feature ingredient dominance and relative contribution intensity.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Enriched Features", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Find features where final-product intensity exceeds the sum of ingredient intensities "
                                                "for Hepar and Hepeel.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Selective Amplification/Attenuation", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Track feature-specific selective amplification or attenuation "
                                                "between Hepar and Hepeel using ratio-based categorization.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Shared vs Unique Chemistry", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Compare shared and product-specific features and inspect detailed cards directly "
                                                "from interactive bars.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card",
                                        children=[
                                            html.H4("Difference Driver Analysis", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Identify strongest Hepar-Hepeel differences and estimate plant/animal drivers.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={
                                            "border": "1px solid #e5e7eb",
                                            "borderRadius": "12px",
                                            "padding": "14px",
                                            "backgroundColor": "#ffffff",
                                            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
                                            "cursor": "pointer",
                                        },
                                        className="home-topic-card home-topic-card--pubchem",
                                        children=[
                                            html.H4("PubChem-annotated features", style={"margin": "0 0 8px 0"}),
                                            html.P(
                                                "Use the PubChem-only filter to show MS features that already have PubChem CID(s) in the dataset.",
                                                style={"margin": 0, "color": "#475569"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="chem-footer",
                                children=[
                                    html.Span("C=C", className="chem-particle", style={"left": "6%", "top": "20%", "fontSize": "20px", "animationDuration": "14s", "animationDelay": "-2s", "color": "rgba(147,197,253,0.55)"}),
                                    html.Span("N-H", className="chem-particle", style={"left": "18%", "top": "52%", "fontSize": "16px", "animationDuration": "12s", "animationDelay": "-5s", "color": "rgba(167,243,208,0.55)"}),
                                    html.Span("O=C=O", className="chem-particle", style={"left": "30%", "top": "30%", "fontSize": "15px", "animationDuration": "13s", "animationDelay": "-8s", "color": "rgba(251,191,36,0.55)"}),
                                    html.Span("C-C-C", className="chem-particle", style={"left": "44%", "top": "64%", "fontSize": "18px", "animationDuration": "15s", "animationDelay": "-1s", "color": "rgba(96,165,250,0.55)"}),
                                    html.Span("H-O-H", className="chem-particle", style={"left": "58%", "top": "26%", "fontSize": "16px", "animationDuration": "11s", "animationDelay": "-4s", "color": "rgba(45,212,191,0.55)"}),
                                    html.Span("C-N", className="chem-particle", style={"left": "72%", "top": "56%", "fontSize": "18px", "animationDuration": "10s", "animationDelay": "-7s", "color": "rgba(165,180,252,0.55)"}),
                                    html.Span("O-H", className="chem-particle", style={"left": "86%", "top": "20%", "fontSize": "15px", "animationDuration": "12s", "animationDelay": "-6s", "color": "rgba(251,113,133,0.55)"}),
                                    html.Span("H-N-H", className="chem-particle", style={"left": "80%", "top": "78%", "fontSize": "14px", "animationDuration": "16s", "animationDelay": "-3s", "color": "rgba(147,197,253,0.55)"}),
                                ],
                            ),
                        ],
                    ),

                    # ---------- Explore view ----------
                    html.Div(
                        id="view_explore",
                        className="page-view",
                        style=HIDE,
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
                        className="page-view",
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
                        className="page-view",
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
                        className="page-view",
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
                        className="page-view",
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
                        className="page-view",
                        style=HIDE,
                        children=[
                            dcc.Store(id="q6_selected_feature"),
                            dcc.Store(id="q6_card_open", data=False),
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
                                id="q6_feature_card",
                                style={"display": "none"},
                                children=[
                                    html.Div(
                                        style={
                                            "border": "1px solid #ddd",
                                            "borderRadius": "8px",
                                            "padding": "10px 12px",
                                            "backgroundColor": "#f9fafb",
                                            "position": "relative",
                                            "marginTop": "8px",
                                        },
                                        children=[
                                            html.Button(
                                                "x",
                                                id="q6_close_card",
                                                n_clicks=0,
                                                title="Close",
                                                style={
                                                    "position": "absolute",
                                                    "top": "8px",
                                                    "right": "10px",
                                                    "border": "none",
                                                    "background": "transparent",
                                                    "fontSize": "18px",
                                                    "cursor": "pointer",
                                                    "lineHeight": "16px",
                                                },
                                            ),
                                            html.Div(id="q6_card_body", style={"paddingRight": "18px"}),
                                        ],
                                    ),
                                ],
                            ),

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
                    #TODO
                    html.Div(
                        id="view_q7",
                        className="page-view",
                        style=HIDE,
                        children=[
                            dcc.Store(id="q7_selected_feature"),
                            dcc.Store(id="q7_card_open", data=False),
                            html.H3(
                                "Q7: Enriched features (final product > sum of ingredient intensities)",
                                style={"marginTop": 0},
                            ),
                            html.Div(
                                style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                                children=[
                                    html.Div(
                                        style={"minWidth": "260px"},
                                        children=[
                                            html.Label("Top enriched features in chart"),
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
                            html.Div(id="q7_stats", style={"marginTop": "10px", "fontSize": "14px"}),
                            dcc.Graph(id="q7_graph", style={"height": "420px", "marginTop": "10px"}),
                            html.Div(
                                id="q7_feature_card",
                                style={"display": "none"},
                                children=[
                                    html.Div(
                                        style={
                                            "border": "1px solid #ddd",
                                            "borderRadius": "8px",
                                            "padding": "10px 12px",
                                            "backgroundColor": "#f9fafb",
                                            "position": "relative",
                                            "marginTop": "8px",
                                        },
                                        children=[
                                            html.Button(
                                                "x",
                                                id="q7_close_card",
                                                n_clicks=0,
                                                title="Close",
                                                style={
                                                    "position": "absolute",
                                                    "top": "8px",
                                                    "right": "10px",
                                                    "border": "none",
                                                    "background": "transparent",
                                                    "fontSize": "18px",
                                                    "cursor": "pointer",
                                                    "lineHeight": "16px",
                                                },
                                            ),
                                            html.Div(id="q7_card_body", style={"paddingRight": "18px"}),
                                        ],
                                    ),
                                ],
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
                        className="page-view",
                        style=HIDE,
                        children=[
                            dcc.Store(id="q8_selected_feature"),
                            dcc.Store(id="q8_card_open", data=False),
                            html.H3(
                                "Q8: Which features show selective amplification vs selective attenuation?",
                                style={"marginTop": 0},
                            ),
                            html.P(
                                "For Hepar vs Hepeel: a feature is selective if, by final / max(component) ratio, one product is amplified or "
                                "attenuated while the other is not. The top panel shows selective amplification and the bottom panel selective "
                                "attenuation (relative to the product selected in the sidebar). Click a bar to open details.",
                                style={"margin": "0 0 10px 0", "color": "#444", "maxWidth": "900px"},
                            ),
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
                                                value=1.0,
                                                marks={1: "1x", 2: "2x", 3: "3x", 5: "5x", 10: "10x"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"minWidth": "320px"},
                                        children=[
                                            html.Label("Show"),
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
                            dcc.Graph(id="q8_graph", style={"height": "720px", "marginTop": "8px"}),
                            html.Div(
                                id="q8_feature_card",
                                style={"display": "none"},
                                children=[
                                    html.Div(
                                        style={
                                            "border": "1px solid var(--q9-card-border, #ddd)",
                                            "borderLeft": "6px solid var(--q9-card-border, #ddd)",
                                            "borderRadius": "8px",
                                            "padding": "12px 12px",
                                            "backgroundColor": "var(--q9-card-bg, #f9fafb)",
                                            "boxShadow": "0 10px 26px rgba(15,23,42,0.08)",
                                            "position": "relative",
                                            "marginTop": "8px",
                                        },
                                        children=[
                                            html.Button(
                                                "x",
                                                id="q8_close_card",
                                                n_clicks=0,
                                                title="Close",
                                                style={
                                                    "position": "absolute",
                                                    "top": "8px",
                                                    "right": "10px",
                                                    "border": "none",
                                                    "background": "transparent",
                                                    "fontSize": "18px",
                                                    "cursor": "pointer",
                                                    "lineHeight": "16px",
                                                },
                                            ),
                                            html.Div(id="q8_card_body", style={"paddingRight": "18px"}),
                                        ],
                                    ),
                                ],
                            ),

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
                    html.Div(
                        id="view_q9",
                        className="page-view",
                        style=HIDE,
                        children=[
                            dcc.Store(id="q9_selected_feature"),
                            dcc.Store(id="q9_card_open", data=False),
                            html.H3(
                                "Q9: How are Hepar and Hepeel chemically different?",
                                style={"marginTop": 0},
                            ),
                            html.P(
                                "Color legend: Shared (both), Unique to Hepar, Unique to Hepeel",
                                style={"margin": "0 0 8px 0", "color": "#444"},
                            ),
                            html.Div(id="q9_stats", style={"marginTop": "6px", "fontSize": "14px"}),
                            dcc.Graph(id="q9_graph", style={"height": "520px", "marginTop": "8px"}),
                            html.Div(
                                id="q9_feature_card",
                                style={"display": "none"},
                                children=[
                                    html.Div(
                                        style={
                                            "border": "1px solid #ddd",
                                            "borderRadius": "8px",
                                            "padding": "10px 12px",
                                            "backgroundColor": "#f9fafb",
                                            "position": "relative",
                                            "marginTop": "8px",
                                        },
                                        children=[
                                            html.Button(
                                                "x",
                                                id="q9_close_card",
                                                n_clicks=0,
                                                title="Close",
                                                style={
                                                    "position": "absolute",
                                                    "top": "8px",
                                                    "right": "10px",
                                                    "border": "none",
                                                    "background": "transparent",
                                                    "fontSize": "18px",
                                                    "cursor": "pointer",
                                                    "lineHeight": "16px",
                                                },
                                            ),
                                            html.Div(id="q9_card_body", style={"paddingRight": "18px"}),
                                        ],
                                    )
                                ],
                            ),
                            html.Div(
                                style={"overflowX": "auto", "width": "100%", "marginTop": "10px"},
                                children=[
                                    dash_table.DataTable(
                                        id="q9_table",
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
                    # ---------- Q10 view ----------
                    html.Div(
                        id="view_q10",
                        className="page-view",
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