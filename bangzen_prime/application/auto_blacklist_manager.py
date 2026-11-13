import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

DEFAULT_BLACKLIST_PATH = Path("data/sniper_blacklist.json")
DEFAULT_MAX_BLACKLIST_SIZE = 10000

@dataclass(frozen=True)
class BlacklistReport:
    added_count: int
    total_blacklisted: int
    source: str
    reason: str

class AutoBlacklistManager:
    def __init__(self, blacklist_path: Path | str = DEFAULT_BLACKLIST_PATH, max_size: int = DEFAULT_MAX_BLACKLIST_SIZE):
        self.blacklist_path = Path(blacklist_path)
        self.max_size = max_size
        self._blacklist: set[str] = self._load()

    def _load(self) -> set[str]:
        if not self.blacklist_path.exists():
            self.blacklist_path.parent.mkdir(parents=True, exist_ok=True)
            return set()
        try:
            data = json.loads(self.blacklist_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {str(addr).strip() for addr in data if str(addr).strip()}
            return set()
        except Exception as e:
            logger.error(f"[AutoBlacklist] Gagal load: {e}")
            return set()

    def _save(self) -> None:
        try:
            self.blacklist_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.blacklist_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(sorted(self._blacklist), indent=2), encoding="utf-8")
            temp_path.replace(self.blacklist_path)
        except Exception as e:
            logger.error(f"[AutoBlacklist] Gagal save: {e}")

    def _trim(self) -> None:
        if len(self._blacklist) > self.max_size:
            excess = len(self._blacklist) - self.max_size
            removed = list(self._blacklist)[:excess]
            for wallet in removed:
                self._blacklist.discard(wallet)

    def is_blacklisted(self, wallet: str) -> bool:
        return wallet in self._blacklist

    def add_wallets(self, wallets: Iterable[str], source: str, reason: str) -> BlacklistReport:
        added = 0
        for w in wallets:
            if not w or not isinstance(w, str): continue
            w = w.strip()
            if len(w) < 32 or len(w) > 44: continue
            if w not in self._blacklist:
                self._blacklist.add(w)
                added += 1

        if added > 0:
            self._trim()
            self._save()
            logger.info(f"[AutoBlacklist] Added {added} wallets from {source}: {reason}")

        return BlacklistReport(
            added_count=added, total_blacklisted=len(self._blacklist),
            source=source, reason=reason
        )
