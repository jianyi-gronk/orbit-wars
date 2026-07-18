"""Quota-controlled, provider-isolated AI assistance for private strategy drafts."""

from __future__ import annotations

import difflib
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Literal, Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import AiAssistRequest, AiCreditAccount, StrategyDraft, User
from orbit_api.domain.strategy_source import validate_source
from orbit_api.security.public_ids import new_public_id

AiAssistKind = Literal["explain", "suggest", "patch"]


class AiAssistError(RuntimeError):
    code = "ai.error"


class AiUnavailableError(AiAssistError):
    code = "ai.unavailable"


class AiQuotaError(AiAssistError):
    code = "ai.quota_exhausted"


class AiRateLimitError(AiAssistError):
    code = "ai.rate_limited"


class AiConsentRequiredError(AiAssistError):
    code = "ai.consent_required"


class AiInvalidResponseError(AiAssistError):
    code = "ai.invalid_response"


@dataclass(frozen=True)
class AiProviderResult:
    summary: str
    reasoning: str
    proposed_source: str
    tests: tuple[str, ...]
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AiAssistResult:
    request_id: str
    summary: str
    reasoning: str
    proposed_source: str
    diff: str
    tests: tuple[str, ...]
    cost: int
    remaining: int


class AiProvider(Protocol):
    model: str

    def complete(
        self,
        *,
        source: str,
        kind: AiAssistKind,
        deep: bool,
        goal: str,
        user_id: str,
    ) -> AiProviderResult: ...


