"""A client for any OpenAI-compatible chat model.

The README's Architecture section has Tidebot talk to "any OpenAI-compatible
model", so this speaks only the common ``/chat/completions`` call. Three
environment variables configure it:

- ``TIDEBOT_AI_URL``: the API base, for example ``https://api.example.com/v1``.
  A URL that already ends in ``/chat/completions`` is used as it is.
- ``TIDEBOT_AI_MODEL``: the model name to ask for.
- ``TIDEBOT_AI_KEY``: the API key. Optional, since local servers often have none.

Every failure becomes an ``AIError`` whose message is safe to show in a
GitHub comment: it never includes the key or the raw response.
"""

from __future__ import annotations

import os
from typing import Dict, List, Mapping, Optional

import httpx

# Seconds to wait for an answer; small free endpoints can be slow.
TIMEOUT = 60
# Seconds to wait for the connection itself.
CONNECT_TIMEOUT = 10
MAX_TOKENS = 800
NOT_CONFIGURED = "AI commands are off here: this Tidebot has no model configured."

Message = Dict[str, str]


class AIError(Exception):
    """The model could not answer; the message is fit for a comment."""


def _endpoint(base_url: str) -> str:
    url = base_url.rstrip("/")
    return url if url.endswith("/chat/completions") else url + "/chat/completions"


class AIClient:
    def __init__(self, base_url: str, model: str, key: Optional[str] = None,
                 http: Optional[httpx.Client] = None):
        self.url = _endpoint(base_url)
        self.model = model
        self.key = key
        self.http = http or httpx.Client(timeout=httpx.Timeout(TIMEOUT, connect=CONNECT_TIMEOUT))

    def complete(self, messages: List[Message], max_tokens: int = MAX_TOKENS,
                 temperature: float = 0.2) -> str:
        """Send ``messages`` and return the model's reply text."""
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        try:
            res = self.http.post(self.url, headers=headers, json={
                "model": self.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature,
            })
        except httpx.TimeoutException:
            raise AIError("the model took too long to answer") from None
        except httpx.HTTPError:
            raise AIError("the model endpoint could not be reached") from None
        if res.status_code == 429:
            raise AIError("the model endpoint is busy (rate limited), try again later")
        if res.status_code != 200:
            raise AIError(f"the model endpoint answered {res.status_code}")
        try:
            text = res.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("the model sent an answer Tidebot could not read") from None
        if not isinstance(text, str) or not text.strip():
            raise AIError("the model sent an empty answer")
        return text.strip()

    def ask(self, system: str, user: str, **kwargs) -> str:
        """One system prompt and one user message, the shape every command uses."""
        return self.complete([{"role": "system", "content": system},
                              {"role": "user", "content": user}], **kwargs)


def ai_from_env(env: Mapping[str, str] = os.environ) -> Optional[AIClient]:
    """Build a client from ``TIDEBOT_AI_*``, or None when no model is set up."""
    url = env.get("TIDEBOT_AI_URL", "").strip()
    model = env.get("TIDEBOT_AI_MODEL", "").strip()
    if not url or not model:
        return None
    return AIClient(url, model, env.get("TIDEBOT_AI_KEY", "").strip() or None)
