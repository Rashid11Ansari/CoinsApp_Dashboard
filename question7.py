import pandas as pd
import numpy as np
from dash import Dash, dcc, html
import plotly.express as px
from dash.dependencies import Input, Output

# ----------------------------------
# Load Data
# ----------------------------------
import pandas as pd
from pathlib import Path

# -------------------------------
# Load Data
# -------------------------------

import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "Product_features_summary_annotation.xlsx"

df = pd.read_excel(EXCEL_PATH, header=1)

print(df.columns.tolist())
print(df.head())

# ----------------------------------
# Ingredient Columns (WIDE FORMAT)
# ----------------------------------
HEPAR_COLS = [
    "Avena.sativa",
    "Chelidonium.majus",
    "Cinchona.pubescens",
    "Cynara.scolymus",
    "Lycopodium.clavatum",
    "Silybum.marianum.",
    "Taraxacum.officinale",
    "Veratrum.album",
    "Colon.Suis.D4",
    "Duodenum.Suis.D4",
    "Hepar.Suis.D4",
    "Pankreas.Suis.D4",
    "Thymus.Suis.D4",
    "Vesica.Fellea.Suis.D4"
]

HEPEEL_COLS = [
    "Chelidonium.majus",
    "Cinchona.pubescens",
    "Citrullus.colocynthis.",
    "Lycopodium.clavatum",
    "Myristica.fragrans.",
    "Silybum.marianum.",
    "Veratrum.album"
]

# ----------------------------------
# Target Columns
# ----------------------------------
HEPAR_TARGET_COL = "Hepar.comp.Ampoules..Bulk.mat.52324."
HEPEEL_BULK_COL = "Hepeel.ampoule.solution..Bulk"


# ----------------------------------
# Hepar Enrichment
# ----------------------------------
df["hepar_sum"] = df[HEPAR_COLS].sum(axis=1)
df["hepar_enrichment"] = df[HEPAR_TARGET_COL] - df["hepar_sum"]

hepar_enriched = df[df["hepar_enrichment"] > 0]

# ----------------------------------
# Hepeel Bulk Enrichment
# ----------------------------------
df["hepeel_sum"] = df[HEPEEL_COLS].sum(axis=1)
df["hepeel_enrichment"] = df[HEPEEL_BULK_COL] - df["hepeel_sum"]

hepeel_enriched = df[df["hepeel_enrichment"] > 0]

# ----------------------------------
# Plotly Figures
# ----------------------------------
fig_hepar = px.bar(
    hepar_enriched,
    x="feature",
    y="hepar_enrichment",
    title="Hepar Enriched Features",
    labels={"hepar_enrichment": "Enrichment Intensity"},
    log_y=True
)
fig_hepar.update_traces(
    marker_color="#C0392B"  # professional red
)

fig_hepeel = px.bar(
    hepeel_enriched,
    x="feature",
    y="hepeel_enrichment",
    title="Hepeel  Enriched Features",
    labels={"hepeel_enrichment": "Enrichment Intensity"},
    log_y=True
)
fig_hepeel.update_traces(
    marker_color="#1E8449"  # professional green
)

# ----------------------------------
# Dash App
# ----------------------------------
app = Dash(__name__)

app.layout = html.Div([
    html.H1("Feature Enrichment Dashboard"),

    html.H2("Hepar Enrichment"),
    dcc.Graph(
        id="hepar-graph",
        figure=fig_hepar),
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

    html.H2("Hepeel Enrichment"),
    dcc.Graph(
        id="hepeel-graph",
        figure=fig_hepeel),


])
from dash import callback_context, html
PUBCHEM_COL = "pubchemids"
@app.callback(
    Output("pubchem-output", "children"),
    Input("hepar-graph", "clickData"),
    Input("hepeel-graph", "clickData")
)
def show_pubchem(hepar_click, hepeel_click):

    ctx = callback_context

    # Nothing clicked yet
    if not ctx.triggered:
        return "Click a feature bar (Hepar or Hepeel) to see PubChem ID(s)"

    # Identify which graph triggered
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "hepar-graph":
        clickData = hepar_click
        source = "Hepar"
    elif trigger_id == "hepeel-graph":
        clickData = hepeel_click
        source = "Hepeel"
    else:
        return "Click a feature bar to see PubChem ID(s)"

    if clickData is None:
        return "Click a feature bar to see PubChem ID(s)"

    feature_clicked = clickData["points"][0]["x"]

    row = df[df["feature"] == feature_clicked]

    if row.empty:
        return f"{source} feature {feature_clicked} not found"

    pubchem_ids = row[PUBCHEM_COL].iloc[0]

    if pd.isna(pubchem_ids) or str(pubchem_ids).strip() == "":
        return f"{source} feature: {feature_clicked} | PubChem ID(s): Not available"

    # Split multiple IDs (semicolon-separated in your Excel)
    ids = [i.strip() for i in str(pubchem_ids).split(";")]

    return html.Div([
        html.B(f"{source} Feature: {feature_clicked} | PubChem ID(s): "),
        html.Span([
            html.A(
                pid,
                href=f"https://pubchem.ncbi.nlm.nih.gov/compound/{pid}",
                target="_blank",
                style={"marginRight": "10px"}
            )
            for pid in ids
        ])
    ])



# ----------------------------------
# Run App
# ----------------------------------
if __name__ == "__main__":
    app.run(debug=True)
