from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import (
    DailyAffiliationMetric,
    DailyGlobalMetric,
    Post,
    Rolling7dAffiliationMetric,
    Rolling7dGlobalMetric,
)


def get_day_click_payload(day):
    global_row = DailyGlobalMetric.objects.filter(day=day).first()
    aff_rows = DailyAffiliationMetric.objects.filter(day=day).order_by("affiliation")

    if not global_row:
        return None

    rows = [
        {
            "affiliation": row.affiliation,
            "post_count": row.posts_count,
            "likes": row.likes_sum,
            "retweets": row.retweets_sum,
            "replies": row.replies_sum,
            "impressions": row.impressions_sum,
            "trends": row.top_trends,
        }
        for row in aff_rows
    ]

    return {
        "rows": rows,
        "total_posts": global_row.posts_count,
        "trends": global_row.top_trends,
        "sentiment_distribution": [
            {"spectrum": row.affiliation, "sentiment_label": "negative", "count": row.negative_count}
            for row in aff_rows
        ]
        + [
            {"spectrum": row.affiliation, "sentiment_label": "neutral", "count": row.neutral_count}
            for row in aff_rows
        ]
        + [
            {"spectrum": row.affiliation, "sentiment_label": "positive", "count": row.positive_count}
            for row in aff_rows
        ],
    }


def get_latest_week_posts(limit=300):
    start_dt = timezone.now() - timedelta(days=7)
    return Post.objects.filter(created_at__gte=start_dt).order_by("-created_at")[:limit]


def get_latest_week_metrics_snapshot():
    last_global = Rolling7dGlobalMetric.objects.order_by("-window_end_day").first()
    if not last_global:
        return None

    by_aff = list(
        Rolling7dAffiliationMetric.objects.filter(window_end_day=last_global.window_end_day).order_by("affiliation")
    )
    return {
        "window_end_day": last_global.window_end_day,
        "global": last_global,
        "by_affiliation": by_aff,
    }


def compute_live_week_metrics_from_posts():
    start_dt = timezone.now() - timedelta(days=7)
    week_qs = Post.objects.filter(created_at__gte=start_dt)

    global_metrics = week_qs.aggregate(
        posts_count=Count("id"),
        avg_sentiment=Avg("sentiment_score"),
        likes_sum=Sum("like_count"),
        retweets_sum=Sum("retweet_count"),
        replies_sum=Sum("reply_count"),
        quotes_sum=Sum("quote_count"),
        impressions_sum=Sum("impression_count"),
        positive_count=Count("id", filter=Q(sentiment_label="positive")),
        neutral_count=Count("id", filter=Q(sentiment_label="neutral")),
        negative_count=Count("id", filter=Q(sentiment_label="negative")),
    )

    by_affiliation = []
    for affiliation in week_qs.values_list("affiliation", flat=True).distinct().order_by("affiliation"):
        sub = week_qs.filter(affiliation=affiliation)
        by_affiliation.append(
            {
                "affiliation": affiliation,
                "posts_count": sub.count(),
                "avg_sentiment": sub.aggregate(v=Avg("sentiment_score"))["v"] or 0,
                "likes_sum": sub.aggregate(v=Sum("like_count"))["v"] or 0,
                "retweets_sum": sub.aggregate(v=Sum("retweet_count"))["v"] or 0,
                "replies_sum": sub.aggregate(v=Sum("reply_count"))["v"] or 0,
                "quotes_sum": sub.aggregate(v=Sum("quote_count"))["v"] or 0,
                "impressions_sum": sub.aggregate(v=Sum("impression_count"))["v"] or 0,
            }
        )

    return {"global": global_metrics, "by_affiliation": by_affiliation}
