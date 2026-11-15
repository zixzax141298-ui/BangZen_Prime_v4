"""Outbound-only Telegram signal delivery for allowlisted chats."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence

from bangzen_prime.core.errors import ExternalServiceError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)


class TelegramNotifier:
    """Send plain-text signal notifications; exposes no update or command API."""

    def __init__(
        self,
        *,
        token: str,
        chat_ids: Sequence[str],
        transport: RequestTransport,
        timeout: float,
    ) -> None:
        if not isinstance(token, str) or not token or any(ch.isspace() for ch in token):
            raise ValueError("Telegram bot token is invalid")
        if isinstance(chat_ids, str):
            raise ValueError(
                "Telegram chat IDs must be provided as a sequence, not a string"
            )
        ids = tuple(chat_ids)
        if not ids or any(
            not isinstance(chat_id, str) or not re.fullmatch(r"-?[0-9]+", chat_id)
            for chat_id in ids
        ):
            raise ValueError("Telegram chat IDs must be a non-empty numeric allowlist")
        if len(set(ids)) != len(ids):
            raise ValueError("Telegram chat IDs must not contain duplicates")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Telegram timeout must be a finite positive number")
        self._token = token
        self._chat_ids = ids
        self._transport = transport
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"TelegramNotifier(chat_count={len(self._chat_ids)}, token=[REDACTED])"

    def send(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Telegram message must be non-empty text")
        if len(text) > 4096:
            raise ValueError("Telegram message exceeds the 4096 character limit")

        # Telegram requires the bot token in the URL path. The shared HTTP layer
        # emits generic errors only; never include this URL in logs or exceptions.
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        for chat_id in self._chat_ids:
            body = json.dumps(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            request = HttpRequest(
                method="POST",
                url=url,
                headers={},
                body=body,
                timeout=self._timeout,
            )
            try:
                result = request_json(
                    service="telegram",
                    request=request,
                    transport=self._transport,
                )
            except ExternalServiceError:
                raise
            except Exception:
                # Do not propagate a transport exception that might include the
                # token-bearing request URL or request representation.
                raise ExternalServiceError(
                    "telegram transport failed",
                    service="telegram",
                    retryable=True,
                ) from None
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise ExternalServiceError(
                    "telegram rejected message",
                    service="telegram",
                    retryable=False,
                )
