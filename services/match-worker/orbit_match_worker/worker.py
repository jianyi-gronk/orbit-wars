"""Queue consumer that runs authoritative live and accelerated matches."""

from __future__ import annotations

import importlib
import json
import logging
import os
import signal
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from orbit_api.builtin_strategies.basic import agent as basic_agent
from orbit_api.db.base import utc_now
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    StrategyVersion,
)
from orbit_api.db.session import SessionLocal
from orbit_api.domain.ratings import RatingError, RatingService
from orbit_api.infrastructure.match_queue import RedisMatchQueue
from orbit_api.storage.replays import S3ReplayStore
from orbit_contracts.models import CommandBatchV1, ObservationV1
from orbit_engine import decode_raw_action
from orbit_runtime.infrastructure import InfrastructureSettings
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_match_worker.engine.adapter import EngineAdapter
from orbit_match_worker.replay import ReplayStreamWriter, persist_replay
from orbit_match_worker.runtime.agent_executor import observation_payload
from orbit_match_worker.runtime.controllers import (
    CommandValidationError,
    validate_command_batch,
)

logger = logging.getLogger("orbit.worker")


@dataclass(frozen=True, slots=True)
class ParticipantSpec:
    slot: int
    controller_type: ControllerType
    strategy_slug: str
    fleet_public_id: str
    fleet_name: str
    strategy_version_public_id: str | None


@dataclass(frozen=True, slots=True)
class QueuedMatch:
    public_id: str
    ruleset_id: str
    seed: int
    map_id: str
    mode: MatchMode
    participants: tuple[ParticipantSpec, ParticipantSpec]


