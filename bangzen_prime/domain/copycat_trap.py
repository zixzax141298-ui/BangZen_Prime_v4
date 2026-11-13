import logging
import re
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

# Daftar simbol canonical yang sudah mapan (bisa dipindah ke config nanti)
CANONICAL_ESTABLISHED: frozenset[str] = frozenset({
    "BONK", "WIF", "POPCAT", "MEW", "BOME", "MYRO", "SILLY", "PNUT", "GOAT", "MOODENG",
})

@dataclass(frozen=True)
class CopycatReport:
    is_fake: bool
    reason: str
    target: str = ""

class CopycatTrap:
    """Menjebak token palsu yang meniru token trending high-cap."""

    def __init__(self, canonical_symbols: frozenset[str] | None = None):
        self.canonical = canonical_symbols or CANONICAL_ESTABLISHED

    def normalize_symbol(self, sym: str) -> str:
        """Membersihkan emoji dan karakter non-alfanumerik untuk perbandingan."""
        return re.sub(r"[^A-Za-z0-9]", "", sym).upper()

    def analyze(self, symbol: str, name: str, liq_usd: Decimal) -> CopycatReport:
        """Mengevaluasi apakah simbol atau nama adalah impostor/copycat."""
        norm_sym = self.normalize_symbol(symbol)
        norm_name = self.normalize_symbol(name)

        # Cek jika token mengklaim token canonical tapi likuiditas tipis (< $150k)
        for canon in self.canonical:
            if norm_sym == canon and liq_usd < Decimal("150000"):
                return CopycatReport(
                    True,
                    f"impersonator_token_{canon}_low_liq",
                    target=canon
                )
            if canon in norm_name and norm_sym != canon and liq_usd < Decimal("50000"):
                return CopycatReport(
                    True,
                    f"copycat_derivative_{canon}_low_liq",
                    target=canon
                )

        # Cek unicode zero-width atau karakter menipu (homoglyph)
        if len(symbol) != len(symbol.encode("ascii", "ignore")):
            if norm_sym in self.canonical:
                return CopycatReport(True, "homoglyph_unicode_impersonator", target=norm_sym)

        return CopycatReport(False, "authentic", target="")

    def check_token(self, symbol: str, name: str, liq_usd: Decimal) -> CopycatReport:
        """Helper entry point untuk pipeline verification."""
        return self.analyze(symbol, name, liq_usd)
