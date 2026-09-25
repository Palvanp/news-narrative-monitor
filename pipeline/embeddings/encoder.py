"""Multilingual sentence embeddings (BAAI/bge-m3 by default), L2-normalized float32."""

import numpy as np

from pipeline import nlp_env

LEAD_CHARS = 1500


def article_text(title: str, body: str | None, max_chars: int = LEAD_CHARS) -> str:
    """Title plus the article lead: enough to place the story without the long tail."""
    if not body:
        return title
    return f"{title}\n{body[:max_chars]}"


class Encoder:
    def __init__(self, model_name: str, device: str | None = None, max_seq_length: int = 512):
        import torch
        from sentence_transformers import SentenceTransformer

        self.device = device or nlp_env.resolve_device()
        kwargs = {"torch_dtype": torch.float16} if self.device == "cuda" else {}
        self.model = SentenceTransformer(model_name, device=self.device, model_kwargs=kwargs)
        self.model.max_seq_length = max_seq_length
        self.model_name = model_name

    def encode(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.model.get_sentence_embedding_dimension()), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)

    def close(self) -> None:
        del self.model
        nlp_env.release_gpu()


# The embedding model is needed by several stages of one run (articles, then
# evidence sentences). Loading it twice doubles peak RAM while it initializes,
# so one instance is shared per process until the run releases it.
_shared: dict[str, Encoder] = {}


def shared_encoder(model_name: str) -> Encoder:
    if model_name not in _shared:
        _shared[model_name] = Encoder(model_name)
    return _shared[model_name]


def release_shared_encoders() -> None:
    while _shared:
        _shared.popitem()[1].close()
