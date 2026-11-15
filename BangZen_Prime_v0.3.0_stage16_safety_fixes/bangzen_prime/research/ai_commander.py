import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from bangzen_prime.data.providers.news_adapter import (
    NewsScraperAdapter,
)
from bangzen_prime.discovery.cross_chain_radar_adapter import (
    CrossChainRadarAdapter,
)
from bangzen_prime.discovery.lp_sniper_adapter import (
    LPSniperAdapter,
)
from bangzen_prime.research.ai_brain import AIBrain, TradeContext
from bangzen_prime.security.honeypot_adapter import (
    HoneypotAdapter,
)
from bangzen_prime.security.sybil_adapter import SybilAdapter
from bangzen_prime.strategies.smart_money_engine import SmartMoneyEngine

logger = logging.getLogger(__name__)

# bangzen_prime/application/ai_commander.py -> repository root is parents[2]
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


class AICommander:
    def __init__(
        self,
        brain: AIBrain,
        sybil: SybilAdapter,
        honeypot: HoneypotAdapter,
        news: NewsScraperAdapter,
        radar: CrossChainRadarAdapter,
        lp_sniper: LPSniperAdapter,
        smart_money: SmartMoneyEngine,
    ):
        self.brain = brain
        self.sybil = sybil
        self.honeypot = honeypot
        self.news = news
        self.radar = radar
        self.lp_sniper = lp_sniper
        self.smart_money = smart_money
        self.tools = self._load_tools()

    def _load_tools(self) -> list:
        # Resolve relative to the repository root, not the process working directory,
        # and surface failures instead of silently exposing an empty tool list.
        path = _CONFIG_DIR / "ai_tools.json"
        try:
            with path.open("r", encoding="utf-8") as f:
                tools = json.load(f)
        except (OSError, ValueError) as exc:
            logger.warning(
                "[AICommander] AI tool config unavailable (%s): %s",
                path.name,
                type(exc).__name__,
            )
            return []
        if not isinstance(tools, list):
            logger.warning(
                "[AICommander] AI tool config has invalid shape: %s", path.name
            )
            return []
        return tools

    async def execute(
        self,
        mint: str,
        context: TradeContext,
        market_data: dict,
        audit_data: dict,
    ) -> Any:
        logger.info("[AICommander] Memulai analisis untuk %s...", mint[:8])

        # Gate 1: Honeypot must explicitly establish token safety.
        try:
            honeypot = await self.honeypot.check_honeypot(mint, force=True)
        except Exception as exc:
            logger.warning(
                "[Commander] Honeypot check failed for %s: %s",
                mint[:8],
                type(exc).__name__,
            )
            return self._reject(context, "honeypot_check_unavailable")

        if not getattr(honeypot, "available", False):
            logger.warning(
                "[Commander] Honeypot evidence unavailable for %s",
                mint[:8],
            )
            return self._reject(context, "honeypot_check_unavailable")

        if (
            getattr(honeypot, "is_honeypot", None) is not False
            or getattr(honeypot, "is_safe", False) is not True
        ):
            logger.warning(
                "[Commander] Honeypot check did not explicitly establish safety for %s",
                mint[:8],
            )
            return self._reject(context, "honeypot_not_cleared")

        # Gate 2: Sybil evidence must be present and explicitly clear.
        top_holders = (
            audit_data.get("top_holders") if isinstance(audit_data, dict) else None
        )
        if not isinstance(top_holders, list) or not top_holders:
            logger.warning(
                "[Commander] Sybil holder evidence missing for %s",
                mint[:8],
            )
            return self._reject(context, "sybil_holder_evidence_unavailable")

        try:
            sybil = await self.sybil.check_sybil_cluster(mint, top_holders)
        except Exception as exc:
            logger.warning(
                "[Commander] Sybil check unavailable for %s: %s",
                mint[:8],
                type(exc).__name__,
            )
            return self._reject(context, "sybil_check_unavailable")

        if not getattr(sybil, "available", False):
            logger.warning(
                "[Commander] Sybil evidence incomplete for %s",
                mint[:8],
            )
            return self._reject(context, "sybil_check_unavailable")

        if getattr(sybil, "is_bundled", None) is True:
            logger.warning(
                "[Commander] Confirmed shared-funder cluster for %s",
                mint[:8],
            )
            return self._reject(context, "sybil_cluster_detected")

        if getattr(sybil, "is_bundled", None) is not False:
            logger.warning(
                "[Commander] Sybil result was not explicitly clear for %s",
                mint[:8],
            )
            return self._reject(context, "sybil_check_not_cleared")

        # Both deterministic safety gates passed. The model is an analyst only: it returns an
        # analysis that is logged and returned. It never gates, selects, or triggers a trade.
        analysis = self.brain.analyze(context)
        logger.info(
            "[Commander] AI analysis for %s: status=%s risk=%s",
            mint[:8],
            analysis.decision,
            analysis.risk_level,
        )
        return analysis

    def _reject(self, context: TradeContext, reason: str) -> Any:
        from bangzen_prime.research.ai_brain import NO_ANALYSIS, AIDecision

        return AIDecision(
            decision=NO_ANALYSIS,
            confidence=Decimal(0),
            reason=reason,
            source="commander_prefilter",
        )
