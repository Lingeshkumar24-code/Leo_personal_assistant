from __future__ import annotations

from app.core.config import settings
from app.providers.base import AIProvider, ProviderError


def get_provider(name: str | None = None) -> AIProvider:
    """
    Return an AIProvider instance for `name` (defaults to settings.ai_provider).
    This is the ONLY place that knows about concrete provider classes.
    """
    provider_name = (name or settings.ai_provider).lower()

    if provider_name == "gemini":
        from app.providers.gemini_provider import GeminiProvider

        return GeminiProvider()
    if provider_name == "groq":
        from app.providers.groq_provider import GroqProvider

        return GroqProvider()
    if provider_name == "openai_compatible":
        from app.providers.openai_compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider()

    raise ProviderError(
        f"Unknown AI provider '{provider_name}'. Supported: gemini, groq, openai_compatible."
    )
