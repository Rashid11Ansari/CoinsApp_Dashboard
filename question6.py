
import dash
from dash import dcc, html, Input, Output
import plotly.express as px

# =========================
# Load and prepare data
# =========================
import pandas as pd
import numpy as np

file_path = "Product_features_summary_annotation.xlsx"

# Read Excel with correct header row
df = pd.read_excel(file_path)

# Feature column
feature_col = "feature"

# Ingredient columns end at formulaRank
formula_rank_idx = df.columns.get_loc("formulaRank")
ingredient_cols = df.columns[1:formula_rank_idx]

# Convert ingredient columns to numeric
df[ingredient_cols] = df[ingredient_cols].apply(
    pd.to_numeric, errors="coerce"
)

# Compute total intensity per feature
# Compute total intensity per feature (RAW)
df["Total_Intensityy"] = df[ingredient_cols].sum(axis=1)

# Log-transform total intensity
df["Total_Intensity"] = np.log10(
    df["Total_Intensityy"].replace(0, np.nan)
)

# =========================
# Initialize Dash app
# =========================
app = dash.Dash(__name__)


def make_feature_figure(highlight_feature=None):
    colors = [
        "crimson" if f == highlight_feature else "lightsteelblue"
        for f in df[feature_col]
    ]

    fig = px.bar(
        df,
        x=feature_col,
        y="Total_Intensity",
        title="Total Intensity per Feature"
    )

    fig.update_traces(marker_color=colors)
    fig.update_layout(xaxis=dict(showticklabels=False))

    return fig

# =========================
# Layout
# =========================

app.layout = html.Div([
    html.H2("Feature-Level Ingredient Contribution Dashboard"),

    dcc.Input(
        id="feature-input",
        type="text",
        placeholder="Type feature ID (e.g. N_37573)",
        debounce=True,
        style={"width": "300px", "marginBottom": "10px"}
    ),

    dcc.Graph(
        id="feature-bar",
        figure=make_feature_figure()   # ✅ ONLY ONE feature-bar
    ),

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

    html.Hr(),

    dcc.Graph(id="ingredient-bar")
])

# =========================
# Callback: click feature → ingredient contributions
# =========================
@app.callback(
    Output("feature-bar", "figure"),
    Input("feature-input", "value")
)
def highlight_feature(feature_input):
    if not feature_input:
        return make_feature_figure()

    return make_feature_figure(feature_input)

@app.callback(
    Output("ingredient-bar", "figure"),
    Input("feature-bar", "clickData"),
    Input("feature-input", "value")
)
def update_ingredient_plot(clickData, feature_input):
    if feature_input:
        feature_value = feature_input
    elif clickData:
        feature_value = clickData["points"][0]["x"]
    else:
        return px.bar(title="Type or click a feature")


    # Subset row
    row = df[df[feature_col] == feature_value]

    # Melt ingredient contributions
    contrib_df = row[ingredient_cols].T.reset_index()
    contrib_df.columns = ["Ingredient", "Contributionn"]
    exclude_patterns = r"Bulk|mat\.52324|solution"
    contrib_df = contrib_df[
        ~contrib_df["Ingredient"].str.contains(
            exclude_patterns, case=False, regex=True, na=False
        )
    ]
    contrib_df["Contribution"] = np.log10(
        contrib_df["Contributionn"].replace(0, np.nan)
    )

    # Identify dominant ingredient
    dominant = contrib_df.loc[contrib_df["Contribution"].idxmax(), "Ingredient"]

    fig = px.bar(
        contrib_df,
        x="Ingredient",
        y="Contribution",
        title=(
            f"Ingredient Contributions for Feature {feature_value}<br>"
            "<span style='font-size:12px'>"
            "🔵 Plant-based ingredients &nbsp;&nbsp; 🔴 Animal-based ingredients (Suis.D4)"
            "</span>"
        )
    )
    # Highlight dominant ingredient
    fig.update_traces(
        marker_color=[
            "crimson" if ing.endswith("Suis.D4") else "steelblue"
            for ing in contrib_df["Ingredient"]
        ]
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        yaxis_title="Contribution Intensity"
    )
    return fig

from dash.dependencies import Input, Output
from dash import html
import pandas as pd

PUBCHEM_COL = "pubchemids"

@app.callback(
    Output("pubchem-output", "children"),
    Input("feature-bar", "clickData")   # ✅ NOW THIS EXISTS
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

# =========================
# Run app
# =========================
if __name__ == "__main__":
    app.run(debug=True)
