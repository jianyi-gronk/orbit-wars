import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, Request
from orbit_api.db.base import Base
from orbit_api.db.models import Fleet, User
from orbit_api.db.session import database_session
from orbit_api.main import app
from orbit_api.security.oidc import Principal, current_principal
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

VALID_FLEET = {
    "name": "Ash Meridian",
    "commanderCode": "AM-07",
    "declaration": "We cross the quiet line and return with every signal intact.",
    "strategyTendency": "balanced",
    "styleDescription": (
        "A narrow graphite hull with split amber sails and a circular signal mast."
    ),
}


@pytest.fixture
def fleet_client(tmp_path: Path) -> Iterator[httpx.AsyncClient]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/fleets.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def test_principal(request: Request) -> Principal:
        subject = request.headers.get("X-Test-Subject")
        if not subject:
            raise HTTPException(status_code=401, detail="authentication required")
        return Principal(subject=subject, claims={"name": f"Pilot {subject}"})

    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    try:
        yield client
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        engine.dispose()


def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    subject: str | None = None,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    headers = {"X-Test-Subject": subject} if subject else None

    async def send() -> httpx.Response:
        return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(send())


def test_create_read_edit_and_public_projection(fleet_client: httpx.AsyncClient) -> None:
    created = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-1",
        json=VALID_FLEET,
    )

    assert created.status_code == 201
    profile = created.json()
    public_id = profile["publicId"]
    assert public_id.startswith("fleet_")
    assert set(profile) == {
        "publicId",
        "name",
        "commanderCode",
        "declaration",
        "strategyTendency",
        "styleDescription",
        "createdAt",
    }

    owned = request(
        fleet_client,
        "GET",
        f"/api/v1/fleets/{public_id}",
        subject="owner-1",
    )
    updated = request(
        fleet_client,
        "PATCH",
        f"/api/v1/fleets/{public_id}",
        subject="owner-1",
        json={"name": "Ash Meridian II", "strategyTendency": "defense"},
    )
    public = request(fleet_client, "GET", f"/api/public/v1/fleets/{public_id}")

    assert owned.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["name"] == "Ash Meridian II"
    assert updated.json()["strategyTendency"] == "defense"
    assert public.status_code == 200
    assert public.json() == updated.json()
    serialized = str(public.json())
    assert "ownerUserId" not in public.json()
    assert "currentStrategyVersionId" not in public.json()
    assert "owner-1" not in serialized


def test_session_and_my_fleet_projection(fleet_client: httpx.AsyncClient) -> None:
    session = request(fleet_client, "GET", "/api/v1/session", subject="owner-session")
    missing = request(fleet_client, "GET", "/api/v1/me/fleet", subject="owner-session")
    created = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-session",
        json=VALID_FLEET,
    )
    owned = request(fleet_client, "GET", "/api/v1/me/fleet", subject="owner-session")

    assert session.json() == {
        "authenticated": True,
        "subject": "owner-session",
        "displayName": "Pilot owner-session",
    }
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "fleet.not_found"
    assert owned.status_code == 200
    assert owned.json()["publicId"] == created.json()["publicId"]
    assert owned.json()["currentStrategyVersionId"].startswith("strategy_")


def test_duplicate_create_has_stable_conflict(fleet_client: httpx.AsyncClient) -> None:
    first = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-1",
        json=VALID_FLEET,
    )
    duplicate = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-1",
        json={**VALID_FLEET, "name": "Another Fleet"},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "fleet.already_exists"


def test_non_owner_cannot_read_or_edit_private_fleet(
    fleet_client: httpx.AsyncClient,
) -> None:
    created = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-1",
        json=VALID_FLEET,
    )
    public_id = created.json()["publicId"]

    read = request(
        fleet_client,
        "GET",
        f"/api/v1/fleets/{public_id}",
        subject="intruder",
    )
    edit = request(
        fleet_client,
        "PATCH",
        f"/api/v1/fleets/{public_id}",
        subject="intruder",
        json={"name": "Claimed Fleet"},
    )

    assert read.status_code == 404
    assert edit.status_code == 404
    assert read.json()["detail"]["code"] == "fleet.not_found"
    assert edit.json()["detail"]["code"] == "fleet.not_found"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": "A"}, "name"),
        ({"commanderCode": "AM\u0007"}, "commanderCode"),
        ({"declaration": "Read https://example.test"}, "declaration"),
        (
            {"styleDescription": "A Star Wars X-wing copied down to every panel."},
            "styleDescription",
        ),
    ],
)
def test_content_boundaries_return_field_errors(
    fleet_client: httpx.AsyncClient,
    change: dict[str, object],
    field: str,
) -> None:
    response = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject=f"owner-{field}",
        json={**VALID_FLEET, **change},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "fleet.invalid_content",
        "message": response.json()["detail"]["message"],
        "field": field,
    }


def test_invalid_tendency_extra_fields_and_empty_patch_are_rejected(
    fleet_client: httpx.AsyncClient,
) -> None:
    invalid_tendency = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-invalid",
        json={**VALID_FLEET, "strategyTendency": "reckless"},
    )
    extra_field = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-extra",
        json={**VALID_FLEET, "ownerUserId": "not-allowed"},
    )
    invalid_template = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-template",
        json={**VALID_FLEET, "strategyTemplate": "unknown-template"},
    )
    created = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-empty-patch",
        json=VALID_FLEET,
    )
    empty_patch = request(
        fleet_client,
        "PATCH",
        f"/api/v1/fleets/{created.json()['publicId']}",
        subject="owner-empty-patch",
        json={},
    )

    assert invalid_tendency.status_code == 422
    assert invalid_template.status_code == 422
    assert extra_field.status_code == 422
    assert empty_patch.status_code == 422
    assert empty_patch.json()["detail"]["code"] == "fleet.empty_update"


def test_profile_text_is_normalized_without_losing_paragraphs(
    fleet_client: httpx.AsyncClient,
) -> None:
    created = request(
        fleet_client,
        "POST",
        "/api/v1/fleets",
        subject="owner-normalized",
        json={
            **VALID_FLEET,
            "name": "  Ash   Meridian  ",
            "declaration": "First line.  \r\nSecond\tline.",
        },
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Ash Meridian"
    assert created.json()["declaration"] == "First line.\nSecond line."


def test_database_owner_constraint_is_the_final_single_fleet_guard(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/constraint.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(oidc_subject="constraint-owner")
        session.add(user)
        session.flush()
        session.add_all(
            [
                Fleet(
                    owner_user_id=user.id,
                    name="One Fleet",
                    commander_code="ONE",
                    style_description="A copper crescent with three narrow engine vanes.",
                ),
                Fleet(
                    owner_user_id=user.id,
                    name="Second Fleet",
                    commander_code="TWO",
                    style_description="A silver ring with a broad asymmetric engine vane.",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        assert session.scalars(select(Fleet)).all() == []
