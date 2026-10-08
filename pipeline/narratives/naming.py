"""Narrative labels and summaries, grounded in each cluster's representative headlines."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from pipeline.llm import LLMClient

SYSTEM = """You label clusters of news coverage for a political analyst.
Use only the headlines and facts provided. Do not add outside knowledge or speculation.
Write in English even when headlines are in Hindi.
The label states the storyline in 4-10 words, neutrally (e.g. "US tariff threat raises concern for Indian exporters"), not just a topic word.
The summary is 1-2 sentences describing what the coverage says."""


class NarrativeName(BaseModel):
    label: str = Field(max_length=120)
    summary: str = Field(max_length=600)


@dataclass
class Headline:
    title: str
    language: str
    source: str | None
    published_at: str


def build_prompt(topic: str, headlines: list[Headline], keywords: list[str], entities: list[str], first_seen: str, last_seen: str) -> str:
    lines = [f"{i}. [{h.language}] {h.title} ({h.source or 'unknown'}, {h.published_at[:16]})" for i, h in enumerate(headlines, 1)]
    return (
        f"Monitored event: {topic}\n"
        f"Coverage period of this cluster: {first_seen[:16]} to {last_seen[:16]} UTC\n"
        f"Top entities: {', '.join(entities) or 'none'}\n"
        f"Keywords: {', '.join(keywords) or 'none'}\n\n"
        "Representative headlines:\n" + "\n".join(lines) + "\n\nReturn the label and summary."
    )


def name_narrative(client: LLMClient, model: str, topic: str, headlines: list[Headline], keywords: list[str], entities: list[str], first_seen: str, last_seen: str) -> NarrativeName:
    prompt = build_prompt(topic, headlines, keywords, entities, first_seen, last_seen)
    return client.generate(model, SYSTEM, prompt, NarrativeName, num_predict=200)
