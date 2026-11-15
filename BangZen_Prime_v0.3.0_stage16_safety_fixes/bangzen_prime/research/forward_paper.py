"""Forward paper record: append-only, hash-chained ledger of paper trades.

- The configuration hash is frozen when the ledger is created. Every trade must carry the
  same hash, so a configuration change cannot be hidden inside a forward record.
- Each entry stores the SHA-256 of the previous entry. ``verify_chain`` detects edits,
  deletions, and reordering.
- Metrics are deterministic and computed from recorded trades only. Missing values are never
  zero. An empty ledger produces no expectancy or profit factor.
- Paper only. Nothing here sends transactions, reads keys, or touches execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.config_freeze import canonical_json
from bangzen_prime.research.readiness_gate import ForwardPaperSummary

ZERO = Decimal(0)
HUNDRED = Decimal(100)
GENESIS_HASH = "0" * 64
# Same names as discovery.lifecycle.LifecyclePhase (kept here so research stays import-free).
LIFECYCLE_PHASES = (
    "DISCOVERED", "LAUNCH", "EARLY_ACTIVITY", "EXPANSION", "CONSOLIDATION",
    "DECLINING", "MIGRATING", "CEX_LISTED", "INACTIVE", "UNKNOWN",
)


@dataclass(frozen=True)
class ForwardTrade:
    trade_id: str
    lifecycle_phase: str
    opened_at: datetime
    closed_at: datetime
    notional: Decimal
    net_pnl: Decimal
    net_return_pct: Decimal
    exit_reason: str

    def __post_init__(self) -> None:
        if not self.trade_id.strip():
            raise DomainError("trade_id must not be empty")
        if self.lifecycle_phase not in LIFECYCLE_PHASES:
            raise DomainError(f"lifecycle_phase must be one of {LIFECYCLE_PHASES}")
        for name in ("opened_at", "closed_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise DomainError(f"{name} must be timezone-aware")
        # Zero holding time is possible when open and settle happen in the same tick.
        if self.closed_at < self.opened_at:
            raise DomainError("closed_at must not be before opened_at")
        for name in ("notional", "net_pnl", "net_return_pct"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise DomainError(f"{name} must be a finite Decimal")
        if self.notional <= ZERO:
            raise DomainError("notional must be > 0")

    @property
    def holding_seconds(self) -> Decimal:
        return Decimal(str((self.closed_at - self.opened_at).total_seconds()))


def _entry_hash(prev_hash: str, payload: dict) -> str:
    body = canonical_json({"prev": prev_hash, "trade": payload})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _trade_payload(trade: ForwardTrade) -> dict:
    data = asdict(trade)
    data["opened_at"] = trade.opened_at.isoformat()
    data["closed_at"] = trade.closed_at.isoformat()
    return data


@dataclass(frozen=True)
class LedgerEntry:
    index: int
    prev_hash: str
    entry_hash: str
    trade: ForwardTrade


@dataclass(frozen=True)
class ForwardMetrics:
    trade_count: int
    expectancy_pct: Decimal | None
    win_rate_pct: Decimal | None
    profit_factor: Decimal | None
    max_drawdown_pct: Decimal | None
    exposure_pct: Decimal | None
    mean_holding_seconds: Decimal | None
    per_phase: dict[str, int]


class ForwardPaperLedger:
    def __init__(self, config_hash: str, initial_equity: Decimal) -> None:
        if len(config_hash) != 64:
            raise DomainError("config_hash must be a 64-character SHA-256 hex digest")
        if not isinstance(initial_equity, Decimal) or initial_equity <= ZERO:
            raise DomainError("initial_equity must be a Decimal > 0")
        self.config_hash = config_hash
        self.initial_equity = initial_equity
        self.entries: list[LedgerEntry] = []

    def record(self, trade: ForwardTrade, trade_config_hash: str) -> LedgerEntry:
        if trade_config_hash != self.config_hash:
            raise DomainError("trade was produced with a different frozen configuration")
        if any(e.trade.trade_id == trade.trade_id for e in self.entries):
            raise DomainError(f"duplicate trade_id: {trade.trade_id}")
        prev = self.entries[-1].entry_hash if self.entries else GENESIS_HASH
        entry = LedgerEntry(
            index=len(self.entries),
            prev_hash=prev,
            entry_hash=_entry_hash(prev, _trade_payload(trade)),
            trade=trade,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev = GENESIS_HASH
        for position, entry in enumerate(self.entries):
            if entry.index != position or entry.prev_hash != prev:
                return False
            if entry.entry_hash != _entry_hash(prev, _trade_payload(entry.trade)):
                return False
            prev = entry.entry_hash
        return True

    def save(self, path: str | Path) -> None:
        lines = [
            canonical_json({"config_hash": self.config_hash, "initial_equity": format(self.initial_equity, "f")})
        ]
        for entry in self.entries:
            lines.append(canonical_json({
                "index": entry.index,
                "prev_hash": entry.prev_hash,
                "entry_hash": entry.entry_hash,
                "trade": _trade_payload(entry.trade),
                "trade_config_hash": self.config_hash,
            }))
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ForwardPaperLedger":
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        if not lines:
            raise DomainError("ledger file is empty")
        header = json.loads(lines[0])
        ledger = cls(header["config_hash"], Decimal(header["initial_equity"]))
        for raw in lines[1:]:
            row = json.loads(raw)
            t = row["trade"]
            trade = ForwardTrade(
                trade_id=t["trade_id"],
                lifecycle_phase=t["lifecycle_phase"],
                opened_at=datetime.fromisoformat(t["opened_at"]),
                closed_at=datetime.fromisoformat(t["closed_at"]),
                notional=Decimal(t["notional"]),
                net_pnl=Decimal(t["net_pnl"]),
                net_return_pct=Decimal(t["net_return_pct"]),
                exit_reason=t["exit_reason"],
            )
            ledger.entries.append(LedgerEntry(
                index=row["index"],
                prev_hash=row["prev_hash"],
                entry_hash=row["entry_hash"],
                trade=trade,
            ))
        if not ledger.verify_chain():
            raise DomainError("ledger hash chain is broken; refusing to use this record")
        return ledger

    def metrics(self, window_start: datetime, window_end: datetime) -> ForwardMetrics:
        """Metrics over the recorded trades. ``window_*`` define exposure time."""
        if window_end <= window_start:
            raise DomainError("window_end must be after window_start")
        trades = [e.trade for e in self.entries]
        per_phase = {p: 0 for p in LIFECYCLE_PHASES}
        for t in trades:
            per_phase[t.lifecycle_phase] += 1
        if not trades:
            return ForwardMetrics(0, None, None, None, None, None, None, per_phase)

        count = Decimal(len(trades))
        expectancy = sum((t.net_return_pct for t in trades), ZERO) / count
        wins = [t for t in trades if t.net_pnl > ZERO]
        gross_profit = sum((t.net_pnl for t in wins), ZERO)
        gross_loss = sum((-t.net_pnl for t in trades if t.net_pnl < ZERO), ZERO)
        profit_factor = gross_profit / gross_loss if gross_loss > ZERO else None

        equity = self.initial_equity
        peak = equity
        max_dd = ZERO
        for t in sorted(trades, key=lambda x: x.closed_at):
            equity += t.net_pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * HUNDRED)

        window_seconds = Decimal(str((window_end - window_start).total_seconds()))
        held = sum((t.holding_seconds for t in trades), ZERO)
        exposure = min(held / window_seconds, ONE) * HUNDRED
        return ForwardMetrics(
            trade_count=len(trades),
            expectancy_pct=expectancy,
            win_rate_pct=Decimal(len(wins)) / count * HUNDRED,
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            exposure_pct=exposure,
            mean_holding_seconds=held / count,
            per_phase=per_phase,
        )

    def summary_for_gate(self) -> ForwardPaperSummary | None:
        """Gate input. None for an empty ledger, so the gate reports the record as missing."""
        if not self.entries:
            return None
        metrics = self.metrics(
            min(e.trade.opened_at for e in self.entries),
            max(e.trade.closed_at for e in self.entries),
        )
        assert metrics.expectancy_pct is not None and metrics.max_drawdown_pct is not None
        return ForwardPaperSummary(
            trade_count=metrics.trade_count,
            expectancy_pct=metrics.expectancy_pct,
            max_drawdown_pct=metrics.max_drawdown_pct,
            config_hash=self.config_hash,
        )


ONE = Decimal(1)
