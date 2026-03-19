from __future__ import annotations

import json
import os
import re
import uuid
from datetime import timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS, TfidfTransformer

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    DailyAffiliationMetric,
    DailyGlobalMetric,
    N8NReply,
    Post,
    Rolling7dAffiliationMetric,
    Rolling7dGlobalMetric,
    UserDashboard,
)
from .forms import SignUpForm, UserDashboardForm
from .repositories import get_day_click_payload
from .x_api import sync_workspace_posts


N8N_REPLY_AUTH_TOKEN = os.getenv("N8N_REPLY_AUTH_TOKEN", "xsignal-n8n-reply-2026")


def _normalize_workspace_key(workspace_id: str | int | None) -> str:
    raw = str(workspace_id or "main").strip()
    return raw or "main"


def _workspace_from_key(workspace_key: str):
    if workspace_key == "main":
        return None
    try:
        return UserDashboard.objects.filter(id=int(workspace_key)).first()
    except ValueError:
        return None


def _get_latest_n8n_reply_data(workspace_key: str):
    latest = (
        N8NReply.objects.filter(workspace_key=workspace_key)
        .annotate(latest_marker=Coalesce("requested_at", "received_at", output_field=DateTimeField()))
        .order_by("-latest_marker", "-received_at", "-id")
        .first()
    )
    if not latest:
        return None
    return {
        "received_at": latest.received_at.isoformat(),
        "response": latest.response,
        "workspace": latest.workspace_key,
        "request_id": latest.request_id,
    }

