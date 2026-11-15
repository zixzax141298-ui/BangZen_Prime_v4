#!/usr/bin/env python3
"""
FENRIR - Custom Exception Hierarchy

Structured error types for precise error handling.
"""


class FenrirError(Exception):
    """Base exception for all FENRIR errors."""


class ConfigError(FenrirError):
    """Invalid or missing configuration."""


class ExecutionError(FenrirError):
    """Trade execution failure."""


class InsufficientLiquidityError(ExecutionError):
    """Not enough liquidity for the requested trade."""


class BondingCurveMigratedError(ExecutionError):
    """Token has already migrated to Raydium; bonding curve is complete."""


class SlippageExceededError(ExecutionError):
    """Price impact exceeds maximum allowed slippage."""


class AIError(FenrirError):
    """AI decision engine failure."""


class AITimeoutError(AIError):
    """AI analysis timed out."""


class WalletError(FenrirError):
    """Wallet or key management error."""
