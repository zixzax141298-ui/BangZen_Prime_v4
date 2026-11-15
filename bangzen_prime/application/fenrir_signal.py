"""FenrirSignalUseCase: jembatan antara FENRIR strategies dan BANGZEN PRIME execution."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from bangzen_prime.application.strategy_dispatcher import StrategyDispatcher
from bangzen_prime.domain.signals import (
    PriceLevels,
    RejectReason,
    Signal,
    SignalStatus,
)
from bangzen_prime.domain.tokens import PairSnapshot, Token
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork

logger = logging.getLogger("bangzen_prime.fenrir_signal")


@dataclass(frozen=True)
class FenrirScanResult:
    mint: str
    status: str
    strategy: str | None
    reason: str
    signal_id: str | None
    score: str | None = None


class FenrirSignalUseCase:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        dispatcher: StrategyDispatcher,
        clock: Callable[[], datetime],
        stop_multiplier: Decimal = Decimal("0.7"),
        target_multiplier: Decimal = Decimal("1.5"),
    ) -> None:
        self._uow = uow
        self._dispatcher = dispatcher
        self._clock = clock
        self._stop = stop_multiplier
        self._target = target_multiplier

    async def execute_async(self, token_data: dict[str, Any]) -> FenrirScanResult:
        now = self._clock()
        mint = token_data.get("token_address") or token_data.get("mint", "")
        symbol = (token_data.get("symbol") or "UNKNOWN")[:32]

        # 1. FENRIR BRAIN: pilih strategi + evaluasi
        decision = await self._dispatcher.route_and_evaluate(token_data)
        status = decision.get("status", "WATCH")
        strategy = decision.get("strategy")
        reason = decision.get("reason", "")

        # 2. Bangun PairSnapshot & Token
        try:
            pair = self._build_pair(token_data, mint, symbol, now)
        except DomainError as e:
            logger.warning("FenrirSignal: cannot build pair for %s: %s", mint[:8], e)
            return FenrirScanResult(mint, "WATCH", strategy, "PAIR_INVALID", None)

        token = Token(chain=pair.chain, mint=mint, symbol=symbol)

        # 3. Jika FENRIR menolak -> simpan sebagai WATCH/REJECTED
        if status != "ACCEPTED":
            sig = Signal.reject(
                token_id=token.id,
                pair_id=pair.pair_id,
                score=Decimal(0),
                reasons=(RejectReason.LOW_SCORE,),
                created_at=now,
            )
            with self._uow.begin() as repos:
                repos.tokens.upsert(token, now)
                repos.pairs.upsert(pair)
                repos.signals.add(sig)
            return FenrirScanResult(
                mint, SignalStatus.WATCH.value, strategy, reason, str(sig.id)
            )

        # 4. FENRIR menerima -> bikin PriceLevels + Signal.accept
        price = pair.price_usd
        if price <= 0:
            return FenrirScanResult(mint, "WATCH", strategy, "PRICE_INVALID", None)

        try:
            levels = PriceLevels(
                entry=price,
                stop_loss=price * self._stop,
                take_profit=price * self._target,
            )
        except DomainError as e:
            return FenrirScanResult(mint, "WATCH", strategy, f"LEVELS_{e}", None)

        score = Decimal(str(decision.get("score", "75")))

        signal = Signal.accept(
            token_id=token.id,
            pair_id=pair.pair_id,
            score=score,
            confidence=Decimal("0.80"),
            levels=levels,
            created_at=now,
            chain=pair.chain,
            mint=mint,
            symbol=symbol,
            pair_address=pair.pair_address,
            dex_id=pair.dex_id,
            market_source=pair.source,
            market_observed_at=pair.observed_at,
        )

        # 5. Persist via uow
        with self._uow.begin() as repos:
            repos.tokens.upsert(token, now)
            repos.pairs.upsert(pair)
            repos.signals.add(signal)
            for event in signal.pull_events():
                repos.outbox.enqueue(event, now)
                repos.audit.append(event.name, event.payload, now)

        logger.info("FenrirSignal ACCEPTED: %s via %s", mint[:8], strategy)
        return FenrirScanResult(
            mint=mint,
            status=SignalStatus.ACCEPTED.value,
            strategy=strategy,
            reason=reason,
            signal_id=str(signal.id),
            score=str(score),
        )

    def _build_pair(
        self, data: dict[str, Any], mint: str, symbol: str, now: datetime
    ) -> PairSnapshot:
        pair_addr = data.get("pair_address") or f"onchain:{mint}"
        dex_id = data.get("dex_id") or (
            "pumpfun" if "bonding_curve" in data else "dexscreener"
        )
        price = Decimal(str(data.get("price_usd", 0) or 0))
        liq = Decimal(str(data.get("liquidity_usd", 0) or 0))
        vol24 = Decimal(str(data.get("volume_24h_usd", 0) or 0))

        return PairSnapshot.create(
            chain="solana",
            pair_address=pair_addr,
            dex_id=dex_id,
            base_mint=mint,
            base_symbol=symbol,
            price_usd=price if price > 0 else Decimal("0.000001"),
            liquidity_usd=liq,
            volume_24h_usd=vol24,
            observed_at=now,
            pair_created_at=data.get("created_at"),
            source=data.get("source", "FENRIR"),
        )
