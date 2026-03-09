from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from nltk.sentiment import SentimentIntensityAnalyzer

from dashboard.models import Post


class Command(BaseCommand):
    help = "Load posts from CSV into Post table (upsert by x_post_id)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="recent_posts_19-2102.csv",
            help="Path to CSV file with posts",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["path"]).resolve()
        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV not found: {csv_path}"))
            return

        df = pd.read_csv(csv_path)
        if df.empty:
            self.stdout.write(self.style.WARNING("CSV is empty. Nothing to ingest."))
            return

        sentiment = SentimentIntensityAnalyzer()
        processed = 0

        with transaction.atomic():
            for _, row in df.iterrows():
                x_post_id = int(row.get("id"))
                text = str(row.get("text") or "")
                author_id = int(row.get("author_id")) if pd.notna(row.get("author_id")) else 0
                author_name = str(row.get("name") or "Unknown")
                affiliation = str(row.get("spectrum") or "Unknown").strip() or "Unknown"

                created_at = pd.to_datetime(row.get("created_at"), errors="coerce", utc=True)
                if pd.isna(created_at):
                    continue

                metrics_raw = row.get("public_metrics")
                metrics = {}
                if isinstance(metrics_raw, str) and metrics_raw.strip():
                    try:
                        parsed = ast.literal_eval(metrics_raw)
                        if isinstance(parsed, dict):
                            metrics = parsed
                    except (ValueError, SyntaxError):
                        metrics = {}

                sentiment_score = float(sentiment.polarity_scores(text)["compound"])
                if sentiment_score <= -0.2:
                    sentiment_label = "negative"
                elif sentiment_score >= 0.2:
                    sentiment_label = "positive"
                else:
                    sentiment_label = "neutral"

                Post.objects.update_or_create(
                    source_dashboard=None,
                    x_post_id=x_post_id,
                    defaults={
                        "author_id": author_id,
                        "author_name": author_name,
                        "affiliation": affiliation,
                        "text": text,
                        "created_at": created_at.to_pydatetime(),
                        "day": created_at.date(),
                        "sentiment_score": sentiment_score,
                        "sentiment_label": sentiment_label,
                        "like_count": int(metrics.get("like_count", 0) or 0),
                        "retweet_count": int(metrics.get("retweet_count", 0) or 0),
                        "reply_count": int(metrics.get("reply_count", 0) or 0),
                        "quote_count": int(metrics.get("quote_count", 0) or 0),
                        "impression_count": int(metrics.get("impression_count", 0) or 0),
                        "public_metrics": metrics,
                    },
                )
                processed += 1

        self.stdout.write(self.style.SUCCESS(f"Ingested/updated {processed} posts from {csv_path.name}"))
