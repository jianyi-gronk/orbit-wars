from orbit_api.db.base import Base
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchParticipant,
    Rating,
    StrategyVersion,
    User,
)
from orbit_api.domain.warmup import WARMUP_AGENTS, provision_warmup
from orbit_api.infrastructure.match_queue import MemoryMatchQueue
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def test_warmup_provisions_real_agents_and_fixtures_exactly_once() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    queue = MemoryMatchQueue()

    with Session(engine, expire_on_commit=False) as session:
        first = provision_warmup(session, queue)
        second = provision_warmup(session, queue)

        assert first.created_fleets == 6
        assert first.created_matches == 6
        assert second.created_fleets == 0
        assert second.created_matches == 0
        assert second.fleet_public_ids == first.fleet_public_ids
        assert second.match_public_ids == first.match_public_ids
        assert queue.items == list(first.match_public_ids)
        assert session.scalar(select(func.count()).select_from(User)) == 6
        assert session.scalar(select(func.count()).select_from(Fleet)) == 6
        assert session.scalar(select(func.count()).select_from(Rating)) == 6
        assert session.scalar(select(func.count()).select_from(Match)) == 6

        subjects = set(session.scalars(select(User.oidc_subject)))
        assert subjects == {agent.subject for agent in WARMUP_AGENTS}
        object_keys = set(session.scalars(select(StrategyVersion.object_key)))
        assert object_keys == {"builtin://basic-v1", "builtin://kaggle-structured-v11"}
        controllers = set(session.scalars(select(MatchParticipant.controller_type)))
        assert controllers == {ControllerType.AGENT}


def test_warmup_can_provision_opponents_without_queueing_matches() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    queue = MemoryMatchQueue()

    with Session(engine) as session:
        result = provision_warmup(session, queue, match_count=0)

        assert result.created_fleets == 6
        assert result.created_matches == 0
        assert result.match_public_ids == ()
        assert queue.items == []
