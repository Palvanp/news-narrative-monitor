"""Class-based TF-IDF keywords per narrative, for English and Hindi text together."""

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

HINDI_STOP_WORDS = set(
    """का की के में है हैं और से को पर यह ने एक भी कि था थे थी इस इसके लिए तो ही कर किया
    गया गई गए हो रहे रहा रही साथ बाद अब जो नहीं या तक वह वे उन उनके उसके अपने करने कहा होगा
    दिया सकते बताया जा ना लेकर द्वारा बीच वाले वाली होने हुए हुई कुछ कई इन इसे उसे जब तब यहां वहां
    सबसे बहुत अधिक करते करता करती किए लिया लेकिन क्योंकि अगर फिर साल दिन खबर न्यूज़ समाचार""".split()
)
EXTRA_STOP_WORDS = {"said", "says", "news", "also", "new", "year", "years", "just", "like", "according", "report", "reports"}
STOP_WORDS = list(ENGLISH_STOP_WORDS | HINDI_STOP_WORDS | EXTRA_STOP_WORDS)

# Latin words of 3+ letters, or Devanagari runs (letters plus vowel signs) of 2+ characters.
TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b|[\u0900-\u097F]{2,}"


def ctfidf_keywords(texts: list[str], labels: list[int], top_k: int = 8) -> dict[int, list[str]]:
    """Top keywords for each cluster label (noise label -1 is ignored)."""
    clusters = sorted({lbl for lbl in labels if lbl >= 0})
    if not clusters:
        return {}
    docs = [" ".join(t for t, lbl in zip(texts, labels) if lbl == c) for c in clusters]
    vectorizer = CountVectorizer(
        token_pattern=TOKEN_PATTERN,
        lowercase=True,
        stop_words=STOP_WORDS,
        ngram_range=(1, 2),
        min_df=1,
    )
    counts = vectorizer.fit_transform(docs).toarray().astype(float)
    vocab = np.array(vectorizer.get_feature_names_out())

    tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
    avg_words = counts.sum() / len(clusters)
    idf = np.log(1 + avg_words / np.maximum(counts.sum(axis=0), 1))
    scores = tf * idf

    result = {}
    for row, c in enumerate(clusters):
        top = np.argsort(scores[row])[::-1]
        picked: list[str] = []
        for idx in top:
            if scores[row, idx] <= 0 or len(picked) >= top_k:
                break
            term = vocab[idx]
            # skip a unigram already covered by a picked bigram, and vice versa
            if any(term in p.split() or p in term.split() for p in picked):
                continue
            picked.append(term)
        result[c] = picked
    return result
