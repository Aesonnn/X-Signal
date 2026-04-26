from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

import pandas as pd
import requests

from .models import Post, UserDashboard
from .sentiment import RobertaSentimentScorer


API_BASE = "https://api.x.com/2"


def _format_api_error(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc) or "Unknown request error"

    response_text = (response.text or "").strip()
    if len(response_text) > 1200:
        response_text = response_text[:1200] + "..."

    base_message = f"X API request failed (HTTP {response.status_code})"
    if response_text:
        return f"{base_message}: {response_text}"
    return base_message


def _parse_accounts_with_affiliation(raw_accounts: str) -> list[tuple[str, str]]:
    if not raw_accounts:
        return []

    entries = [part.strip() for part in re.split(r"[\n,]+", raw_accounts) if part.strip()]
    result: list[tuple[str, str]] = []
    for entry in entries:
        if "|" in entry:
            account, affiliation = [part.strip() for part in entry.split("|", 1)]
        elif ":" in entry:
            account, affiliation = [part.strip() for part in entry.split(":", 1)]
        else:
            continue

        account = account.lstrip("@").strip()
        aff = affiliation.upper()
        if not account or aff not in {"L", "C"}:
            continue

        canonical = "Liberal (L)" if aff == "L" else "Conservative (C)"
        result.append((account, canonical))

    return result


def _build_time_window(days: int) -> tuple[str, str]:
    now_utc = datetime.now(timezone.utc)
    # recent search requires end_time to be slightly in the past.
    end_utc = now_utc - timedelta(minutes=1)
    start_utc = end_utc - timedelta(days=max(7, days))
    # recent search supports up to ~7 days from the current time, not end_time.
    min_supported_start = now_utc - timedelta(days=7)
    if start_utc < min_supported_start:
        start_utc = min_supported_start
    return (
        start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _build_author_query(username: str) -> str:
    normalized = username.lstrip("@").strip()
    return f"from:{normalized} -is:reply -is:retweet"


def _fetch_user_posts(
    username: str,
    headers: dict[str, str],
    start_time: str,
    end_time: str,
    max_results: int,
) -> list[dict[str, Any]]:
    safe_max_results = max(10, min(100, max_results))
    params = {
        "query": _build_author_query(username),
        "max_results": safe_max_results,
        "tweet.fields": "id,text,author_id,public_metrics,created_at",
        "start_time": start_time,
        "end_time": end_time,
    }
    response = requests.get(
        f"{API_BASE}/tweets/search/recent",
        headers=headers,
        params=params,
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", [])


def sync_workspace_posts(
    workspace: UserDashboard,
    window_days: int = 7,
    max_results_per_account: int = 30,
) -> dict[str, Any]:
    api_key = (workspace.x_api_key or "").strip()
    accounts = _parse_accounts_with_affiliation(workspace.selected_accounts or "")

    if not api_key:
        return {"ok": False, "error": "Workspace API key is missing."}
    if not accounts:
        return {"ok": False, "error": "Workspace selected accounts are empty."}

    headers = {"Authorization": f"Bearer {api_key}"}
    start_time, end_time = _build_time_window(window_days)
    sentiment = RobertaSentimentScorer()

    processed_accounts = 0
    skipped_accounts = 0
    created_posts = 0
    updated_posts = 0

    for account, canonical_affiliation in accounts:
        account_label = account
        processed_accounts += 1
        try:
            posts = _fetch_user_posts(account, headers, start_time, end_time, max_results_per_account)
        except requests.RequestException as exc:
            return {"ok": False, "error": _format_api_error(exc)}

        if not posts:
            skipped_accounts += 1
            continue

        for post in posts:
            post_id_raw = post.get("id")
            if not post_id_raw:
                continue

            text = str(post.get("text") or "")
            created_at = pd.to_datetime(post.get("created_at"), errors="coerce", utc=True)
            if pd.isna(created_at):
                continue

            public_metrics = post.get("public_metrics") or {}
            if not isinstance(public_metrics, dict):
                public_metrics = {}

            sentiment_score, sentiment_label = sentiment.score(text)

            _, created = Post.objects.update_or_create(
                source_dashboard=workspace,
                x_post_id=int(post_id_raw),
                defaults={
                    "author_id": int(post.get("author_id") or 0),
                    "author_name": str(account_label)[:120],
                    "affiliation": canonical_affiliation,
                    "text": text,
                    "created_at": created_at.to_pydatetime(),
                    "day": created_at.date(),
                    "sentiment_score": sentiment_score,
                    "sentiment_label": sentiment_label,
                    "like_count": int(public_metrics.get("like_count", 0) or 0),
                    "retweet_count": int(public_metrics.get("retweet_count", 0) or 0),
                    "reply_count": int(public_metrics.get("reply_count", 0) or 0),
                    "quote_count": int(public_metrics.get("quote_count", 0) or 0),
                    "impression_count": int(public_metrics.get("impression_count", 0) or 0),
                    "public_metrics": public_metrics,
                },
            )
            if created:
                created_posts += 1
            else:
                updated_posts += 1

    return {
        "ok": True,
        "processed_accounts": processed_accounts,
        "skipped_accounts": skipped_accounts,
        "created_posts": created_posts,
        "updated_posts": updated_posts,
    }
