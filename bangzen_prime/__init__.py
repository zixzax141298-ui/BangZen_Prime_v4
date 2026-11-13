"""Bangzen Prime: Solana token intelligence with 3 operating modes
(TELEGRAM_ONLY, EXECUTION_ONLY, HYBRID).

bootstrap is exposed via __getattr__ + importlib so:
- mock.patch("bangzen_prime.bootstrap...") resolves the attribute
- package import does not eagerly load the composition root
- no recursive getattr (importlib.import_module, not from bangzen_prime import bootstrap)
"""

from __future__ import annotations

from typing import Any

__version__ = "0.3.0"

__all__ = ["__version__", "bootstrap"]


def __getattr__(name: str) -> Any:
    if name == "bootstrap":
        import importlib

        return importlib.import_module("bangzen_prime.bootstrap")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
