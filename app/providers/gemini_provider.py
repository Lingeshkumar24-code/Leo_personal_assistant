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


def _messages_to_gemini(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """Split out a system instruction and convert the rest to Gemini's `contents` format."""
    system_instruction = None
    contents = []
    for m in messages:
        if m.role == "system":
            system_instruction = (system_instruction + "\n" + m.content) if system_instruction else m.content
            continue
        role = "model" if m.role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.content}]})
    return system_instruction, contents


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        if not settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is not set in .env")
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ProviderError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            ) from e
        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self.model_name = settings.gemini_model

    def _model(self, system_instruction: str | None = None, tools: list[dict] | None = None):
        return self._genai.GenerativeModel(
            self.model_name,
            system_instruction=system_instruction,
            tools=tools,
        )

    def generate(self, messages: list[Message], **kwargs) -> GenerationResult:
        system, contents = _messages_to_gemini(messages)
        model = self._model(system_instruction=system)
        try:
            response = model.generate_content(contents, **kwargs)
        except Exception as e:  # noqa: BLE001 - surfacing provider errors uniformly
            raise ProviderError(f"Gemini generate_content failed: {e}") from e
        return GenerationResult(text=response.text, raw=response)

    def stream(self, messages: list[Message], **kwargs) -> Iterator[str]:
        system, contents = _messages_to_gemini(messages)
        model = self._model(system_instruction=system)
        try:
            response = model.generate_content(contents, stream=True, **kwargs)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Gemini streaming failed: {e}") from e

    def vision(self, messages: list[Message], image_paths: list[str], **kwargs) -> GenerationResult:
        system, contents = _messages_to_gemini(messages)
        model = self._model(system_instruction=system)
        images = []
        for path in image_paths:
            try:
                from PIL import Image

                images.append(Image.open(path))
            except ImportError as e:
                raise ProviderError("Pillow is required for vision(). Run: pip install pillow") from e
        prompt_text = "\n".join(m.content for m in messages if m.role != "system")
        try:
            response = model.generate_content([prompt_text, *images], **kwargs)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Gemini vision call failed: {e}") from e
        return GenerationResult(text=response.text, raw=response)

    def structured_output(self, messages: list[Message], schema: dict[str, Any], **kwargs) -> dict[str, Any]:
        system, contents = _messages_to_gemini(messages)
        instructive_system = (
            (system + "\n" if system else "")
            + "You must respond with ONLY valid JSON matching this schema, no markdown fences:\n"
            + json.dumps(schema)
        )
        model = self._model(system_instruction=instructive_system)
        try:
            response = model.generate_content(
                contents,
                generation_config={"response_mime_type": "application/json"},
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Gemini structured_output failed: {e}") from e
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Gemini did not return valid JSON: {response.text!r}") from e

    def tool_call(self, messages: list[Message], tools: list[ToolSpec], **kwargs) -> GenerationResult:
        system, contents = _messages_to_gemini(messages)
        gemini_tools = [
            {
                "function_declarations": [
                    {"name": t.name, "description": t.description, "parameters": t.parameters}
                    for t in tools
                ]
            }
        ]
        model = self._model(system_instruction=system, tools=gemini_tools)
        try:
            response = model.generate_content(contents, **kwargs)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Gemini tool_call failed: {e}") from e

        tool_calls = []
        text_parts = []
        for candidate in getattr(response, "candidates", []) or []:
            for part in candidate.content.parts:
                fc = getattr(part, "function_call", None)
                if fc and fc.name:
                    tool_calls.append(ToolCallRequest(name=fc.name, arguments=dict(fc.args)))
                elif getattr(part, "text", None):
                    text_parts.append(part.text)
        return GenerationResult(text="".join(text_parts), tool_calls=tool_calls, raw=response)
