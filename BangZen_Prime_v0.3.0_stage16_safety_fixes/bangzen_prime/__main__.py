"""Entry point for `python -m bangzen_prime` and the `bangzen-prime` console script."""

import sys

from bangzen_prime.core.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
