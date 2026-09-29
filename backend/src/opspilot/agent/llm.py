"""LLM port. The agent only sees `LLM.step`; providers live behind it (docs/07)."""

import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class LLMUnavailable(Exception):
    """Provider missing, unreachable or misbehaving. Investigations fail as retryable."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Final:
    output: dict[str, Any]


# One executed call and the (already redacted) result text the model gets back.
History = list[tuple[ToolCall, str]]


class LLM(Protocol):
    model: str

    def step(
        self, system: str, prompt: str, history: History, tools: list[dict[str, Any]]
    ) -> ToolCall | Final: ...


_SECRET = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{8,}|(?:api[_-]?key|token|secret|password|authorization)"
    r"[\"'\s:=]+(?:bearer\s+)?[^\s\"',;]{4,}|sk-[a-z0-9_-]{16,}|gh[pousr]_[a-z0-9]{20,})"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def redact(s: str) -> str:
    """Second redaction pass before anything leaves for the provider (docs/08 §5)."""
    return _EMAIL.sub("[email]", _SECRET.sub("[redacted]", s))


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self.model = model
        self._client = httpx.Client(
            base_url="https://api.anthropic.com",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=timeout,
        )

    def step(
        self, system: str, prompt: str, history: History, tools: list[dict[str, Any]]
    ) -> ToolCall | Final:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        for call, result in history:
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.args}
                    ],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": call.id, "content": result}],
                }
            )
        try:
            r = self._client.post(
                "/v1/messages",
                json={
                    "model": self.model,
                    "max_tokens": 2048,
                    "system": system,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": {"type": "any"},
                },
            )
            r.raise_for_status()
            blocks = r.json()["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}"[:300]) from exc
        for b in blocks:
            if b.get("type") == "tool_use":
                if b["name"] == "submit_findings":
                    return Final(b["input"])
                return ToolCall(b["id"], b["name"], b.get("input") or {})
        raise LLMUnavailable("model returned no tool call")