class DeepSeekProvider:
    model = "deepseek-v4-flash"

    def __init__(self, api_key: str, *, base_url: str = "https://api.deepseek.com") -> None:
        if not api_key:
            raise AiUnavailableError("DeepSeek is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_environment(cls) -> DeepSeekProvider:
        return cls(
            os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        )

    def complete(
        self,
        *,
        source: str,
        kind: AiAssistKind,
        deep: bool,
        goal: str,
        user_id: str,
    ) -> AiProviderResult:
        system = (
            "You improve a deterministic Orbit/Wars Python strategy. Return one JSON object with "
            "summary, reasoning, proposedSource, and tests. Never use network, filesystem, "
            "subprocess, environment variables, third-party packages, or change the agent(obs) "
            "entrypoint. "
            "For explain/suggest, proposedSource must equal the input source."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"kind": kind, "goal": goal[:2000], "source": source},
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 8192,
            "temperature": 0.2,
            "user_id": user_id,
            "thinking": {"type": "enabled" if deep else "disabled"},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=45.0,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            usage = body.get("usage", {})
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise AiUnavailableError("the AI provider did not return a usable response") from error
        return _provider_result(parsed, usage, source, kind)


def _provider_result(
    parsed: object,
    usage: object,
    source: str,
    kind: AiAssistKind,
) -> AiProviderResult:
    if not isinstance(parsed, dict):
        raise AiInvalidResponseError("the AI response must be a JSON object")
    summary = parsed.get("summary")
    reasoning = parsed.get("reasoning")
    proposed = parsed.get("proposedSource")
    tests = parsed.get("tests", [])
    if not isinstance(summary, str) or not isinstance(reasoning, str):
        raise AiInvalidResponseError("the AI response is missing explanation fields")
    if not isinstance(proposed, str) or not isinstance(tests, list):
        raise AiInvalidResponseError("the AI response is missing proposed source")
    if kind != "patch":
        proposed = source
    validate_source(proposed)
    normalized_tests = tuple(str(item)[:500] for item in tests[:12])
    usage_value = usage if isinstance(usage, dict) else {}
    return AiProviderResult(
        summary=summary[:4000],
        reasoning=reasoning[:12000],
        proposed_source=proposed,
        tests=normalized_tests,
        input_tokens=max(0, int(usage_value.get("prompt_tokens", 0))),
        output_tokens=max(0, int(usage_value.get("completion_tokens", 0))),
    )


def anonymous_user_id(user_id: object) -> str:
    secret = os.environ.get("ORBIT_AI_USER_SECRET", "local-ai-user-secret-change-me").encode()
    return hmac.new(secret, str(user_id).encode(), hashlib.sha256).hexdigest()


def _daily_limit() -> int:
    try:
        return max(1, int(os.environ.get("ORBIT_AI_DAILY_USER_CREDITS", "5")))
    except ValueError:
        return 5


def _global_budget() -> int:
    try:
        return max(0, int(os.environ.get("ORBIT_AI_DAILY_BUDGET_CREDITS", "10000")))
    except ValueError:
        return 10000


def run_ai_assist(
    session: Session,
    *,
    user: User,
    fleet_id: object,
    draft: StrategyDraft,
    provider: AiProvider,
    kind: AiAssistKind,
    deep: bool,
    goal: str,
    consent: bool,
) -> AiAssistResult:
    if not consent:
        raise AiConsentRequiredError("explicit consent is required")
    cost = 2 if deep else 1
    account = session.get(AiCreditAccount, user.id)
    if account is None or account.remaining < cost:
        raise AiQuotaError("AI credits are exhausted")
    active = session.scalar(
        select(func.count())
        .select_from(AiAssistRequest)
        .where(AiAssistRequest.user_id == user.id, AiAssistRequest.status == "reserved")
    )
    if active:
        raise AiRateLimitError("another AI task is already running")
    today = datetime.now(UTC).date()
    day_start = datetime.combine(today, time.min, tzinfo=UTC)
    succeeded = list(
        session.scalars(
            select(AiAssistRequest).where(
                AiAssistRequest.user_id == user.id,
                AiAssistRequest.status == "succeeded",
            )
        )
    )
    used_today = sum(item.cost for item in succeeded if item.created_at.date() == today)
    if used_today + cost > _daily_limit():
        raise AiRateLimitError("the daily AI credit limit was reached")
    global_used = session.scalar(
        select(func.coalesce(func.sum(AiAssistRequest.cost), 0)).where(
            AiAssistRequest.status == "succeeded",
            AiAssistRequest.created_at >= day_start,
        )
    )
    if int(global_used or 0) + cost > _global_budget():
        raise AiUnavailableError("the daily AI budget is paused")
    record = AiAssistRequest(
        public_id=new_public_id("assist"),
        user_id=user.id,
        fleet_id=fleet_id,
        draft_revision=draft.revision,
        kind=kind,
        cost=cost,
        status="reserved",
        model=provider.model,
    )
    session.add(record)
    session.commit()
    try:
        result = provider.complete(
            source=draft.source_code,
            kind=kind,
            deep=deep,
            goal=goal,
            user_id=anonymous_user_id(user.id),
        )
    except AiAssistError as error:
        record.status = "failed"
        record.error_code = error.code
        record.finished_at = utc_now()
        session.commit()
        raise
    except Exception as error:
        record.status = "failed"
        record.error_code = "ai.unavailable"
        record.finished_at = utc_now()
        session.commit()
        raise AiUnavailableError("the AI provider failed") from error
    account = session.get(AiCreditAccount, user.id)
    if account is None or account.remaining < cost:
        record.status = "failed"
        record.error_code = "ai.quota_exhausted"
        record.finished_at = utc_now()
        session.commit()
        raise AiQuotaError("AI credits are exhausted")
    account.remaining -= cost
    account.updated_at = utc_now()
    record.status = "succeeded"
    record.input_tokens = result.input_tokens
    record.output_tokens = result.output_tokens
    record.finished_at = utc_now()
    session.commit()
    diff = "".join(
        difflib.unified_diff(
            draft.source_code.splitlines(keepends=True),
            result.proposed_source.splitlines(keepends=True),
            fromfile="current/main.py",
            tofile="proposed/main.py",
        )
    )
    return AiAssistResult(
        request_id=record.public_id,
        summary=result.summary,
        reasoning=result.reasoning,
        proposed_source=result.proposed_source,
        diff=diff,
        tests=result.tests,
        cost=cost,
        remaining=account.remaining,
    )
