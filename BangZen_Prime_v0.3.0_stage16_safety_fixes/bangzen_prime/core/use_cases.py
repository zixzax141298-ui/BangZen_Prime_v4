# bangzen_prime/application/use_cases/scan_market.py
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.phase_policy import (
    DEFAULT_POLICY,
    Action,
    Evidence,
    PhasePolicy,
)
from bangzen_prime.core.ports import (
    HolderDataPort,
    MarketDataPort,
    TokenSafetyPort,
)
from bangzen_prime.data.data_validation import validate_holder_profile
from bangzen_prime.data.resilience import (
    CircuitBreaker,
    ResilienceConfig,
    ResiliencePolicy,
)
from bangzen_prime.discovery.tokens import PairSnapshot, SafetyAssessment, Token
from bangzen_prime.execution.lifecycle import assess_token_phase
from bangzen_prime.market.indicators import mean_abs_change, rsi
from bangzen_prime.risk.risk_state import DbRiskStateReader
from bangzen_prime.scoring.scoring import score_token
from bangzen_prime.scoring.signals import (
    PriceLevels,
    RejectReason,
    Signal,
    SignalStatus,
)
from bangzen_prime.security.token_program_evidence import (
    BLOCKED,
    TokenProgramEvidenceUseCase,
)
from bangzen_prime.storage.repositories import (
    Repositories,
    UnitOfWork,
)

logger = logging.getLogger("bangzen_prime.use_cases")

RSI_PERIOD = 14
VOLATILITY_PERIOD = 14
HISTORY_LIMIT = 50


@dataclass(frozen=True)
class ScanResult:
    mint: str
    status: str
    reasons: tuple[str, ...]
    signal_id: str | None
    score: str | None
    # None means the phase was not observed (duplicate, market missing). Callers must not
    # treat None as a lifecycle phase, or they record fake transitions.
    phase: str | None = None


@dataclass(frozen=True)
class SignalPolicy:
    min_liquidity_usd: Decimal
    max_risk_score: Decimal
    max_data_age_seconds: int
    min_history_points: int = 15
    min_risk_reward: Decimal = Decimal("1.5")
    # Survival floor. Most new Solana launches stop trading within a day, so "any volume" is
    # not evidence of a live market. Bot-generated volume is common, so keep this explicit.
    min_volume_24h_usd: Decimal = Decimal("5000")
    min_score: Decimal = Decimal(45)
    volatility_floor_pct: Decimal = Decimal("0.25")
    volatility_cap_pct: Decimal = Decimal("12.0")
    stop_multiplier: Decimal = Decimal(2)
    target_multiplier: Decimal = Decimal(3)
    cooldown_seconds: int = 90
    max_concurrent_scans: int = 8


@dataclass(frozen=True)
class RiskGovernor:
    """Kill switch dan budget risiko global perusahaan."""

    trading_enabled: bool = True
    max_open_positions: int = 10
    max_daily_new_signals: int = 50
    max_portfolio_risk_pct: Decimal = Decimal("2.0")
    max_single_position_risk_pct: Decimal = Decimal("0.25")
    daily_loss_limit_pct: Decimal = Decimal("1.0")

    def can_accept_new_signal(
        self,
        *,
        open_positions: int,
        signals_today: int,
        portfolio_risk_pct: Decimal,
        daily_loss_pct: Decimal,
    ) -> tuple[bool, RejectReason | None]:
        if not self.trading_enabled:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if open_positions >= self.max_open_positions:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if signals_today >= self.max_daily_new_signals:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if portfolio_risk_pct >= self.max_portfolio_risk_pct:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if daily_loss_pct >= self.daily_loss_limit_pct:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        return True, None


def select_best_pair(
    pairs: Iterable[PairSnapshot], chain: str, mint: str
) -> PairSnapshot | None:
    matching = [p for p in pairs if p.chain == chain and p.base_mint == mint]
    if not matching:
        return None
    return max(
        matching, key=lambda p: (p.liquidity_usd, p.volume_24h_usd, p.pair_address)
    )


