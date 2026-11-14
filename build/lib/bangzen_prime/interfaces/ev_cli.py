import logging
from decimal import Decimal

from bangzen_prime.application.ev_engine import EVEngine

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main():
    print("\n" + "=" * 50)
    print("🧠 BANGZEN PRIME - EV ENGINE SIMULATOR (Fenrir v2)")
    print("=" * 50)

    # Modal $1000, Risiko 1.5% per trade
    engine = EVEngine(equity_usd=Decimal("1000.00"), risk_pct=Decimal("1.5"))

    # SKENARIO 1: Trade Standard (EV Negatif)
    print("\n[SKENARIO 1: TP TERLALU KECIL]")
    entry = Decimal("0.00001000")
    sl = Decimal("0.00000850")  # SL -15%
    tp = Decimal("0.00001500")  # TP +50%
    cost = Decimal("2.5")  # Fee 2.5%

    result1 = engine.simulate_entry(entry, sl, tp, cost)
    print(f"Status: {'✅ DITERIMA' if result1.is_executed else '❌ DITOLAK'}")
    print(f"Alasan: {result1.reason}")

    # SKENARIO 2: Trade Sniper (EV Positif)
    print("\n[SKENARIO 2: TP BESAR & EV POSITIF]")
    sl2 = Decimal("0.00000850")  # SL -15%
    tp2 = Decimal("0.00002500")  # TP +150% (Lebih besar)

    result2 = engine.simulate_entry(entry, sl2, tp2, cost)
    print(f"Status: {'✅ DITERIMA' if result2.is_executed else '❌ DITOLAK'}")
    print(f"Alasan: {result2.reason}")
    print(f"Posisi USD: ${result2.position_size_usd:.2f}")
    print(f"Expected Value: {result2.expected_value}")

    print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
