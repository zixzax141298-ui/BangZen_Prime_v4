"""Bridge to the optional Rust module `bangzen_native` (built from native/rust with maturin).

Rules:
- If the Rust module is missing or fails to load, every function uses the Python implementation.
- If a Rust call raises, the Python implementation runs for that call and a warning is logged.
- Both implementations are defined to give identical results. Tests check this when Rust exists.
"""

from __future__ import annotations

import html
import logging

logger = logging.getLogger("bangzen_prime.native")

try:  # any failure to import, including a broken build, means "no Rust"
    import bangzen_native as _rust  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    _rust = None

BACKEND = "rust" if _rust is not None else "python"
BPS_SCALE = 10_000


def _call(name: str, rust_call, python_call):
    if _rust is None:
        return python_call()
    try:
        return rust_call()
    except Exception:  # noqa: BLE001 - graceful fallback, never a crash
        logger.warning("rust call %s failed; using python fallback", name)
        return python_call()


def min_out_amount(out_amount: int, slippage_bps: int) -> int:
    if out_amount < 0 or not (0 <= slippage_bps <= BPS_SCALE):
        raise ValueError("invalid amount or slippage")
    return _call(
        "min_out_amount",
        lambda: _rust.min_out_amount(out_amount, slippage_bps),
        lambda: out_amount * (BPS_SCALE - slippage_bps) // BPS_SCALE,
    )


def bundle_within_limits(num_txs: int, tip_lamports: int, cap_lamports: int) -> bool:
    return _call(
        "bundle_within_limits",
        lambda: _rust.bundle_within_limits(num_txs, tip_lamports, cap_lamports),
        lambda: 1 <= num_txs <= 5 and 0 <= tip_lamports <= cap_lamports,
    )


def html_escape(text: str) -> str:
    return _call(
        "html_escape",
        lambda: _rust.html_escape(text),
        lambda: html.escape(text, quote=False),
    )
