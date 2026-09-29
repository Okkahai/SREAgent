"""Scripted LLM for tests only. Production code never imports this."""

from typing import Any

from opspilot.agent.llm import Final, History, LLMUnavailable, ToolCall


class FakeLLM:
    model = "fake"

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.prompts: list[History] = []

    def step(self, system: str, prompt: str, history: History, tools: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
        self.prompts.append(list(history))
        nxt = self.script.pop(0)
        if callable(nxt):
            nxt = nxt(history)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


__all__ = ["FakeLLM", "Final", "LLMUnavailable", "ToolCall"]
