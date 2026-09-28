"""Job <-> profile matching and form-field mapping (pure logic, no browser)."""
from __future__ import annotations

import re

from app.jobs.profile import UserProfile


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\+\#\.]{2,}", text.lower()))


def score_job(job_text: str, profile: UserProfile) -> dict:
    """Honest keyword match of the user's declared skills against a job description."""
    job_lower = job_text.lower()
    matched = [s for s in profile.skills if s.lower() in job_lower]
    missing = [s for s in profile.skills if s.lower() not in job_lower]
    role_hit = any(r.lower() in job_lower for r in profile.preferred_roles)
    score = round(100 * len(matched) / len(profile.skills)) if profile.skills else 0
    return {
        "score": score,
        "matched_skills": matched,
        "unmentioned_skills": missing,
        "matches_preferred_role": role_hit,
        "note": "Keyword match against skills in your profile; read the posting before applying.",
    }


# Fields LEO must NOT guess: it asks the user instead (spec: never fabricate answers).
_SENSITIVE = ("salary", "ctc", "compensation", "visa", "sponsor", "disability", "gender", "race", "ethnic",
              "veteran", "criminal", "notice", "why", "cover", "describe", "tell us", "experience with")


def map_field_to_profile(label: str, name: str, input_type: str, profile: UserProfile) -> str | None:
    """Return the profile value for a form field, or None if LEO shouldn't/can't fill it."""
    key = f"{label} {name}".lower()
    if any(w in key for w in _SENSITIVE):
        return None
    if input_type == "email" or "email" in key or "e-mail" in key:
        return profile.email or None
    if input_type == "tel" or any(w in key for w in ("phone", "mobile", "contact number")):
        return profile.phone or None
    parts = profile.name.split()
    if "first" in key and "name" in key:
        return parts[0] if parts else None
    if "last" in key and ("name" in key or "surname" in key):
        return parts[-1] if len(parts) > 1 else None
    if "full name" in key or key.strip() in {"name", "your name"} or re.search(r"\bname\b", key):
        return profile.name or None
    if "linkedin" in key or "github" in key or "portfolio" in key:
        return None
    return None
