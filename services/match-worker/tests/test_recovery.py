from __future__ import annotations

import pytest
from orbit_engine import OrbitEngine
from orbit_match_worker.engine import PlayerControllerError
from orbit_match_worker.runtime.recovery import (
    Checkpoint,
    DeterminismRecoveryError,
    DisconnectTracker,
    FinalizationCoordinator,
    MatchJournal,
    MemoryRecoveryStore,
    recover_engine,
)


def run_steps(engine: OrbitEngine, journal: MatchJournal | None, count: int) -> None:
    for _ in range(count):
        step = engine.snapshot().step
        actions = [[], []]
        snapshot = engine.step_raw(actions).snapshot
        if journal:
            journal.record(step, actions, snapshot)


def test_worker_recovery_replays_checkpoint_and_tail_to_identical_hash() -> None:
    seed = 20260718
    baseline = OrbitEngine()
    baseline.reset(seed=seed)
    run_steps(baseline, None, 80)

    store = MemoryRecoveryStore()
    journal = MatchJournal("match-recover", store)
    interrupted = OrbitEngine()
    interrupted.reset(seed=seed)
    run_steps(interrupted, journal, 37)
    recovered = recover_engine("match-recover", seed, store)
    run_steps(recovered, journal, 43)

    assert recovered.snapshot().step == 80
    assert recovered.snapshot().state_hash == baseline.snapshot().state_hash
    assert store.latest_checkpoint("match-recover").step == 80


def test_corrupt_checkpoint_fails_unscored_instead_of_guessing() -> None:
    store = MemoryRecoveryStore()
    journal = MatchJournal("match-corrupt", store)
    engine = OrbitEngine()
    engine.reset(seed=9)
    run_steps(engine, journal, 20)
    store.checkpoints["match-corrupt"][20] = Checkpoint(20, "0" * 64)

    with pytest.raises(DeterminismRecoveryError, match="state hash"):
        recover_engine("match-corrupt", 9, store)


def test_command_persistence_is_idempotent_across_short_store_retry() -> None:
    store = MemoryRecoveryStore()
    journal = MatchJournal("match-retry", store)
    engine = OrbitEngine()
    engine.reset(seed=3)
    snapshot = engine.step_raw([[], []]).snapshot
    journal.record(0, [[], []], snapshot)
    journal.record(0, [[], []], snapshot)
    assert len(store.commands("match-retry")) == 1


def test_human_ten_consecutive_misses_forfeit_but_reconnect_resets_counter() -> None:
    tracker = DisconnectTracker()
    for _ in range(9):
        tracker.record(0, False, human=True)
    tracker.record(0, True, human=True)
    for _ in range(9):
        tracker.record(0, False, human=True)
    with pytest.raises(PlayerControllerError) as captured:
        tracker.record(0, False, human=True)
    assert captured.value.slot == 0
    assert captured.value.code == "human.consecutive_disconnects"


class FlakyUploader:
    def __init__(self) -> None:
        self.calls = 0

    def upload_once(self, match_id: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary object storage failure")
        return f"replay:{match_id}"


class OnceRating:
    def __init__(self) -> None:
        self.calls = 0

    def settle_once(self, match_id: str) -> None:
        del match_id
        self.calls += 1


def test_finalizing_retries_upload_and_never_duplicates_rating() -> None:
    coordinator = FinalizationCoordinator()
    uploader = FlakyUploader()
    rating = OnceRating()
    with pytest.raises(OSError):
        coordinator.finalize("match-final", uploader, rating, ranked_and_scoreable=True)
    completed = coordinator.finalize("match-final", uploader, rating, ranked_and_scoreable=True)
    duplicate = coordinator.finalize("match-final", uploader, rating, ranked_and_scoreable=True)

    assert completed.finished is True
    assert completed.replay_id == "replay:match-final"
    assert duplicate is completed
    assert uploader.calls == 2
    assert rating.calls == 1
