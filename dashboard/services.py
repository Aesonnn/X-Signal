from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import nltk
import pandas as pd
from nltk.sentiment import SentimentIntensityAnalyzer


TWITTER_EPOCH_MS = 1288834974657
DATA_PATH = Path(__file__).resolve().parent.parent / "recent_posts_from_ids.csv"


def ensure_vader() -> None:
    nltk.download("vader_lexicon", quiet=True)


def tweet_id_to_datetime(tweet_id: str | int) -> datetime:
    tweet_id_int = int(tweet_id)
    timestamp_ms = (tweet_id_int >> 22) + TWITTER_EPOCH_MS
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def load_and_prepare_data(path: Path = DATA_PATH) -> pd.DataFrame:
    ensure_vader()
    sentiment = SentimentIntensityAnalyzer()

    df = pd.read_csv(path)
    df = df.copy()
    df["text"] = df.get("text", "").fillna("").astype(str)
    df["spectrum"] = df.get("spectrum", "Unknown").fillna("Unknown").astype(str).str.strip()

    if "created_at" in df.columns:
        created = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    elif "date" in df.columns:
        created = pd.to_datetime(df["date"], errors="coerce", utc=True)
    else:
        created = pd.to_datetime(df["id"].apply(tweet_id_to_datetime), errors="coerce", utc=True)

    df["created_at"] = created
    df = df.dropna(subset=["created_at"]).copy()
    df["day"] = df["created_at"].dt.date.astype(str)

    # Parse public_metrics if available
    metric_cols = ["like_count", "retweet_count", "reply_count", "quote_count", "impression_count"]
    if "public_metrics" in df.columns:
        def _parse(val):
            if not isinstance(val, str):
                return {}
            try:
                parsed = ast.literal_eval(val)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, SyntaxError):
                return {}
        
        metrics_extracted = df["public_metrics"].apply(_parse).apply(pd.Series)
        # Rename if they don't match exactly, but usually they come as snake_case
        for col in metric_cols:
            if col in metrics_extracted.columns:
                df[col] = pd.to_numeric(metrics_extracted[col], errors="coerce").fillna(0)
            else:
                df[col] = 0
    else:
        for col in metric_cols:
            df[col] = 0

    df["sentiment_score"] = df["text"].apply(lambda value: float(sentiment.polarity_scores(value)["compound"]))
    df["sentiment_label"] = pd.cut(
        df["sentiment_score"],
        bins=[-1.0001, -0.2, 0.2, 1.0001],
        labels=["negative", "neutral", "positive"],
    )

    return df
