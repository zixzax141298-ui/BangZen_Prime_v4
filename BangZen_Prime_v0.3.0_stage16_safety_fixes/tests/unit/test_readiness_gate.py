import ast
import dataclasses
import pathlib
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError, DomainError
from bangzen_prime.research.backtesting import BacktestConfig, BacktestReport, BacktestTrade
from bangzen_prime.research.config_freeze import config_hash
from bangzen_prime.research.cost_model import CostInputs, estimate_costs
from bangzen_prime.research.readiness_gate import (
    GATE_VERSION,
    STATUS_HUMAN_REVIEW,
    STATUS_NOT_READY,
    DataCoverage,
    ForwardPaperSummary,
    GateDecision,
    GateThresholds,
    evaluate_readiness,
)
from bangzen_prime.research.walk_forward import (
    FoldResult,
    PhaseResult,
    WalkForwardReport,
    chronological_split,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE_SOURCE = ROOT / "bangzen_prime" / "research" / "readiness_gate.py"
T = datetime(2026, 1, 1, tzinfo=UTC)


def _report(pnls: list[str], max_dd: str = "5") -> BacktestReport:
    trades = tuple(
        BacktestTrade(
            candidate_id=f"t{i}",
            entry_time=T,
            exit_time=T,
            entry_fill=D(1),
            exit_fill=D(1),
            exit_reason="TAKE_PROFIT",
            gross_return_pct=D(p),
            net_return_pct=D(p),
            net_pnl=D(p),
        )
        for i, p in enumerate(pnls)
    )
    total = sum((D(p) for p in pnls), D(0))
    expectancy = total / len(pnls) if pnls else D(0)
    return BacktestReport(
        trades=trades,
        initial_equity=D(1000),
        final_equity=D(1000) + total,
        total_return_pct=D(0),
        win_rate_pct=D(0),
        expectancy_pct=expectancy,
        profit_factor=None,
        max_drawdown_pct=D(max_dd),
        wins=len(pnls),
        losses=0,
        breakeven=0,
        rejected_candidates=0,
    )


def _walk_forward(
    dev_pnls=("1",) * 40,
    val_pnls=("2",) * 40,
    test_pnls=("2",) * 40,
    test_dd="5",
    buy_and_hold="-10",
    fold_pnls=(("2",) * 10, ("2",) * 10, ("2",) * 10, ("2",) * 10),
    config_hash_value: str | None = None,
) -> WalkForwardReport:
    split = chronological_split(300)
    phases = (
        PhaseResult("development", split.development.start, split.development.end, len(dev_pnls),
                    _report(list(dev_pnls)), D("-10")),
        PhaseResult("validation", split.validation.start, split.validation.end, len(val_pnls),
                    _report(list(val_pnls)), D("-10")),
        PhaseResult("test", split.test.start, split.test.end, len(test_pnls),
                    _report(list(test_pnls), test_dd), D(buy_and_hold)),
    )
    folds = []
    width = (split.test.end - split.test.start) // len(fold_pnls)
    for i, pnls in enumerate(fold_pnls):
        trades = len(pnls)
        expectancy = (sum((D(p) for p in pnls), D(0)) / trades) if trades else None
        folds.append(FoldResult(i, split.test.start + i * width, split.test.start + (i + 1) * width,
                                trades, trades, expectancy,
                                sum((D(p) for p in pnls), D(0))))
    return WalkForwardReport(
        config_hash=config_hash_value or config_hash(BacktestConfig()),
        split=split,
        phases=phases,
        folds=tuple(folds),
    )


def _cost(complete: bool = True) -> object:
    priority = D("0.01") if complete else None
    return estimate_costs(
        CostInputs(
            notional=D(100),
            fee_rate_per_side=D("0.001"),
            base_slippage_rate=D("0.001"),
            liquidity_quote=D(10000),
            impact_coefficient=D("0.5"),
            priority_fee_quote=priority,
            tx_failure_rate=D("0.1"),
        )
    )


GOOD_COVERAGE = DataCoverage(
    point_in_time_snapshots=True,
    includes_dead_tokens=True,
    includes_rugged_tokens=True,
    includes_delisted_tokens=True,
    includes_low_liquidity=True,
    source_timezone="UTC",
)


def _forward(config_hash_value: str, trades: int = 60, dd: str = "5") -> ForwardPaperSummary:
    return ForwardPaperSummary(
        trade_count=trades,
        expectancy_pct=D("1"),
        max_drawdown_pct=D(dd),
        config_hash=config_hash_value,
    )


def _all_good() -> tuple:
    wf = _walk_forward()
    return wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash)


