"""Bangzen Prime: Solana token intelligence with 3 operating modes
(TELEGRAM_ONLY, EXECUTION_ONLY, HYBRID).

bootstrap is exposed lazily via __getattr__ so mock.patch("bangzen_prime.bootstrap...")
works in tests without importing the composition root on every package import.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.3.0"

__all__ = ["__version__", "bootstrap"]


def __getattr__(name: str) -> Any:
    if name == "bootstrap":
        from bangzen_prime import bootstrap as _bootstrap

        return _bootstrap
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
