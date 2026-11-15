"""HTTP transport abstraction. Production uses urllib; tests inject fakes (no network)."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bangzen_prime.core.errors import ExternalServiceError


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow redirects. urllib would copy custom headers, including API keys, to the new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirects)


def _check_not_redirect(service: str, status: int) -> None:
    if 300 <= status < 400:
        raise ExternalServiceError(
            f"{service} redirect refused",
            service=service,
            retryable=False,
            status=status,
        )


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


Transport = Callable[[str, float], HttpResponse]


class TransportTimeout(Exception):
    """Raised by a transport when the request times out."""


def urllib_transport(url: str, timeout: float) -> HttpResponse:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "bangzen-prime/0.1"}
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return HttpResponse(
                response.status, response.read(), dict(response.headers)
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read() or b"", dict(exc.headers or {}))
    except TimeoutError as exc:
        raise TransportTimeout(str(type(exc).__name__)) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise TransportTimeout("timeout") from None
        raise ExternalServiceError(
            "network error", service="http", retryable=True
        ) from None


def get_json(*, service: str, url: str, timeout: float, transport: Transport) -> Any:
    """Single GET with status-to-error mapping. Retries are handled by ResilientCaller."""
    try:
        response = transport(url, timeout)
    except TransportTimeout:
        raise ExternalServiceError(
            f"{service} timed out", service=service, retryable=True
        ) from None
    _check_not_redirect(service, response.status)
    if response.status == 429:
        retry_after = _parse_retry_after(response.headers)
        raise ExternalServiceError(
            f"{service} rate limited",
            service=service,
            retryable=True,
            status=429,
            retry_after=retry_after,
        )
    if response.status >= 500:
        raise ExternalServiceError(
            f"{service} server error {response.status}",
            service=service,
            retryable=True,
            status=response.status,
        )
    if response.status >= 400:
        raise ExternalServiceError(
            f"{service} rejected request {response.status}",
            service=service,
            retryable=False,
            status=response.status,
        )
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExternalServiceError(
            f"{service} returned malformed JSON",
            service=service,
            retryable=False,
            status=response.status,
        ) from None


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                return None
            return seconds if seconds >= 0 else None
    return None


@dataclass(frozen=True)
class HttpRequest:
    """Request with method, headers, and optional body. Headers may carry API keys:
    never place them in exception messages or logs."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout: float


RequestTransport = Callable[[HttpRequest], HttpResponse]


def urllib_request_transport(request: HttpRequest) -> HttpResponse:
    if request.method not in ("GET", "POST"):
        raise ValueError("only GET and POST are supported")
    headers = {
        "Accept": "application/json",
        "User-Agent": "bangzen-prime/0.2",
        **dict(request.headers),
    }
    if request.body is not None:
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        request.url, data=request.body, headers=headers, method=request.method
    )
    try:
        with _OPENER.open(req, timeout=request.timeout) as response:
            return HttpResponse(
                response.status, response.read(), dict(response.headers)
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read() or b"", dict(exc.headers or {}))
    except TimeoutError:
        raise TransportTimeout("timeout") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise TransportTimeout("timeout") from None
        raise ExternalServiceError(
            "network error", service="http", retryable=True
        ) from None


def request_json(
    *, service: str, request: HttpRequest, transport: RequestTransport
) -> Any:
    """Send one request and map the response. Retries are handled by ResilientCaller."""
    try:
        response = transport(request)
    except TransportTimeout:
        raise ExternalServiceError(
            f"{service} timed out", service=service, retryable=True
        ) from None
    return _map_response(service, response)


def _map_response(service: str, response: HttpResponse) -> Any:
    _check_not_redirect(service, response.status)
    if response.status == 429:
        raise ExternalServiceError(
            f"{service} rate limited",
            service=service,
            retryable=True,
            status=429,
            retry_after=_parse_retry_after(response.headers),
        )
    if response.status >= 500:
        raise ExternalServiceError(
            f"{service} server error {response.status}",
            service=service,
            retryable=True,
            status=response.status,
        )
    if response.status >= 400:
        raise ExternalServiceError(
            f"{service} rejected request {response.status}",
            service=service,
            retryable=False,
            status=response.status,
        )
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExternalServiceError(
            f"{service} returned malformed JSON",
            service=service,
            retryable=False,
            status=response.status,
        ) from None
