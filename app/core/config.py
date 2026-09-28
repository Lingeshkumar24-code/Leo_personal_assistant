"""
Central configuration for LEO.

All secrets and environment-specific values come from environment variables
(loaded from .env via python-dotenv). Nothing here is hardcoded, per the
spec's config/security requirements. Import `settings` anywhere you need
configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env once, at import time, without overriding real environment vars.
load_dotenv(override=False)


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # AI provider selection
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "gemini"))

    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))

    openai_compat_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_COMPATIBLE_BASE_URL", ""))
    openai_compat_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_COMPATIBLE_API_KEY", ""))
    openai_compat_model: str = field(default_factory=lambda: os.getenv("OPENAI_COMPATIBLE_MODEL", ""))

    # Voice (Phase 2)
    stt_provider: str = field(default_factory=lambda: os.getenv("STT_PROVIDER", ""))
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", ""))
    wake_word: str = field(default_factory=lambda: os.getenv("LEO_WAKE_WORD", "leo"))

    # Feature flags
    screen_capture_enabled: bool = field(default_factory=lambda: _bool("SCREEN_CAPTURE_ENABLED", False))
    browser_automation_enabled: bool = field(default_factory=lambda: _bool("BROWSER_AUTOMATION_ENABLED", False))

    # Operating mode: manual | assisted | autonomous
    mode: str = field(default_factory=lambda: os.getenv("LEO_MODE", "manual"))

    # Paths
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LEO_DATA_DIR", "data")))
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("LEO_LOG_DIR", "logs")))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LEO_LOG_LEVEL", "INFO"))

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def validate_for_provider(self) -> list[str]:
        """Return a list of human-readable problems, empty if config is usable."""
        problems = []
        if self.ai_provider == "gemini" and not self.gemini_api_key:
            problems.append("AI_PROVIDER=gemini but GEMINI_API_KEY is not set in .env")
        elif self.ai_provider == "groq" and not self.groq_api_key:
            problems.append("AI_PROVIDER=groq but GROQ_API_KEY is not set in .env")
        elif self.ai_provider == "openai_compatible" and not self.openai_compat_base_url:
            problems.append(
                "AI_PROVIDER=openai_compatible but OPENAI_COMPATIBLE_BASE_URL is not set in .env"
            )
        elif self.ai_provider not in {"gemini", "groq", "openai_compatible"}:
            problems.append(
                f"Unknown AI_PROVIDER '{self.ai_provider}'. Use gemini | groq | openai_compatible."
            )
        if self.mode not in {"manual", "assisted", "autonomous"}:
            problems.append(f"Unknown LEO_MODE '{self.mode}'. Use manual | assisted | autonomous.")
        return problems


settings = Settings()
