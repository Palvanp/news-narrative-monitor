"""Stage 2: embeddings, near-duplicate dedup, topic relevance, sentiment, entities.

Models are loaded one at a time and released before the next, so peak GPU use
stays within a 6 GB card.
"""

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import Article, ArticleEmbedding, ArticleEntity, Entity, Monitor, MonitoringRun, SentimentScore
from backend.services.progress import Reporter
from pipeline.cleaning.dedup import near_duplicates
from pipeline.embeddings.encoder import Encoder, article_text
from pipeline.entities.extractor import EntityExtractor, Mention
from pipeline.sentiment.classifier import SentimentClassifier, sentiment_text


def topic_text(monitor: Monitor) -> str:
    return f"{monitor.topic} {monitor.hindi_keywords or ''}".strip()


def enrich(session: Session, run: MonitoringRun, monitor: Monitor, report: Reporter) -> None:
    settings = get_settings()
    articles = list(
        session.scalars(
            select(Article)
            .where(Article.run_id == run.id, Article.duplicate_of.is_(None))
            .order_by(Article.published_at, Article.id)
        )
    )
    if not articles:
        raise RuntimeError("No articles were collected for this monitor; try a broader topic or longer time range")

    report("embed", 0.0, f"Embedding {len(articles)} articles")
    encoder = Encoder(settings.embedding_model)
    try:
        vectors = encoder.encode([article_text(a.title, a.body) for a in articles])
        topic_vector = encoder.encode([topic_text(monitor)])[0]
    finally:
        encoder.close()

    near = near_duplicates(vectors, [a.language for a in articles])
    active: list[Article] = []
    for article, vector, dup in zip(articles, vectors, near):
        article.embedding = ArticleEmbedding(model=settings.embedding_model, vector=vector)
        article.relevance = float(vector @ topic_vector)
        if dup is None:
            active.append(article)
        else:
            article.duplicate_of = articles[dup].id
            article.dedup_reason = "near_dup"
    session.commit()

    report("sentiment", 0.35, f"Classifying sentiment for {len(active)} articles")
    classifier = SentimentClassifier(settings.sentiment_model)
    try:
        predictions = classifier.predict([sentiment_text(a.title, a.body) for a in active])
    finally:
        classifier.close()
    for article, pred in zip(active, predictions):
        article.sentiment = SentimentScore(
            model=settings.sentiment_model,
            label=pred.label,
            positive=pred.positive,
            neutral=pred.neutral,
            negative=pred.negative,
        )
    session.commit()

    report("entities", 0.6, f"Extracting entities from {len(active)} articles")
    extractor = EntityExtractor(settings.hindi_ner_model)
    try:
        mentions = extractor.extract_many([(a.title, a.body, a.language) for a in active])
    finally:
        extractor.close()
    store_entities(session, active, mentions)

    run.stats = {
        **(run.stats or {}),
        "near_duplicates": sum(d is not None for d in near),
        "enriched": len(active),
        "sentiment": dict(Counter(p.label for p in predictions)),
    }
    session.commit()
    report("entities", 1.0, "Enrichment complete")


def store_entities(session: Session, articles: list[Article], mentions: list[Counter]) -> None:
    cache: dict[tuple[str, str], Entity] = {}

    def get_entity(canonical: str, etype: str) -> Entity:
        # NER casing varies ("Commerce Ministry" / "commerce ministry"); key on casefold.
        key = (canonical.casefold(), etype)
        if key not in cache:
            entity = session.scalar(
                select(Entity).where(Entity.canonical_name == canonical, Entity.type == etype)
            )
            if entity is None:
                entity = Entity(canonical_name=canonical, type=etype)
                session.add(entity)
                session.flush()
            cache[key] = entity
        return cache[key]

    for article, counter in zip(articles, mentions):
        # group case variants together so each entity appears once per article
        grouped: dict[tuple[str, str], Counter] = defaultdict(Counter)
        names: dict[tuple[str, str], str] = {}
        for mention, count in counter.items():
            mention: Mention
            key = (mention.canonical.casefold(), mention.type)
            names.setdefault(key, mention.canonical)
            grouped[key][mention.surface] += count
        for key, surfaces in grouped.items():
            entity = get_entity(names[key], key[1])
            article.entities.append(
                ArticleEntity(
                    entity=entity,
                    surface_form=surfaces.most_common(1)[0][0],
                    count=sum(surfaces.values()),
                )
            )
    session.commit()
