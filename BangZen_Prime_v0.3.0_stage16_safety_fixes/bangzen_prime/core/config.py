"""Typed, fail-closed settings loaded from BANGZEN_* environment variables."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from bangzen_prime.core.errors import ConfigurationError, DomainError
from bangzen_prime.risk.emergency_stop import halt_engaged
from bangzen_prime.core.operating_mode import OperatingMode
from bangzen_prime.discovery.tokens import validate_mint

ENV_PREFIX = "BANGZEN_"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})
_KNOWN_KEYS = frozenset(
    {
        "LIVE_TRADING",
        "PAPER_TRADING",
        "DRY_RUN",
        "EMERGENCY_STOP",
        "HALT_FLAG_PATH",
        "DB_PATH",
        "LOG_LEVEL",
        "DEXSCREENER_BASE_URL",
        "RUGCHECK_BASE_URL",
        "HTTP_TIMEOUT_SECONDS",
        "HTTP_MAX_ATTEMPTS",
        "MARKET_DATA_MAX_AGE_SECONDS",
        "MIN_LIQUIDITY_USD",
        "MIN_VOLUME_24H_USD",
        "MAX_RISK_SCORE",
        "MAX_RISK_PER_TRADE_PCT",
        "MAX_OPEN_POSITIONS",
        "MAX_EXPOSURE_QUOTE",
        "MAX_DRAWDOWN_PCT",
        "FEE_RATE",
        "SLIPPAGE_RATE",
        "STARTING_EQUITY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "BROADCAST_ENABLED",
        "HELIUS_API_KEY",
        "BIRDEYE_API_KEY",
        "JUPITER_API_KEY",
        "SOLANA_TRACKER_API_KEY",
        "LUNARCRUSH_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GROK_API_KEY",
        "AI_ENABLED",
        "AI_PROVIDER",
        "AI_PROVIDER_ORDER",
        "AI_MODEL",
        "AI_CONFIDENCE_THRESHOLD",
        "WATCHDOG_TIMEOUT_SECONDS",
        "JITO_TIP_CAP_LAMPORTS",
        "JUPITER_SLIPPAGE_BPS",
        "GRPC_ENDPOINT",
        "MODE",
        "OPERATING_MODE",
        "POLICY_PATH",
        "WALLET_PUBLIC_ADDRESS",
    }
)
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
AI_PROVIDERS = frozenset({"anthropic", "openai", "grok"})
_AI_KEY_FOR = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "grok": "grok_api_key",
}


def _parse_bool(key: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigurationError(f"{ENV_PREFIX}{key} must be a boolean")


def _parse_decimal(
    key: str,
    raw: str,
    *,
    lo: Decimal | None = None,
    hi: Decimal | None = None,
    strict_lo: bool = False,
) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, ValueError):
        raise ConfigurationError(
            f"{ENV_PREFIX}{key} must be a decimal number"
        ) from None
    if not value.is_finite():
        raise ConfigurationError(f"{ENV_PREFIX}{key} must be finite")
    if lo is not None and (value < lo or (strict_lo and value == lo)):
        raise ConfigurationError(f"{ENV_PREFIX}{key} is out of range")
    if hi is not None and value > hi:
        raise ConfigurationError(f"{ENV_PREFIX}{key} is out of range")
    return value


def _parse_int(key: str, raw: str, *, lo: int, hi: int) -> int:
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigurationError(f"{ENV_PREFIX}{key} must be an integer") from None
    if not lo <= value <= hi:
        raise ConfigurationError(f"{ENV_PREFIX}{key} is out of range")
    return value


def parse_env_file(path: str) -> dict[str, str]:
    """Read KEY=VALUE lines from a dotenv file. Only BANGZEN_* keys are returned.

    Stdlib only, so it works in a bare Termux install. Missing file means no overrides.
    Values are passed through from_env, which applies the same validation as real env vars.
    """
    if not os.path.isfile(path):
        return {}
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, sep, value = line.partition("=")
            key = key.strip()
            if not sep or not key.startswith(ENV_PREFIX):
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            elif " #" in value:
                # Unquoted values may carry an inline comment: KEY=value # note
                value = value.split(" #", 1)[0].rstrip()
            values[key] = value
    return values


def load_settings_env(dotenv_path: str = ".env") -> dict[str, str]:
    """Process environment, with BANGZEN_* values from the dotenv file filling any gaps.

    Real environment variables always win over the file.
    """
    merged = dict(os.environ)
    for key, value in parse_env_file(dotenv_path).items():
        merged.setdefault(key, value)
    return merged


@dataclass(frozen=True)
class Settings:
    live_trading: bool = False
    paper_trading: bool = True
    dry_run: bool = True
    emergency_stop: bool = False
    # Absolute path of the HALT.flag kill switch. Defaults to HALT.flag in the startup directory.
    halt_flag_path: str = field(default_factory=lambda: os.path.abspath("HALT.flag"))
    db_path: str = "bangzen.db"
    log_level: str = "INFO"
    dexscreener_base_url: str = "https://api.dexscreener.com"
    rugcheck_base_url: str = "https://api.rugcheck.xyz/v1"
    http_timeout_seconds: float = 10.0
    http_max_attempts: int = 3
    market_data_max_age_seconds: int = 120
    min_liquidity_usd: Decimal = Decimal(10000)
    min_volume_24h_usd: Decimal = Decimal(5000)
    max_risk_score: Decimal = Decimal(60)
    max_risk_per_trade_pct: Decimal = Decimal(1)
    max_open_positions: int = 3
    max_exposure_quote: Decimal = Decimal(500)
    max_drawdown_pct: Decimal = Decimal(20)
    fee_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0.005")
    starting_equity: Decimal = Decimal(1000)
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_allowed_chat_ids: tuple[str, ...] = ()
    operating_mode: OperatingMode = OperatingMode.TELEGRAM_ONLY
    wallet_public_address: str | None = field(default=None, repr=False)
    broadcast_enabled: bool = False
    helius_api_key: str | None = field(default=None, repr=False)
    birdeye_api_key: str | None = field(default=None, repr=False)
    jupiter_api_key: str | None = field(default=None, repr=False)
    solana_tracker_api_key: str | None = field(default=None, repr=False)
    lunarcrush_api_key: str | None = field(default=None, repr=False)
    anthropic_api_key: str | None = field(default=None, repr=False)
    openai_api_key: str | None = field(default=None, repr=False)
    grok_api_key: str | None = field(default=None, repr=False)
    ai_enabled: bool = False
    ai_provider: str = "anthropic"
    # Ordered failover list. The first entry equals ai_provider. Only one provider is active per call.
    ai_provider_order: tuple[str, ...] = ()
    ai_model: str | None = None
    ai_confidence_threshold: Decimal = Decimal("0.6")
    watchdog_timeout_seconds: float = 5.0
    jito_tip_cap_lamports: int = 100_000
    jupiter_slippage_bps: int = 50
    grpc_endpoint: str | None = None
    mode: str = "paper"
    policy_path: str | None = None

    def halt_active(self) -> bool:
        """True if the env kill switch is set or HALT.flag exists at the configured absolute path."""
        return halt_engaged(self.emergency_stop, self.halt_flag_path)

    def __post_init__(self) -> None:
        if not os.path.isabs(self.halt_flag_path):
            raise ConfigurationError("halt_flag_path must be an absolute path")
        if not isinstance(self.operating_mode, OperatingMode):
            raise ConfigurationError(
                "operating_mode must be TELEGRAM_ONLY, EXECUTION_ONLY, or HYBRID"
            )
        if bool(self.telegram_bot_token) != bool(self.telegram_allowed_chat_ids):
            raise ConfigurationError(
                "Telegram bot token and allowed chat ids must be configured together"
            )
        if self.wallet_public_address is not None:
            try:
                validate_mint(self.wallet_public_address)
            except DomainError:
                raise ConfigurationError(
                    "BANGZEN_WALLET_PUBLIC_ADDRESS must be a valid Solana public address"
                ) from None
        # Only paper mode exists. Live execution is not implemented and is never selected by config.
        if self.mode != "paper":
            raise ConfigurationError(
                "BANGZEN_MODE must be 'paper'; live execution is not implemented"
            )
        if self.ai_provider not in AI_PROVIDERS:
            raise ConfigurationError(
                "ai_provider must be one of anthropic, openai, grok"
            )
        order = self.ai_provider_order or (self.ai_provider,)
        if not order or any(name not in AI_PROVIDERS for name in order):
            raise ConfigurationError("ai_provider_order must list only anthropic, openai, grok")
        if len(set(order)) != len(order):
            raise ConfigurationError("ai_provider_order must not contain duplicates")
        if order[0] != self.ai_provider:
            raise ConfigurationError("ai_provider must be the first entry of ai_provider_order")
        if self.ai_enabled and not any(
            getattr(self, _AI_KEY_FOR[name]) is not None for name in order
        ):
            raise ConfigurationError(
                "AI is enabled but no provider in ai_provider_order has an API key"
            )
        if not (Decimal(0) <= self.ai_confidence_threshold <= Decimal(1)):
            raise ConfigurationError("ai_confidence_threshold must be within [0, 1]")
        if not (1.0 <= self.watchdog_timeout_seconds <= 60.0):
            raise ConfigurationError("watchdog_timeout_seconds must be within [1, 60]")
        if self.jito_tip_cap_lamports <= 0:
            raise ConfigurationError("jito_tip_cap_lamports must be positive")
        if not (0 <= self.jupiter_slippage_bps <= 1000):
            raise ConfigurationError("jupiter_slippage_bps must be within [0, 1000]")

        # Live execution is intentionally unavailable until the complete transaction
        # inspection, signer, RPC, reconciliation, and end-to-end safety gates exist.
        # Preserve actionable legacy validation errors, then block even fully configured keys.
        if self.live_trading:
            raise ConfigurationError(
                "LIVE_TRADING is blocked: production execution pipeline is not implemented"
            )
        if self.broadcast_enabled:
            if not self.live_trading:
                raise ConfigurationError("BROADCAST_ENABLED requires LIVE_TRADING=true")
            raise ConfigurationError(
                "BROADCAST_ENABLED is blocked: live broadcast is not implemented"
            )
        if "OWNER_PRIVATE_KEY" in os.environ:
            raise ConfigurationError(
                "FATAL: OWNER_PRIVATE_KEY terdeteksi! Hapus segera demi keamanan."
            )

        if not self.paper_trading or not self.dry_run:
            raise ConfigurationError("paper_trading and dry_run must both be true")
        if self.log_level not in _LOG_LEVELS:
            raise ConfigurationError("log_level is not supported")
        if not (Decimal(0) < self.max_risk_per_trade_pct <= Decimal(100)):
            raise ConfigurationError("max_risk_per_trade_pct must be in (0, 100]")
        if not (Decimal(0) < self.max_drawdown_pct <= Decimal(100)):
            raise ConfigurationError("max_drawdown_pct must be in (0, 100]")
        if not (Decimal(0) <= self.fee_rate <= Decimal("0.1")):
            raise ConfigurationError("fee_rate must be in [0, 0.1]")
        if not (Decimal(0) <= self.slippage_rate <= Decimal("0.5")):
            raise ConfigurationError("slippage_rate must be in [0, 0.5]")
        if self.starting_equity <= 0 or self.max_exposure_quote <= 0:
            raise ConfigurationError("equity and exposure limits must be positive")
        if (
            self.min_liquidity_usd < 0
            or self.max_risk_score < 0
            or self.max_risk_score > 100
        ):
            raise ConfigurationError("liquidity and risk score limits are out of range")
        for chat_id in self.telegram_allowed_chat_ids:
            # str.isdigit() also accepts Unicode digits such as "²", so match ASCII explicitly.
            if not re.fullmatch(r"-?[0-9]+", chat_id):
                raise ConfigurationError("telegram chat ids must be numeric")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = dict(os.environ if env is None else env)
        if "OWNER_PRIVATE_KEY" in source:
            raise ConfigurationError(
                "FATAL: OWNER_PRIVATE_KEY terdeteksi! Hapus segera demi keamanan."
            )
        unknown = sorted(
            key[len(ENV_PREFIX) :]
            for key in source
            if key.startswith(ENV_PREFIX) and key[len(ENV_PREFIX) :] not in _KNOWN_KEYS
        )
        if unknown:
            raise ConfigurationError(
                f"unknown configuration keys: {', '.join(unknown)}"
            )

        def value(key: str) -> str | None:
            raw = source.get(ENV_PREFIX + key)
            return raw if raw is not None and raw.strip() != "" else None

        kwargs: dict[str, object] = {}
        if (v := value("LIVE_TRADING")) is not None:
            kwargs["live_trading"] = _parse_bool("LIVE_TRADING", v)
        if (v := value("PAPER_TRADING")) is not None:
            kwargs["paper_trading"] = _parse_bool("PAPER_TRADING", v)
        if (v := value("DRY_RUN")) is not None:
            kwargs["dry_run"] = _parse_bool("DRY_RUN", v)
        if (v := value("EMERGENCY_STOP")) is not None:
            kwargs["emergency_stop"] = _parse_bool("EMERGENCY_STOP", v)
        if (v := value("HALT_FLAG_PATH")) is not None:
            kwargs["halt_flag_path"] = v.strip()
        if (v := value("DB_PATH")) is not None:
            kwargs["db_path"] = v.strip()
        if (v := value("LOG_LEVEL")) is not None:
            kwargs["log_level"] = v.strip().upper()
        for key, attr in (
            ("DEXSCREENER_BASE_URL", "dexscreener_base_url"),
            ("RUGCHECK_BASE_URL", "rugcheck_base_url"),
        ):
            if (v := value(key)) is not None:
                if not v.startswith("https://"):
                    raise ConfigurationError(f"{ENV_PREFIX}{key} must use https")
                kwargs[attr] = v.strip().rstrip("/")
        if (v := value("HTTP_TIMEOUT_SECONDS")) is not None:
            kwargs["http_timeout_seconds"] = float(
                _parse_decimal(
                    "HTTP_TIMEOUT_SECONDS",
                    v,
                    lo=Decimal(0),
                    strict_lo=True,
                    hi=Decimal(60),
                )
            )
        if (v := value("HTTP_MAX_ATTEMPTS")) is not None:
            kwargs["http_max_attempts"] = _parse_int(
                "HTTP_MAX_ATTEMPTS", v, lo=1, hi=10
            )
        if (v := value("MARKET_DATA_MAX_AGE_SECONDS")) is not None:
            kwargs["market_data_max_age_seconds"] = _parse_int(
                "MARKET_DATA_MAX_AGE_SECONDS", v, lo=1, hi=86400
            )
        if (v := value("MIN_VOLUME_24H_USD")) is not None:
            kwargs["min_volume_24h_usd"] = _parse_decimal(
                "MIN_VOLUME_24H_USD", v, lo=Decimal(0)
            )
        if (v := value("MIN_LIQUIDITY_USD")) is not None:
            kwargs["min_liquidity_usd"] = _parse_decimal(
                "MIN_LIQUIDITY_USD", v, lo=Decimal(0)
            )
        if (v := value("MAX_RISK_SCORE")) is not None:
            kwargs["max_risk_score"] = _parse_decimal(
                "MAX_RISK_SCORE", v, lo=Decimal(0), hi=Decimal(100)
            )
        if (v := value("MAX_RISK_PER_TRADE_PCT")) is not None:
            kwargs["max_risk_per_trade_pct"] = _parse_decimal(
                "MAX_RISK_PER_TRADE_PCT",
                v,
                lo=Decimal(0),
                strict_lo=True,
                hi=Decimal(100),
            )
        if (v := value("MAX_OPEN_POSITIONS")) is not None:
            kwargs["max_open_positions"] = _parse_int(
                "MAX_OPEN_POSITIONS", v, lo=1, hi=1000
            )
        if (v := value("MAX_EXPOSURE_QUOTE")) is not None:
            kwargs["max_exposure_quote"] = _parse_decimal(
                "MAX_EXPOSURE_QUOTE", v, lo=Decimal(0), strict_lo=True
            )
        if (v := value("MAX_DRAWDOWN_PCT")) is not None:
            kwargs["max_drawdown_pct"] = _parse_decimal(
                "MAX_DRAWDOWN_PCT", v, lo=Decimal(0), strict_lo=True, hi=Decimal(100)
            )
        if (v := value("FEE_RATE")) is not None:
            kwargs["fee_rate"] = _parse_decimal(
                "FEE_RATE", v, lo=Decimal(0), hi=Decimal("0.1")
            )
        if (v := value("SLIPPAGE_RATE")) is not None:
            kwargs["slippage_rate"] = _parse_decimal(
                "SLIPPAGE_RATE", v, lo=Decimal(0), hi=Decimal("0.5")
            )
        if (v := value("STARTING_EQUITY")) is not None:
            kwargs["starting_equity"] = _parse_decimal(
                "STARTING_EQUITY", v, lo=Decimal(0), strict_lo=True
            )
        if (v := value("TELEGRAM_BOT_TOKEN")) is not None:
            token = v.strip()
            if any(ch.isspace() for ch in token):
                raise ConfigurationError(
                    "telegram bot token must not contain whitespace"
                )
            kwargs["telegram_bot_token"] = token
        if (v := value("BROADCAST_ENABLED")) is not None:
            kwargs["broadcast_enabled"] = _parse_bool("BROADCAST_ENABLED", v)

        for key, attr in (
            ("HELIUS_API_KEY", "helius_api_key"),
            ("BIRDEYE_API_KEY", "birdeye_api_key"),
            ("JUPITER_API_KEY", "jupiter_api_key"),
            ("SOLANA_TRACKER_API_KEY", "solana_tracker_api_key"),
            ("LUNARCRUSH_API_KEY", "lunarcrush_api_key"),
            ("ANTHROPIC_API_KEY", "anthropic_api_key"),
            ("OPENAI_API_KEY", "openai_api_key"),
            ("GROK_API_KEY", "grok_api_key"),
        ):
            if (v := value(key)) is not None:
                kwargs[attr] = v.strip()

        if (v := value("AI_ENABLED")) is not None:
            kwargs["ai_enabled"] = _parse_bool("AI_ENABLED", v)
        if (v := value("AI_PROVIDER")) is not None:
            kwargs["ai_provider"] = v.strip().lower()
        if (v := value("AI_PROVIDER_ORDER")) is not None:
            names = tuple(part.strip().lower() for part in v.split(",") if part.strip())
            kwargs["ai_provider_order"] = names
            if names:
                kwargs["ai_provider"] = names[0]
        if (v := value("AI_MODEL")) is not None:
            kwargs["ai_model"] = v.strip()
        if (v := value("AI_CONFIDENCE_THRESHOLD")) is not None:
            kwargs["ai_confidence_threshold"] = _parse_decimal(
                "AI_CONFIDENCE_THRESHOLD", v, lo=Decimal(0), hi=Decimal(1)
            )
        if (v := value("WATCHDOG_TIMEOUT_SECONDS")) is not None:
            kwargs["watchdog_timeout_seconds"] = float(
                _parse_decimal(
                    "WATCHDOG_TIMEOUT_SECONDS", v, lo=Decimal(1), hi=Decimal(60)
                )
            )
        if (v := value("JITO_TIP_CAP_LAMPORTS")) is not None:
            kwargs["jito_tip_cap_lamports"] = _parse_int(
                "JITO_TIP_CAP_LAMPORTS", v, lo=1, hi=10**12
            )
        if (v := value("JUPITER_SLIPPAGE_BPS")) is not None:
            kwargs["jupiter_slippage_bps"] = _parse_int(
                "JUPITER_SLIPPAGE_BPS", v, lo=0, hi=1000
            )
        if (v := value("GRPC_ENDPOINT")) is not None:
            if not v.startswith("https://"):
                raise ConfigurationError(f"{ENV_PREFIX}GRPC_ENDPOINT must use https")
            kwargs["grpc_endpoint"] = v.strip().rstrip("/")
        if (v := value("MODE")) is not None:
            kwargs["mode"] = v.strip().lower()
        if (v := value("OPERATING_MODE")) is not None:
            try:
                kwargs["operating_mode"] = OperatingMode(v.strip().upper())
            except ValueError:
                raise ConfigurationError(
                    "BANGZEN_OPERATING_MODE must be TELEGRAM_ONLY, EXECUTION_ONLY, or HYBRID"
                ) from None
        if (v := value("POLICY_PATH")) is not None:
            kwargs["policy_path"] = v.strip()
        if (v := value("WALLET_PUBLIC_ADDRESS")) is not None:
            kwargs["wallet_public_address"] = v.strip()
        if (v := value("TELEGRAM_ALLOWED_CHAT_IDS")) is not None:
            kwargs["telegram_allowed_chat_ids"] = tuple(
                part.strip() for part in v.split(",") if part.strip()
            )
        return cls(**kwargs)  # type: ignore[arg-type]
