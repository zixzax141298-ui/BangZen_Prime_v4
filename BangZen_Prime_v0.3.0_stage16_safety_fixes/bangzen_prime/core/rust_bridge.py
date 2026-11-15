"""Bridge to the optional Rust module `bangzen_native` (built from native/rust with maturin).

Rules:
- If the Rust module is missing or fails to load, every function uses the Python implementation.
- If a Rust call raises, the Python implementation runs for that call and a warning is logged.
- Both implementations are defined to give identical results. Tests check this when Rust exists.
"""

from __future__ import annotations

import html
import importlib.util
import logging
import os

logger = logging.getLogger("bangzen_prime.native")


def _load_native():
    """Load bangzen_native only from outside the working directory.

    With `python -m`, the working directory is first on sys.path, so a planted
    bangzen_native.py there would run at startup. Such a module is ignored and the
    Python implementation is used instead (fail closed to the reviewed code path).
    """
    try:
        spec = importlib.util.find_spec("bangzen_native")
        if spec is None or spec.origin is None:
            return None
        origin = os.path.realpath(spec.origin)
        cwd = os.path.realpath(os.getcwd())
    except Exception:  # noqa: BLE001 - any failure means "no Rust"
        return None
    if origin == cwd or origin.startswith(cwd + os.sep):
        logger.error("bangzen_native found in the working directory; ignored")
        return None
    try:
        import bangzen_native as rust  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - broken build means "no Rust"
        return None
    return rust


_rust = _load_native()

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