async def build_signal(
    *,
    repos: Repositories,
    token: Token,
    pair: PairSnapshot,
    risk_score: Decimal,
    policy: SignalPolicy,
    now: datetime,
) -> Signal:
    token_id, pair_id = token.id, pair.pair_id
    history = repos.prices.recent(token_id, HISTORY_LIMIT)

    reasons: list[RejectReason] = []
    if len(history) < policy.min_history_points:
        reasons.append(RejectReason.INSUFFICIENT_HISTORY)
        rsi_val = Decimal(50)
        volatility = Decimal(0)
        entry = pair.price_usd
    else:
        rsi_val = rsi(history, RSI_PERIOD)
        entry = history[-1]
        volatility = mean_abs_change(history, VOLATILITY_PERIOD)
        if volatility == 0:
            reasons.append(RejectReason.NO_VOLATILITY)

    phase = assess_token_phase(pair.pair_created_at, now)
    breakdown = score_token(
        liquidity_usd=pair.liquidity_usd,
        volume_24h_usd=pair.volume_24h_usd,
        risk_score=risk_score,
        rsi_value=rsi_val,
        phase=phase.phase.value,
    )

    if pair.liquidity_usd < policy.min_liquidity_usd and phase.phase.value not in {
        "UNKNOWN",
        "LAUNCH",
        "EARLY",
    }:
        reasons.append(RejectReason.LOW_LIQUIDITY)

    if breakdown.total < policy.min_score:
        reasons.append(RejectReason.LOW_SCORE)

    levels: PriceLevels | None = None
    if not reasons:
        try:
            levels = PriceLevels(
                entry,
                entry - policy.stop_multiplier * volatility,
                entry + policy.target_multiplier * volatility,
            )
        except DomainError:
            reasons.append(RejectReason.INVALID_LEVELS)

        if levels is not None and levels.risk_reward < policy.min_risk_reward:
            reasons.append(RejectReason.LOW_RISK_REWARD)
            levels = None

    if reasons or levels is None:
        return Signal.reject(
            token_id=token_id,
            pair_id=pair_id,
            score=breakdown.total,
            reasons=tuple(dict.fromkeys(reasons)),
            created_at=now,
        )

    return Signal.accept(
        token_id=token_id,
        pair_id=pair_id,
        score=breakdown.total,
        confidence=breakdown.confidence,
        levels=levels,
        created_at=now,
        chain=pair.chain,
        mint=pair.base_mint,
        symbol=pair.base_symbol,
        pair_address=pair.pair_address,
        dex_id=pair.dex_id,
        market_source=pair.source,
        market_observed_at=pair.observed_at,
    )


class AuditTokenUseCase:
    """Run the authoritative token-safety port without blocking the async scan loop.

    The adapter remains responsible for provider parsing. This use case additionally
    verifies that the returned assessment belongs to the exact requested chain/mint.
    """

    def __init__(self, safety: TokenSafetyPort) -> None:
        self._safety = safety

    async def execute_async(self, chain: str, mint: str) -> SafetyAssessment:
        assessment = await asyncio.to_thread(self._safety.fetch_safety, chain, mint)
        if not isinstance(assessment, SafetyAssessment):
            raise DomainError("safety adapter returned an invalid assessment")
        if assessment.chain != chain or assessment.mint != mint:
            raise DomainError("safety assessment identity does not match request")
        return assessment


