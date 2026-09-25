"""One place that loads the local models and keeps them between runs.

Most of a run's time used to be spent loading (importing torch/transformers,
reading ~3 GB of weights from disk), not computing. With KEEP_MODELS_LOADED the
first run pays that once and later runs reuse the loaded models. The models use
about 2.5 GB of GPU memory while loaded; release_models() frees it.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from backend.config import get_settings
from pipeline import nlp_env

log = logging.getLogger(__name__)
T = TypeVar("T")

_models: dict[str, object] = {}
_lock = threading.Lock()


def _get(key: str, load: Callable[[], T]) -> T:
    with _lock:
        if key not in _models:
            started = time.perf_counter()
            _models[key] = load()
            log.info("loaded %s in %.1fs", key, time.perf_counter() - started)
        return _models[key]  # type: ignore[return-value]


def encoder():
    from pipeline.embeddings.encoder import Encoder

    name = get_settings().embedding_model
    return _get(f"embeddings ({name})", lambda: Encoder(name))


def sentiment():
    from pipeline.sentiment.classifier import SentimentClassifier

    name = get_settings().sentiment_model
    return _get(f"sentiment ({name})", lambda: SentimentClassifier(name))


def entities():
    from pipeline.entities.extractor import EntityExtractor

    settings = get_settings()

    def load():
        extractor = EntityExtractor(settings.hindi_ner_model, settings.hindi_ner_tokenizer)
        extractor.warm_up()
        return extractor

    return _get(f"entities ({settings.hindi_ner_model})", load)


def release_models() -> None:
    with _lock:
        while _models:
            key, model = _models.popitem()
            model.close()  # type: ignore[attr-defined]
            log.info("released %s", key)
    nlp_env.release_gpu()
