"""
AI provider abstraction (§4 of the spec).

No other part of LEO should import google.generativeai or groq directly.
Everything goes through this interface so the provider is swappable via
config, with zero code changes elsewhere.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ToolSpec:
    """Describes a callable tool so the model can request it (tool_call)."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON-schema-like dict


@dataclass
class ToolCallRequest:
    name: str
    arguments: dict[str, Any]


@dataclass
class GenerationResult:
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    raw: Any = None


class ProviderError(RuntimeError):
    """Raised when the underlying AI API call fails."""


class AIProvider(ABC):
    """Abstract base class every concrete provider (Gemini, Groq, ...) implements."""

    name: str = "base"

    @abstractmethod
    def generate(self, messages: list[Message], **kwargs) -> GenerationResult:
        """Single-shot text generation."""
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: list[Message], **kwargs) -> Iterator[str]:
        """Streamed text generation, yielding chunks as they arrive."""
        raise NotImplementedError

    @abstractmethod
    def vision(self, messages: list[Message], image_paths: list[str], **kwargs) -> GenerationResult:
        """Generation with image inputs (used by the Vision System, Phase 4)."""
        raise NotImplementedError

    @abstractmethod
    def structured_output(self, messages: list[Message], schema: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Generation constrained to return JSON matching `schema`."""
        raise NotImplementedError

    @abstractmethod
    def tool_call(
        self, messages: list[Message], tools: list[ToolSpec], **kwargs
    ) -> GenerationResult:
        """Generation that may request one or more tool calls."""
        raise NotImplementedError