class ReadinessGateTest(unittest.TestCase):
    def failed(self, decision: GateDecision) -> set[str]:
        return set(decision.blockers)

    def test_all_evidence_present_and_passing_gives_review_candidate_only(self):
        decision = evaluate_readiness(*_all_good())
        self.assertEqual(decision.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(decision.blockers, ())
        self.assertEqual(decision.gate_version, GATE_VERSION)
        self.assertFalse(decision.live_trading_allowed)
        self.assertIn("not an authorisation", decision.notice)

    def test_missing_evidence_is_never_a_pass(self):
        decision = evaluate_readiness(None, None, None, None)
        self.assertEqual(decision.status, STATUS_NOT_READY)
        self.assertIn("walk_forward_present", decision.blockers)
        self.assertIn("cost_model_available", decision.blockers)
        self.assertIn("data_coverage_declared", decision.blockers)
        self.assertIn("forward_paper_present", decision.blockers)

    def test_forward_paper_is_required_even_when_walk_forward_passes(self):
        wf, cost, cov, _ = _all_good()
        decision = evaluate_readiness(wf, cost, cov, None)
        self.assertEqual(decision.status, STATUS_NOT_READY)
        self.assertEqual(
            self.failed(decision),
            {"forward_paper_present", "forward_paper_config_match",
             "forward_paper_sample", "forward_paper_drawdown"},
        )

    def test_validation_sample_minimum_is_enforced(self):
        wf = _walk_forward(val_pnls=("2",) * 10)
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("validation_sample", self.failed(decision))
        self.assertEqual(decision.status, STATUS_NOT_READY)

    def test_test_sample_minimum_is_enforced(self):
        wf = _walk_forward(test_pnls=("2",) * 10)
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("test_sample", self.failed(decision))

    def test_test_drawdown_limit_is_enforced(self):
        wf = _walk_forward(test_dd="25")
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("test_drawdown", self.failed(decision))

    def test_negative_test_expectancy_fails_expectancy_and_no_trade_baseline(self):
        wf = _walk_forward(test_pnls=("-2",) * 40)
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("positive_expectancy", self.failed(decision))
        self.assertIn("beats_baselines", self.failed(decision))

    def test_fold_instability_fails(self):
        wf = _walk_forward(
            fold_pnls=(("2",) * 10, ("-2",) * 10, ("-2",) * 10, ("2",) * 10)
        )
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("fold_stability", self.failed(decision))

    def test_fold_without_trades_is_no_evidence_not_a_pass(self):
        wf = _walk_forward(fold_pnls=(("2",) * 10, ("2",) * 10, ("2",) * 10, ()))
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertIn("fold_stability", self.failed(decision))

    def test_strategy_that_loses_to_buy_and_hold_fails_baseline_check(self):
        wf = _walk_forward(buy_and_hold="100")
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash))
        self.assertEqual(self.failed(decision), {"beats_baselines"})

    def test_unavailable_cost_model_blocks(self):
        wf = _walk_forward()
        decision = evaluate_readiness(wf, _cost(complete=False), GOOD_COVERAGE,
                                      _forward(wf.config_hash))
        self.assertEqual(self.failed(decision), {"cost_model_available"})
        self.assertIn("UNAVAILABLE", decision.checks[1].detail)

    def test_survivorship_coverage_must_be_declared_explicitly(self):
        wf = _walk_forward()
        no_dead = replace(GOOD_COVERAGE, includes_dead_tokens=False)
        decision = evaluate_readiness(wf, _cost(), no_dead, _forward(wf.config_hash))
        self.assertEqual(self.failed(decision), {"data_coverage_declared"})

    def test_missing_point_in_time_snapshots_block(self):
        wf = _walk_forward()
        cov = replace(GOOD_COVERAGE, point_in_time_snapshots=False)
        decision = evaluate_readiness(wf, _cost(), cov, _forward(wf.config_hash))
        self.assertIn("data_coverage_declared", self.failed(decision))

    def test_forward_paper_must_use_frozen_walk_forward_config(self):
        wf = _walk_forward()
        decision = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward("0" * 64))
        self.assertEqual(self.failed(decision), {"forward_paper_config_match"})

    def test_forward_paper_sample_and_drawdown_are_enforced(self):
        wf = _walk_forward()
        few = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash, trades=5))
        self.assertEqual(self.failed(few), {"forward_paper_sample"})
        deep = evaluate_readiness(wf, _cost(), GOOD_COVERAGE, _forward(wf.config_hash, dd="40"))
        self.assertEqual(self.failed(deep), {"forward_paper_drawdown"})

    def test_thresholds_can_only_be_tightened_or_set_within_valid_ranges(self):
        with self.assertRaises(DomainError):
            GateThresholds(min_test_trades=0)
        with self.assertRaises(DomainError):
            GateThresholds(fold_count=1)
        with self.assertRaises(DomainError):
            GateThresholds(min_positive_fold_ratio=D("1.5"))
        with self.assertRaises(DomainError):
            GateThresholds(max_test_drawdown_pct=D(150))

    def test_stricter_threshold_can_turn_a_pass_into_a_block(self):
        wf, cost, cov, fwd = _all_good()
        strict = GateThresholds(min_test_trades=100)
        decision = evaluate_readiness(wf, cost, cov, fwd, thresholds=strict)
        self.assertEqual(decision.status, STATUS_NOT_READY)
        self.assertIn("test_sample", self.failed(decision))

    def test_decision_is_reproducible_and_records_threshold_hash(self):
        args = _all_good()
        self.assertEqual(evaluate_readiness(*args), evaluate_readiness(*args))
        self.assertEqual(
            evaluate_readiness(*args).thresholds_hash, config_hash(GateThresholds())
        )