# Filters irrelevant words and common stop words on X
def extract_trends_from_texts(text_data: list[str], top_n: int = 5):
    if not text_data:
        return []

    url_pattern = re.compile(r"https?://\S+|www\.\S+")
    mention_pattern = re.compile(r"@\w+")

    custom_stop_words = {
        "rt",
        "amp",
        "https",
        "http",
        "co",
        "tco",
    }
    stop_words = ENGLISH_STOP_WORDS.union(custom_stop_words)

    clean_text: list[str] = []
    for text in text_data:
        value = str(text or "")
        value = url_pattern.sub(" ", value)
        value = mention_pattern.sub(" ", value)
        value = value.replace("&amp;", " and ")
        value = value.replace("#", " ")
        value = re.sub(r"[^A-Za-z\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip().lower()
        if value:
            clean_text.append(value)

    if not clean_text:
        return []

    try:
        min_df = 2 if len(clean_text) >= 20 else 1
        max_df = 0.85 if len(clean_text) >= 20 else 1.0

        vec = CountVectorizer(
            stop_words=list(stop_words),
            ngram_range=(1, 2),
            min_df=min_df,
            max_df=max_df,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
        )
        X = vec.fit_transform(clean_text)
        counts = X.sum(axis=0).A1
        terms = vec.get_feature_names_out()

        if len(clean_text) >= 20:
            tfidf = TfidfTransformer(norm=None, use_idf=True, smooth_idf=True, sublinear_tf=True)
            tfidf.fit(X)
            ranking_scores = counts * tfidf.idf_
        else:
            ranking_scores = counts

        sorted_indices = ranking_scores.argsort()[::-1][:top_n]
        top_terms = [{"term": terms[i], "count": int(counts[i])} for i in sorted_indices]
        return top_terms
    except ValueError:
        return []


def _build_day_breakdown_payload(selected_affiliation: str) -> dict:
    payload: dict[str, dict] = {}

    if selected_affiliation == "ALL":
        for day in DailyGlobalMetric.objects.order_by("day").values_list("day", flat=True):
            data = get_day_click_payload(day)
            if data:
                payload[str(day)] = data
        return payload

    day_rows = DailyAffiliationMetric.objects.filter(affiliation=selected_affiliation).order_by("day")
    for row in day_rows:
        payload[str(row.day)] = {
            "rows": [
                {
                    "affiliation": row.affiliation,
                    "post_count": row.posts_count,
                    "likes": row.likes_sum,
                    "retweets": row.retweets_sum,
                    "replies": row.replies_sum,
                    "impressions": row.impressions_sum,
                    "trends": row.top_trends,
                }
            ],
            "total_posts": row.posts_count,
            "trends": row.top_trends,
            "sentiment_distribution": [
                {"spectrum": row.affiliation, "sentiment_label": "negative", "count": row.negative_count},
                {"spectrum": row.affiliation, "sentiment_label": "neutral", "count": row.neutral_count},
                {"spectrum": row.affiliation, "sentiment_label": "positive", "count": row.positive_count},
            ],
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


def _build_figures(line_df: pd.DataFrame, bar_df: pd.DataFrame | None = None):
    if bar_df is None:
        bar_df = line_df

    if line_df.empty:
        empty_line = go.Figure()
        empty_line.update_layout(title="No data available")
        _apply_dark_style(empty_line)

        if bar_df.empty:
            empty_bar = go.Figure()
            empty_bar.update_layout(title="No data available")
            _apply_dark_style(empty_bar)
            return empty_line, empty_bar

    avg_daily = line_df.groupby("day", as_index=False)["sentiment_score"].mean().sort_values("day")

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

    if bar_df.empty:
        bar_fig = go.Figure()
        bar_fig.update_layout(title="No data in last 7 days")
        _apply_dark_style(bar_fig)
    else:
        if "count" in bar_df.columns:
            label_counts = (
                bar_df.groupby(["affiliation", "sentiment_label"], as_index=False)["count"]
                .sum()
            )
        else:
            label_counts = bar_df.groupby(["affiliation", "sentiment_label"]).size().reset_index(name="count")
        bar_fig = px.bar(
            label_counts,
            x="affiliation",
            y="count",
            color="sentiment_label",
            barmode="stack",
            labels={
                "affiliation": "Affiliation",
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


def _get_latest_rolling_affiliation_rows(selected_affiliation: str):
    if selected_affiliation == "ALL":
        latest_global = Rolling7dGlobalMetric.objects.order_by("-window_end_day").first()
        if not latest_global:
            return []
        return list(
            Rolling7dAffiliationMetric.objects.filter(window_end_day=latest_global.window_end_day).order_by("affiliation")
        )

    latest_aff = (
        Rolling7dAffiliationMetric.objects.filter(affiliation=selected_affiliation)
        .order_by("-window_end_day")
        .first()
    )
    if not latest_aff:
        return []
    return [latest_aff]


def _build_bar_df_from_rolling_rows(rolling_rows):
    records = []
    for row in rolling_rows:
        records.append({"affiliation": row.affiliation, "sentiment_label": "negative", "count": row.negative_count})
        records.append({"affiliation": row.affiliation, "sentiment_label": "neutral", "count": row.neutral_count})
        records.append({"affiliation": row.affiliation, "sentiment_label": "positive", "count": row.positive_count})
    return pd.DataFrame(records)


def _get_weekly_trends_from_rolling(selected_affiliation: str):
    if selected_affiliation == "ALL":
        latest_global = Rolling7dGlobalMetric.objects.order_by("-window_end_day").first()
        if not latest_global:
            return [], {}

        aff_rows = Rolling7dAffiliationMetric.objects.filter(window_end_day=latest_global.window_end_day).order_by("affiliation")
        trends_by_affiliation = {row.affiliation: (row.top_trends or []) for row in aff_rows}
        return latest_global.top_trends or [], trends_by_affiliation

    latest_aff = (
        Rolling7dAffiliationMetric.objects.filter(affiliation=selected_affiliation)
        .order_by("-window_end_day")
        .first()
    )
    if not latest_aff:
        return [], {}
    return latest_aff.top_trends or [], {latest_aff.affiliation: latest_aff.top_trends or []}


def _get_daily_top_trends_last_7_days(selected_affiliation: str):
    if selected_affiliation == "ALL":
        rows = DailyGlobalMetric.objects.order_by("-day")[:7]
        results = []
        for row in rows:
            trends = row.top_trends or []
            top_trend = trends[0] if trends else {}
            results.append(
                {
                    "day": str(row.day),
                    "term": top_trend.get("term", "N/A"),
                    "count": int(top_trend.get("count", 0) or 0),
                }
            )
        return list(reversed(results))

    rows = DailyAffiliationMetric.objects.filter(affiliation=selected_affiliation).order_by("-day")[:7]
    results = []
    for row in rows:
        trends = row.top_trends or []
        top_trend = trends[0] if trends else {}
        results.append(
            {
                "day": str(row.day),
                "term": top_trend.get("term", "N/A"),
                "count": int(top_trend.get("count", 0) or 0),
            }
        )
    return list(reversed(results))


def _build_weekly_correlation_data(week_df: pd.DataFrame):
    metrics = ["like_count", "retweet_count", "reply_count", "impression_count"]
    correlation_data = []

    global_corr = {"affiliation": "Global (7d)", "is_global": True}
    for metric in metrics:
        global_corr[metric] = _get_correlation(week_df, metric)
    correlation_data.append(global_corr)

    if not week_df.empty:
        affs = sorted(week_df["affiliation"].dropna().astype(str).unique().tolist())
        for aff in affs:
            sub_df = week_df[week_df["affiliation"] == aff]
            row = {"affiliation": aff, "is_global": False}
            for metric in metrics:
                row[metric] = _get_correlation(sub_df, metric)
            correlation_data.append(row)

    return correlation_data


def _build_ai_overview_payload(post_qs, selected_affiliation: str, workspace_id: str = "main", request_id: str = ""):
    if selected_affiliation and selected_affiliation != "ALL":
        post_qs = post_qs.filter(affiliation=selected_affiliation)

    week_cutoff = timezone.now() - timedelta(days=7)
    week_df = pd.DataFrame(
        post_qs.filter(created_at__gte=week_cutoff).values(
            "day",
            "sentiment_score",
            "affiliation",
            "like_count",
            "retweet_count",
            "reply_count",
            "impression_count",
            "text",
        )
    )

    avg_sentiment_per_day = []
    if not week_df.empty:
        week_df["day"] = week_df["day"].astype(str)
        avg_daily = week_df.groupby("day", as_index=False)["sentiment_score"].mean().sort_values("day")
        avg_sentiment_per_day = [
            {"day": row["day"], "avg_sentiment_score": round(float(row["sentiment_score"]), 6)}
            for _, row in avg_daily.iterrows()
        ]

    week_texts = week_df.get("text", pd.Series(dtype=str)).dropna().astype(str).tolist()
    global_trends_7d = extract_trends_from_texts(week_texts, top_n=10)
    trends_by_affiliation = {}
    if not week_df.empty:
        for affiliation in sorted(week_df["affiliation"].dropna().astype(str).unique().tolist()):
            texts = week_df[week_df["affiliation"] == affiliation]["text"].dropna().astype(str).tolist()
            trends_by_affiliation[affiliation] = extract_trends_from_texts(texts, top_n=5)

    weekly_correlation = _build_weekly_correlation_data(week_df)

    return {
        "generated_at": timezone.now().isoformat(),
        "request_id": request_id,
        "affiliation_filter": selected_affiliation,
        "window": "last_7_days",
        "reply_instructions": {
            "endpoint": reverse("n8n_reply"),
            "method": "POST",
            "authorization_header": "Authorization: Bearer <N8N_REPLY_AUTH_TOKEN>",
            "body_example": {
                "response": "Your AI overview summary here",
                "workspace": "<workspace_id>",
                "request_id": "<request_id>",
                "generated_at": "<generated_at>",
            },
            "note": "Include workspace and request_id from this payload so stale replies do not replace newer ones.",
        },
        "workspace": workspace_id,
        "metrics": {
            "average_sentiment_score_per_day": avg_sentiment_per_day,
            "trends": {
                "global": global_trends_7d,
                "by_affiliation": trends_by_affiliation,
            },
            "sentiment_correlation_analysis": weekly_correlation,
        },
    }


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Account created successfully.")
            return redirect("dashboard")
    else:
        form = SignUpForm()

    return render(request, "dashboard/auth/signup.html", {"form": form})


@login_required
def dashboard_hub(request):
    dashboards = UserDashboard.objects.filter(owner=request.user).order_by("-updated_at", "id")
    form = UserDashboardForm()
    return render(
        request,
        "dashboard/workspaces/index.html",
        {
            "dashboards": dashboards,
            "form": form,
        },
    )


@login_required
@require_POST
def create_user_dashboard(request):
    form = UserDashboardForm(request.POST)
    if not form.is_valid():
        dashboards = UserDashboard.objects.filter(owner=request.user).order_by("-updated_at", "id")
        return render(
            request,
            "dashboard/workspaces/index.html",
            {
                "dashboards": dashboards,
                "form": form,
            },
            status=400,
        )

    user_dashboard = form.save(commit=False)
    user_dashboard.owner = request.user
    user_dashboard.save()
    messages.success(request, "Dashboard workspace created.")
    return redirect(f"{reverse('dashboard')}?workspace={user_dashboard.id}")


@login_required
def edit_user_dashboard(request, workspace_id: int):
    workspace = UserDashboard.objects.filter(owner=request.user, id=workspace_id).first()
    if not workspace:
        messages.error(request, "Workspace not found.")
        return redirect("dashboard_hub")

    if request.method == "POST":
        existing_api_key = workspace.x_api_key
        form = UserDashboardForm(request.POST, instance=workspace)
        if form.is_valid():
            updated_workspace = form.save(commit=False)
            if not (request.POST.get("x_api_key") or "").strip():
                updated_workspace.x_api_key = existing_api_key
            updated_workspace.owner = request.user
            updated_workspace.save()
            messages.success(request, f"Workspace '{updated_workspace.name}' updated.")
            return redirect("dashboard_hub")
    else:
        form = UserDashboardForm(instance=workspace)

    return render(
        request,
        "dashboard/workspaces/edit.html",
        {
            "form": form,
            "workspace": workspace,
        },
    )


@login_required
@require_POST
def sync_dashboard_posts(request, workspace_id: int):
    workspace = UserDashboard.objects.filter(owner=request.user, id=workspace_id).first()
    if not workspace:
        messages.error(request, "Workspace not found.")
        return redirect("dashboard_hub")

    try:
        sync_result = sync_workspace_posts(
            workspace,
            window_days=workspace.fetch_window_days,
            max_results_per_account=workspace.fetch_posts_per_account,
        )
    except Exception as exc:
        messages.error(request, f"Failed to sync posts: {exc}")
        return redirect("dashboard_hub")

    if not sync_result.get("ok"):
        messages.error(request, sync_result.get("error", "Failed to sync posts from X."))
        return redirect("dashboard_hub")

    messages.success(
        request,
        (
            f"Sync complete for '{workspace.name}'. Accounts processed: {sync_result['processed_accounts']}, "
            f"accounts skipped: {sync_result['skipped_accounts']}, "
            f"posts created: {sync_result['created_posts']}, posts updated: {sync_result['updated_posts']}."
        ),
    )
    return redirect(f"{reverse('dashboard')}?workspace={workspace.id}")


@login_required
@require_POST
def ai_overview(request):
    selected_affiliation = request.POST.get("affiliation", "ALL")
    workspace_id = _normalize_workspace_key(request.POST.get("workspace", ""))
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()

    scoped_post_qs = Post.objects.filter(source_dashboard__isnull=True)
    if workspace_id and workspace_id != "main":
        workspace = UserDashboard.objects.filter(owner=request.user, id=workspace_id).first()
        if workspace:
            scoped_post_qs = Post.objects.filter(source_dashboard=workspace)

    if not webhook_url:
        messages.error(request, "N8N_WEBHOOK_URL is not configured.")
        target = f"/?affiliation={selected_affiliation}"
        if workspace_id:
            target += f"&workspace={workspace_id}"
        return redirect(target)

    request_id = uuid.uuid4().hex
    payload = _build_ai_overview_payload(
        scoped_post_qs,
        selected_affiliation,
        workspace_id=workspace_id or "main",
        request_id=request_id,
    )

    try:
        response = requests.post(webhook_url, json=payload, timeout=25)
        response.raise_for_status()
        messages.success(request, "AI Overview sent to n8n webhook.")
    except requests.RequestException as exc:
        messages.error(request, f"Failed to send AI Overview to n8n: {exc}")

    target = f"/?affiliation={selected_affiliation}"
    if workspace_id:
        target += f"&workspace={workspace_id}"
    return redirect(target)


@csrf_exempt
@require_POST
def n8n_reply(request):
    expected_auth = f"Bearer {N8N_REPLY_AUTH_TOKEN}"
    provided_auth = request.headers.get("Authorization", "").strip()
    if provided_auth != expected_auth:
        return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {"raw": request.body.decode("utf-8", errors="replace")}

    reply_workspace = _normalize_workspace_key(payload.get("workspace", "main"))
    generated_at_raw = payload.get("generated_at") or payload.get("requested_at")
    generated_at = parse_datetime(str(generated_at_raw)) if generated_at_raw else None

    N8NReply.objects.create(
        source_dashboard=_workspace_from_key(reply_workspace),
        workspace_key=reply_workspace,
        request_id=str(payload.get("request_id", "") or "").strip(),
        requested_at=generated_at,
        response=payload.get("response", payload),
        raw_payload=payload,
    )

    return JsonResponse({"ok": True})


@login_required
@require_GET
def latest_n8n_reply(request):
    workspace_key = _normalize_workspace_key(request.GET.get("workspace") or "main")
    if workspace_key != "main":
        workspace = UserDashboard.objects.filter(owner=request.user, id=workspace_key).first()
        if not workspace:
            return JsonResponse({"ok": False, "error": "Workspace not found"}, status=404)

    data = _get_latest_n8n_reply_data(workspace_key)
    return JsonResponse({"ok": True, "data": data})


@login_required
def dashboard(request):
    user_dashboards = UserDashboard.objects.filter(owner=request.user).order_by("-updated_at", "id")
    workspace_items = [{"id": "main", "name": "Main", "is_main": True}]
    workspace_items.extend(
        [{"id": str(item.id), "name": item.name, "is_main": False} for item in user_dashboards]
    )

    requested_workspace = _normalize_workspace_key(request.GET.get("workspace") or "main")
    active_workspace = None
    if requested_workspace != "main":
        try:
            active_workspace = user_dashboards.filter(id=int(requested_workspace)).first()
        except ValueError:
            active_workspace = None

    if requested_workspace != "main" and not active_workspace:
        requested_workspace = "main"

    active_workspace_id = requested_workspace
    active_workspace_name = active_workspace.name if active_workspace else "Main"

    workspace_posts = Post.objects.filter(source_dashboard__isnull=True)
    if active_workspace:
        workspace_posts = Post.objects.filter(source_dashboard=active_workspace)

    affiliation_options = sorted(workspace_posts.exclude(affiliation="").values_list("affiliation", flat=True).distinct())
    selected_affiliation = request.GET.get("affiliation", "ALL")

    post_qs = workspace_posts
    if selected_affiliation and selected_affiliation != "ALL":
        post_qs = post_qs.filter(affiliation=selected_affiliation)

    dataframe = pd.DataFrame(
        post_qs.values(
            "day",
            "sentiment_score",
            "sentiment_label",
            "affiliation",
            "text",
            "like_count",
            "retweet_count",
            "reply_count",
            "impression_count",
        )
    )
    if not dataframe.empty:
        dataframe["day"] = dataframe["day"].astype(str)

    week_cutoff = timezone.now() - timedelta(days=7)
    week_df = pd.DataFrame(
        post_qs.filter(created_at__gte=week_cutoff).values(
            "day",
            "sentiment_score",
            "affiliation",
            "like_count",
            "retweet_count",
            "reply_count",
            "impression_count",
            "text",
            "sentiment_label",
        )
    )

    bar_df = week_df[["affiliation", "sentiment_label"]].copy() if not week_df.empty else pd.DataFrame()

    line_fig, bar_fig = _build_figures(dataframe, bar_df)

    day_breakdown = {}
    if not dataframe.empty:
        grouped_days = dataframe.groupby("day", sort=True)
        for day_value, day_frame in grouped_days:
            day_texts = day_frame["text"].dropna().astype(str).tolist()
            day_rows = []
            sentiment_distribution = []

            for affiliation in sorted(day_frame["affiliation"].dropna().astype(str).unique().tolist()):
                sub = day_frame[day_frame["affiliation"] == affiliation]
                aff_texts = sub["text"].dropna().astype(str).tolist()
                day_rows.append(
                    {
                        "affiliation": affiliation,
                        "post_count": int(len(sub)),
                        "likes": int(sub["like_count"].fillna(0).sum()),
                        "retweets": int(sub["retweet_count"].fillna(0).sum()),
                        "replies": int(sub["reply_count"].fillna(0).sum()),
                        "impressions": int(sub["impression_count"].fillna(0).sum()),
                        "trends": extract_trends_from_texts(aff_texts, top_n=5),
                    }
                )

                for label in ["negative", "neutral", "positive"]:
                    label_count = int((sub["sentiment_label"] == label).sum())
                    sentiment_distribution.append(
                        {
                            "spectrum": affiliation,
                            "sentiment_label": label,
                            "count": label_count,
                        }
                    )

            day_breakdown[str(day_value)] = {
                "rows": day_rows,
                "total_posts": int(len(day_frame)),
                "trends": extract_trends_from_texts(day_texts, top_n=8),
                "sentiment_distribution": sentiment_distribution,
            }

    global_trends_7d = []
    trends_by_affiliation = {}
    daily_top_trends_7d = []
    if not week_df.empty:
        week_texts = week_df["text"].dropna().astype(str).tolist()
        global_trends_7d = extract_trends_from_texts(week_texts, top_n=10)

        for affiliation in sorted(week_df["affiliation"].dropna().astype(str).unique().tolist()):
            aff_texts = week_df[week_df["affiliation"] == affiliation]["text"].dropna().astype(str).tolist()
            trends_by_affiliation[affiliation] = extract_trends_from_texts(aff_texts, top_n=5)

        for day_value, day_frame in week_df.groupby("day", sort=True):
            top_trend = extract_trends_from_texts(day_frame["text"].dropna().astype(str).tolist(), top_n=1)
            if top_trend:
                daily_top_trends_7d.append(
                    {
                        "day": str(day_value),
                        "term": top_trend[0]["term"],
                        "count": int(top_trend[0]["count"]),
                    }
                )
            else:
                daily_top_trends_7d.append(
                    {
                        "day": str(day_value),
                        "term": "N/A",
                        "count": 0,
                    }
                )

    # All-time top discussion topics from filtered post corpus
    all_time_texts = dataframe.get("text", pd.Series(dtype=str)).dropna().astype(str).tolist()
    # global_trends_all_time = extract_trends_from_texts(all_time_texts, top_n=10)

    # Calculate Correlations with Sentiment
    metrics = ["like_count", "retweet_count", "reply_count", "impression_count"]
    correlation_data = []
    
    # Global Correlation for current filtered view
    global_corr = {"affiliation": "Global (Filtered)", "is_global": True}
    for m in metrics:
        global_corr[m] = _get_correlation(dataframe, m)
        global_corr[f"{m}_7d"] = _get_correlation(week_df, m)
    correlation_data.append(global_corr)
    
    # Per Affiliation in current view
    if not dataframe.empty:
        affs = sorted(dataframe["affiliation"].unique())
        for aff in affs:
            if pd.isna(aff):
                continue
            aff_str = str(aff)
            sub_df = dataframe[dataframe["affiliation"] == aff]
            sub_week_df = week_df[week_df["affiliation"] == aff] if not week_df.empty else pd.DataFrame()
            row = {"affiliation": aff_str, "is_global": False}
            for m in metrics:
                row[m] = _get_correlation(sub_df, m)
                row[f"{m}_7d"] = _get_correlation(sub_week_df, m)
            correlation_data.append(row)

    context = {
        "line_chart": line_fig.to_html(full_html=False, include_plotlyjs=False, div_id="daily-line-chart"),
        "bar_chart": bar_fig.to_html(full_html=False, include_plotlyjs=False, div_id="affiliation-bar-chart"),
        "affiliation_options": affiliation_options,
        "selected_affiliation": selected_affiliation,
        "day_breakdown": day_breakdown,
        "global_trends": global_trends_7d,
        # "global_trends_all_time": global_trends_all_time,
        "global_trends_7d": global_trends_7d,
        "daily_top_trends_7d": daily_top_trends_7d,
        "trends_by_affiliation": trends_by_affiliation,
        "correlation_data": correlation_data,
        "n8n_reply_data": _get_latest_n8n_reply_data(active_workspace_id),
        "n8n_reply_auth_value": f"Bearer {N8N_REPLY_AUTH_TOKEN}",
        "user_dashboards": user_dashboards,
        "active_user_dashboard": active_workspace,
        "workspace_items": workspace_items,
        "active_workspace_id": active_workspace_id,
        "active_workspace_name": active_workspace_name,
    }
    return render(request, "dashboard/index.html", context)
