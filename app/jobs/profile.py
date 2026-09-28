"""
§15 User Profile. Editable by the user, stored locally, never exposed
unnecessarily. This is data plumbing for the (not-yet-implemented) Job
Assistant — implemented now because other phases may also want to read a
user's name/preferences.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.config import settings


@dataclass
class UserProfile:
    name: str = ""
    email: str = ""
    phone: str = ""
    education: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    resume_paths: list[str] = field(default_factory=list)
    preferred_roles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    remote_preference: str = ""
    salary_preferences: str = ""
    availability: str = ""


class ProfileStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path(settings.data_dir) / "profile.json")

    def load(self) -> UserProfile:
        if not self.path.exists():
            return UserProfile()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return UserProfile(**raw)

    def save(self, profile: UserProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(profile), indent=2, ensure_ascii=False), encoding="utf-8")


profile_store = ProfileStore()
