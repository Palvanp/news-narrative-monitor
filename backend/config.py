from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default (naming, brief) models per LLM provider; LLM_NAMING_MODEL / LLM_BRIEF_MODEL override.
DEFAULT_LLM_MODELS = {
    # gpt-oss-20b made factual slips naming narratives (wrong acronym expansions), so
    # Groq uses the 120b model for both; 12 naming calls per run are well within limits.
    "groq": ("openai/gpt-oss-120b", "openai/gpt-oss-120b"),
    "ollama": ("qwen2.5:3b-instruct", "qwen2.5:7b-instruct"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///data/nazar.db"

    # groq (hosted API, default) or ollama (self-hosted server)
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_url: str = "https://api.groq.com/openai/v1"
    # Prompt size cap for Groq. The free tier allows ~8K tokens per minute, counting
    # the prompt plus the answer budget; long brief prompts are trimmed to fit.
    groq_max_prompt_tokens: int = 4500
    # 127.0.0.1 rather than "localhost": on Windows "localhost" tries IPv6 first,
    # which adds seconds when nothing is listening.
    ollama_url: str = "http://127.0.0.1:11434"
    llm_naming_model: str = ""
    llm_brief_model: str = ""
    llm_timeout_seconds: float = 600.0

    device: str = "auto"
    embedding_model: str = "BAAI/bge-m3"
    sentiment_model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    # Open Hindi NER (IIT Bombay HiNER on MuRIL). Its repo ships no usable vocabulary,
    # so the tokenizer comes from the base model it was fine-tuned from.
    hindi_ner_model: str = "cfilt/HiNER-collapsed-muril-base-cased"
    hindi_ner_tokenizer: str = "google/muril-base-cased"
    # Keep the NLP models loaded between runs (faster repeat runs; holds ~2.5 GB of
    # GPU memory and some RAM while the server runs). False frees them after each run.
    keep_models_loaded: bool = True

    # comma-separated: rss, gdelt. GDELT's API rate-limits heavily, so it is off by default.
    news_sources: str = "rss"

    # articles less similar than this to the monitor topic are left out of clustering
    # Floor, not the main filter: bge-m3 similarity between an article and a short
    # topic phrase is blunt (see docs/JOURNAL.md). Narrative cohesion does most of the work.
    relevance_min: float = 0.33

    data_dir: Path = PROJECT_ROOT / "data"

    @model_validator(mode="after")
    def _default_llm_models(self) -> "Settings":
        self.llm_provider = self.llm_provider.strip().lower()
        if self.llm_provider not in DEFAULT_LLM_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_LLM_MODELS)}")
        naming, brief = DEFAULT_LLM_MODELS[self.llm_provider]
        self.llm_naming_model = self.llm_naming_model or naming
        self.llm_brief_model = self.llm_brief_model or brief
        return self

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
