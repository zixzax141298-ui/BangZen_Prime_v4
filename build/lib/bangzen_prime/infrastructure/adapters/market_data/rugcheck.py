"""RugCheck adapter. Endpoint: GET /tokens/{mint}/report/summary under the configured base URL.

Schema assumption (from third-party documentation, NOT verified against an official schema
in this environment): `score_normalised` is 0-100 where higher means more risk. The raw
`score` is never used as a safety score. A `Rugged` flag is taken from `rugged` or from a
danger-level risk entry named "Rugged".
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import quote

from bangzen_prime.domain.tokens import SafetyAssessment, validate_chain, validate_mint
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.market_data.parsing import (
    MalformedData,
    to_decimal,
)
from bangzen_prime.infrastructure.http import Transport, get_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

SERVICE = "rugcheck"


class RugCheckAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        transport: Transport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock

    def fetch_safety(self, chain: str, mint: str) -> SafetyAssessment:
        validate_chain(chain)
        validate_mint(mint)
        url = f"{self._base}/tokens/{quote(mint, safe='')}/report/summary"
        data = self._caller.call(
            lambda: get_json(
                service=SERVICE,
                url=url,
                timeout=self._timeout,
                transport=self._transport,
            )
        )
        if not isinstance(data, dict):
            raise MalformedData(SERVICE, "expected an object")
        if "score_normalised" not in data:
            raise MalformedData(SERVICE, "score_normalised missing")
        risk = to_decimal(
            data["score_normalised"], service=SERVICE, field="score_normalised"
        )
        rugged = _rugged_flag(data)
        try:
            return SafetyAssessment.create(
                chain=chain,
                mint=mint,
                risk_score=risk,
                rugged=rugged,
                source=SERVICE,
                checked_at=self._clock(),
            )
        except DomainError as exc:
            raise MalformedData(SERVICE, str(exc)) from None


def _rugged_flag(data: dict[str, Any]) -> bool:
    flag = data.get("rugged", False)
    if not isinstance(flag, bool):
        raise MalformedData(SERVICE, "rugged must be boolean when present")
    if flag:
        return True
    risks = data.get("risks") or []
    if not isinstance(risks, list):
        raise MalformedData(SERVICE, "risks must be a list when present")
    return any(
        isinstance(r, dict) and r.get("name") == "Rugged" and r.get("level") == "danger"
        for r in risks
    )
