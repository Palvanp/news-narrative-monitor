"""Shared setup for the local NLP models: cache location and device selection.

Import this before transformers/sentence-transformers so model downloads land
under data/models on the project drive (C: is full on the dev machine).
"""

import gc
import os

from backend.config import get_settings

_settings = get_settings()
os.environ.setdefault("HF_HOME", str(_settings.data_dir / "models" / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(_settings.data_dir / "models" / "torch"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def resolve_device() -> str:
    if _settings.device != "auto":
        return _settings.device
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def release_gpu() -> None:
    """Free cached GPU memory after a model is dropped, so the next one fits in 6 GB."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
