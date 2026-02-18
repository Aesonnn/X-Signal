from __future__ import annotations

import re
import pandas as pd
import plotly.express as px
from sklearn.feature_extraction.text import CountVectorizer

from django.shortcuts import render

from .services import load_and_prepare_data


def extract_trends(df: pd.DataFrame, top_n: int = 5):
    if df.empty:
        return []

    text_data = df["text"].dropna().astype(str).tolist()
    if not text_data:
        return []

    # Remove URLs
    url_pattern = re.compile(r"https?://\S+|www\.\S+")
    clean_text = [url_pattern.sub("", t) for t in text_data]

    try:
        vec = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_df=1.0)
        X = vec.fit_transform(clean_text)
        counts = X.sum(axis=0).A1
        terms = vec.get_feature_names_out()

        sorted_indices = counts.argsort()[::-1][:top_n]
        top_terms = [{"term": terms[i], "count": int(counts[i])} for i in sorted_indices]
        return top_terms
    except ValueError:
        return []


def _build_day_breakdown_payload(df: pd.DataFrame) -> dict:
    payload = {}
    if df.empty:
        return payload

    working_df = df.copy()
    working_df["day"] = working_df["day"].astype(str)

    for day, day_data in df.groupby("day"):
        day = str(day)
        rows = []
        
        # Affiliation stats for this day
        aff_grouped = day_data.groupby("spectrum")
        for aff_code, aff_rows in aff_grouped:
            post_count = len(aff_rows)
            aff_code = str(aff_code)
            
            # Trends for this affiliation on this day
            aff_day_trends = extract_trends(aff_rows, top_n=3)
            
            rows.append(
                {
                    "affiliation": aff_code,
                    "post_count": post_count,
                    "likes": int(aff_rows["like_count"].sum()) if "like_count" in aff_rows else 0,
                    "retweets": int(aff_rows["retweet_count"].sum()) if "retweet_count" in aff_rows else 0,
                    "replies": int(aff_rows["reply_count"].sum()) if "reply_count" in aff_rows else 0,
                    "impressions": int(aff_rows["impression_count"].sum()) if "impression_count" in aff_rows else 0,
                    "trends": aff_day_trends,
                }
            )

        # Trends for the whole day
        day_overall_trends = extract_trends(day_data, top_n=5)
        
        # Sentiment distribution for bar chart update
        # We need a list of dicts: {spectrum: '...', sentiment_label: '...', count: N}
        sentiment_counts = day_data.groupby(["spectrum", "sentiment_label"]).size().reset_index(name="count")
        sentiment_distribution = []
        for _, r in sentiment_counts.iterrows():
            sentiment_distribution.append({
                "spectrum": str(r["spectrum"]),
                "sentiment_label": str(r["sentiment_label"]),
                "count": int(r["count"])
            })

        payload[day] = {
            "rows": rows,
            "total_posts": int(len(day_data)),
            "trends": day_overall_trends,
            "sentiment_distribution": sentiment_distribution,
        }

    return payload


def _apply_dark_style(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0b0b",
        plot_bgcolor="#0b0b0b",
        font={"color": "#E7E9EA", "family": "Inter, ui-sans-serif, system-ui"},
        margin={"l": 28, "r": 18, "t": 50, "b": 36},
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


def _build_figures(df: pd.DataFrame):
    avg_daily = df.groupby("day", as_index=False)["sentiment_score"].mean().sort_values("day")

    line_fig = px.line(
        avg_daily,
        x="day",
        y="sentiment_score",
        markers=True,
        custom_data=["day"],
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

    label_counts = df.groupby(["spectrum", "sentiment_label"]).size().reset_index(name="count")
    bar_fig = px.bar(
        label_counts,
        x="spectrum",
        y="count",
        color="sentiment_label",
        barmode="stack",
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

    line_fig.update_layout(hovermode="x")
    return line_fig, bar_fig


def _get_correlation(df, metric_col):
    if df.empty or metric_col not in df.columns or len(df) < 2:
        return 0.0
    val = df["sentiment_score"].corr(df[metric_col])
    return round(val, 3) if not pd.isna(val) else 0.0


def dashboard(request):
    dataframe = load_and_prepare_data()
    affiliation_options = sorted(dataframe["spectrum"].dropna().astype(str).unique().tolist())
    selected_affiliation = request.GET.get("affiliation", "ALL")

    if selected_affiliation and selected_affiliation != "ALL":
        filtered_df = dataframe[dataframe["spectrum"] == selected_affiliation].copy()
    else:
        filtered_df = dataframe

    line_fig, bar_fig = _build_figures(filtered_df)
    day_breakdown = _build_day_breakdown_payload(filtered_df)

    # Weekly/Global Trends Calculation
    global_trends = extract_trends(filtered_df, top_n=10)
    
    # Trends by affiliation for the entire period
    trends_by_affiliation = {}
    if not filtered_df.empty:
        affs = filtered_df["spectrum"].unique()
        for aff in affs:
            if pd.isna(aff):
                continue
            aff_str = str(aff)
            trends_by_affiliation[aff_str] = extract_trends(filtered_df[filtered_df["spectrum"] == aff], top_n=5)

    # Calculate Correlations with Sentiment
    metrics = ["like_count", "retweet_count", "reply_count", "impression_count"]
    correlation_data = []
    
    # Global Correlation for current filtered view
    global_corr = {"affiliation": "Global (Filtered)", "is_global": True}
    for m in metrics:
        global_corr[m] = _get_correlation(filtered_df, m)
    correlation_data.append(global_corr)
    
    # Per Affiliation in current view
    if not filtered_df.empty:
        affs = sorted(filtered_df["spectrum"].unique())
        for aff in affs:
            if pd.isna(aff):
                continue
            aff_str = str(aff)
            sub_df = filtered_df[filtered_df["spectrum"] == aff]
            row = {"affiliation": aff_str, "is_global": False}
            for m in metrics:
                row[m] = _get_correlation(sub_df, m)
            correlation_data.append(row)

    context = {
        "line_chart": line_fig.to_html(full_html=False, include_plotlyjs=False, div_id="daily-line-chart"),
        "bar_chart": bar_fig.to_html(full_html=False, include_plotlyjs=False, div_id="affiliation-bar-chart"),
        "affiliation_options": affiliation_options,
        "selected_affiliation": selected_affiliation,
        "day_breakdown": day_breakdown,
        "global_trends": global_trends,
        "trends_by_affiliation": trends_by_affiliation,
        "correlation_data": correlation_data,
    }
    return render(request, "dashboard/index.html", context)
