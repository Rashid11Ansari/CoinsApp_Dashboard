import pandas as pd
import numpy as np
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
# ===============================
# 1. LOAD DATA
# ===============================
# Update this path if needed
DATA_PATH = "Product_features_summary_annotation.xlsx"
df = pd.read_excel(DATA_PATH)
# Feature column name (adjust if different)
FEATURE_COL = "feature"
# ===============================
# 2. DEFINE INGREDIENT GROUPS
# ===============================

# ---- Hepar ingredients ----
hepar_plant = [
    "Chelidonium majus",
    "Cinchona pubescens",
    "Cynara scolymus",
    "Lycopodium clavatum",
    "Silybum marianum",
    "Taraxacum officinale",
    "Veratrum album"
]

hepar_animal = [
    "Colon suis",
    "Duodenum suis",
    "Hepar suis",
    "Pankreas suis",
    "Thymus suis",
    "Vesica fellea suis"
]

# ---- Hepeel ingredients ----
hepeel_plant = [
    "Chelidonium majus",
    "Cinchona pubescens",
    "Citrullus colocynthis",
    "Lycopodium clavatum",
    "Myristica fragrans",
    "Silybum marianum",
    "Veratrum album"
]
# Normalize names to match column headers
def normalize(name):
    return name.replace(" ", ".")

hepar_plant = [normalize(c) for c in hepar_plant]
hepar_animal = [normalize(c) for c in hepar_animal]
hepeel_plant = [normalize(c) for c in hepeel_plant]

hepar_plant = [c for c in hepar_plant if c in df.columns]
hepar_animal = [c for c in hepar_animal if c in df.columns]
hepeel_plant = [c for c in hepeel_plant if c in df.columns]

# ===============================
# 3. CLEAN + NUMERIC CONVERSION
# ===============================

all_ingredients = list(set(hepar_plant + hepar_animal + hepeel_plant))

df[all_ingredients] = df[all_ingredients].apply(
    pd.to_numeric, errors="coerce"
).fillna(0)

# ===============================
# 4. COMPUTE RAW SUMS
# ===============================

df["Hepar_Plant"] = df[hepar_plant].sum(axis=1)
df["Hepar_Animal"] = df[hepar_animal].sum(axis=1)
df["Hepar_Total"] = df["Hepar_Plant"] + df["Hepar_Animal"]

df["Hepeel_Total"] = df[hepeel_plant].sum(axis=1)
df["Difference"] = np.abs(df["Hepar_Total"] - df["Hepeel_Total"])

# Log difference (important!)

# ===============================
# 5. DASH APP
# ===============================

app = dash.Dash(__name__)

# ===============================
# 6. LAYOUT
# ===============================

app.layout = html.Div([

    html.H1("CoinsApp Dashboard"),
    html.H3("Feature-wise Difference: Hepar vs Hepeel"),
html.Div(
    [
        html.Label(
            "Show features with Difference ≥",
            style={"fontWeight": "bold"}
        ),

        dcc.Slider(
            id="diff-threshold",
            min=0,
            max=df["Difference"].max(),
            step=100_000,
            value=1_000_000,
            marks={
                0: "0",
                1_000_000: "1M",
                5_000_000: "5M",
                10_000_000: "10M"
            },
            tooltip={"placement": "bottom", "always_visible": True}
        ),
    ],
    style={
        "width": "40%",
        "marginBottom": "20px",
        "padding": "10px",
        "border": "1px solid #ccc",
        "borderRadius": "6px",
        "backgroundColor": "#f9f9f9"
    }
),


    # --------- GRAPH 1 ----------
    dcc.Graph(
        id="difference-graph",
        figure=px.bar(
            df,
            x="feature",
            y="Difference",
            title="Feature Ranking by Raw Difference (Hepar − Hepeel)",
            labels={"Difference": "Raw Intensity Difference"}
        ).update_layout(
            xaxis=dict(showticklabels=False)
        )
    ),

    html.Hr(),

    html.Div(
        id="pubchem-output",
        style={
            "marginBottom": "20px",
            "fontSize": "18px",
            "fontWeight": "bold",
            "color": "black",
            "backgroundColor": "#f5f5f5",
            "padding": "10px",
            "borderRadius": "5px"
        }
    ),

    # --------- GRAPH 2 ----------
    dcc.Graph(
        id="breakdown-graph",
        figure=px.bar(title="Click a feature above to see ingredient breakdown")
    ),


])

# ===============================
# 7. CALLBACK
# ===============================
@app.callback(
    Output("difference-graph", "figure"),
    Input("diff-threshold", "value"),
)
def update_difference_graph(threshold):

    filtered_df = df[df["Difference"] >= threshold]

    fig = px.bar(
        filtered_df,
        x="feature",
        y="Difference",
        title=f"Features with Difference ≥ {threshold:,.0f}",
        labels={"Difference": "Raw Intensity Difference"},
    )

    fig.update_traces(
        width=0.8,
        opacity=0.9
    )

    fig.update_layout(
        bargap=0.05,
        xaxis=dict(showticklabels=False)
    )

    return fig

@app.callback(
    Output("breakdown-graph", "figure"),
    Input("difference-graph", "clickData")
)
def update_breakdown(clickData):

    if not clickData:
        return px.bar(title="Click a feature above")

    feature_value = clickData["points"][0]["x"]
    row = df[df[FEATURE_COL] == feature_value].iloc[0]

    breakdown_df = pd.DataFrame({
        "Source": [
            "Hepar – Plant",
            "Hepar – Animal",
            "Hepeel – Total"
        ],
        "Intensity": [
            row["Hepar_Plant"],
            row["Hepar_Animal"],
            row["Hepeel_Total"]
        ]
    })

    fig = px.bar(
        breakdown_df,
        x="Source",
        y="Intensity",
        color="Source",
        color_discrete_map={
            "Hepar – Plant": "steelblue",
            "Hepar – Animal": "crimson",
            "Hepeel – Total": "darkgreen"
        },
        title=f"Ingredient Contribution Breakdown for Feature {feature_value}"
    )
    return fig
PUBCHEM_COL = "pubchemids"

@app.callback(
    Output("pubchem-output", "children"),
    Input("difference-graph", "clickData")   # ✅ NOW THIS EXISTS
)
def show_pubchem(clickData):
    if clickData is None:
        return "Click on a Hepar feature bar to see PubChem ID(s)"

    feature_clicked = clickData["points"][0]["x"]

    row = df[df["feature"] == feature_clicked]

    if row.empty:
        return f"Feature {feature_clicked} not found"

    pubchem_ids = row[PUBCHEM_COL].iloc[0]

    if pd.isna(pubchem_ids) or str(pubchem_ids).strip() == "":
        return f"Feature: {feature_clicked} | PubChem ID(s): Not available"

    return html.Div([
        html.Span(f"Feature: {feature_clicked} | PubChem ID(s): "),
        html.A(
            pubchem_ids,
            href=f"https://pubchem.ncbi.nlm.nih.gov/search/#query={pubchem_ids}",
            target="_blank"
        )
    ])

# ===============================
# 8. RUN SERVER
# ===============================
if __name__ == "__main__":
    app.run(debug=True)
