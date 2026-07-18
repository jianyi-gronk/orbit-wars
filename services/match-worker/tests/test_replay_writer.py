import gzip
import json
from pathlib import Path

import pytest
from orbit_engine import OrbitEngine
from orbit_match_worker.replay import ReplayStreamWriter


def records(path: Path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def test_long_replay_streams_checkpoints_deltas_commands_and_checksum(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl.gz"
    writer = ReplayStreamWriter(
        path,
        match={
            "publicId": "match-public",
            "rulesetId": "orbit-wars-2p-v1",
            "seed": 42,
            "privateTicket": "must-not-leak",
        },
        participants=[
            {
                "fleetPublicId": "fleet-a",
                "slot": 0,
                "controllerType": "human",
                "sessionTicket": "must-not-leak",
            },
            {
                "fleetPublicId": "fleet-b",
                "slot": 1,
                "controllerType": "agent",
                "sourceCode": "must-not-leak",
            },
        ],
    )
    engine = OrbitEngine()
    snapshot = engine.reset(seed=42)
    writer.append(snapshot, ([], []))
    for _ in range(100):
        snapshot = engine.step_raw([[], []]).snapshot
        writer.append(snapshot, ([], []))
    info = writer.finalize(
        {"winnerSlot": None, "reason": "step_limit", "finalStep": 100, "stack": "secret"}
    )
    decoded = records(path)

    assert info.frame_count == 101
    assert info.checkpoint_count == 6
    assert len(info.checksum) == 64
    assert decoded[0]["type"] == "header"
    assert decoded[1]["type"] == "checkpoint"
    assert decoded[2]["type"] == "delta"
    assert decoded[21]["type"] == "checkpoint"
    assert decoded[-1]["type"] == "result"
    assert not hasattr(writer, "frames")
    serialized = json.dumps(decoded)
    assert "must-not-leak" not in serialized
    assert "sourceCode" not in serialized
    assert "stack" not in serialized


class FlakyStore:
    def __init__(self) -> None:
        self.calls = 0
        self.content = b""

    def put_immutable(self, key: str, content: bytes):
        del key
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary upload failure")
        self.content = content


def test_upload_failure_can_retry_identical_compressed_artifact(tmp_path: Path) -> None:
    writer = ReplayStreamWriter(
        tmp_path / "retry.jsonl.gz",
        match={"publicId": "match-retry", "rulesetId": "orbit-wars-2p-v1", "seed": 1},
        participants=[],
    )
    writer.append(OrbitEngine().reset(seed=1), ([], []))
    info = writer.finalize({"reason": "failed", "finalStep": 0})
    store = FlakyStore()
    with pytest.raises(OSError):
        writer.upload(store, "replays/match-retry", info)
    writer.upload(store, "replays/match-retry", info)

    import hashlib

    assert hashlib.sha256(store.content).hexdigest() == info.checksum
    assert store.calls == 2
