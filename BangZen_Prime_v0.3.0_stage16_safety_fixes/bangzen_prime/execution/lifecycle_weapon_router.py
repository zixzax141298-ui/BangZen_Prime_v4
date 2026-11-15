"""Fail-closed, phase-aware selector for one analysis/defensive weapon.

This module selects a registered analysis capability from validated evidence. It does
not call providers, mutate policy, produce financial advice, or execute transactions.
The caller must supply a lifecycle phase established by the upstream evidence pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.research.ai_manager_contract import (
    EvidencePackage,
)

POLICY_VERSION = 1
MAX_SELECTED_WEAPONS = 1
PHASES = frozenset(
    {
        "UNKNOWN",
        "PUMPFUN_LAUNCH",
        "BONDING_CURVE",
        "MIGRATION",
        "RAYDIUM_POOL",
        "RAYDIUM_EARLY",
        "GROWTH",
        "DISTRIBUTION",
        "REVIVAL",
    }
)
# Explicit allowlist: no execution, financial, strategy-action, or placeholder modules.
ANALYSIS_ONLY_WEAPONS = frozenset(
    {
        "lp_sniper_adapter",
        "sybil_adapter",
        "sequential_bundle_detector",
        "honeypot_adapter",
        "pre_dump_radar",
        "kol_exit_adapter",
        "autopsy_engine",
        "cross_chain_radar",
        "copycat_trap",
    }
)


@dataclass(frozen=True)
class WeaponCandidate:
    weapon_id: str
    required_evidence: frozenset[str]
    priority: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.weapon_id, str)
            or self.weapon_id not in ANALYSIS_ONLY_WEAPONS
        ):
            raise ConfigurationError("weapon is not in the analysis-only allowlist")
        if not self.required_evidence or any(
            not isinstance(item, str) or not item.strip()
            for item in self.required_evidence
        ):
            raise ConfigurationError("weapon requires named evidence types")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ConfigurationError("weapon priority must be an integer")
        if not 0 <= self.priority <= 1000:
            raise ConfigurationError("weapon priority must be within [0, 1000]")


@dataclass(frozen=True)
class LifecycleWeaponPolicy:
    phases: Mapping[str, tuple[WeaponCandidate, ...]]

    def __post_init__(self) -> None:
        if set(self.phases) != PHASES:
            raise ConfigurationError(
                "policy must define every lifecycle phase exactly once"
            )
        for candidates in self.phases.values():
            if not isinstance(candidates, tuple) or any(
                not isinstance(candidate, WeaponCandidate) for candidate in candidates
            ):
                raise ConfigurationError(
                    "phase candidates must be WeaponCandidate tuples"
                )
            ids = [candidate.weapon_id for candidate in candidates]
            if len(ids) != len(set(ids)):
                raise ConfigurationError("duplicate weapon in phase policy")


@dataclass(frozen=True)
class WeaponPlan:
    phase: str
    selected_weapon: str | None
    evidence_refs: tuple[str, ...]
    reason_code: str
    policy_version: int = POLICY_VERSION
    max_selected_weapons: int = MAX_SELECTED_WEAPONS
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ConfigurationError("invalid lifecycle phase in plan")
        if (
            self.selected_weapon is not None
            and self.selected_weapon not in ANALYSIS_ONLY_WEAPONS
        ):
            raise ConfigurationError("plan contains a non-analysis weapon")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ConfigurationError("duplicate evidence reference")
        if self.max_selected_weapons != 1 or self.execution_authorized:
            raise ConfigurationError("weapon plan cannot grant execution authority")
        if self.selected_weapon is None and self.evidence_refs:
            raise ConfigurationError("empty selection cannot claim supporting evidence")
        if self.selected_weapon is not None and not self.evidence_refs:
            raise ConfigurationError("selected weapon requires evidence references")


def policy_from_mapping(raw: object) -> LifecycleWeaponPolicy:
    if not isinstance(raw, dict) or set(raw) != {
        "version",
        "max_selected_weapons",
        "phases",
    }:
        raise ConfigurationError(
            "policy must contain exactly version, max_selected_weapons, phases"
        )
    if raw["version"] != POLICY_VERSION or isinstance(raw["version"], bool):
        raise ConfigurationError("unsupported lifecycle weapon policy version")
    max_selected = raw["max_selected_weapons"]
    if (
        isinstance(max_selected, bool)
        or not isinstance(max_selected, int)
        or max_selected != MAX_SELECTED_WEAPONS
    ):
        raise ConfigurationError("policy may select at most one weapon")
    phases_raw = raw["phases"]
    if not isinstance(phases_raw, dict) or set(phases_raw) != PHASES:
        raise ConfigurationError(
            "policy must define every lifecycle phase exactly once"
        )

    phases: dict[str, tuple[WeaponCandidate, ...]] = {}
    for phase, items in phases_raw.items():
        if not isinstance(items, list):
            raise ConfigurationError(f"{phase}: candidates must be a list")
        candidates: list[WeaponCandidate] = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {
                "weapon_id",
                "required_evidence",
                "priority",
            }:
                raise ConfigurationError(f"{phase}: invalid candidate schema")
            evidence = item["required_evidence"]
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in evidence
                )
                or len(evidence) != len(set(evidence))
            ):
                raise ConfigurationError(f"{phase}: invalid required_evidence")
            candidates.append(
                WeaponCandidate(
                    weapon_id=item["weapon_id"],
                    required_evidence=frozenset(evidence),
                    priority=item["priority"],
                )
            )
        phases[phase] = tuple(candidates)
    return LifecycleWeaponPolicy(phases)


def load_policy(path: str | Path) -> LifecycleWeaponPolicy:
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            f"cannot read lifecycle weapon policy: {exc.strerror}"
        ) from None
    try:
        raw: Any = json.loads(content)
    except json.JSONDecodeError:
        raise ConfigurationError("lifecycle weapon policy is not valid JSON") from None
    return policy_from_mapping(raw)


class LifecycleWeaponSelector:
    """Select zero or one analysis weapon using only complete, fresh, verified evidence."""

    def __init__(self, policy: LifecycleWeaponPolicy) -> None:
        if not isinstance(policy, LifecycleWeaponPolicy):
            raise ConfigurationError("a validated LifecycleWeaponPolicy is required")
        self._policy = policy

    def select(
        self,
        phase: str,
        package: EvidencePackage,
        *,
        max_age_seconds: int,
        now: datetime,
    ) -> WeaponPlan:
        if not isinstance(phase, str) or phase not in PHASES:
            return WeaponPlan("UNKNOWN", None, (), "UNKNOWN_OR_UNVERIFIED_PHASE")
        if not isinstance(package, EvidencePackage):
            return WeaponPlan(phase, None, (), "EVIDENCE_PACKAGE_UNAVAILABLE")
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            return WeaponPlan(phase, None, (), "INVALID_SELECTION_TIME")

        eligible = package.eligible_evidence(max_age_seconds=max_age_seconds, now=now)
        if not eligible:
            return WeaponPlan(phase, None, (), "NO_FRESH_VERIFIED_EVIDENCE")

        available_types = {item.evidence_type for item in eligible}
        candidates = [
            candidate
            for candidate in self._policy.phases[phase]
            if candidate.required_evidence.issubset(available_types)
        ]
        if not candidates:
            return WeaponPlan(phase, None, (), "NO_RELEVANT_WEAPON_OR_EVIDENCE")

        selected = sorted(
            candidates, key=lambda item: (-item.priority, item.weapon_id)
        )[0]
        refs = tuple(
            sorted(
                item.evidence_id
                for item in eligible
                if item.evidence_type in selected.required_evidence
            )
        )
        return WeaponPlan(
            phase=phase,
            selected_weapon=selected.weapon_id,
            evidence_refs=refs,
            reason_code="ONE_RELEVANT_ANALYSIS_WEAPON_SELECTED",
        )
