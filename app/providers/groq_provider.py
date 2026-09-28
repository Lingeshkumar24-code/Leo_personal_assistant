from __future__ import annotations

import json
from typing import Any, Iterator

from app.core.config import settings
from app.providers.base import (
    AIProvider,
    GenerationResult,
    Message,
    ProviderError,
    ToolCallRequest,
    ToolSpec,
)


def _messages_to_openai(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self):
        if not settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is not set in .env")
        try:
            from groq import Groq
        except ImportError as e:
            raise ProviderError("groq package is not installed. Run: pip install groq") from e
        self._client = Groq(api_key=settings.groq_api_key)
        self.model_name = settings.groq_model

    def generate(self, messages: list[Message], **kwargs) -> GenerationResult:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=_messages_to_openai(messages),
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Groq chat.completions failed: {e}") from e
        text = response.choices[0].message.content or ""
        return GenerationResult(text=text, raw=response)

    def stream(self, messages: list[Message], **kwargs) -> Iterator[str]:
        try:
            stream = self._client.chat.completions.create(
                model=self.model_name,
                messages=_messages_to_openai(messages),
                stream=True,
                **kwargs,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Groq streaming failed: {e}") from e

    def vision(self, messages: list[Message], image_paths: list[str], **kwargs) -> GenerationResult:
        raise ProviderError(
            "The configured Groq model does not support vision in this implementation. "
            "Use a Groq vision-capable model or switch AI_PROVIDER=gemini for vision tasks."
        )

    def structured_output(self, messages: list[Message], schema: dict[str, Any], **kwargs) -> dict[str, Any]:
        instructive = list(messages) + [
            Message(
                role="system",
                content=(
                    "Respond with ONLY valid JSON matching this schema, no markdown fences:\n"
                    + json.dumps(schema)
                ),
            )
        ]
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=_messages_to_openai(instructive),
                response_format={"type": "json_object"},
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Groq structured_output failed: {e}") from e
        text = response.choices[0].message.content or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Groq did not return valid JSON: {text!r}") from e

    def tool_call(self, messages: list[Message], tools: list[ToolSpec], **kwargs) -> GenerationResult:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=_messages_to_openai(messages),
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else "none",
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Groq tool_call failed: {e}") from e

        choice = response.choices[0]
        tool_calls = []
        for tc in getattr(choice.message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCallRequest(name=tc.function.name, arguments=args))
        return GenerationResult(text=choice.message.content or "", tool_calls=tool_calls, raw=response)
