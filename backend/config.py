from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipeline.safety.defences import parse_defences

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default (naming, brief) models per LLM provider; LLM_NAMING_MODEL / LLM_BRIEF_MODEL override.
DEFAULT_LLM_MODELS = {
    # gpt-oss-20b made factual slips naming narratives (wrong acronym expansions), so
    # Groq uses the 120b model for both; 12 naming calls per run are well within limits.
    "groq": ("openai/gpt-oss-120b", "openai/gpt-oss-120b"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///data/nazar.db"

    # hosted LLM API; groq is the only provider
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_url: str = "https://api.groq.com/openai/v1"
    # Prompt size cap for Groq. The free tier allows ~8K tokens per minute, counting
    # the prompt plus the answer budget; long brief prompts are trimmed to fit.
    groq_max_prompt_tokens: int = 4500
    llm_naming_model: str = ""
    llm_brief_model: str = ""

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
    # Compute the home page's trending topics when the API starts (reads all feeds once).
    trending_warm_up: bool = True

    # articles less similar than this to the monitor topic are left out of clustering
    # Floor, not the main filter: bge-m3 similarity between an article and a short
    # topic phrase is blunt (see docs/JOURNAL.md). Narrative cohesion does most of the work.
    relevance_min: float = 0.33

    # Prompt-injection defences applied to fetched article pages: any of
    # "html,unicode,filter", "all", or empty for none. See pipeline/safety/defences.py
    # and docs/redteam.md for what each blocks and costs.
    injection_defences: str = ""

    data_dir: Path = PROJECT_ROOT / "data"

    @model_validator(mode="after")
    def _default_llm_models(self) -> "Settings":
        self.llm_provider = self.llm_provider.strip().lower()
        if self.llm_provider not in DEFAULT_LLM_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_LLM_MODELS)}")
        naming, brief = DEFAULT_LLM_MODELS[self.llm_provider]
        self.llm_naming_model = self.llm_naming_model or naming
        self.llm_brief_model = self.llm_brief_model or brief
        parse_defences(self.injection_defences)  # fail at startup on a typo
        return self

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
