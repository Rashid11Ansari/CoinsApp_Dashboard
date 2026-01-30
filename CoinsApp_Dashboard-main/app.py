from __future__ import annotations

from pathlib import Path

from dash import Dash

from dashboard.analysis.queries import QueryRegistry
from dashboard.config import APP_TITLE
from dashboard.data.context import DataContext
from dashboard.ui.callbacks import CallbackBinder
from dashboard.ui.layout import LayoutBuilder

# Dash dropdown choices burada olacak (kept here to avoid duplicating literals).
ORIGIN_OPTIONS = [
    {"label": "All product features", "value": "All product features"},
    {"label": "Common (plant+animal)", "value": "Common (plant+animal)"},
    {"label": "Product-only (Q5)", "value": "Unique to product"},
]


def create_app() -> Dash:
    """Factory that wires data, queries, layout, and callbacks."""
    data_dir = Path(__file__).resolve().parent / "data"
    data_ctx = DataContext(data_dir)
    data_ctx.load()

    app = Dash(__name__)
    app.title = APP_TITLE

    layout_builder = LayoutBuilder(APP_TITLE)
    app.layout = layout_builder.build(ORIGIN_OPTIONS)

    queries = QueryRegistry(data_ctx.summary, data_ctx.groups)
    CallbackBinder(app, data_ctx, queries).register_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

