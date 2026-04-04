from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db import models


User = get_user_model()


class Post(models.Model):
    SENTIMENT_CHOICES = [
        ("negative", "negative"),
        ("neutral", "neutral"),
        ("positive", "positive"),
    ]

    source_dashboard = models.ForeignKey(
        "UserDashboard",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    x_post_id = models.BigIntegerField()
    author_id = models.BigIntegerField(db_index=True)
    author_name = models.CharField(max_length=120)
    affiliation = models.CharField(max_length=32, db_index=True)
    text = models.TextField()

    created_at = models.DateTimeField(db_index=True)
    day = models.DateField(db_index=True)

    sentiment_score = models.FloatField(db_index=True)
    sentiment_label = models.CharField(max_length=16, choices=SENTIMENT_CHOICES, db_index=True)

    like_count = models.BigIntegerField(default=0)
    retweet_count = models.BigIntegerField(default=0)
    reply_count = models.BigIntegerField(default=0)
    quote_count = models.BigIntegerField(default=0)
    impression_count = models.BigIntegerField(default=0)

    public_metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "posts"
        constraints = [
            models.UniqueConstraint(
                fields=["x_post_id"],
                condition=Q(source_dashboard__isnull=True),
                name="uniq_main_post_xid",
            ),
            models.UniqueConstraint(
                fields=["source_dashboard", "x_post_id"],
                condition=Q(source_dashboard__isnull=False),
                name="uniq_workspace_post_xid",
            ),
        ]
        indexes = [
            models.Index(fields=["source_dashboard", "day"], name="idx_post_dash_day"),
            models.Index(fields=["day", "affiliation"], name="idx_post_day_aff"),
            models.Index(fields=["affiliation", "created_at"], name="idx_post_aff_created"),
            models.Index(fields=["sentiment_label", "day"], name="idx_post_sent_day"),
        ]


class DailyGlobalMetric(models.Model):
    day = models.DateField(unique=True)

    posts_count = models.IntegerField(default=0)
    avg_sentiment = models.FloatField(default=0)

    likes_sum = models.BigIntegerField(default=0)
    retweets_sum = models.BigIntegerField(default=0)
    replies_sum = models.BigIntegerField(default=0)
    quotes_sum = models.BigIntegerField(default=0)
    impressions_sum = models.BigIntegerField(default=0)

    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)

    top_trends = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_global_metrics"


class DailyAffiliationMetric(models.Model):
    day = models.DateField(db_index=True)
    affiliation = models.CharField(max_length=32, db_index=True)

    posts_count = models.IntegerField(default=0)
    avg_sentiment = models.FloatField(default=0)

    likes_sum = models.BigIntegerField(default=0)
    retweets_sum = models.BigIntegerField(default=0)
    replies_sum = models.BigIntegerField(default=0)
    quotes_sum = models.BigIntegerField(default=0)
    impressions_sum = models.BigIntegerField(default=0)

    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)

    top_trends = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_affiliation_metrics"
        constraints = [
            models.UniqueConstraint(fields=["day", "affiliation"], name="uniq_daily_aff_metric"),
        ]
        indexes = [
            models.Index(fields=["day", "affiliation"], name="idx_daily_aff_day_aff"),
        ]


class Rolling7dGlobalMetric(models.Model):
    window_end_day = models.DateField(unique=True)

    posts_count = models.IntegerField(default=0)
    avg_sentiment = models.FloatField(default=0)

    likes_sum = models.BigIntegerField(default=0)
    retweets_sum = models.BigIntegerField(default=0)
    replies_sum = models.BigIntegerField(default=0)
    quotes_sum = models.BigIntegerField(default=0)
    impressions_sum = models.BigIntegerField(default=0)

    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)

    top_trends = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rolling_7d_global_metrics"


class Rolling7dAffiliationMetric(models.Model):
    window_end_day = models.DateField(db_index=True)
    affiliation = models.CharField(max_length=32, db_index=True)

    posts_count = models.IntegerField(default=0)
    avg_sentiment = models.FloatField(default=0)

    likes_sum = models.BigIntegerField(default=0)
    retweets_sum = models.BigIntegerField(default=0)
    replies_sum = models.BigIntegerField(default=0)
    quotes_sum = models.BigIntegerField(default=0)
    impressions_sum = models.BigIntegerField(default=0)

    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)

    top_trends = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rolling_7d_affiliation_metrics"
        constraints = [
            models.UniqueConstraint(fields=["window_end_day", "affiliation"], name="uniq_rolling7_aff_metric"),
        ]
        indexes = [
            models.Index(fields=["window_end_day", "affiliation"], name="idx_roll7_aff_day_aff"),
        ]


class UserDashboard(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_dashboards")
    name = models.CharField(max_length=120)
    selected_accounts = models.TextField(blank=True)
    x_api_key = models.CharField(max_length=255, blank=True)
    fetch_window_days = models.PositiveIntegerField(default=7)
    fetch_posts_per_account = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_dashboards"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_owner_dashboard_name"),
        ]
        indexes = [
            models.Index(fields=["owner", "updated_at"], name="idx_user_dash_owner_updated"),
        ]


class N8NReply(models.Model):
    source_dashboard = models.ForeignKey(
        "UserDashboard",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="n8n_replies",
    )
    workspace_key = models.CharField(max_length=32, db_index=True, default="main")
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    response = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "n8n_replies"
        indexes = [
            models.Index(fields=["workspace_key", "received_at"], name="idx_n8n_reply_ws_received"),
            models.Index(fields=["workspace_key", "requested_at"], name="idx_n8n_reply_ws_requested"),
        ]


class UserProfile(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_USER = "user"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_USER, "User"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_USER, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"
