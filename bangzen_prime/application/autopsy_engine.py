import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AutopsyReport:
    is_zombie: bool
    reason: str

class AutopsyEngine:
    """
    Mesin Forensik untuk mencatat DNA kematian token (kena SL/Rug)
    dan mendeteksi jika token baru memiliki pola yang sama (Zombie Token).
    """
    def __init__(self, db_connection: Any):
        # Menerima koneksi database (sqlite3.Connection) via Dependency Injection
        self.db = db_connection

    def _ensure_table(self) -> None:
        """Membuat tabel autopsy jika belum ada."""
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_autopsy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                setup TEXT,
                liq_usd TEXT,
                top10_pct TEXT,
                recorded_at TEXT
            )
        """)
        self.db.commit()

    def record_death(self, symbol: str, setup: str, liq_usd: Decimal, top10_pct: Decimal, recorded_at: str) -> None:
        """Mencatat DNA koin yang mati (kena SL/rug)."""
        try:
            self._ensure_table()
            cursor = self.db.cursor()
            cursor.execute(
                "INSERT INTO token_autopsy (symbol, setup, liq_usd, top10_pct, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (symbol, setup, str(liq_usd), str(top10_pct), recorded_at)
            )
            self.db.commit()
            logger.info(f"[Autopsy] Mencatat kematian token {symbol} (Setup: {setup})")
        except Exception as e:
            logger.error(f"[Autopsy] Gagal mencatat: {e}")

    def is_zombie_token(self, setup: str, current_liq: Decimal, tolerance_pct: Decimal = Decimal("0.10")) -> AutopsyReport:
        """
        Mengecek apakah token baru punya DNA yang sama dengan koin mati.
        Toleransi default: 10% (0.10) perbedaan likuiditas.
        """
        try:
            self._ensure_table()
            cursor = self.db.cursor()
            cursor.execute("SELECT liq_usd, top10_pct FROM token_autopsy WHERE setup = ?", (setup,))
            rows = cursor.fetchall()

            if not rows:
                return AutopsyReport(False, "no_autopsy_data")

            for row in rows:
                dead_liq = Decimal(row[0])
                max_liq = max(current_liq, dead_liq, Decimal("1"))
                diff_pct = abs(dead_liq - current_liq) / max_liq

                if diff_pct < tolerance_pct:
                    reason = f"DNA match dengan koin mati (Setup: {setup}, LP Match: {diff_pct*100:.1f}%)"
                    return AutopsyReport(True, reason)

            return AutopsyReport(False, "no_dna_match")

        except Exception as e:
            logger.error(f"[Autopsy] Gagal mengecek zombie: {e}")
            return AutopsyReport(False, f"error_{e}")