class ScanMarketUseCase:
    def __init__(
        self,
        *,
        market: MarketDataPort,
        audit: AuditTokenUseCase,
        uow: UnitOfWork,
        policy: SignalPolicy,
        clock: callable,
        intel_adapter=None,
        holder_data: HolderDataPort | None = None,
        sybil_checker=None,
        phase_policy: PhasePolicy | None = None,
        resilience: ResilienceConfig | None = None,
        risk_governor: RiskGovernor | None = None,
        token_program_evidence: TokenProgramEvidenceUseCase | None = None,
        risk_state: DbRiskStateReader | None = None,
    ) -> None:
        self._market = market
        self._audit = audit
        self._uow = uow
        self._policy = policy
        self._clock = clock
        self.intel_adapter = intel_adapter
        self.holder_data = holder_data
        self.sybil_checker = sybil_checker
        self._phase_policy = phase_policy or DEFAULT_POLICY
        self._risk_governor = risk_governor or RiskGovernor()
        # Without live state the governor cannot judge limits, so it must refuse (fail closed).
        self._risk_state = risk_state
        self._token_program_evidence = (
            token_program_evidence or TokenProgramEvidenceUseCase(None)
        )

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

        self._scan_semaphore = asyncio.Semaphore(policy.max_concurrent_scans)
        self._recent_scans: dict[str, datetime] = {}

    async def execute_async(self, chain: str, mints: Iterable[str]) -> list[ScanResult]:
        tasks = [self._scan_one(chain, mint) for mint in mints]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    def execute(self, chain: str, mints: Iterable[str]) -> list[ScanResult]:
        """Sync facade for callers that are not yet async."""
        return asyncio.run(self.execute_async(chain, mints))

    def _is_duplicate(self, mint: str, now: datetime) -> bool:
        last = self._recent_scans.get(mint)
        if last is None:
            return False
        return (now - last).total_seconds() < self._policy.cooldown_seconds

    def _mark_scanned(self, mint: str, now: datetime) -> None:
        # Prune expired entries so a long-running monitor does not grow without bound.
        cutoff = self._policy.cooldown_seconds
        for key in [
            k
            for k, t in self._recent_scans.items()
            if (now - t).total_seconds() >= cutoff
        ]:
            del self._recent_scans[key]
        self._recent_scans[mint] = now

    def is_recent(self, mint: str) -> bool:
        """True if this mint would be skipped as a duplicate right now (no provider call)."""
        return self._is_duplicate(mint, self._clock())

    async def _scan_one(self, chain: str, mint: str) -> ScanResult:
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
                logger.warning(
                    "market unavailable for %s: %s", mint, type(exc).__name__
                )
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

            phase = assess_token_phase(pair.pair_created_at, now)

            if pair.is_stale(now, self._policy.max_data_age_seconds):
                return await self._persist_rejection(
                    chain=chain,
                    mint=mint,
                    pair=pair,
                    reasons=(RejectReason.STALE_MARKET,),
                    now=now,
                    phase=phase.phase.value,
                    result_status=SignalStatus.WATCH.value,
                )

            if chain == "solana":
                token_program_result = await asyncio.to_thread(
                    self._token_program_evidence.execute,
                    mint,
                    now=now,
                    max_age=timedelta(seconds=self._policy.max_data_age_seconds),
                )
                if not token_program_result.approved:
                    codes = set(token_program_result.reason_codes)
                    if token_program_result.status == BLOCKED:
                        reason = (
                            RejectReason.TOKEN2022_HARD_VETO
                            if "TOKEN2022_HARD_VETO" in codes
                            else (
                                RejectReason.TOKEN2022_MINT_MISMATCH
                                if "TOKEN2022_MINT_MISMATCH" in codes
                                else (
                                    RejectReason.TOKEN2022_EVIDENCE_REJECTED
                                    if "TOKEN2022_EVIDENCE_REJECTED" in codes
                                    else RejectReason.TOKEN_PROGRAM_UNSUPPORTED
                                )
                            )
                        )
                        result_status = SignalStatus.REJECTED.value
                    else:
                        reason = (
                            RejectReason.TOKEN2022_REVIEW_REQUIRED
                            if "TOKEN2022_REVIEW_REQUIRED" in codes
                            else (
                                RejectReason.TOKEN2022_EVIDENCE_STALE
                                if "TOKEN_PROGRAM_EVIDENCE_STALE" in codes
                                else (
                                    RejectReason.TOKEN2022_EVIDENCE_NOT_VERIFIED
                                    if "TOKEN2022_EVIDENCE_NOT_VERIFIED" in codes
                                    else RejectReason.TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE
                                )
                            )
                        )
                        result_status = SignalStatus.WATCH.value
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(reason,),
                        now=now,
                        phase=phase.phase.value,
                        result_status=result_status,
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
                    phase=phase.phase.value,
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
                    phase=phase.phase.value,
                )

            holder_profile = None
            if self.holder_data is not None:
                try:
                    holder_profile = await self._holder_breaker.call(
                        lambda: self.holder_data.holder_profile(chain, mint)
                    )
                    validate_holder_profile(holder_profile, mint)
                except Exception as exc:
                    logger.warning(
                        "holder data unavailable for %s: %s",
                        mint,
                        type(exc).__name__,
                    )
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.HOLDER_DATA_UNAVAILABLE,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                        result_status=SignalStatus.WATCH.value,
                    )

            # Sybil is a hard pre-scoring safety gate. No missing evidence is treated as clear.
            if self.sybil_checker is not None:
                raw_holder_addresses = (
                    getattr(holder_profile, "top_holders", None)
                    if holder_profile is not None
                    else None
                )
                holder_addresses = (
                    list(
                        dict.fromkeys(
                            address
                            for address in raw_holder_addresses
                            if isinstance(address, str) and address
                        )
                    )[:5]
                    if isinstance(raw_holder_addresses, (list, tuple))
                    else []
                )
                if len(holder_addresses) < 3:
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.SYBIL_UNAVAILABLE,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                        result_status=SignalStatus.WATCH.value,
                    )
                try:
                    sybil_report = await self.sybil_checker.check_sybil_cluster(
                        mint, holder_addresses
                    )
                except Exception as exc:
                    logger.warning(
                        "Sybil evidence unavailable for %s: %s",
                        mint,
                        type(exc).__name__,
                    )
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.SYBIL_UNAVAILABLE,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                        result_status=SignalStatus.WATCH.value,
                    )
                sybil_state = getattr(sybil_report, "is_bundled", None)
                if not getattr(sybil_report, "available", False) or (
                    sybil_state is not True and sybil_state is not False
                ):
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.SYBIL_UNAVAILABLE,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                        result_status=SignalStatus.WATCH.value,
                    )
                if sybil_report.is_bundled is True:
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.SYBIL_CLUSTER_DETECTED,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                    )

            intel_report = None
            if self.intel_adapter is not None:
                try:
                    intel_report = await self._intel_breaker.call(
                        lambda: self.intel_adapter.analyze_token(mint)
                    )
                    if (
                        intel_report.is_bundled
                        or intel_report.has_mev
                        or intel_report.score < Decimal("50.0")
                    ):
                        return await self._persist_rejection(
                            chain=chain,
                            mint=mint,
                            pair=pair,
                            reasons=(RejectReason.LOW_SCORE,),
                            now=now,
                            assessment=assessment,
                            phase=phase.phase.value,
                        )
                except Exception as exc:
                    logger.warning(
                        "intel unavailable for %s: %s",
                        mint,
                        type(exc).__name__,
                    )
                    return await self._persist_rejection(
                        chain=chain,
                        mint=mint,
                        pair=pair,
                        reasons=(RejectReason.INTEL_UNAVAILABLE,),
                        now=now,
                        assessment=assessment,
                        phase=phase.phase.value,
                        result_status=SignalStatus.WATCH.value,
                    )

            if self._risk_state is None:
                allowed, governor_reason = False, RejectReason.RISK_GOVERNOR_PAUSED
            else:
                state = self._risk_state.read(now)
                allowed, governor_reason = self._risk_governor.can_accept_new_signal(
                    open_positions=state.open_positions,
                    signals_today=state.signals_today,
                    portfolio_risk_pct=state.portfolio_risk_pct,
                    daily_loss_pct=state.daily_loss_pct,
                )

            if not allowed:
                return await self._persist_rejection(
                    chain=chain,
                    mint=mint,
                    pair=pair,
                    reasons=(governor_reason,),
                    now=now,
                    assessment=assessment,
                    phase=phase.phase.value,
                    result_status=SignalStatus.WATCH.value,
                )

            evidence = Evidence(
                safety=True,
                holders=holder_profile is not None,
                liquidity=pair.liquidity_usd >= self._policy.min_liquidity_usd,
                volume=pair.volume_24h_usd >= self._policy.min_volume_24h_usd,
                intel=intel_report is not None,
            )

            verdict = self._phase_policy.evaluate(phase.phase.value, evidence)

            return await self._persist_signal(
                chain=chain,
                mint=mint,
                pair=pair,
                assessment=assessment,
                now=now,
                phase=phase.phase.value,
                gate=verdict,
            )

    async def _persist_rejection(
        self,
        *,
        chain: str,
        mint: str,
        pair: PairSnapshot,
        reasons: tuple[RejectReason, ...],
        now: datetime,
        assessment: SafetyAssessment | None = None,
        phase: str = "UNKNOWN",
        result_status: str | None = None,
    ) -> ScanResult:
        token = Token(chain=chain, mint=mint, symbol=pair.base_symbol or "UNKNOWN")
        signal = Signal.reject(
            token_id=token.id,
            pair_id=pair.pair_id,
            score=Decimal(0),
            reasons=reasons,
            created_at=now,
        )

        with self._uow.begin() as repos:
            repos.tokens.upsert(token, now)
            repos.pairs.upsert(pair)

            if assessment is not None:
                repos.safety.append(token.id, assessment)

            repos.signals.add(signal)

        return ScanResult(
            mint=mint,
            status=result_status or signal.status.value,
            reasons=tuple(reason.value for reason in reasons),
            signal_id=str(signal.id),
            score=None,
            phase=phase,
        )

    async def _persist_signal(
        self,
        *,
        chain: str,
        mint: str,
        pair: PairSnapshot,
        assessment: SafetyAssessment,
        now: datetime,
        phase: str = "UNKNOWN",
        gate=None,
    ) -> ScanResult:
        token = Token(chain=chain, mint=mint, symbol=pair.base_symbol or "UNKNOWN")

        with self._uow.begin() as repos:
            repos.tokens.upsert(token, now)
            repos.pairs.upsert(pair)
            repos.safety.append(token.id, assessment)
            repos.prices.append(token.id, pair.price_usd, now)

            signal = await build_signal(
                repos=repos,
                token=token,
                pair=pair,
                risk_score=assessment.risk_score,
                policy=self._policy,
                now=now,
            )

            if (
                gate is not None
                and gate.action is not Action.ENTER_PAPER
                and signal.status.value == SignalStatus.ACCEPTED.value
            ):
                gate_reason = (
                    RejectReason.PHASE_WATCH_ONLY
                    if gate.action is Action.WATCH
                    else RejectReason.PHASE_EVIDENCE_MISSING
                )
                signal = Signal.reject(
                    token_id=token.id,
                    pair_id=pair.pair_id,
                    score=Decimal(0),
                    reasons=(gate_reason,),
                    created_at=now,
                )

            repos.signals.add(signal)

            for event in signal.pull_events():
                repos.outbox.enqueue(event, now)
                repos.audit.append(event.name, event.payload, now)

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
