import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db import init_db
from backend.models import Article, ArticleEmbedding, Monitor, MonitoringRun


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_embedding_roundtrip_on_sqlite(session):
    run = MonitoringRun(monitor=Monitor(topic="India-US trade negotiations"))
    session.add(run)
    session.flush()
    article = Article(run_id=run.id, url="https://a.in/x", normalized_url="a.in/x", title="t")
    vec = np.random.default_rng(0).random(1024, dtype=np.float32)
    article.embedding = ArticleEmbedding(model="test", vector=vec)
    session.add(article)
    session.commit()
    session.expire_all()

    stored = session.get(ArticleEmbedding, article.id).vector
    assert stored.dtype == np.float32
    np.testing.assert_array_equal(stored, vec)


def test_embedding_rejects_wrong_dimension(session):
    run = MonitoringRun(monitor=Monitor(topic="x"))
    session.add(run)
    session.flush()
    article = Article(run_id=run.id, url="u", normalized_url="u", title="t")
    article.embedding = ArticleEmbedding(model="test", vector=np.zeros(3))
    session.add(article)
    with pytest.raises(Exception, match="1024-d"):
        session.commit()
