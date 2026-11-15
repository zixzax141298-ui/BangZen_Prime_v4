"""Test package. Installs a network guard so any real socket use fails the test run."""

import socket

_REAL_CONNECT = socket.socket.connect


class NetworkAccessForbidden(RuntimeError):
    pass


def _guarded_connect(self, address):  # type: ignore[no-untyped-def]
    raise NetworkAccessForbidden(f"tests must not open sockets: {address!r}")


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
