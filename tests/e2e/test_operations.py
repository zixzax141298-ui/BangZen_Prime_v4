import os
import unittest
from unittest.mock import patch

from bangzen_prime.interfaces.cli import main


class OperationsCliTest(unittest.TestCase):
    def test_broadcast_cannot_be_enabled_by_env(self):
        # Memastikan bot menolak menyala jika BROADCAST_ENABLED=true tapi LIVE_TRADING=false
        with patch.dict(
            os.environ,
            {"BANGZEN_BROADCAST_ENABLED": "true", "BANGZEN_LIVE_TRADING": "false"},
        ):
            # Berikan perintah dummy "status" agar argparse tidak crash
            code = main(["status"])
            self.assertEqual(code, 1)  # EXIT_ERROR


if __name__ == "__main__":
    unittest.main()
