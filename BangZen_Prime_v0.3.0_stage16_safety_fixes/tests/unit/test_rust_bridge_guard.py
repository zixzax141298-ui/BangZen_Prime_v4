"""bangzen_native must not be loaded from the working directory (planted-module guard). Stdlib only."""

import importlib
import logging
import os
import sys
import tempfile
import unittest


class RustBridgeGuardTests(unittest.TestCase):
    def setUp(self):
        self._saved_path = list(sys.path)
        self._saved_cwd = os.getcwd()
        self._saved_module = sys.modules.pop("bangzen_native", None)
        self.addCleanup(self._restore)
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _restore(self):
        os.chdir(self._saved_cwd)
        sys.path[:] = self._saved_path
        sys.modules.pop("bangzen_native", None)
        if self._saved_module is not None:
            sys.modules["bangzen_native"] = self._saved_module

    def test_planted_module_in_working_directory_is_ignored(self):
        planted = os.path.join(self._dir.name, "bangzen_native.py")
        with open(planted, "w", encoding="utf-8") as fh:
            fh.write("MARKER = 'planted'\n\ndef min_out_amount(a, b):\n    return -1\n")
        sys.path.insert(0, self._dir.name)
        os.chdir(self._dir.name)
        from bangzen_prime.core import rust_bridge

        with self.assertLogs("bangzen_prime.native", level=logging.ERROR):
            importlib.reload(rust_bridge)
        self.assertIsNone(rust_bridge._rust)
        self.assertEqual(rust_bridge.BACKEND, "python")
        # The Python implementation still answers, so behaviour is the reviewed one.
        self.assertEqual(rust_bridge.min_out_amount(1000, 100), 990)


if __name__ == "__main__":
    unittest.main()
