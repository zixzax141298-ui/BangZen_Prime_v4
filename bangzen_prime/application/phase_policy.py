"""Phase-aware paper decision policy.

Each token phase declares which evidence must be present before a PAPER entry is allowed.
Checks that a phase does not require are not used for that phase. This module never
places orders. Its only output is ENTER_PAPER, WATCH, or REJECT.

The policy is data (JSON) so it can be tuned without code changes, but it is validated
strictly. A file cannot remove the safety floor, cannot enable a live action, and cannot
introduce unknown keys or phases.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from bangzen_prime.errors import ConfigurationError

POLICY_VERSION = 1
PHASES = frozenset({"UNKNOWN", "LAUNCH", "EARLY", "GROWTH", "MATURE", "CEX_LISTED"})
EVIDENCE = frozenset({"safety", "holders", "liquidity", "volume", "ai", "intel"})

# Evidence that every paper-entry phase must have. A policy file may add requirements,
# but it cannot remove these.
SAFETY_FLOOR = frozenset({"safety", "holders", "ai"})


class Action(StrEnum):
    ENTER_PAPER = "ENTER_PAPER"
    WATCH = "WATCH"
    REJECT = "REJECT"


@dataclass(frozen=True)
class Evidence:
    safety: bool
    holders: bool
    liquidity: bool
    volume: bool
    ai: bool
    intel: bool

    def present(self) -> frozenset[str]:
        return frozenset(name for name in EVIDENCE if getattr(self, name))


@dataclass(frozen=True)
class PhaseRule:
    mode: Action  # ENTER_PAPER or WATCH only
    required: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.mode not in (Action.ENTER_PAPER, Action.WATCH):
            raise ConfigurationError("phase mode must be ENTER_PAPER or WATCH")
        if not self.required <= EVIDENCE:
            raise ConfigurationError("unknown evidence name in phase rule")
        if self.mode is Action.ENTER_PAPER and not SAFETY_FLOOR <= self.required:
            raise ConfigurationError(
                "paper entry requires safety, holders, and ai evidence"
            )


@dataclass(frozen=True)
class Verdict:
    action: Action
    phase: str
    missing: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class PhasePolicy:
    rules: Mapping[str, PhaseRule] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if set(self.rules) != PHASES:
            raise ConfigurationError("policy must define every phase exactly once")

    def required_checks(self, phase: str) -> frozenset[str]:
        return self.rule_for(phase).required

    def rule_for(self, phase: str) -> PhaseRule:
        if phase not in PHASES:
            raise ConfigurationError(f"unknown phase: {phase!r}")
        return self.rules[phase]

    def evaluate(self, phase: str, evidence: Evidence) -> Verdict:
        """Fail closed. Unknown phase, missing evidence, or watch-only phase never enters."""
        try:
            rule = self.rule_for(phase)
        except ConfigurationError:
            return Verdict(Action.REJECT, phase, (), "UNKNOWN_PHASE")
        if rule.mode is Action.WATCH:
            return Verdict(Action.WATCH, phase, (), "PHASE_WATCH_ONLY")
        missing = tuple(sorted(rule.required - evidence.present()))
        if missing:
            return Verdict(Action.REJECT, phase, missing, "PHASE_EVIDENCE_MISSING")
        return Verdict(Action.ENTER_PAPER, phase, (), "PHASE_EVIDENCE_OK")


DEFAULT_RULES: dict[str, PhaseRule] = {
    # Pair age unknown: never enter, only observe.
    "UNKNOWN": PhaseRule(Action.WATCH, frozenset({"safety", "holders"})),
    # Very new pairs: observe only. Holder concentration changes fast here.
    "LAUNCH": PhaseRule(Action.WATCH, frozenset({"safety", "holders"})),
    # Early activity: paper entry needs liquidity and an intel check on top of the floor.
    "EARLY": PhaseRule(
        Action.ENTER_PAPER, frozenset({"safety", "holders", "ai", "liquidity", "intel"})
    ),
    # Established growth: volume becomes a requirement.
    "GROWTH": PhaseRule(
        Action.ENTER_PAPER,
        frozenset({"safety", "holders", "ai", "liquidity", "volume", "intel"}),
    ),
    "MATURE": PhaseRule(
        Action.ENTER_PAPER,
        frozenset({"safety", "holders", "ai", "liquidity", "volume", "intel"}),
    ),
    # CEX listed tokens are not a paper target in this version.
    "CEX_LISTED": PhaseRule(Action.WATCH, frozenset({"safety", "holders"})),
}

DEFAULT_POLICY = PhasePolicy(DEFAULT_RULES)

_TOP_KEYS = frozenset({"version", "phases"})
_RULE_KEYS = frozenset({"mode", "required"})


def policy_from_dict(data: object) -> PhasePolicy:
    if not isinstance(data, dict) or set(data) != _TOP_KEYS:
        raise ConfigurationError("policy file must contain exactly: version, phases")
    if data["version"] != POLICY_VERSION or isinstance(data["version"], bool):
        raise ConfigurationError(
            f"unsupported policy version (expected {POLICY_VERSION})"
        )
    phases = data["phases"]
    if not isinstance(phases, dict) or set(phases) != PHASES:
        raise ConfigurationError("policy must define every phase exactly once")
    rules: dict[str, PhaseRule] = {}
    for name, raw in phases.items():
        if not isinstance(raw, dict) or set(raw) != _RULE_KEYS:
            raise ConfigurationError(
                f"phase {name} must contain exactly: mode, required"
            )
        try:
            mode = Action(raw["mode"])
        except ValueError:
            raise ConfigurationError(
                f"phase {name}: mode must be ENTER_PAPER or WATCH"
            ) from None
        required = raw["required"]
        if not isinstance(required, list) or not all(
            isinstance(x, str) for x in required
        ):
            raise ConfigurationError(f"phase {name}: required must be a list of names")
        rules[name] = PhaseRule(mode, frozenset(required))
    return PhasePolicy(rules)


def load_policy(path: str | Path) -> PhasePolicy:
    """Load and validate a policy file. Any problem raises ConfigurationError (fail closed)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"cannot read policy file: {exc.strerror}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ConfigurationError("policy file is not valid JSON") from None
    return policy_from_dict(data)
