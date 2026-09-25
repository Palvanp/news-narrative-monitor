"""Three-way sentiment with a multilingual XLM-R model.

The default model (cardiffnlp/twitter-xlm-roberta-base-sentiment) was trained on
tweets in 8 languages including Hindi; news headlines are a domain shift, which
the evaluation measures. Input is the headline plus the article's first sentences.
"""

import re
from dataclasses import dataclass

from pipeline import nlp_env

LABELS = ("negative", "neutral", "positive")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=।)\s*")


@dataclass
class Sentiment:
    label: str
    negative: float
    neutral: float
    positive: float


def sentiment_text(title: str, body: str | None, lead_sentences: int = 2, max_chars: int = 600) -> str:
    if not body:
        return title
    lead = " ".join(_SENTENCE_END.split(body.replace("\n", " "))[:lead_sentences])
    return f"{title}. {lead}"[:max_chars]


def _normalize_label(raw: str) -> str:
    raw = raw.lower()
    if raw.startswith("label_"):
        return LABELS[int(raw.removeprefix("label_"))]
    return raw


class SentimentClassifier:
    def __init__(self, model_name: str, device: str | None = None):
        from transformers import pipeline

        device = device or nlp_env.resolve_device()
        self.model_name = model_name
        self.pipe = pipeline(
            "text-classification",
            model=model_name,
            tokenizer=model_name,
            device=0 if device == "cuda" else -1,
            top_k=None,
        )

    def predict(self, texts: list[str], batch_size: int = 32) -> list[Sentiment]:
        if not texts:
            return []
        outputs = self.pipe(texts, batch_size=batch_size, truncation=True, max_length=256)
        results = []
        for scores in outputs:
            by_label = {_normalize_label(s["label"]): float(s["score"]) for s in scores}
            label = max(by_label, key=by_label.get)
            results.append(Sentiment(label=label, **{k: by_label.get(k, 0.0) for k in LABELS}))
        return results

    def close(self) -> None:
        del self.pipe
        nlp_env.release_gpu()
