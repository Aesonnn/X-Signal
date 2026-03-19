from __future__ import annotations

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"


class RobertaSentimentScorer:
    def __init__(self, model_name: str = MODEL_NAME):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        self.id2label = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        self.weights = torch.tensor([self._label_to_score(self.id2label[i]) for i in range(len(self.id2label))])

    @staticmethod
    def _normalize_label(label: str) -> str:
        if "neg" in label:
            return "negative"
        if "neu" in label:
            return "neutral"
        return "positive"

    def _label_to_score(self, label: str) -> float:
        normalized = self._normalize_label(label)
        if normalized == "negative":
            return -1.0
        if normalized == "neutral":
            return 0.0
        return 1.0

    def score(self, text: str) -> tuple[float, str]:
        encoded = self.tokenizer(text, truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**encoded).logits[0]
        probabilities = torch.softmax(logits, dim=-1)
        sentiment_score = float(torch.dot(probabilities, self.weights).item())

        if sentiment_score <= -0.2:
            sentiment_label = "negative"
        elif sentiment_score >= 0.2:
            sentiment_label = "positive"
        else:
            sentiment_label = "neutral"

        return sentiment_score, sentiment_label