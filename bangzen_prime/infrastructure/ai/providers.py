"""AI providers behind one interface. Selected by BANGZEN_AI_PROVIDER.

- anthropic: POST https://api.anthropic.com/v1/messages (x-api-key, anthropic-version header)
- openai:   POST https://api.openai.com/v1/chat/completions (Bearer key)
- grok:     POST https://api.x.ai/v1/chat/completions (Bearer key, OpenAI-compatible)

Model identifiers come from BANGZEN_AI_MODEL. They are NOT verified against the providers' live
model lists here. Keys are sent only in headers and never appear in exception text.
"""

from __future__ import annotations

import json
from datetime import datetime  # noqa: F401 - kept for signature symmetry
from typing import Any

from bangzen_prime.errors import ConfigurationError, ExternalServiceError
from bangzen_prime.infrastructure.http import HttpRequest, RequestTransport, request_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

MAX_OUTPUT_TOKENS = 300


class _Base:
    name = "base"

    def __init__(self, *, api_key: str, model: str, transport: RequestTransport,
                 caller: ResilientCaller, timeout: float) -> None:
        if not api_key:
            raise ConfigurationError(f"{self.name} API key is required")
        if not model:
            raise ConfigurationError(f"{self.name} model is required")
        self._key = api_key
        self._model = model
        self._transport = transport
        self._caller = caller
        self._timeout = timeout

    def _post(self, url: str, headers: dict[str, str], body: dict) -> Any:
        request = HttpRequest("POST", url, {**headers, "Content-Type": "application/json"},
                              json.dumps(body).encode("utf-8"), self._timeout)
        return self._caller.call(lambda: request_json(service=self.name, request=request,
                                                      transport=self._transport))

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class AnthropicProvider(_Base):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def complete(self, system: str, user: str) -> str:
        payload = self._post(self.URL, {"x-api-key": self._key, "anthropic-version": "2023-06-01"},
                             {"model": self._model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system,
                              "messages": [{"role": "user", "content": user}]})
        try:
            return "".join(block["text"] for block in payload["content"] if block.get("type") == "text")
        except (KeyError, TypeError, AttributeError):
            raise ExternalServiceError("anthropic returned an unexpected shape", service=self.name,
                                       retryable=False) from None


class _OpenAICompatible(_Base):
    URL = ""

    def complete(self, system: str, user: str) -> str:
        payload = self._post(self.URL, {"Authorization": f"Bearer {self._key}"},
                             {"model": self._model, "max_tokens": MAX_OUTPUT_TOKENS,
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]})
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise ExternalServiceError(f"{self.name} returned an unexpected shape", service=self.name,
                                       retryable=False) from None


class OpenAIProvider(_OpenAICompatible):
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"


class GrokProvider(_OpenAICompatible):
    name = "grok"
    URL = "https://api.x.ai/v1/chat/completions"


PROVIDERS: dict[str, type[_Base]] = {"anthropic": AnthropicProvider, "openai": OpenAIProvider,
                                     "grok": GrokProvider}


def build_provider(*, name: str, api_key: str | None, model: str | None, transport: RequestTransport,
                   caller: ResilientCaller, timeout: float) -> _Base:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ConfigurationError("unknown AI provider")
    defaults = {"anthropic": "claude-opus-4-1", "openai": "gpt-4o", "grok": "grok-4"}
    return cls(api_key=api_key or "", model=model or defaults[name], transport=transport,
               caller=caller, timeout=timeout)
