from __future__ import annotations

import re
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q, Sum
from sklearn.feature_extraction.text import CountVectorizer

from dashboard.models import (
    DailyAffiliationMetric,
    DailyGlobalMetric,
    Post,
    Rolling7dAffiliationMetric,
    Rolling7dGlobalMetric,
)


class Command(BaseCommand):
    help = "Rebuild daily and rolling-7-day aggregate metric tables from Main Post data."

    def _extract_trends(self, qs, top_n: int = 5):
        texts = [text for text in qs.values_list("text", flat=True) if text]
        if not texts:
            return []

        url_pattern = re.compile(r"https?://\S+|www\.\S+")
        clean_texts = [url_pattern.sub("", str(text)) for text in texts]

        try:
            vec = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_df=1.0)
            matrix = vec.fit_transform(clean_texts)
            counts = matrix.sum(axis=0).A1
            terms = vec.get_feature_names_out()

            sorted_indices = counts.argsort()[::-1][:top_n]
            return [{"term": terms[i], "count": int(counts[i])} for i in sorted_indices]
        except ValueError:
            return []

    def handle(self, *args, **options):
        main_posts = Post.objects.filter(source_dashboard__isnull=True)
        all_days = list(main_posts.order_by("day").values_list("day", flat=True).distinct())
        if not all_days:
            self.stdout.write(self.style.WARNING("No Main posts found. Nothing to aggregate."))
            return

        DailyGlobalMetric.objects.all().delete()
        DailyAffiliationMetric.objects.all().delete()
        Rolling7dGlobalMetric.objects.all().delete()
        Rolling7dAffiliationMetric.objects.all().delete()

        for day in all_days:
            day_qs = main_posts.filter(day=day)

            daily_global = day_qs.aggregate(
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

            DailyGlobalMetric.objects.create(
                day=day,
                posts_count=daily_global["posts_count"] or 0,
                avg_sentiment=daily_global["avg_sentiment"] or 0,
                likes_sum=daily_global["likes_sum"] or 0,
                retweets_sum=daily_global["retweets_sum"] or 0,
                replies_sum=daily_global["replies_sum"] or 0,
                quotes_sum=daily_global["quotes_sum"] or 0,
                impressions_sum=daily_global["impressions_sum"] or 0,
                positive_count=daily_global["positive_count"] or 0,
                neutral_count=daily_global["neutral_count"] or 0,
                negative_count=daily_global["negative_count"] or 0,
                top_trends=self._extract_trends(day_qs, top_n=5),
            )

            affiliations = day_qs.values_list("affiliation", flat=True).distinct()
            for aff in affiliations:
                aff_qs = day_qs.filter(affiliation=aff)
                aff_agg = aff_qs.aggregate(
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

                DailyAffiliationMetric.objects.create(
                    day=day,
                    affiliation=aff,
                    posts_count=aff_agg["posts_count"] or 0,
                    avg_sentiment=aff_agg["avg_sentiment"] or 0,
                    likes_sum=aff_agg["likes_sum"] or 0,
                    retweets_sum=aff_agg["retweets_sum"] or 0,
                    replies_sum=aff_agg["replies_sum"] or 0,
                    quotes_sum=aff_agg["quotes_sum"] or 0,
                    impressions_sum=aff_agg["impressions_sum"] or 0,
                    positive_count=aff_agg["positive_count"] or 0,
                    neutral_count=aff_agg["neutral_count"] or 0,
                    negative_count=aff_agg["negative_count"] or 0,
                    top_trends=self._extract_trends(aff_qs, top_n=3),
                )

            start_day = day - timedelta(days=6)
            week_qs = main_posts.filter(day__gte=start_day, day__lte=day)
            week_global = week_qs.aggregate(
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

            Rolling7dGlobalMetric.objects.create(
                window_end_day=day,
                posts_count=week_global["posts_count"] or 0,
                avg_sentiment=week_global["avg_sentiment"] or 0,
                likes_sum=week_global["likes_sum"] or 0,
                retweets_sum=week_global["retweets_sum"] or 0,
                replies_sum=week_global["replies_sum"] or 0,
                quotes_sum=week_global["quotes_sum"] or 0,
                impressions_sum=week_global["impressions_sum"] or 0,
                positive_count=week_global["positive_count"] or 0,
                neutral_count=week_global["neutral_count"] or 0,
                negative_count=week_global["negative_count"] or 0,
                top_trends=self._extract_trends(week_qs, top_n=10),
            )

            week_affiliations = week_qs.values_list("affiliation", flat=True).distinct()
            for aff in week_affiliations:
                aff_week_qs = week_qs.filter(affiliation=aff)
                week_aff = aff_week_qs.aggregate(
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

                Rolling7dAffiliationMetric.objects.create(
                    window_end_day=day,
                    affiliation=aff,
                    posts_count=week_aff["posts_count"] or 0,
                    avg_sentiment=week_aff["avg_sentiment"] or 0,
                    likes_sum=week_aff["likes_sum"] or 0,
                    retweets_sum=week_aff["retweets_sum"] or 0,
                    replies_sum=week_aff["replies_sum"] or 0,
                    quotes_sum=week_aff["quotes_sum"] or 0,
                    impressions_sum=week_aff["impressions_sum"] or 0,
                    positive_count=week_aff["positive_count"] or 0,
                    neutral_count=week_aff["neutral_count"] or 0,
                    negative_count=week_aff["negative_count"] or 0,
                    top_trends=self._extract_trends(aff_week_qs, top_n=5),
                )

        self.stdout.write(self.style.SUCCESS("Daily and rolling 7-day metrics refreshed."))
