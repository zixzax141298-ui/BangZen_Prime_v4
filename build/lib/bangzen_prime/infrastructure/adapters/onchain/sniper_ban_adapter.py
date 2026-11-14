import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SniperBanReport:
    is_banned: bool
    malicious_count: int
    total_sample: int
    malicious_ratio: Decimal
    reason: str


class SniperBanAdapter:
    def __init__(
        self,
        blacklist_path: Path | None = None,
        max_malicious_ratio: Decimal = Decimal("30.0"),
    ):
        self.max_malicious_ratio = max_malicious_ratio
        self._blacklist = self._load_blacklist(blacklist_path)

    def _load_blacklist(self, path) -> set[str]:
        p = Path(path) if path else Path("data/sniper_blacklist.json")
        if not p.exists():
            return set()
        try:
            data = json.loads(p.read_text())
            return set(data) if isinstance(data, list) else set()
        except:
            return set()

    def check_first_buyers(self, first_buyers: list[str]) -> SniperBanReport:
        if not first_buyers or not self._blacklist:
            return SniperBanReport(False, 0, 0, Decimal(0), "no_data")

        sample = first_buyers[:100]
        total = len(sample)
        malicious = sum(1 for b in sample if b in self._blacklist)
        ratio = (Decimal(str(malicious)) / Decimal(str(total))) * Decimal(100)

        return SniperBanReport(
            is_banned=ratio > self.max_malicious_ratio,
            malicious_count=malicious,
            total_sample=total,
            malicious_ratio=ratio.quantize(Decimal("0.01")),
            reason=(
                "toxic_sniper_detected" if ratio > self.max_malicious_ratio else "clean"
            ),
        )
