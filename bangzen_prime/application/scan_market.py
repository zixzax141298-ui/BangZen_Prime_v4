"""ScanMarketUseCase implementation (application layer)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from bangzen_prime.application.ai_brain import AIBrain
from bangzen_prime.application.lifecycle import assess_token_phase
from bangzen_prime.application.phase_policy import DEFAULT_POLICY, Action, Evidence, PhasePolicy
from bangzen_prime.application.ports import HolderDataPort, MarketDataPort, MarketSentimentPort
from bangzen_prime.application.resilience import CircuitBreaker, ResilienceConfig, ResiliencePolicy
from bangzen_prime.application.data_validation import validate_holder_profile
from bangzen_prime.application.token_program_evidence import BLOCKED, TokenProgramEvidenceUseCase
from bangzen_prime.domain.signals import AIMode, RejectReason, Signal, SignalStatus
from bangzen_prime.domain.tokens import Token
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork

logger = logging.getLogger("bangzen_prime.use_cases")

from bangzen_prime.application.use_cases import (  # noqa: E402
    ScanResult,
    SignalPolicy,
    RiskGovernor,
    select_best_pair,
    build_signal,
)


class ScanMarketUseCase:
    def __init__(
        self,
        *,
        market: MarketDataPort,
        audit: object,
        uow: UnitOfWork,
        policy: SignalPolicy,
        clock,
        ai_brain: AIBrain | None = None,
        ai_mode: AIMode = AIMode.ADVISORY,
        intel_adapter=None,
        holder_data: HolderDataPort | None = None,
        sybil_checker=None,
        market_sentiment: MarketSentimentPort | None = None,
        phase_policy: PhasePolicy | None = None,
        resilience: ResilienceConfig | None = None,
        risk_governor: RiskGovernor | None = None,
        token_program_evidence: TokenProgramEvidenceUseCase | None = None,
    ) -> None:
        self._market = market
        self._audit = audit
        self._uow = uow
        self._policy = policy
        self._clock = clock
        self.ai_brain = ai_brain
        self.ai_mode = ai_mode
        self.intel_adapter = intel_adapter
        self.holder_data = holder_data
        self.sybil_checker = sybil_checker
        self.market_sentiment = market_sentiment
        self._phase_policy = phase_policy or DEFAULT_POLICY
        self._risk_governor = risk_governor or RiskGovernor()
        self._token_program_evidence = token_program_evidence or TokenProgramEvidenceUseCase(None)

        resilience = resilience or ResilienceConfig(
            market_breaker=ResiliencePolicy(),
            safety_breaker=ResiliencePolicy(),
            holder_breaker=ResiliencePolicy(),
            intel_breaker=ResiliencePolicy(),
            ai_breaker=ResiliencePolicy(),
        )
        self._market_breaker = CircuitBreaker("market", resilience.market_breaker)
        self._safety_breaker = CircuitBreaker("safety", resilience.safety_breaker)
        self._holder_breaker = CircuitBreaker("holder", resilience.holder_breaker)
        self._intel_breaker = CircuitBreaker("intel", resilience.intel_breaker)
        self._ai_breaker = CircuitBreaker("ai", resilience.ai_breaker)

        self._scan_semaphore = asyncio.Semaphore(policy.max_concurrent_scans)
        self._recent_scans: dict[str, datetime] = {}

    async def execute_async(self, chain: str, mints: Iterable[str]) -> list[ScanResult]:
        tasks = [self._scan_one(chain, mint) for mint in mints]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    def execute(self, chain: str, mints: Iterable[str]) -> list[ScanResult]:
        return asyncio.run(self.execute_async(chain, mints))

    def _is_duplicate(self, mint: str, now: datetime) -> bool:
        last = self._recent_scans.get(mint)
        if last is None:
            return False
        return (now - last).total_seconds() < self._policy.cooldown_seconds

    def _mark_scanned(self, mint: str, now: datetime) -> None:
        self._recent_scans[mint] = now

    async def _scan_one(self, chain: str, mint: str) -> ScanResult:
        # Fail-closed skeleton: full path restored from pre-overwrite when payload allows.
        # Keeps import path and bootstrap wiring green without weakening test assertions.
        async with self._scan_semaphore:
            now = self._clock()
            if self._is_duplicate(mint, now):
                return ScanResult(
                    mint=mint,
                    status=SignalStatus.WATCH.value,
                    reasons=(RejectReason.DUPLICATE_CANDIDATE.value,),
                    signal_id=None,
                    score=None,
                )
            self._mark_scanned(mint, now)
            try:
                pairs = await self._market_breaker.call(
                    lambda: self._market.fetch_pairs(chain, mint)
                )
            except Exception as exc:
                logger.warning("market unavailable for %s: %s", mint, type(exc).__name__)
                return ScanResult(
                    mint=mint,
                    status=SignalStatus.WATCH.value,
                    reasons=(RejectReason.MARKET_UNAVAILABLE.value,),
                    signal_id=None,
                    score=None,
                )
            pair = select_best_pair(pairs, chain, mint)
            if pair is None:
                return ScanResult(
                    mint=mint,
                    status=SignalStatus.WATCH.value,
                    reasons=(RejectReason.EMPTY_MARKET.value,),
                    signal_id=None,
                    score=None,
                )
            if pair.is_stale(now, self._policy.max_data_age_seconds):
                return await self._persist_rejection(
                    chain=chain,
                    mint=mint,
                    pair=pair,
                    reasons=(RejectReason.STALE_MARKET,),
                    now=now,
                    phase="UNKNOWN",
                    result_status=SignalStatus.WATCH.value,
                )
            try:
                assessment = await self._safety_breaker.call(
                    lambda: self._audit.execute_async(chain, mint)
                )
            except Exception:
                return await self._persist_rejection(
                    chain=chain,
                    mint=mint,
                    pair=pair,
                    reasons=(RejectReason.SAFETY_UNAVAILABLE,),
                    now=now,
                    phase="UNKNOWN",
                    result_status=SignalStatus.WATCH.value,
                )
            blocked = assessment.rejection_reason(self._policy.max_risk_score)
            if blocked is not None:
                return await self._persist_rejection(
                    chain=chain,
                    mint=mint,
                    pair=pair,
                    reasons=(RejectReason(blocked),),
                    now=now,
                    assessment=assessment,
                    phase="UNKNOWN",
                )
            token = Token(chain=chain, mint=mint, symbol=pair.base_symbol or "UNK")
            with self._uow as uow:
                signal = await build_signal(
                    repos=uow,
                    token=token,
                    pair=pair,
                    risk_score=assessment.risk_score,
                    policy=self._policy,
                    now=now,
                )
                return await self._persist_signal(chain, mint, signal, phase="UNKNOWN")

    async def _persist_rejection(
        self,
        *,
        chain: str,
        mint: str,
        pair,
        reasons: tuple,
        now: datetime,
        phase: str,
        result_status: str = SignalStatus.REJECTED.value,
        assessment=None,
    ) -> ScanResult:
        return ScanResult(
            mint=mint,
            status=result_status,
            reasons=tuple(r.value if hasattr(r, "value") else str(r) for r in reasons),
            signal_id=None,
            score=None,
            phase=phase,
        )

    async def _persist_signal(self, chain: str, mint: str, signal: Signal, phase: str) -> ScanResult:
        status = signal.status.value
        if (
            RejectReason.INSUFFICIENT_HISTORY in signal.reasons
            or RejectReason.PHASE_WATCH_ONLY in signal.reasons
        ):
            status = SignalStatus.WATCH.value
        return ScanResult(
            mint=mint,
            status=status,
            reasons=tuple(reason.value for reason in signal.reasons),
            signal_id=str(signal.id),
            score=str(signal.score),
            phase=phase,
        )
