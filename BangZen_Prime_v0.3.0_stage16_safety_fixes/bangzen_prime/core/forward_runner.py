"""Operator loop for forward paper testing: scan watchlist -> accepted signals -> paper session.

Paper only. Every order goes through PaperTradingUseCase. Nothing here signs, builds, or
broadcasts a transaction.

Fail-closed choices:
- No observed spread source is wired, so spread_lookup returns None. RiskEngine then refuses
  every order (SPREAD_UNAVAILABLE). The forward record stays empty until a real spread source
  exists. This is intentional, not a bug.
- The halt check (HALT.flag or BANGZEN_EMERGENCY_STOP) is passed to both the monitor and the
  paper use case. Either one stops new scans and new orders.
- A signal is attempted at most once per process, and only if it was created within
  signal_max_age_seconds. A stale signal is never executed after a long delay.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.monitor import Monitor, load_watchlist
from bangzen_prime.core.use_cases import RiskGovernor
from bangzen_prime.data.api_budget_defaults import default_budget_registry
from bangzen_prime.execution.forward_session import (
    ForwardPaperSession,
    SessionCycle,
    paper_config_hash,
)
from bangzen_prime.execution.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.execution.simulated import SimulatedExecution
from bangzen_prime.risk.risk_engine import ExposureReservations, RiskEngine, RiskLimits
from bangzen_prime.risk.risk_state import DbRiskStateReader, daily_loss_provider
from bangzen_prime.storage.database import utc_iso

MIN_INTERVAL_SECONDS = 15
MIN_SIGNAL_AGE_SECONDS = 60


@dataclass(frozen=True)
class ForwardRunSettings:
    watchlist_path: str
    ledger_path: str
    interval_seconds: int = 60
    cycles: int = 0  # 0 = run until halted or stopped
    scans_per_minute: int = 20
    signal_max_age_seconds: int = 300

    def validate(self) -> None:
        if self.interval_seconds < MIN_INTERVAL_SECONDS:
            raise ConfigurationError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
        if self.scans_per_minute < 1:
            raise ConfigurationError("scans_per_minute must be >= 1")
        if self.cycles < 0:
            raise ConfigurationError("cycles must be >= 0")
        if self.signal_max_age_seconds < MIN_SIGNAL_AGE_SECONDS:
            raise ConfigurationError(f"signal_max_age_seconds must be >= {MIN_SIGNAL_AGE_SECONDS}")


def risk_limits_for_paper(settings: Settings) -> RiskLimits:
    # Same limits as core/interfaces/demo.py. Spread and slippage caps are 1%.
    return RiskLimits(
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        max_open_positions=settings.max_open_positions,
        max_exposure_quote=settings.max_exposure_quote,
        max_drawdown_pct=settings.max_drawdown_pct,
        min_liquidity_usd=settings.min_liquidity_usd,
        max_spread_pct=Decimal(1),
        max_slippage_pct=Decimal(1),
        fee_rate=settings.fee_rate,
        emergency_stop=settings.emergency_stop,
    )


def _frozen_config_hash(settings: Settings) -> str:
    return paper_config_hash(
        risk_limits=risk_limits_for_paper(settings),
        fee_rate=settings.fee_rate,
        slippage_rate=settings.slippage_rate,
        daily_loss_limit_pct=RiskGovernor().daily_loss_limit_pct,
    )


def _check_paper_only(settings: Settings) -> None:
    if settings.live_trading or settings.broadcast_enabled:
        raise ConfigurationError("forward-paper refuses live_trading or broadcast_enabled")
    if not settings.paper_trading or not settings.dry_run:
        raise ConfigurationError("forward-paper requires paper_trading=true and dry_run=true")


def build_forward_paper(container, settings: Settings) -> PaperTradingUseCase:
    _check_paper_only(settings)
    from bangzen_prime.core.interfaces.demo import latest_sampled_price

    execution = SimulatedExecution(
        db=container.db,
        fee_rate=settings.fee_rate,
        slippage_rate=settings.slippage_rate,
        clock=container.clock.now,
        paper=True,
        dry_run=True,
    )
    return PaperTradingUseCase(
        db=container.db,
        uow=container.uow,
        engine=RiskEngine(risk_limits_for_paper(settings)),
        execution=execution,
        portfolio=PaperPortfolio(container.db, settings.starting_equity),
        reservations=ExposureReservations(settings.max_exposure_quote),
        clock=container.clock.now,
        expected_slippage_pct=settings.slippage_rate * 100,
        halt=settings.halt_active,
        price_lookup=latest_sampled_price(container.db),
        # No observed spread source is wired yet. None makes every order refuse (fail closed).
        spread_lookup=lambda _mint: None,
        daily_loss_provider=daily_loss_provider(
            DbRiskStateReader(container.db, settings.starting_equity)
        ),
        daily_loss_limit_pct=RiskGovernor().daily_loss_limit_pct,
    )


def run_forward_paper(
    container,
    settings: Settings,
    run: ForwardRunSettings,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    out: Callable[[str], None] = print,
) -> list[SessionCycle]:
    run.validate()
    _check_paper_only(settings)
    monitor = Monitor(
        scan=container.scan,
        worker=container.worker,
        budget=default_budget_registry(time.monotonic, scans_per_minute=run.scans_per_minute),
        watchlist=load_watchlist(run.watchlist_path),
        halt_check=settings.halt_active,
    )
    session = ForwardPaperSession.open(
        paper=build_forward_paper(container, settings),
        db=container.db,
        ledger_path=run.ledger_path,
        config_hash_value=_frozen_config_hash(settings),
        initial_equity=settings.starting_equity,
    )
    attempted: set[str] = set()
    results: list[SessionCycle] = []
    cycle_number = 0
    while run.cycles == 0 or cycle_number < run.cycles:
        cycle_number += 1
        report = monitor.run_cycle()
        if report.halted:
            out(json.dumps({"cycle": cycle_number, "status": "HALTED"}))
            break
        cutoff = utc_iso(now() - timedelta(seconds=run.signal_max_age_seconds))
        rows = container.db.query_all(
            "SELECT id FROM signals WHERE status = 'ACCEPTED' AND created_at >= ?"
            " ORDER BY created_at",
            (cutoff,),
        )
        fresh = [row["id"] for row in rows if row["id"] not in attempted]
        attempted.update(fresh)
        cycle = session.run_once(uuid.UUID(signal_id) for signal_id in fresh)
        results.append(cycle)
        out(
            json.dumps(
                {
                    "cycle": cycle_number,
                    "scanned": report.scanned,
                    "accepted_signals": report.accepted,
                    "attempted_signals": len(fresh),
                    "opened": len(cycle.opened),
                    "rejected": [{"signal": s, "reasons": list(r)} for s, r in cycle.rejected],
                    "closed": cycle.closed,
                    "recorded": cycle.recorded,
                }
            )
        )
        if run.cycles == 0 or cycle_number < run.cycles:
            sleep(run.interval_seconds)
    return results
