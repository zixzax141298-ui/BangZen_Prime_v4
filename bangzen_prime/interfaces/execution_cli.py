"""Signal inspection CLI. This command never signs or submits a transaction.

The former implementation printed a simulated purchase using a hard-coded illustrative
price and EV inputs. That output could be mistaken for an actual execution result.
This replacement reports only the scanner's observed signal decision.
"""
from __future__ import annotations

import argparse
import json
import sys

from bangzen_prime.bootstrap import build_container
from bangzen_prime.errors import BangzenError
from bangzen_prime.settings import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a Solana token signal; no swap or wallet action is performed."
    )
    parser.add_argument("mint", help="Base58 Solana token mint")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
        if settings.live_trading or settings.broadcast_enabled:
            raise BangzenError("live execution is blocked in this release")
        container = build_container(settings)
    except BangzenError as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}), file=sys.stderr)
        return 1

    try:
        results = container.scan.execute("solana", [args.mint])
        if not results:
            print(json.dumps({"status": "NO_RESULT", "mint": args.mint,
                              "execution": "NOT_ATTEMPTED"}, indent=2))
            return 1
        signal = results[0]
        print(json.dumps({
            "mint": args.mint,
            "signal_status": signal.status,
            "reasons": signal.reasons,
            "execution": "NOT_ATTEMPTED",
            "live_trading": False,
        }, indent=2, default=str))
        return 0 if signal.status == "ACCEPTED" else 1
    except BangzenError as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc),
                          "execution": "NOT_ATTEMPTED"}), file=sys.stderr)
        return 1
    finally:
        container.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
