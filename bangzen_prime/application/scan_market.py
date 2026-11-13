"""Compatibility re-export — ScanMarketUseCase lives in use_cases (application layer).

DDD: application use cases stay cohesive in use_cases.py. This module exists so any
import of bangzen_prime.application.scan_market continues to resolve without cycles.
"""
from __future__ import annotations

from bangzen_prime.application.use_cases import ScanMarketUseCase

__all__ = ["ScanMarketUseCase"]
