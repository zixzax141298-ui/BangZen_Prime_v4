from __future__ import annotations

import importlib.util
import unittest


class RemovedBurnerWalletTest(unittest.TestCase):
    def test_plaintext_burner_wallet_module_is_not_importable(self):
        self.assertIsNone(
            importlib.util.find_spec(
                "bangzen_prime.infrastructure.adapters.execution.burner_wallet"
            )
        )

    def test_project_local_ed25519_signer_module_is_not_importable(self):
        self.assertIsNone(
            importlib.util.find_spec(
                "bangzen_prime.infrastructure.adapters.execution.ed25519"
            )
        )


if __name__ == "__main__":
    unittest.main()
