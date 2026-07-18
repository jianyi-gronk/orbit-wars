from orbit_api.db.base import Base
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    Rating,
    User,
)
from orbit_api.domain.matchmaking import ChallengeRestricted, Matchmaker
from orbit_api.domain.ratings import RatingService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _fleet(session: Session, index: int, score: float) -> Fleet:
    user = User(oidc_subject=f"matchmaker-{index}")
    session.add(user)
    session.flush()
    fleet = Fleet(
        owner_user_id=user.id,
        name=f"Fleet {index}",
        commander_code=f"MM-{index}",
        style_description="An original orbital frame.",
    )
    session.add(fleet)
    session.flush()
    session.add(Rating(fleet_id=fleet.id, mu=15 + score / 100, sigma=5, display_score=score))
    session.flush()
    return fleet


def _finished_pair(session: Session, left: Fleet, right: Fleet, *, multiplier: float = 1) -> Match:
    match = Match(
        ruleset_id="orbit-wars-2p-v1",
        seed=7,
        mode=MatchMode.RANKED,
        status=MatchStatus.FINISHED,
        rating_multiplier=multiplier,
        result={"winnerSlot": 0, "reason": "elimination"},
    )
    session.add(match)
    session.flush()
    session.add_all(
        [
            MatchParticipant(
                match_id=match.id,
                fleet_id=left.id,
                slot=0,
                controller_type=ControllerType.HUMAN,
            ),
            MatchParticipant(
                match_id=match.id,
                fleet_id=right.id,
                slot=1,
                controller_type=ControllerType.AGENT,
            ),
        ]
    )
    session.commit()
    return match


def test_matchmaker_uses_one_pool_for_all_controller_combinations_and_penalizes_repeats() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        own = _fleet(session, 0, 500)
        close = _fleet(session, 1, 520)
        alternate = _fleet(session, 2, 650)
        session.commit()

        assert Matchmaker().find(session, own, "human").opponent.id == close.id
        _finished_pair(session, own, close)
        human_offer = Matchmaker().find(session, own, "human")
        agent_offer = Matchmaker().find(session, own, "agent")

        assert human_offer.opponent.id == alternate.id
        assert agent_offer.opponent.id == alternate.id
        assert human_offer.reason == agent_offer.reason


def test_repeated_challenge_stops_rating_movement_and_then_is_restricted() -> None:
    import pytest

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        winner = _fleet(session, 10, 1000)
        opponent = _fleet(session, 11, 900)
        session.commit()
        matches = [_finished_pair(session, winner, opponent) for _ in range(3)]
        matches[-1].rating_multiplier = 0
        session.commit()
        before = {
            rating.fleet_id: (rating.mu, rating.sigma, rating.display_score)
            for rating in (session.get(Rating, winner.id), session.get(Rating, opponent.id))
            if rating is not None
        }

        event = RatingService().apply_once(session, matches[-1].id)
        after = {
            rating.fleet_id: (rating.mu, rating.sigma, rating.display_score)
            for rating in (session.get(Rating, winner.id), session.get(Rating, opponent.id))
            if rating is not None
        }

        assert before == after
        assert all(change["delta"] == 0 for change in event.changes)
        with pytest.raises(ChallengeRestricted):
            Matchmaker().challenge(session, winner, opponent)
