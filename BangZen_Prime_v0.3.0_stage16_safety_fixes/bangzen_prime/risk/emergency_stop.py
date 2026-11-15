"""HALT.flag kill switch (AI_RULES non_negotiable_safety.halt_flag; blueprint 11.2 and 21).

Fail-closed: the switch counts as engaged when the flag file exists, and also when its state
cannot be determined (permissions, a path whose parent is not a directory, and so on). Only a
definite "file does not exist" lets decision-producing processes continue.

The default path is resolved to an absolute path when the module is imported, so a later change of
working directory cannot make the flag invisible. Callers should pass Settings.halt_flag_path.
"""

from __future__ import annotations

import os

HALT_FLAG_PATH = os.path.abspath("HALT.flag")


def halt_flag_engaged(path: str | os.PathLike[str] = HALT_FLAG_PATH) -> bool:
    try:
        os.stat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def halt_engaged(
    emergency_stop: bool, path: str | os.PathLike[str] = HALT_FLAG_PATH
) -> bool:
    """Either the environment kill switch (BANGZEN_EMERGENCY_STOP) or the HALT.flag file."""
    return bool(emergency_stop) or halt_flag_engaged(path)
