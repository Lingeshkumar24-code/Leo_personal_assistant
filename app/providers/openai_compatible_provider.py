from __future__ import annotations

import json
from typing import Any, Iterator

import requests

from app.core.config import settings
from app.providers.base import (
    AIProvider,
    GenerationResult,
    Message,
    ProviderError,
    ToolCallRequest,
    ToolSpec,
)


class OpenAICompatibleProvider(AIProvider):
    """
    Works with any server exposing the OpenAI /chat/completions API shape:
    LM Studio, vLLM, Ollama's OpenAI-compat endpoint, OpenRouter, etc.
    This is how optional local-model support plugs in without making Ollama
    (or any single backend) a hard dependency.
    """

    name = "openai_compatible"

    def __init__(self):
        if not settings.openai_compat_base_url:
            raise ProviderError("OPENAI_COMPATIBLE_BASE_URL is not set in .env")
        self.base_url = settings.openai_compat_base_url.rstrip("/")
        self.api_key = settings.openai_compat_api_key
        self.model_name = settings.openai_compat_model or "default"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise ProviderError(f"OpenAI-compatible request failed: {e}") from e

    def generate(self, messages: list[Message], **kwargs) -> GenerationResult:
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **kwargs,
        }
        data = self._post(payload)
        text = data["choices"][0]["message"].get("content", "")
        return GenerationResult(text=text, raw=data)

    def stream(self, messages: list[Message], **kwargs) -> Iterator[str]:
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            **kwargs,
        }
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith(b"data: "):
                        continue
                    chunk = line[len(b"data: "):]
                    if chunk.strip() == b"[DONE]":
                        break
                    obj = json.loads(chunk)
                    delta = obj["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
        except requests.RequestException as e:
            raise ProviderError(f"OpenAI-compatible streaming failed: {e}") from e

    def vision(self, messages: list[Message], image_paths: list[str], **kwargs) -> GenerationResult:
        raise ProviderError(
            "This OpenAI-compatible endpoint's vision support is not configured. "
            "Use a vision-capable local model and extend this method, or switch AI_PROVIDER=gemini."
        )

    def structured_output(self, messages: list[Message], schema: dict[str, Any], **kwargs) -> dict[str, Any]:
        instructive = list(messages) + [
            Message(
                role="system",
                content="Respond with ONLY valid JSON matching this schema, no markdown fences:\n"
                + json.dumps(schema),
            )
        ]
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in instructive],
            "response_format": {"type": "json_object"},
            **kwargs,
        }
        data = self._post(payload)
        text = data["choices"][0]["message"].get("content", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Model did not return valid JSON: {text!r}") from e

    def tool_call(self, messages: list[Message], tools: list[ToolSpec], **kwargs) -> GenerationResult:
        openai_tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in tools
        ]
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "tools": openai_tools,
            "tool_choice": "auto",
            **kwargs,
        }
        data = self._post(payload)
        message = data["choices"][0]["message"]
        tool_calls = []
        for tc in message.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCallRequest(name=tc["function"]["name"], arguments=args))
        return GenerationResult(text=message.get("content") or "", tool_calls=tool_calls, raw=data)
