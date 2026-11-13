"""Transaction ingestion. Two sources, one interface.

- MockTransactionStream: deterministic events for tests and demos. No network.
- YellowstoneStream: gRPC Geyser client. It needs the `grpc` package and generated protobuf
  stubs for Yellowstone. Neither is bundled here, so it refuses to start with a clear error
  instead of failing at runtime. Stub generation is a manual step documented in RUNBOOK.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from bangzen_prime.errors import ConfigurationError


@dataclass(frozen=True)
class ChainEvent:
    slot: int
    signature: str
    accounts: tuple[str, ...]


class MockTransactionStream:
    def __init__(self, events: Iterable[ChainEvent]) -> None:
        self._events = list(events)

    def events(self) -> Iterator[ChainEvent]:
        yield from self._events


class YellowstoneStream:
    STUB_MODULE = "bangzen_prime.infrastructure.chain.yellowstone_pb2"

    def __init__(self, *, endpoint: str, token: str) -> None:
        if not endpoint.startswith("https://"):
            raise ConfigurationError("gRPC endpoint must use https")
        if importlib.util.find_spec("grpc") is None:
            raise ConfigurationError("grpc package is not installed")
        if importlib.util.find_spec(self.STUB_MODULE) is None:
            raise ConfigurationError(
                "Yellowstone protobuf stubs are not generated; see RUNBOOK"
            )
        self._endpoint = endpoint
        self._token = token
        self._stubs = importlib.import_module(self.STUB_MODULE)

    def events(
        self,
    ) -> Iterator[ChainEvent]:  # pragma: no cover - requires network and stubs
        raise ConfigurationError("live gRPC streaming is not enabled in this build")
