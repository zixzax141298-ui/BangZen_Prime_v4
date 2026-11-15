"""Controlled chain execution: quote -> validate -> plan -> inspect -> simulate [-> broadcast].

Defaults are the safest path: VALIDATE_ONLY stops before simulation; SIMULATE_ONLY stops after
simulation. BROADCAST is refused unless the caller explicitly enables it, and the production
bootstrap never does (Settings.broadcast_enabled is locked to False). Existing attempts for the
same idempotency key are returned unchanged, so a retry never submits twice. After a broadcast
whose outcome is unknown, the attempt is reconciled by signature status and is never resubmitted.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.core.errors import ExternalServiceError
from bangzen_prime.core.ports import (
    QuotePort,
    RpcPort,
    TransactionBuilderPort,
    TransactionSigner,
)
from bangzen_prime.execution.execution import (
    balance_delta_matches,
    inspect_plan,
    validate_quote,
)
from bangzen_prime.execution.signing import SigningDisabled
from bangzen_prime.storage.attempts import Attempt
from bangzen_prime.storage.repositories import UnitOfWork

logger = logging.getLogger("bangzen_prime.chain")
MODES = ("VALIDATE_ONLY", "SIMULATE_ONLY", "BROADCAST")


@dataclass(frozen=True)
class ChainPolicy:
    owner: str
    allowed_programs: frozenset[str]
    allowed_destinations: frozenset[str]
    max_price_impact_pct: Decimal
    balance_tolerance_pct: Decimal = Decimal(1)


@dataclass(frozen=True)
class SafetyApproval:
    """Explicit deterministic Risk/Safety veto result; AI output cannot construct a pass."""

    approved: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool):
            raise ValueError("safety approval must be boolean")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("safety approval requires a reason code")


class ControlledExecution:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        quotes: QuotePort,
        builder: TransactionBuilderPort,
        rpc: RpcPort,
        signer: TransactionSigner,
        policy: ChainPolicy,
        clock: Callable[[], datetime],
        broadcast_allowed: bool = False,
        risk_gate: Callable[[str, str, Decimal], SafetyApproval] | None = None,
        ai_confidence_threshold: Decimal = Decimal("0.6"),
    ) -> None:
        self._uow = uow
        self._quotes = quotes
        self._builder = builder
        self._rpc = rpc
        self._signer = signer
        self._policy = policy
        self._clock = clock
        self._broadcast_allowed = broadcast_allowed
        self._risk_gate = risk_gate
        if not ai_confidence_threshold.is_finite() or not Decimal(
            0
        ) <= ai_confidence_threshold <= Decimal(1):
            raise ValueError("AI confidence threshold must be finite and within [0, 1]")
        self._ai_confidence_threshold = ai_confidence_threshold

    def run(
        self,
        *,
        idempotency_key: str,
        input_mint: str,
        output_mint: str,
        in_amount: Decimal,
        mode: str = "VALIDATE_ONLY",
    ) -> Attempt:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode}")
        with self._uow.begin() as repos:
            existing = repos.attempts.by_key(idempotency_key)
        if existing is not None:
            return existing
        now = self._clock()
        if mode == "BROADCAST" and not self._broadcast_allowed:
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason="BROADCAST_DISABLED",
                now=now,
            )
        if mode == "BROADCAST":
            # Deterministic Risk/Safety approval is an independent mandatory veto.
            # It runs before AI approval and before any quote/build/RPC/signing work.
            if self._risk_gate is None:
                return self._record(
                    idempotency_key,
                    mode,
                    "REJECTED",
                    input_mint,
                    output_mint,
                    in_amount,
                    reason="RISK_APPROVAL_UNAVAILABLE",
                    now=now,
                )
            try:
                risk_decision = self._risk_gate(input_mint, output_mint, in_amount)
                risk_approved = (
                    isinstance(risk_decision, SafetyApproval)
                    and risk_decision.approved is True
                    and risk_decision.reason_code == "RISK_APPROVED"
                )
            except Exception:
                risk_approved = False
            if not risk_approved:
                return self._record(
                    idempotency_key,
                    mode,
                    "REJECTED",
                    input_mint,
                    output_mint,
                    in_amount,
                    reason="RISK_APPROVAL_DENIED",
                    now=now,
                )
        try:
            quote = self._quotes.quote(input_mint, output_mint, in_amount)
        except ExternalServiceError:
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason="QUOTE_UNAVAILABLE",
                now=now,
            )
        reasons = validate_quote(
            quote,
            now=now,
            expected_input=input_mint,
            expected_output=output_mint,
            expected_in_amount=in_amount,
            max_price_impact_pct=self._policy.max_price_impact_pct,
        )
        if reasons:
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason=",".join(reasons),
                quote=quote,
                now=now,
            )
        plan = self._builder.build(quote)
        reasons = inspect_plan(
            plan,
            quote=quote,
            owner=self._policy.owner,
            allowed_programs=self._policy.allowed_programs,
            allowed_destinations=self._policy.allowed_destinations,
            now=now,
        )
        if reasons:
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason=",".join(reasons),
                quote=quote,
                plan=plan,
                now=now,
            )
        try:
            sim = self._rpc.simulate(plan)
        except ExternalServiceError:
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason="RPC_UNAVAILABLE",
                quote=quote,
                plan=plan,
                now=now,
            )
        if not sim.ok:
            reason = (
                "INSUFFICIENT_BALANCE"
                if sim.error_code == "INSUFFICIENT_FUNDS"
                else "SIMULATION_FAILED"
            )
            return self._record(
                idempotency_key,
                mode,
                "REJECTED",
                input_mint,
                output_mint,
                in_amount,
                reason=reason,
                quote=quote,
                plan=plan,
                now=now,
            )
        if mode == "VALIDATE_ONLY":
            return self._record(
                idempotency_key,
                mode,
                "VALIDATED",
                input_mint,
                output_mint,
                in_amount,
                quote=quote,
                plan=plan,
                now=now,
            )
        if mode == "SIMULATE_ONLY":
            return self._record(
                idempotency_key,
                mode,
                "SIMULATED",
                input_mint,
                output_mint,
                in_amount,
                quote=quote,
                plan=plan,
                now=now,
            )
        return self._broadcast(
            idempotency_key, input_mint, output_mint, in_amount, quote, plan, now
        )

    def _broadcast(
        self, key, input_mint, output_mint, in_amount, quote, plan, now
    ) -> Attempt:
        # Persist the idempotency key BEFORE signing or any network side effect. If the
        # process dies after send() but before storing its signature, a retry sees UNKNOWN
        # and cannot submit the same intent again.
        attempt = self._record(
            key,
            "BROADCAST",
            "UNKNOWN",
            input_mint,
            output_mint,
            in_amount,
            quote=quote,
            plan=plan,
            now=now,
        )
        try:
            signed = self._signer.sign(plan)
        except SigningDisabled:
            self._update_attempt(attempt.id, state="REJECTED", reason="SIGNER_DISABLED")
            return self._get_attempt(attempt.id)
        except Exception:
            self._update_attempt(attempt.id, state="REJECTED", reason="SIGNING_FAILED")
            return self._get_attempt(attempt.id)

        try:
            signature = self._rpc.send(signed)
        except Exception:
            # Timeouts and unexpected transport failures have an ambiguous outcome.
            # Never resubmit; reconcile out-of-band if a signature can be recovered.
            self._update_attempt(
                attempt.id, state="UNKNOWN", reason="SEND_OUTCOME_UNKNOWN"
            )
            return self._get_attempt(attempt.id)

        if not isinstance(signature, str) or not signature.strip():
            self._update_attempt(
                attempt.id, state="UNKNOWN", reason="SEND_SIGNATURE_UNAVAILABLE"
            )
            return self._get_attempt(attempt.id)

        self._update_attempt(
            attempt.id, state="SUBMITTED", signature=signature, reason=None
        )
        return self.reconcile(attempt.id)

    def _update_attempt(
        self,
        attempt_id: str,
        *,
        state: str,
        reason: str | None = None,
        signature: str | None = None,
    ) -> None:
        with self._uow.begin() as repos:
            repos.attempts.update(
                attempt_id,
                state=state,
                reason=reason,
                signature=signature,
                now=self._clock(),
            )

    def _get_attempt(self, attempt_id: str) -> Attempt:
        with self._uow.begin() as repos:
            attempt = repos.attempts.get(attempt_id)
        if attempt is None:
            raise RuntimeError("persisted chain attempt disappeared")
        return attempt

    def reconcile(self, attempt_id: str) -> Attempt:
        """Poll the signature. Never resubmits. Unknown outcomes stay UNKNOWN until plan expiry."""
        now = self._clock()
        with self._uow.begin() as repos:
            attempt = repos.attempts.get(attempt_id)
            if attempt is None:
                raise ValueError("unknown attempt")
            if (
                attempt.state not in ("SUBMITTED", "UNKNOWN")
                or attempt.signature is None
            ):
                return attempt
            status = self._rpc.signature_status(attempt.signature)
            if status in ("CONFIRMED", "FINALIZED"):
                new_state, reason = "CONFIRMED", None
            elif status == "FAILED":
                new_state, reason = "FAILED", "ON_CHAIN_FAILURE"
            elif (
                status == "NOT_FOUND"
                and attempt.plan_expires_at
                and now >= attempt.plan_expires_at
            ):
                new_state, reason = "DROPPED", "EXPIRED_WITHOUT_LANDING"
            else:
                new_state, reason = (
                    "SUBMITTED" if status == "PROCESSED" else "UNKNOWN"
                ), "PENDING"
            repos.attempts.update(attempt_id, state=new_state, reason=reason, now=now)
            return repos.attempts.get(attempt_id)  # type: ignore[return-value]

    def check_balance(
        self, *, mint: str, before: Decimal, after: Decimal, expected: Decimal
    ) -> bool:
        return balance_delta_matches(
            before=before,
            after=after,
            expected_increase=expected,
            tolerance_pct=self._policy.balance_tolerance_pct,
        )

    def _record(
        self,
        key,
        mode,
        state,
        input_mint,
        output_mint,
        in_amount,
        *,
        reason=None,
        quote=None,
        plan=None,
        now,
        signature=None,
    ) -> Attempt:
        with self._uow.begin() as repos:
            attempt = repos.attempts.create(
                idempotency_key=key,
                mode=mode,
                state=state,
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount=in_amount,
                out_amount=quote.out_amount if quote else None,
                provider=quote.provider if quote else None,
                reason=reason,
                plan_expires_at=plan.expires_at if plan else None,
                now=now,
            )
            if signature is not None:
                repos.attempts.update(
                    attempt.id, state=state, signature=signature, now=now
                )
                attempt = repos.attempts.get(attempt.id)  # type: ignore[assignment]
        logger.info("chain attempt %s state=%s reason=%s", key, state, reason)
        return attempt
