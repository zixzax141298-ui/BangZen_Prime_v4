from __future__ import annotations

import contextlib
import io
import unittest

from bangzen_prime.errors import BangzenError
from bangzen_prime.infrastructure.adapters.execution.wallet_signer import WalletSigner
from bangzen_prime.interfaces.wallet_cli import main as wallet_cli_main


class LegacyWalletSignerLockTest(unittest.TestCase):
    def test_constructor_refuses_to_load_or_sign_private_key(self):
        secret = "synthetic-private-key-must-never-be-logged"
        with self.assertRaises(BangzenError) as ctx:
            WalletSigner(secret)
        self.assertNotIn(secret, str(ctx.exception))

    def test_wallet_diagnostics_are_keyless_and_report_locked_state(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = wallet_cli_main()

        self.assertEqual(result, 2)
        self.assertIn("paper-only", output.getvalue())
        self.assertIn("No private key was loaded", output.getvalue())
        self.assertNotIn("synthetic-private-key", output.getvalue())


if __name__ == "__main__":
    unittest.main()
