import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bangzen_prime.infrastructure.resilience.policies import Clock
from bangzen_prime.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmartMoneyIntel:
    is_bundled: bool
    has_mev: bool
    is_kol_dumping: bool
    sm_count: int
    sm_cluster: bool
    score: Decimal
    holding_strength: Decimal
    quality_score: Decimal
    recommendation: str


class SmartMoneyAdapter:
    def __init__(self, transport, settings: Settings, clock: Clock):
        self.transport = transport
        self.settings = settings
        self.clock = clock
        self.smart_money_wallets = set()
        self.mev_wallets = set()
        self._load_wallets()

    def _load_wallets(self):
        fpath = "data/target_wallets.json"
        if not os.path.exists(fpath):
            logger.warning("[!] File data/target_wallets.json tidak ditemukan.")
            return
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
                self.smart_money_wallets = set(data.get("smart_money", []))
                self.mev_wallets = set(data.get("mev_predators", []))
                logger.info(
                    f"[*] Loaded {len(self.smart_money_wallets)} Bangzen Smart Money & {len(self.mev_wallets)} MEV wallets."
                )
        except Exception as e:
            logger.error(f"[-] Gagal memuat target_wallets.json: {e}")

    def _safe_decimal(self, val: Any) -> Decimal:
        try:
            if val is None:
                return Decimal(0)
            return Decimal(str(val))
        except Exception:
            return Decimal(0)

    def _safe_int(self, val: Any) -> int:
        try:
            if val is None:
                return 0
            return int(float(val))
        except Exception:
            return 0

    async def analyze_funder_graph(self, rc_data: dict) -> bool:
        """Deteksi Bundled Wallets (Satu Funder)."""
        try:
            holders = (rc_data.get("topHolders") or [])[:20]
            funder_map_dict = rc_data.get("funderMap") or {}
            funder_map = {}
            for h in holders:
                if not isinstance(h, dict):
                    continue

                raw_f1 = h.get("funder") or h.get("fundedBy") or {}
                if isinstance(raw_f1, dict):
                    f1_dict = raw_f1
                    f1 = str(
                        f1_dict.get("address")
                        or f1_dict.get("funder")
                        or h.get("funderAddress")
                        or ""
                    )
                else:
                    f1_dict = {}
                    f1 = str(raw_f1 or h.get("funderAddress") or "")

                if not f1:
                    continue

                raw_f2 = (
                    f1_dict.get("parentFunder")
                    or f1_dict.get("funder")
                    or f1_dict.get("fundedBy")
                    or funder_map_dict.get(f1)
                    or h.get("funder2")
                    or h.get("parentFunder")
                )
                f2 = (
                    str(raw_f2.get("address"))
                    if isinstance(raw_f2, dict)
                    else str(raw_f2 or "")
                )
                root_funder = f2 if (f2 and f2 != f1) else f1

                pct = self._safe_decimal(h.get("pct") or h.get("percentage"))
                if root_funder not in funder_map:
                    funder_map[root_funder] = {"count": 0, "pct_total": Decimal(0)}
                funder_map[root_funder]["count"] += 1
                funder_map[root_funder]["pct_total"] += pct

            return any(
                info["count"] >= 3 and info["pct_total"] > Decimal("5.0")
                for info in funder_map.values()
            )
        except Exception as e:
            logger.error(f"Funder graph error: {e}")
            return False

    async def track_mev_predators(self, trades: list) -> bool:
        """Cek MEV Predator di 100 pembeli awal."""
        if not self.mev_wallets or not trades:
            return False
        found_predators = set()
        for p in trades[:100]:
            if isinstance(p, dict):
                addr = str(p.get("wallet") or p.get("owner") or p.get("address") or "")
                if addr in self.mev_wallets:
                    found_predators.add(addr)
        return len(found_predators) >= 2

    async def check_kol_dumping(self, trades: list) -> bool:
        """Cek apakah Smart Money menjual (dump) < 30 menit."""
        if not self.smart_money_wallets or not trades:
            return False
        now = self.clock.now().timestamp()
        for p in trades:
            if not isinstance(p, dict):
                continue
            addr = str(p.get("wallet") or p.get("owner") or p.get("address") or "")
            if addr not in self.smart_money_wallets:
                continue

            ts = self._safe_decimal(
                p.get("time")
                or p.get("timestamp")
                or p.get("blockTime")
                or p.get("created_at")
            )
            if ts > 1e11:
                ts /= Decimal("1000.0")
            if ts > 0 and (Decimal(str(now)) - ts) > Decimal(1800):
                continue

            tx_type = str(
                p.get("type") or p.get("side") or p.get("txType") or ""
            ).lower()
            if "sell" in tx_type or p.get("is_sell") is True or p.get("isSell") is True:
                return True
        return False

    async def check_smart_money_overlap(self, rc_data: dict, trades: list) -> tuple:
        """Cek apakah ada Bangzen Smart Money yang membeli (Overlap)."""
        found = set()
        for h in rc_data.get("topHolders") or []:
            if isinstance(h, dict):
                addr = str(h.get("address") or h.get("owner") or h.get("wallet") or "")
                if addr in self.smart_money_wallets:
                    found.add(addr)

        for p in trades:
            if isinstance(p, dict):
                addr = str(p.get("wallet") or p.get("owner") or p.get("address") or "")
                if addr in self.smart_money_wallets:
                    found.add(addr)
        return len(found), list(found)

    def calculate_quality_score(self, sm_count: int, is_dumping: bool) -> tuple:
        """Hitung skor kualitas Bangzen Smart Money."""
        if sm_count == 0:
            return Decimal(0), "no_smart_money"

        base = Decimal("55.0") if sm_count >= 2 else Decimal("25.0")
        if sm_count >= 3:
            base += Decimal("10.0")
        elif sm_count >= 2:
            base += Decimal("5.0")

        if is_dumping:
            return Decimal("30.0"), "smart_money_selling_flag"

        # Asumsi holding kuat jika tidak dumping
        strength = Decimal("0.85")
        base += strength * Decimal("30.0")
        return round(min(base, Decimal("100.0")), 1), "assumed_holding"

    async def execute_intel(
        self, mint: str, rugcheck_data: dict, trades_data: list
    ) -> SmartMoneyIntel:
        is_bundled = await self.analyze_funder_graph(rugcheck_data)
        has_mev = await self.track_mev_predators(trades_data)
        is_dumping = await self.check_kol_dumping(trades_data)
        sm_count, _ = await self.check_smart_money_overlap(rugcheck_data, trades_data)

        quality_score, _ = self.calculate_quality_score(sm_count, is_dumping)
        holding_strength = Decimal("0.0") if is_dumping else Decimal("0.85")

        # Skor Keamanan (Penalti)
        safety_score = Decimal("100.0")
        if is_bundled:
            safety_score -= Decimal("50.0")
        if has_mev:
            safety_score -= Decimal("30.0")
        if is_dumping:
            safety_score -= Decimal("40.0")
        safety_score = max(safety_score, Decimal("0.0"))

        recommendation = "SCALP"
        if quality_score >= Decimal("60.0") and safety_score > Decimal("50.0"):
            recommendation = "HOLD"

        return SmartMoneyIntel(
            is_bundled=is_bundled,
            has_mev=has_mev,
            is_kol_dumping=is_dumping,
            sm_count=sm_count,
            sm_cluster=(sm_count >= 2),
            score=safety_score,
            holding_strength=holding_strength,
            quality_score=quality_score,
            recommendation=recommendation,
        )
