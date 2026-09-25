from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///data/nazar.db"

    ollama_url: str = "http://localhost:11434"
    llm_naming_model: str = "qwen2.5:3b-instruct"
    llm_brief_model: str = "qwen2.5:7b-instruct"
    llm_timeout_seconds: float = 600.0

    device: str = "auto"
    embedding_model: str = "BAAI/bge-m3"
    sentiment_model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    # Open Hindi NER (IIT Bombay HiNER on MuRIL). Its repo ships no usable vocabulary,
    # so the tokenizer comes from the base model it was fine-tuned from.
    hindi_ner_model: str = "cfilt/HiNER-collapsed-muril-base-cased"
    hindi_ner_tokenizer: str = "google/muril-base-cased"
    # comma-separated: rss, gdelt. GDELT's API rate-limits heavily, so it is off by default.
    news_sources: str = "rss"

    # articles less similar than this to the monitor topic are left out of clustering
    relevance_min: float = 0.0

    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def enabled_sources(self) -> list[str]:
        return [s.strip().lower() for s in self.news_sources.split(",") if s.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Relative SQLite paths are resolved against the project root, not the cwd."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            path = Path(self.database_url[len(prefix):])
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{path.as_posix()}"
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