class MatchWorker:
    """Consume queued match IDs and publish live state through Redis."""

    def __init__(
        self,
        client: Redis,
        *,
        turn_seconds: float = 2.5,
        replay_store: Any | None = None,
        replay_directory: Path | None = None,
    ) -> None:
        self.client = client
        self.turn_seconds = turn_seconds
        self.replay_store = replay_store or S3ReplayStore.from_environment()
        self.replay_directory = replay_directory or Path(
            os.environ.get(
                "ORBIT_REPLAY_TMP_DIR",
                str(Path(tempfile.gettempdir()) / "orbit-wars-replays"),
            )
        )
        self.running = True

    @classmethod
    def from_environment(cls) -> MatchWorker:
        settings = InfrastructureSettings.from_environment()
        seconds = float(os.environ.get("ORBIT_TURN_SECONDS", "2.5"))
        return cls(
            Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=max(10.0, seconds + 2.0),
            ),
            turn_seconds=seconds,
        )

    def stop(self, *_args: object) -> None:
        self.running = False

    def serve(self) -> None:
        logger.info("match worker ready")
        while self.running:
            queued = self.client.blpop(RedisMatchQueue.queue_name, timeout=1)
            if queued is None:
                continue
            _queue, match_id = cast(tuple[str, str], queued)
            try:
                spec = self._load(match_id)
                if spec is not None:
                    self._run(spec)
            except Exception:
                logger.exception("match execution failed", extra={"matchId": match_id})
                self._mark_failed(match_id, "platform.execution_error")

    def _load(self, public_id: str) -> QueuedMatch | None:
        with SessionLocal() as session:
            match = session.scalar(select(Match).where(Match.public_id == public_id))
            if match is None or match.status not in {MatchStatus.QUEUED, MatchStatus.PREPARING}:
                return None
            rows = list(
                session.scalars(
                    select(MatchParticipant)
                    .where(MatchParticipant.match_id == match.id)
                    .order_by(MatchParticipant.slot)
                )
            )
            if len(rows) != 2 or tuple(row.slot for row in rows) != (0, 1):
                raise RuntimeError("match participants are incomplete")
            participant_specs: list[ParticipantSpec] = []
            for row in rows:
                fleet = session.get(Fleet, row.fleet_id)
                version = (
                    session.get(StrategyVersion, row.strategy_version_id)
                    if row.strategy_version_id
                    else None
                )
                if fleet is None:
                    raise RuntimeError("match participant fleet is missing")
                participant_specs.append(
                    ParticipantSpec(
                        row.slot,
                        row.controller_type,
                        self._strategy_slug(session, row),
                        fleet.public_id,
                        fleet.name,
                        version.public_id if version else None,
                    )
                )
            match.status = MatchStatus.PREPARING
            session.commit()
            return QueuedMatch(
                public_id=match.public_id,
                ruleset_id=match.ruleset_id,
                seed=match.seed,
                map_id=match.map_id,
                mode=match.mode,
                participants=cast(
                    tuple[ParticipantSpec, ParticipantSpec],
                    tuple(participant_specs),
                ),
            )

    @staticmethod
    def _strategy_slug(session: Session, participant: MatchParticipant) -> str:
        if participant.strategy_version_id is None:
            return "basic-v1"
        version = session.get(StrategyVersion, participant.strategy_version_id)
        if version is None or not version.object_key.startswith("builtin://"):
            return "basic-v1"
        return version.object_key.removeprefix("builtin://")

    def _run(self, spec: QueuedMatch) -> None:
        replay_path = self.replay_directory / f"{spec.public_id}.jsonl.gz"
        writer = ReplayStreamWriter(
            replay_path,
            match={
                "publicId": spec.public_id,
                "rulesetId": spec.ruleset_id,
                "seed": spec.seed,
                "mapId": spec.map_id,
                "mode": spec.mode.value,
            },
            participants=[
                {
                    "fleetPublicId": participant.fleet_public_id,
                    "fleetName": participant.fleet_name,
                    "slot": participant.slot,
                    "controllerType": participant.controller_type.value,
                    "strategyVersionId": participant.strategy_version_public_id,
                }
                for participant in spec.participants
            ],
        )
        adapter = EngineAdapter(spec.ruleset_id)
        initial = adapter.reset(seed=spec.seed, slots=(0, 1))
        writer.append(initial, ([], []))
        self._set_status(spec.public_id, MatchStatus.RUNNING)
        self._publish_snapshots(spec.public_id, adapter, initial.step)
        command_cursor = "0-0"

        while self.running and not adapter.done:
            step = adapter.snapshot().step
            deadline = datetime.now(UTC) + timedelta(seconds=self.turn_seconds)
            observations = cast(
                tuple[ObservationV1, ObservationV1],
                tuple(
                    self._observation(spec.public_id, adapter, slot, deadline) for slot in (0, 1)
                ),
            )
            self._publish_event(
                spec.public_id,
                {
                    "type": "turn.open",
                    "step": step,
                    "deadlineAt": deadline.isoformat().replace("+00:00", "Z"),
                },
            )
            actions: list[list[list[int | float]]] = [[], []]
            human_slots = {
                participant.slot
                for participant in spec.participants
                if participant.controller_type == ControllerType.HUMAN
            }
            for participant in spec.participants:
                if participant.controller_type == ControllerType.AGENT:
                    observation = observations[participant.slot].model_dump(
                        mode="json", by_alias=True
                    )
                    actions[participant.slot] = _builtin_action(
                        participant.strategy_slug,
                        observation,
                    )

            submissions, command_cursor = self._human_actions(
                spec.public_id,
                observations,
                human_slots,
                command_cursor,
                deadline,
            )
            for slot, commands in submissions.items():
                actions[slot] = commands

            result = adapter.step([decode_raw_action(batch) for batch in actions])
            writer.append(result.snapshot, (actions[0], actions[1]))
            self._publish_event(
                spec.public_id,
                {"type": "turn.closed", "step": step},
            )
            self._publish_event(
                spec.public_id,
                {
                    "type": "match.frame",
                    "payload": self._frame_payload(spec.public_id, result.snapshot),
                },
            )
            self._publish_snapshots(spec.public_id, adapter, result.snapshot.step)

        final = adapter.snapshot()
        winners = [slot for slot, reward in enumerate(final.rewards) if reward == 1]
        outcome = {
            "winnerSlot": winners[0] if len(winners) == 1 else None,
            "reason": "step_limit"
            if final.step >= final.config.episode_steps - 1
            else "elimination",
            "finalStep": final.step,
            "rewards": list(final.rewards),
        }
        info = writer.finalize({**outcome, "endedAt": utc_now().isoformat()})
        persist_replay(
            spec.public_id,
            info.path.read_bytes(),
            frame_count=info.frame_count,
            session_factory=SessionLocal,
            store=self.replay_store,
        )
        info.path.unlink(missing_ok=True)
        self._finish(spec.public_id, outcome)
        self._publish_event(spec.public_id, {"type": "match.finished", "result": outcome})

    def _human_actions(
        self,
        match_id: str,
        observations: tuple[ObservationV1, ObservationV1],
        human_slots: set[int],
        cursor: str,
        deadline: datetime,
    ) -> tuple[dict[int, list[list[int | float]]], str]:
        if not human_slots:
            return {}, cursor
        commands: dict[int, list[list[int | float]]] = {}
        stream = f"orbit:match:{match_id}:commands:v1"
        while self.running and commands.keys() != human_slots:
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                break
            rows = self.client.xread(
                {stream: cursor},
                block=max(1, int(remaining * 1000)),
                count=100,
            )
            for _stream, entries in cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], rows):
                for row_id, fields in entries:
                    cursor = row_id
                    slot = int(fields["slot"])
                    if slot not in human_slots or slot in commands:
                        continue
                    try:
                        payload = json.loads(fields["payload"])
                        batch = CommandBatchV1.model_validate(payload)
                        validate_command_batch(batch, observations[slot], slot=slot)
                    except (ValueError, CommandValidationError):
                        continue
                    commands[slot] = [
                        [command.from_planet_id, command.angle, command.ships]
                        for command in batch.commands
                    ]
        return commands, cursor

    def _observation(
        self,
        match_id: str,
        adapter: EngineAdapter,
        slot: int,
        deadline: datetime,
    ) -> ObservationV1:
        payload = observation_payload(match_id, adapter.snapshot(player=slot), player=slot)
        payload["deadlineAt"] = deadline
        return ObservationV1.model_validate(payload)

    def _frame_payload(self, match_id: str, snapshot: Any) -> dict[str, Any]:
        payload = observation_payload(match_id, snapshot, player=0)
        return {"step": payload["step"], "planets": payload["planets"], "fleets": payload["fleets"]}

    def _publish_snapshots(self, match_id: str, adapter: EngineAdapter, step: int) -> None:
        deadline = datetime.now(UTC) + timedelta(seconds=self.turn_seconds)
        for slot in (0, 1):
            observation = self._observation(match_id, adapter, slot, deadline)
            event = {
                "type": "match.snapshot",
                "payload": observation.model_dump(mode="json", by_alias=True),
            }
            self.client.set(
                f"orbit:match:{match_id}:snapshot:{slot}:v1",
                json.dumps(event, separators=(",", ":")),
                ex=3600,
            )
        logger.debug("published snapshot", extra={"matchId": match_id, "step": step})

    def _publish_event(self, match_id: str, event: dict[str, Any]) -> None:
        self.client.xadd(
            f"orbit:match:{match_id}:events:v1",
            {"payload": json.dumps(event, separators=(",", ":"))},
            maxlen=4096,
        )

    def _set_status(self, match_id: str, status: MatchStatus) -> None:
        with SessionLocal() as session:
            match = session.scalar(select(Match).where(Match.public_id == match_id))
            if match is None:
                raise RuntimeError("match disappeared during execution")
            match.status = status
            session.commit()

    def _finish(self, match_id: str, outcome: dict[str, Any]) -> None:
        with SessionLocal() as session:
            match = session.scalar(select(Match).where(Match.public_id == match_id))
            if match is None:
                raise RuntimeError("match disappeared during finalization")
            match.status = MatchStatus.FINISHED
            match.result = outcome
            match.finished_at = utc_now()
            session.commit()
            if match.mode == MatchMode.RANKED and outcome.get("winnerSlot") in (0, 1):
                try:
                    RatingService().apply_once(session, match.id)
                except RatingError:
                    logger.warning(
                        "ranked match could not be settled",
                        extra={"matchId": match_id},
                    )

    def _mark_failed(self, match_id: str, code: str) -> None:
        with SessionLocal() as session:
            match = session.scalar(select(Match).where(Match.public_id == match_id))
            if match is None or match.status in {MatchStatus.FINISHED, MatchStatus.CANCELLED}:
                return
            match.status = MatchStatus.FAILED
            match.result = {"reason": code}
            match.finished_at = utc_now()
            session.commit()
        self._publish_event(
            match_id,
            {"type": "match.error", "code": code, "recoverable": False},
        )


def _builtin_action(slug: str, observation: dict[str, Any]) -> list[list[int | float]]:
    if slug == "kaggle-structured-v11":
        module = importlib.import_module(
            "orbit_api.builtin_strategies.kaggle_structured_v11.entrypoint"
        )
        return cast(list[list[int | float]], module.agent(observation))
    return basic_agent(observation)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    worker = MatchWorker.from_environment()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    worker.serve()


if __name__ == "__main__":
    main()
