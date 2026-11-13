"""Telegram signal-only notifier and read-only command handler.

Guarantees:
- Only allowlisted chat ids receive messages or get command replies.
- Payloads are HTML-escaped and length-capped at Telegram's 4096-character limit.
- Every message carries the "[SIGNAL ONLY | PAPER]" label.
- Identical messages within the cooldown window are suppressed.
- The bot token never appears in exception messages or logs.
- Rate limits (429) honour Telegram's retry_after value.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from bangzen_prime.errors import ConfigurationError, ExternalServiceError
from bangzen_prime.infrastructure.http import HttpResponse, Transport, TransportTimeout
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller
from bangzen_prime.native import rust_bridge

logger = logging.getLogger("bangzen_prime.telegram")
MAX_MESSAGE_CHARS = 4096
LABEL = "[SIGNAL ONLY | PAPER]"
SERVICE = "telegram"
API_ROOT = "https://api.telegram.org"


def _retry_after_from_body(body: bytes) -> float | None:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    params = data.get("parameters") if isinstance(data, dict) else None
    value = params.get("retry_after") if isinstance(params, dict) else None
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


def build_message(text: str) -> str:
    """Escape, label, and cap a message. Escaping happens last-but-one so the label stays intact."""
    body = rust_bridge.html_escape(text)
    if not body.startswith(LABEL):
        body = f"<b>{html.escape(LABEL, quote=False)}</b>\n{body}"
    if len(body) > MAX_MESSAGE_CHARS:
        cut = body[: MAX_MESSAGE_CHARS - 3]
        # Never end inside an HTML entity such as "&amp;". Telegram rejects the whole message
        # with 400 when an entity is left unterminated.
        amp = cut.rfind("&")
        if amp != -1 and ";" not in cut[amp:]:
            cut = cut[:amp]
        body = cut + "..."
    return body


@dataclass
class TelegramNotifier:
    token: str = field(repr=False)
    chat_id: str
    allowed_chat_ids: Sequence[str]
    transport: Transport
    caller: ResilientCaller
    timeout: float
    clock: Callable[[], float]
    cooldown_seconds: float = 60.0
    _recent: dict[str, float] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.token:
            raise ConfigurationError("telegram token is required for telegram delivery")
        if self.chat_id not in self.allowed_chat_ids:
            raise ConfigurationError("telegram chat id is not in the allowlist")

    def _url(self, method: str, params: dict[str, str]) -> str:
        # The token is part of the path. It is never logged or placed in exception text.
        return f"{API_ROOT}/bot{self.token}/{method}?{urllib.parse.urlencode(params)}"

    def send(self, text: str) -> None:
        message = build_message(text)
        key = hashlib.sha256(message.encode("utf-8")).hexdigest()
        now = self.clock()
        last = self._recent.get(key)
        if last is not None and now - last < self.cooldown_seconds:
            logger.info("telegram message suppressed by cooldown")
            return
        url = self._url("sendMessage", {"chat_id": self.chat_id, "text": message,
                                        "parse_mode": "HTML", "disable_web_page_preview": "true"})
        self.caller.call(lambda: self._request(url))
        self._recent[key] = now

    def _request(self, url: str) -> None:
        try:
            response: HttpResponse = self.transport(url, self.timeout)
        except TransportTimeout:
            raise ExternalServiceError("telegram timed out", service=SERVICE, retryable=True) from None
        if response.status == 429:
            raise ExternalServiceError("telegram rate limited", service=SERVICE, retryable=True,
                                       status=429, retry_after=_retry_after_from_body(response.body))
        if response.status >= 500:
            raise ExternalServiceError(f"telegram server error {response.status}",
                                       service=SERVICE, retryable=True, status=response.status)
        if response.status >= 400:
            raise ExternalServiceError(f"telegram rejected message ({response.status})",
                                       service=SERVICE, retryable=False, status=response.status)


STATUS_COMMANDS = {"/status", "/health"}


def handle_command(*, chat_id: str, command: str, allowed_chat_ids: Sequence[str],
                   status_text: Callable[[], str]) -> str | None:
    """Read-only command handling. Unknown chats and unknown commands get no reply."""
    if chat_id not in allowed_chat_ids:
        logger.warning("telegram command from unauthorised chat ignored")
        return None
    name = command.strip().split()[0].lower() if command.strip() else ""
    if name in STATUS_COMMANDS:
        return build_message(status_text())
    return None
