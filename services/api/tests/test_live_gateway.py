from datetime import UTC, datetime

from fastapi.testclient import TestClient
from orbit_api.domain.match_tickets import MatchTicketService
from orbit_api.infrastructure.live_bus import MemoryLiveMatchBus
from orbit_api.main import app


def snapshot(match_id: str, slot: int) -> dict[str, object]:
    return {
        "type": "match.snapshot",
        "payload": {
            "schemaVersion": 1,
            "matchId": match_id,
            "step": 4,
            "player": slot,
            "deadlineAt": datetime(2026, 7, 18, tzinfo=UTC).isoformat(),
            "angularVelocity": 0.01,
            "planets": [],
            "fleets": [],
            "initialPlanets": [],
            "comets": [],
        },
    }


def ticket(service: MatchTicketService, match_id: str, slot: int) -> str:
    return service.issue(
        match_id=match_id,
        fleet_id=f"fleet-{slot}",
        slot=slot,
        subject=f"player-{slot}",
    ).token


def test_two_slots_receive_scoped_snapshot_and_publish_private_commands() -> None:
    match_id = "match-live-1"
    service = MatchTicketService("a-secure-test-ticket-secret-value")
    bus = MemoryLiveMatchBus()
    bus.snapshots[(match_id, 0)] = snapshot(match_id, 0)
    bus.snapshots[(match_id, 1)] = snapshot(match_id, 1)
    app.state.match_ticket_service = service
    app.state.live_match_bus = bus
    try:
        with TestClient(app) as client:
            with client.websocket_connect(
                f"/api/live/v1/matches/{match_id}?ticket={ticket(service, match_id, 0)}"
            ) as first:
                assert first.receive_json()["payload"]["player"] == 0
                first.send_json(
                    {
                        "type": "turn.submit",
                        "payload": {
                            "schemaVersion": 1,
                            "matchId": match_id,
                            "expectedStep": 4,
                            "commands": [],
                            "idempotencyKey": "socket-command-0",
                        },
                    }
                )
                accepted = first.receive_json()
                assert accepted["type"] == "turn.accepted"
                assert len(accepted["commandHash"]) == 64
            with client.websocket_connect(
                f"/api/live/v1/matches/{match_id}?ticket={ticket(service, match_id, 1)}"
            ) as second:
                assert second.receive_json()["payload"]["player"] == 1
        assert [(item[0], item[1]) for item in bus.commands] == [(match_id, 0)]
        assert "commands" not in bus.snapshots[(match_id, 1)]
    finally:
        del app.state.match_ticket_service
        del app.state.live_match_bus


def test_resync_sorts_and_deduplicates_authoritative_events() -> None:
    match_id = "match-live-2"
    service = MatchTicketService("another-secure-test-ticket-secret")
    bus = MemoryLiveMatchBus()
    bus.snapshots[(match_id, 0)] = snapshot(match_id, 0)
    frame = {"type": "match.frame", "payload": {"step": 6}}
    bus.events[match_id] = [frame, {"type": "turn.closed", "step": 5}, frame]
    app.state.match_ticket_service = service
    app.state.live_match_bus = bus
    try:
        with (
            TestClient(app) as client,
            client.websocket_connect(
                f"/api/live/v1/matches/{match_id}?ticket={ticket(service, match_id, 0)}"
            ) as socket,
        ):
            socket.receive_json()
            socket.send_json({"type": "match.resync", "lastSeenStep": 4})
            assert socket.receive_json() == {"type": "turn.closed", "step": 5}
            assert socket.receive_json() == frame
    finally:
        del app.state.match_ticket_service
        del app.state.live_match_bus
