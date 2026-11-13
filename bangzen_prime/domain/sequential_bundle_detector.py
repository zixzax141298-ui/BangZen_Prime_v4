import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# Konstanta sesuai aturan v2
MIN_WALLETS_FOR_BUNDLE = 5
MAX_TIME_WINDOW_SEC = Decimal("3.0")

@dataclass(frozen=True)
class SequentialBundleReport:
    is_sequential_bundle: bool
    funder: str = ""
    wallet_count: int = 0
    time_window_sec: Decimal = Decimal("0")
    wallets: tuple[str, ...] = ()
    reason: str = ""

class SequentialBundleDetector:
    """
    Mendeteksi bundle Sybil terkoordinasi:
    Jika >= 5 wallet berbeda (didanai funder yang sama) membeli dalam < 3 detik.
    Fail-closed: jika data korup, anggap sebagai bundle (reject).
    """

    def __init__(
        self,
        min_wallets: int = MIN_WALLETS_FOR_BUNDLE,
        max_time_window_sec: Decimal = MAX_TIME_WINDOW_SEC,
    ):
        self.min_wallets = min_wallets
        self.max_time_window_sec = max_time_window_sec

    def _safe_decimal(self, value: Any) -> Decimal | None:
        try:
            if value is None:
                return None
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def detect(self, transactions: list[dict[str, Any]]) -> SequentialBundleReport:
        """
        Analisa list transaksi untuk mendeteksi sequential bundle.
        Format transaksi yang diharapkan:
            {"wallet": str, "funder": str, "timestamp": Decimal|float|str, "type": "buy"}
        """
        # Fail-closed: jika data korup, anggap bundle
        if not isinstance(transactions, list):
            logger.warning("[SequentialBundle] Invalid transactions type, fail-closed.")
            return SequentialBundleReport(
                is_sequential_bundle=True,
                reason="invalid_data_type"
            )

        buys_by_funder: dict[str, list[dict[str, Any]]] = {}

        for tx in transactions:
            if not isinstance(tx, dict):
                logger.warning("[SequentialBundle] Corrupted transaction, fail-closed.")
                return SequentialBundleReport(
                    is_sequential_bundle=True,
                    reason="corrupted_transaction"
                )

            tx_type = str(tx.get("type", "buy")).lower()
            if tx_type != "buy":
                continue

            wallet = str(tx.get("wallet") or tx.get("buyer") or tx.get("user") or "").strip()
            funder = str(tx.get("funder") or tx.get("source") or tx.get("funding_wallet") or "").strip()

            raw_ts = tx.get("timestamp", tx.get("time", tx.get("blockTime", None)))
            ts = self._safe_decimal(raw_ts)

            if ts is None or not wallet or not funder:
                continue

            # Skip self-funded (bukan Sybil kalau dompetnya sama)
            if wallet == funder:
                continue

            buys_by_funder.setdefault(funder, []).append({
                "wallet": wallet,
                "timestamp": ts,
            })

        # Sliding window: cek setiap funder apakah ada 5+ wallet dalam < 3 detik
        for funder, buys in buys_by_funder.items():
            buys.sort(key=lambda x: x["timestamp"])
            n = len(buys)

            for i in range(n):
                window_wallets: set[str] = set()
                start_ts = buys[i]["timestamp"]

                for j in range(i, n):
                    diff = buys[j]["timestamp"] - start_ts
                    if diff >= self.max_time_window_sec:
                        break
                    window_wallets.add(buys[j]["wallet"])

                    if len(window_wallets) >= self.min_wallets:
                        logger.info(
                            f"[SequentialBundle] 🚨 SYBIL BUNDLE DETECTED: "
                            f"{len(window_wallets)} wallets funded by {funder[:8]}... "
                            f"bought within {diff:.2f}s"
                        )
                        return SequentialBundleReport(
                            is_sequential_bundle=True,
                            funder=funder,
                            wallet_count=len(window_wallets),
                            time_window_sec=diff.quantize(Decimal("0.01")),
                            wallets=tuple(sorted(window_wallets)),
                            reason=f"sybil_bundle_{len(window_wallets)}_wallets_{diff:.2f}s"
                        )

        return SequentialBundleReport(
            is_sequential_bundle=False,
            reason="clean_no_bundle_detected"
        )
