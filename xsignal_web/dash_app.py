from __future__ import annotations

import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html
from flask import Flask, redirect

try:
    from .data import load_and_prepare_data
except ImportError:
    from data import load_and_prepare_data

DASH_INDEX_STRING = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                theme: {
                    extend: {
                        colors: {
                            xbg: "#15202B",
                            xpanel: "#16181C",
                            xline: "#2F3336",
                            xtext: "#E7E9EA",
                            xmuted: "#71767B",
                            xblue: "#1D9BF0"
                        }
                    }
                }
            }
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


def _apply_dark_style(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#16181C",
        plot_bgcolor="#16181C",
        font={"color": "#E7E9EA", "family": "Inter, ui-sans-serif, system-ui"},
        margin={"l": 40, "r": 20, "t": 54, "b": 40},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#E5E7EB"}},
        hoverlabel={"bgcolor": "#0F1419", "font_color": "#F9FAFB"},
    )
    fig.update_xaxes(gridcolor="#2F3336", linecolor="#2F3336", zerolinecolor="#2F3336")
    fig.update_yaxes(gridcolor="#2F3336", linecolor="#2F3336", zerolinecolor="#2F3336")
    return fig


def build_figures(df: pd.DataFrame):
    avg_daily = (
        df.groupby("day", as_index=False)["sentiment_score"]
        .mean()
        .sort_values("day")
    )

    line_fig = px.line(
        avg_daily,
        x="day",
        y="sentiment_score",
        markers=True,
        title="Average Sentiment Score Per Day",
        labels={"day": "Day", "sentiment_score": "Average Sentiment Score"},
    )
    line_fig.update_traces(line={"color": "#38BDF8", "width": 3}, marker={"size": 7, "color": "#A78BFA"})
    line_fig.add_hline(y=0, line_dash="dash", line_color="#94A3B8")
    _apply_dark_style(line_fig)

    label_counts = (
        df.groupby(["spectrum", "sentiment_label"])  # affiliation by sentiment label
        .size()
        .reset_index(name="count")
    )


    bar_fig = px.bar(
        label_counts,
        x="spectrum",
        y="count",
        color="sentiment_label",
        barmode="stack",
        title="Sentiment Label Distribution by Affiliation",
        labels={
            "spectrum": "Affiliation",
            "count": "Number of Posts",
            "sentiment_label": "Sentiment",
        },
        category_orders={"sentiment_label": ["negative", "neutral", "positive"]},
        color_discrete_map={
            "negative": "#EF4444",
            "neutral": "#F59E0B",
            "positive": "#22C55E",
        },
    )
    _apply_dark_style(bar_fig)

    return line_fig, bar_fig


def init_dashboard(server):
    dash_app = Dash(
        __name__,
        server=server,
        routes_pathname_prefix="/dashboard/",
        title="X Sentiment Dashboard",
    )
    dash_app.index_string = DASH_INDEX_STRING

    dataframe = load_and_prepare_data()
    line_fig, bar_fig = build_figures(dataframe)

    dash_app.layout = html.Div(
        className="min-h-screen bg-xbg text-xtext font-sans",
        children=[
            html.Div(
                className="border-b border-xline bg-xbg/95 backdrop-blur",
                children=[
                    html.Div(
                        className="max-w-[1320px] mx-auto px-4 md:px-6 py-4 flex items-center justify-between",
                        children=[
                            html.Div("X-Signal", className="text-xl font-semibold tracking-tight text-white"),
                            html.Div("Sentiment Dashboard", className="text-sm text-xmuted"),
                        ],
                    )
                ],
            ),
            html.Div(
                className="max-w-[1320px] mx-auto px-4 md:px-6 py-6",
                children=[
                    html.Div(
                        className="grid grid-cols-12 gap-6",
                        children=[
                            html.Aside(
                                className="hidden lg:block col-span-3",
                                children=[
                                    html.Div(
                                        className="rounded-2xl border border-xline bg-xpanel p-4",
                                        children=[
                                            html.Div("Overview", className="text-sm font-medium text-xtext py-2"),
                                            html.Div("Daily Sentiment", className="text-sm text-xmuted py-2"),
                                            html.Div("Affiliation Distribution", className="text-sm text-xmuted py-2"),
                                        ],
                                    )
                                ],
                            ),
                            html.Main(
                                className="col-span-12 lg:col-span-9 space-y-6",
                                children=[
                                    html.Div(
                                        className="rounded-2xl border border-xline bg-xpanel p-5",
                                        children=[
                                            html.H1(
                                                "Sentiment Dashboard",
                                                className="text-2xl md:text-3xl font-bold tracking-tight text-white",
                                            ),
                                            html.P(
                                                "X-style layout with daily trend and affiliation sentiment distribution.",
                                                className="mt-1 text-xmuted text-sm",
                                            ),
                                        ],
                                    ),
                                    html.Section(
                                        className="rounded-2xl border border-xline bg-xpanel p-4 md:p-5",
                                        children=[
                                            html.H2(
                                                "Average Sentiment Score Per Day",
                                                className="text-lg font-semibold text-xtext mb-3",
                                            ),
                                            html.Div(
                                                className="max-w-5xl",
                                                children=[
                                                    dcc.Graph(
                                                        figure=line_fig,
                                                        config={"displayModeBar": False},
                                                        style={"height": "420px"},
                                                    )
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Section(
                                        className="rounded-2xl border border-xline bg-xpanel p-4 md:p-5",
                                        children=[
                                            html.H2(
                                                "Sentiment Label Distribution by Affiliation",
                                                className="text-lg font-semibold text-xtext mb-3",
                                            ),
                                            html.Div(
                                                className="max-w-5xl",
                                                children=[
                                                    dcc.Graph(
                                                        figure=bar_fig,
                                                        config={"displayModeBar": False},
                                                        style={"height": "420px"},
                                                    )
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        ],
    )

    return dash_app


if __name__ == "__main__":
    standalone_server = Flask(__name__)

    @standalone_server.route("/")
    def _home_redirect():
        return redirect("/dashboard/")

    @standalone_server.route("/favicon.ico")
    def _favicon():
        return "", 204

    init_dashboard(standalone_server)
    standalone_server.run(debug=True, host="0.0.0.0", port=8050)
