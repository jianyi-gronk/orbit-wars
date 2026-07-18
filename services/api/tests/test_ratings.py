from orbit_api.db.base import Base
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    Rating,
    RatingEvent,
    User,
)
from orbit_api.domain.ratings import (
    RatingError,
    RatingService,
    competitive_rank_for,
    tier_for,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def setup_match(session: Session, *, mode=MatchMode.RANKED, status=MatchStatus.FINISHED):
    users = [User(oidc_subject=f"rating-{index}") for index in range(2)]
    session.add_all(users)
    session.flush()
    fleets = [
        Fleet(
            owner_user_id=users[index].id,
            name=f"Fleet {index}",
            commander_code=f"R-{index}",
            style_description="An original fleet silhouette.",
        )
        for index in range(2)
    ]
    session.add_all(fleets)
    session.flush()
    match = Match(
        ruleset_id="orbit-wars-2p-v1",
        seed=3,
        mode=mode,
        status=status,
        result={"winnerSlot": 0, "reason": "elimination", "finalStep": 30},
    )
    session.add(match)
    session.flush()
    session.add_all(
        MatchParticipant(
            match_id=match.id,
            fleet_id=fleet.id,
            slot=index,
            controller_type=ControllerType.HUMAN if index == 0 else ControllerType.AGENT,
        )
        for index, fleet in enumerate(fleets)
    )
    session.commit()
    return match, fleets


def test_human_and_agent_update_one_rating_each_and_duplicate_finalizing_is_exactly_once() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = RatingService()
    with Session(engine, expire_on_commit=False) as session:
        match, fleets = setup_match(session)
        first = service.apply_once(session, match.id)
        duplicate = service.apply_once(session, match.id)
        ratings = list(session.scalars(select(Rating).order_by(Rating.display_score.desc())))
        event_count = session.scalar(select(func.count()).select_from(RatingEvent))

    assert duplicate.id == first.id
    assert event_count == 1
    assert len(ratings) == 2
    assert ratings[0].fleet_id == fleets[0].id
    assert ratings[0].display_score > ratings[1].display_score
    assert {change["fleetPublicId"] for change in first.changes} == {
        fleet.public_id for fleet in fleets
    }
    assert tier_for(ratings[0].display_score) in {"Cadet", "Orbit", "Vector", "Nova", "Eclipse"}


def test_training_failed_and_unattributed_results_never_settle() -> None:
    import pytest

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = RatingService()
    with Session(engine, expire_on_commit=False) as session:
        training, _fleets = setup_match(session, mode=MatchMode.TRAINING)
        with pytest.raises(RatingError):
            service.apply_once(session, training.id)
        assert session.scalar(select(func.count()).select_from(RatingEvent)) == 0

        training.mode = MatchMode.RANKED
        training.status = MatchStatus.FAILED
        session.commit()
        with pytest.raises(RatingError):
            service.apply_once(session, training.id)
        assert session.scalar(select(func.count()).select_from(RatingEvent)) == 0


def test_unified_score_maps_to_rank_division_and_in_band_points() -> None:
    cases = {
        0: ("bronze", "III", 0),
        99.9: ("bronze", "III", 99.9),
        100: ("bronze", "II", 0),
        299: ("bronze", "I", 99),
        300: ("silver", "III", 0),
        625: ("gold", "III", 25),
        1499: ("diamond", "I", 99),
        1500: ("master", None, 0),
        1725: ("master", None, 225),
    }

    for score, expected in cases.items():
        rank = competitive_rank_for(score)
        assert (rank.tier.value, rank.division, rank.points) == expected
