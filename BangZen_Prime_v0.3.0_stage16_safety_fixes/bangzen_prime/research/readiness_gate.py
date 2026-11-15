"""Deterministic readiness gate for research evidence.

What it can say:
- NOT_READY: at least one required check failed or had no evidence.
- HUMAN_REVIEW_CANDIDATE: every check passed. A human may review the evidence. This is not
  an authorisation of any kind.

What it can never do:
- It cannot enable live trading, signing, or broadcast. ``live_trading_allowed`` is a
  constant False and has no constructor parameter.
- It does not read market data, does not call providers, and does not call AI.
- It does not compute profit claims. Its output must not be presented as a profit claim.

Thresholds are proposals. Changing them requires owner approval and a Change Ledger entry
(AI_RULES risk_policy.thresholds_change_requires).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.config_freeze import config_hash
from bangzen_prime.research.cost_model import AVAILABLE, CostEstimate
from bangzen_prime.research.walk_forward import WalkForwardReport

GATE_VERSION = "readiness-gate-1"
STATUS_NOT_READY = "NOT_READY"
STATUS_HUMAN_REVIEW = "HUMAN_REVIEW_CANDIDATE"
NOTICE = (
    "HUMAN_REVIEW_CANDIDATE means the evidence passed the automated checks and may be "
    "reviewed by a person. It is not an authorisation to trade, not a live-trading signal, "
    "and not a profit claim."
)

ZERO = Decimal(0)
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class GateThresholds:
    min_validation_trades: int = 30
    min_test_trades: int = 30
    max_test_drawdown_pct: Decimal = Decimal("20")
    fold_count: int = 4
    min_positive_fold_ratio: Decimal = Decimal("0.6")
    min_forward_paper_trades: int = 50
    max_forward_paper_drawdown_pct: Decimal = Decimal("20")

    def __post_init__(self) -> None:
        for name in ("min_validation_trades", "min_test_trades", "min_forward_paper_trades"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise DomainError(f"{name} must be an integer >= 1")
        if isinstance(self.fold_count, bool) or not isinstance(self.fold_count, int) or self.fold_count < 2:
            raise DomainError("fold_count must be an integer >= 2")
        for name in (
            "max_test_drawdown_pct",
            "max_forward_paper_drawdown_pct",
            "min_positive_fold_ratio",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise DomainError(f"{name} must be a finite Decimal")
        if not (ZERO <= self.min_positive_fold_ratio <= Decimal(1)):
            raise DomainError("min_positive_fold_ratio must be in [0, 1]")
        if self.max_test_drawdown_pct < ZERO or self.max_test_drawdown_pct > HUNDRED:
            raise DomainError("max_test_drawdown_pct must be in [0, 100]")
        if self.max_forward_paper_drawdown_pct < ZERO or self.max_forward_paper_drawdown_pct > HUNDRED:
            raise DomainError("max_forward_paper_drawdown_pct must be in [0, 100]")


@dataclass(frozen=True)
class DataCoverage:
    """Declared properties of the historical dataset. Each flag must be explicitly True."""

    point_in_time_snapshots: bool
    includes_dead_tokens: bool
    includes_rugged_tokens: bool
    includes_delisted_tokens: bool
    includes_low_liquidity: bool
    source_timezone: str = ""


@dataclass(frozen=True)
class ForwardPaperSummary:
    """Summary of a forward paper test. Produced by a later stage, not by this module."""

    trade_count: int
    expectancy_pct: Decimal
    max_drawdown_pct: Decimal
    config_hash: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateDecision:
    gate_version: str
    status: str
    checks: tuple[CheckResult, ...]
    thresholds_hash: str
    live_trading_allowed: bool = field(default=False, init=False)
    notice: str = field(default=NOTICE, init=False)

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)


def _check(name: str, passed: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, passed=bool(passed), detail=detail)


def evaluate_readiness(
    walk_forward: WalkForwardReport | None,
    cost: CostEstimate | None,
    coverage: DataCoverage | None,
    forward_paper: ForwardPaperSummary | None,
    thresholds: GateThresholds = GateThresholds(),
) -> GateDecision:
    checks: list[CheckResult] = []
    thresholds_hash = config_hash(thresholds)

    # Missing inputs are recorded as failed checks. They are never treated as passing.
    checks.append(_check("walk_forward_present", walk_forward is not None,
                         "walk-forward report supplied" if walk_forward else "no walk-forward report"))
    checks.append(_check(
        "cost_model_available",
        cost is not None and cost.status == AVAILABLE,
        "cost estimate AVAILABLE" if cost is not None and cost.status == AVAILABLE
        else ("no cost estimate" if cost is None else "UNAVAILABLE: " + ", ".join(cost.missing)),
    ))
    if coverage is None:
        checks.append(_check("data_coverage_declared", False, "no data coverage declaration"))
    else:
        coverage_ok = all((
            coverage.point_in_time_snapshots,
            coverage.includes_dead_tokens,
            coverage.includes_rugged_tokens,
            coverage.includes_delisted_tokens,
            coverage.includes_low_liquidity,
        ))
        checks.append(_check(
            "data_coverage_declared",
            coverage_ok,
            "point-in-time with dead, rugged, delisted and low-liquidity tokens"
            if coverage_ok else "dataset lacks point-in-time snapshots or survivorship coverage",
        ))

    if walk_forward is None:
        for name in (
            "validation_sample", "test_sample", "test_drawdown", "positive_expectancy",
            "fold_stability", "beats_baselines", "config_hash_present",
        ):
            checks.append(_check(name, False, "no walk-forward report"))
    else:
        validation = walk_forward.phase("validation")
        test = walk_forward.phase("test")
        checks.append(_check(
            "validation_sample",
            validation.trade_count >= thresholds.min_validation_trades,
            f"validation trades={validation.trade_count} min={thresholds.min_validation_trades}",
        ))
        checks.append(_check(
            "test_sample",
            test.trade_count >= thresholds.min_test_trades,
            f"test trades={test.trade_count} min={thresholds.min_test_trades}",
        ))
        drawdown = test.report.max_drawdown_pct
        checks.append(_check(
            "test_drawdown",
            drawdown <= thresholds.max_test_drawdown_pct,
            f"test max drawdown={drawdown}% limit={thresholds.max_test_drawdown_pct}%",
        ))
        checks.append(_check(
            "positive_expectancy",
            validation.trade_count > 0 and test.trade_count > 0
            and validation.report.expectancy_pct > ZERO and test.report.expectancy_pct > ZERO,
            f"validation expectancy={validation.report.expectancy_pct}% "
            f"test expectancy={test.report.expectancy_pct}% (net of costs)",
        ))
        ratio = walk_forward.positive_fold_ratio
        fold_ok = (
            len(walk_forward.folds) >= thresholds.fold_count
            and walk_forward.folds_with_trades == len(walk_forward.folds)
            and ratio is not None
            and ratio >= thresholds.min_positive_fold_ratio
        )
        checks.append(_check(
            "fold_stability",
            fold_ok,
            f"folds={len(walk_forward.folds)} with_trades={walk_forward.folds_with_trades} "
            f"positive_ratio={ratio} min_ratio={thresholds.min_positive_fold_ratio}",
        ))
        checks.append(_check(
            "beats_baselines",
            test.beats_no_trade and test.beats_buy_and_hold,
            f"test strategy_net_pnl={test.strategy_net_pnl} "
            f"buy_and_hold={test.buy_and_hold_net_pnl} no_trade=0",
        ))
        checks.append(_check(
            "config_hash_present",
            bool(walk_forward.config_hash),
            "walk-forward config hash recorded",
        ))

    if forward_paper is None:
        checks.append(_check("forward_paper_present", False, "no forward paper record"))
        checks.append(_check("forward_paper_config_match", False, "no forward paper record"))
        checks.append(_check("forward_paper_sample", False, "no forward paper record"))
        checks.append(_check("forward_paper_drawdown", False, "no forward paper record"))
    else:
        checks.append(_check("forward_paper_present", True, "forward paper record supplied"))
        matches = walk_forward is not None and forward_paper.config_hash == walk_forward.config_hash
        checks.append(_check(
            "forward_paper_config_match",
            matches,
            "forward paper used the walk-forward configuration hash" if matches
            else "forward paper config hash differs from walk-forward config",
        ))
        checks.append(_check(
            "forward_paper_sample",
            forward_paper.trade_count >= thresholds.min_forward_paper_trades,
            f"forward trades={forward_paper.trade_count} min={thresholds.min_forward_paper_trades}",
        ))
        checks.append(_check(
            "forward_paper_drawdown",
            forward_paper.max_drawdown_pct <= thresholds.max_forward_paper_drawdown_pct,
            f"forward max drawdown={forward_paper.max_drawdown_pct}% "
            f"limit={thresholds.max_forward_paper_drawdown_pct}%",
        ))

    all_passed = all(check.passed for check in checks)
    return GateDecision(
        gate_version=GATE_VERSION,
        status=STATUS_HUMAN_REVIEW if all_passed else STATUS_NOT_READY,
        checks=tuple(checks),
        thresholds_hash=thresholds_hash,
    )
