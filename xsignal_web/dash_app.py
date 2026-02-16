from __future__ import annotations

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dcc, html
from flask import Flask, redirect

# TODO: Rewrite in Django
#      - Use real dates from posts, fetch created_at fro X API and convert to datetime
#      - Add more interactivity (show sentient breakdown for day on click, filter by affiliation, etc.)
#      - Add trends over time for each affiliation
#      - Add public metrics for each side (likes, retweets, etc.) and show correlation with sentiment
#      - Plug in n8n and agent to interpret trends and generate insights (e.g. "Positive sentiment for X is rising, likely due to Y event")
#      - Use n8n to fetch images for latest trending topics and show in dashboard
#      - Host on Azure and create a domain for it (e.g. xsignal.ai) to share with others


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
                            xbg: "#050505",
                            xpanel: "#0b0b0b",
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
        paper_bgcolor="#0b0b0b",
        plot_bgcolor="#0b0b0b",
        font={"color": "#E7E9EA", "family": "Inter, ui-sans-serif, system-ui"},
        margin={"l": 28, "r": 18, "t": 60, "b": 36},
        legend={
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E5E7EB"},
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
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
        # title="Average Sentiment Score Per Day",
        labels={"day": "Date", "sentiment_score": "Average Score"},
    )
    line_fig.update_traces(line={"color": "#38BDF8", "width": 3}, marker={"size": 7, "color": "#A78BFA"})

    reference_x = avg_daily["day"].tolist()
    line_fig.add_scatter(
        x=reference_x,
        y=[1.0] * len(reference_x),
        mode="lines",
        name="1 = Positive",
        line={"color": "#22C55E", "width": 1.5, "dash": "dot"},
        hoverinfo="skip",
    )
    line_fig.add_scatter(
        x=reference_x,
        y=[0.0] * len(reference_x),
        mode="lines",
        name="0 = Neutral",
        line={"color": "#94A3B8", "width": 1.5, "dash": "dash"},
        hoverinfo="skip",
    )
    line_fig.add_scatter(
        x=reference_x,
        y=[-1.0] * len(reference_x),
        mode="lines",
        name="-1 = Negative",
        line={"color": "#EF4444", "width": 1.5, "dash": "dot"},
        hoverinfo="skip",
    )
    _apply_dark_style(line_fig)
    # line_fig.update_layout(plot_bgcolor="#0b0b0b")

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
        # title="Sentiment Label Distribution by Affiliation",
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
                className="max-w-[1700px] mx-auto px-4 md:px-8 lg:px-10 py-6",
                children=[
                    html.Div(
                        className="w-full",
                        children=[
                            html.Main(
                                className="space-y-8",
                                children=[
                                    html.Div(
                                        className="rounded-2xl border-2 border-xline bg-xpanel p-6",
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
                                    html.Div(
                                        className="grid grid-cols-1 xl:grid-cols-[7fr_3fr] gap-8",
                                        children=[
                                            html.Section(
                                                className="rounded-2xl border-2 border-xline bg-xpanel p-6",
                                                children=[
                                                    html.H2(
                                                        "Average Sentiment Score Per Day",
                                                        className="text-lg font-semibold text-xtext mb-3",
                                                    ),
                                                    dcc.Graph(
                                                        id="daily-sentiment-graph",
                                                        figure=line_fig,
                                                        config={"displayModeBar": False},
                                                        style={"height": "520px", "width": "100%"},
                                                    ),
                                                    html.Div(
                                                        id="daily-sentiment-hover-info",
                                                        className="mt-3 rounded-lg border border-xline bg-xbg px-3 py-2 text-sm text-xmuted",
                                                        children="Hover over a point to see details here.",
                                                    ),
                                                ],
                                            ),
                                            html.Section(
                                                className="rounded-2xl border-2 border-xline bg-xpanel p-6",
                                                children=[
                                                    html.H2(
                                                        "Sentiment Label Distribution by Affiliation",
                                                        className="text-lg font-semibold text-xtext mb-3",
                                                    ),
                                                    dcc.Graph(
                                                        figure=bar_fig,
                                                        config={"displayModeBar": False},
                                                        style={"height": "520px", "width": "100%"},
                                                    ),
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

    @dash_app.callback(
        Output("daily-sentiment-hover-info", "children"),
        Input("daily-sentiment-graph", "hoverData"),
    )
    def show_daily_hover_details(hover_data):
        if not hover_data or "points" not in hover_data or not hover_data["points"]:
            return "Hover over a point to see details here."

        point = hover_data["points"][0]
        day_value = point.get("x", "N/A")
        score_value = point.get("y")
        if score_value is None:
            return f"Day: {day_value}"

        return f"Day: {day_value} | Average Sentiment Score: {float(score_value):.4f}"

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