class LiveLockTest(unittest.TestCase):
    """Live trading and broadcast must stay locked, whatever the gate decides."""

    def test_decision_cannot_be_constructed_with_live_enabled(self):
        decision = evaluate_readiness(*_all_good())
        self.assertEqual(decision.status, STATUS_HUMAN_REVIEW)
        with self.assertRaises(TypeError):
            GateDecision(  # type: ignore[call-arg]
                gate_version=GATE_VERSION,
                status=STATUS_HUMAN_REVIEW,
                checks=(),
                thresholds_hash="x",
                live_trading_allowed=True,
            )
        field = {f.name: f for f in dataclasses.fields(GateDecision)}["live_trading_allowed"]
        self.assertFalse(field.init)
        self.assertFalse(field.default)

    def test_gate_module_imports_nothing_from_execution_signing_or_network(self):
        tree = ast.parse(GATE_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = ("bangzen_prime.execution", "bangzen_prime.security", "bangzen_prime.core.bootstrap",
                     "bangzen_prime.notifications", "bangzen_prime.data", "httpx", "socket",
                     "urllib", "requests", "solders", "solana")
        for name in imported:
            for prefix in forbidden:
                self.assertFalse(name == prefix or name.startswith(prefix + "."), name)

    def test_settings_still_reject_live_trading_and_broadcast(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(env={"BANGZEN_LIVE_TRADING": "true"})
        with self.assertRaises(ConfigurationError):
            Settings.from_env(env={"BANGZEN_BROADCAST_ENABLED": "true"})


if __name__ == "__main__":
    unittest.main()
