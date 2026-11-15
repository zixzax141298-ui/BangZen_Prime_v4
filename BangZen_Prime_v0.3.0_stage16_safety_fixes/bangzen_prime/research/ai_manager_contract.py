"""Versioned, fail-closed contract for AI Manager evidence and recommendations.

This module is deliberately provider- and model-agnostic. It does not fetch data,
call an LLM, execute a strategy, or authorize an order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

CONTRACT_VERSION = "1.0"
POLICY_VERSION = "13.0"
MAX_EVIDENCE_ITEMS = 256
MAX_REASON_CODES = 32
MAX_ID_LENGTH = 128


class ValidationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTED = "CONFLICTED"
    REJECTED = "REJECTED"


class DecisionAction(StrEnum):
    BUY_CANDIDATE = "BUY_CANDIDATE"
    HOLD = "HOLD"
    SKIP = "SKIP"


class ContractError(ValueError):
    """Raised when untrusted input violates the versioned contract."""


def _non_empty(value: object, field: str, limit: int = MAX_ID_LENGTH) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a string")
    value = value.strip()
    if not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise ContractError(f"{field} is invalid")
    return value


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ContractError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError(f"{field} is invalid") from exc
    if not result.is_finite():
        raise ContractError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    subject: str
    evidence_type: str
    observed_at: datetime
    received_at: datetime
    source: str
    source_record_id: str
    freshness_seconds: int
    completeness: Decimal
    validation_status: ValidationStatus
    confidence_basis: str
    reason_codes: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> EvidenceRecord:
        if not isinstance(raw, Mapping):
            raise ContractError("evidence item must be an object")
        expected = {
            "evidence_id",
            "subject",
            "evidence_type",
            "observed_at",
            "received_at",
            "source",
            "source_record_id",
            "freshness_seconds",
            "completeness",
            "validation_status",
            "confidence_basis",
            "reason_codes",
        }
        if set(raw) != expected:
            raise ContractError("evidence item has missing or unknown fields")
        freshness = raw["freshness_seconds"]
        if (
            isinstance(freshness, bool)
            or not isinstance(freshness, int)
            or freshness < 0
        ):
            raise ContractError("freshness_seconds must be a non-negative integer")
        completeness = _decimal(raw["completeness"], "completeness")
        if not Decimal(0) <= completeness <= Decimal(1):
            raise ContractError("completeness must be within [0, 1]")
        try:
            status = ValidationStatus(raw["validation_status"])
        except (ValueError, TypeError) as exc:
            raise ContractError("validation_status is not supported") from exc
        codes = raw["reason_codes"]
        if not isinstance(codes, list) or len(codes) > MAX_REASON_CODES:
            raise ContractError("reason_codes must be a bounded list")
        reason_codes = tuple(_non_empty(code, "reason_code") for code in codes)
        return cls(
            evidence_id=_non_empty(raw["evidence_id"], "evidence_id"),
            subject=_non_empty(raw["subject"], "subject"),
            evidence_type=_non_empty(raw["evidence_type"], "evidence_type"),
            observed_at=_timestamp(raw["observed_at"], "observed_at"),
            received_at=_timestamp(raw["received_at"], "received_at"),
            source=_non_empty(raw["source"], "source"),
            source_record_id=_non_empty(raw["source_record_id"], "source_record_id"),
            freshness_seconds=freshness,
            completeness=completeness,
            validation_status=status,
            confidence_basis=_non_empty(
                raw["confidence_basis"], "confidence_basis", 512
            ),
            reason_codes=reason_codes,
        )

    def is_eligible(self, *, max_age_seconds: int, now: datetime) -> bool:
        if self.validation_status is not ValidationStatus.VERIFIED:
            return False
        if self.completeness != Decimal(1):
            return False
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, int)
            or max_age_seconds < 1
        ):
            return False
        if now.tzinfo is None or now.utcoffset() is None:
            return False
        now_utc = now.astimezone(UTC)
        age = (now_utc - self.observed_at).total_seconds()
        received_age = (now_utc - self.received_at).total_seconds()
        return (
            0 <= age <= max_age_seconds
            and 0 <= received_age <= max_age_seconds
            and self.freshness_seconds <= max_age_seconds
        )


@dataclass(frozen=True)
class EvidencePackage:
    schema_version: str
    subject: str
    collected_at: datetime
    evidence: tuple[EvidenceRecord, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> EvidencePackage:
        if not isinstance(raw, Mapping) or set(raw) != {
            "schema_version",
            "subject",
            "collected_at",
            "evidence",
        }:
            raise ContractError("evidence package has missing or unknown fields")
        if raw["schema_version"] != CONTRACT_VERSION:
            raise ContractError("unsupported evidence schema_version")
        items = raw["evidence"]
        if not isinstance(items, list) or not items or len(items) > MAX_EVIDENCE_ITEMS:
            raise ContractError("evidence must be a non-empty bounded list")
        subject = _non_empty(raw["subject"], "subject")
        records = tuple(EvidenceRecord.from_mapping(item) for item in items)
        ids = [item.evidence_id for item in records]
        if len(ids) != len(set(ids)):
            raise ContractError("duplicate evidence_id")
        if any(item.subject != subject for item in records):
            raise ContractError("evidence subject mismatch")
        collected_at = _timestamp(raw["collected_at"], "collected_at")
        if any(item.observed_at > item.received_at for item in records):
            raise ContractError("evidence observed after it was received")
        if any(item.received_at > collected_at for item in records):
            raise ContractError("evidence received after package collection time")
        return cls(CONTRACT_VERSION, subject, collected_at, records)

    def eligible_evidence(
        self, *, max_age_seconds: int, now: datetime
    ) -> tuple[EvidenceRecord, ...]:
        return tuple(
            item
            for item in self.evidence
            if item.is_eligible(max_age_seconds=max_age_seconds, now=now)
        )


@dataclass(frozen=True)
class WeaponSpec:
    weapon_id: str
    required_evidence: frozenset[str]
    priority: int
    enabled: bool = True

    def __post_init__(self) -> None:
        _non_empty(self.weapon_id, "weapon_id")
        if not self.required_evidence:
            raise ContractError("weapon must declare required evidence")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.required_evidence
        ):
            raise ContractError("weapon evidence requirements are invalid")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ContractError("weapon priority must be an integer")
        if not isinstance(self.enabled, bool):
            raise ContractError("weapon enabled must be boolean")


class WeaponRegistry:
    """Allowlisted deterministic selector; returns at most one eligible weapon."""

    def __init__(self, weapons: tuple[WeaponSpec, ...] = ()) -> None:
        self._weapons: dict[str, WeaponSpec] = {}
        for weapon in weapons:
            self.register(weapon)

    def register(self, weapon: WeaponSpec) -> None:
        if not isinstance(weapon, WeaponSpec):
            raise ContractError("only WeaponSpec can be registered")
        if weapon.weapon_id in self._weapons:
            raise ContractError("duplicate weapon_id")
        self._weapons[weapon.weapon_id] = weapon

    def select_one(
        self,
        package: EvidencePackage,
        *,
        max_age_seconds: int,
        now: datetime,
    ) -> WeaponSpec | None:
        if not isinstance(package, EvidencePackage):
            return None
        available_types = {
            item.evidence_type
            for item in package.eligible_evidence(
                max_age_seconds=max_age_seconds, now=now
            )
        }
        eligible = [
            weapon
            for weapon in self._weapons.values()
            if weapon.enabled and weapon.required_evidence.issubset(available_types)
        ]
        if not eligible:
            return None
        return sorted(eligible, key=lambda item: (-item.priority, item.weapon_id))[0]


@dataclass(frozen=True)
class AIManagerDecision:
    decision_id: str
    schema_version: str
    subject: str
    action: DecisionAction
    selected_weapon: str | None
    evidence_refs: tuple[str, ...]
    risk_flags: tuple[str, ...]
    reason_codes: tuple[str, ...]
    data_quality: ValidationStatus
    policy_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        _non_empty(self.decision_id, "decision_id")
        _non_empty(self.subject, "subject")
        if not isinstance(self.action, DecisionAction):
            raise ContractError("action is not supported")
        if not isinstance(self.data_quality, ValidationStatus):
            raise ContractError("data_quality is not supported")
        if self.selected_weapon is not None:
            _non_empty(self.selected_weapon, "selected_weapon")
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs
        ):
            raise ContractError("evidence_refs must be a tuple of non-empty strings")
        if not isinstance(self.risk_flags, tuple) or any(
            not isinstance(flag, str) or not flag.strip() for flag in self.risk_flags
        ):
            raise ContractError("risk_flags must be a tuple of non-empty strings")
        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(code, str) or not code.strip() for code in self.reason_codes
        ):
            raise ContractError("reason_codes must be a tuple of non-empty strings")
        if self.schema_version != CONTRACT_VERSION:
            raise ContractError("unsupported decision schema_version")
        if self.policy_version != POLICY_VERSION:
            raise ContractError("unsupported policy_version")
        if self.action is DecisionAction.BUY_CANDIDATE and not self.selected_weapon:
            raise ContractError("BUY_CANDIDATE requires exactly one selected_weapon")
        if (
            self.action is not DecisionAction.BUY_CANDIDATE
            and self.selected_weapon is not None
        ):
            raise ContractError("HOLD/SKIP cannot select a weapon")
        if self.action is DecisionAction.BUY_CANDIDATE and not self.evidence_refs:
            raise ContractError("BUY_CANDIDATE requires evidence_refs")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ContractError("duplicate evidence_refs")
        if not self.reason_codes:
            raise ContractError("decision requires reason_codes")
        if not isinstance(self.created_at, datetime) or (
            self.created_at.tzinfo is None or self.created_at.utcoffset() is None
        ):
            raise ContractError("created_at must include a timezone")
        if (
            self.action is DecisionAction.BUY_CANDIDATE
            and self.data_quality is not ValidationStatus.VERIFIED
        ):
            raise ContractError("BUY_CANDIDATE requires VERIFIED data_quality")

    @classmethod
    def hold(
        cls,
        *,
        decision_id: str,
        subject: str,
        reason_code: str,
        data_quality: ValidationStatus = ValidationStatus.UNAVAILABLE,
        evidence_refs: tuple[str, ...] = (),
        created_at: datetime | None = None,
    ) -> AIManagerDecision:
        return cls(
            decision_id=decision_id,
            schema_version=CONTRACT_VERSION,
            subject=subject,
            action=DecisionAction.HOLD,
            selected_weapon=None,
            evidence_refs=evidence_refs,
            risk_flags=(),
            reason_codes=(reason_code,),
            data_quality=data_quality,
            policy_version=POLICY_VERSION,
            created_at=created_at or datetime.now(UTC),
        )
