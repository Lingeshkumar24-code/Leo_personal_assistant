"""
Phase 11 - Job Assistant (implemented). Rules from the spec, enforced in code:
  * never invents answers: unknown/sensitive questions are returned to the user
  * never bypasses CAPTCHA: detects it and stops
  * never submits on its own: PrepareApplication fills only; SubmitApplication is HIGH_RISK
    and always asks for confirmation
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote_plus

from app.core.config import settings
from app.jobs.matching import map_field_to_profile, score_job
from app.jobs.profile import UserProfile, profile_store
from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult

_FIELDS_JS = """
() => Array.from(document.querySelectorAll('input, textarea, select')).map((el, i) => {
  const t = (el.type || el.tagName).toLowerCase();
  if (['hidden','submit','button','checkbox','radio'].includes(t)) return null;
  let label = el.getAttribute('aria-label') || '';
  if (!label && el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) label = l.innerText; }
  if (!label) { const l = el.closest('label'); if (l) label = l.innerText; }
  if (!label) label = el.placeholder || '';
  el.setAttribute('data-leo-idx', i);
  return {idx: i, tag: el.tagName.toLowerCase(), type: t, label: label.trim(), name: el.name || '', required: el.required};
}).filter(Boolean)
"""

_CAPTCHA_JS = """
() => !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .g-recaptcha, .h-captcha, [data-sitekey]')
   || /captcha|verify you are human/i.test(document.body ? document.body.innerText : '')
"""


def _applications_path() -> Path:
    return Path(settings.data_dir) / "applications.json"


def record_application(entry: dict) -> None:
    path = _applications_path()
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    items.append({**entry, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _page():
    from app.browser.tools import BrowserSession

    return BrowserSession.get_page()


class SearchJobsTool(Tool):
    name = "jobs.search"
    description = "Search the web for job postings for a role (and optional location); returns titles and links."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"role": {"type": "string"}, "location": {"type": "string"}, "site": {"type": "string", "description": "Optional site, e.g. linkedin.com"}},
        "required": ["role"],
    }

    def run(self, role: str, location: str = "", site: str = "", **kwargs) -> ToolResult:
        query = f"{role} jobs {location}".strip() + (f" site:{site}" if site else "")
        try:
            page = _page()
            page.goto(f"https://duckduckgo.com/html/?q={quote_plus(query)}", wait_until="domcontentloaded")
            results = page.eval_on_selector_all(
                "a.result__a", "els => els.slice(0, 10).map(e => ({title: e.innerText, url: e.href}))"
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        if not results:
            return ToolResult(success=False, error="No results found (the search page may have changed or blocked automation).")
        return ToolResult(success=True, data={"query": query, "results": results})


class AnalyzeJobTool(Tool):
    name = "jobs.analyze"
    description = "Open a job posting URL, read it, and compare it with the user's saved profile skills."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    def run(self, url: str, **kwargs) -> ToolResult:
        try:
            page = _page()
            page.goto(url, wait_until="domcontentloaded")
            text = page.evaluate("document.body ? document.body.innerText : ''")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        profile = profile_store.load()
        if not profile.skills:
            return ToolResult(success=False, error="Your profile has no skills yet. Use jobs.update_profile first.", data={"job_text": text[:4000]})
        return ToolResult(success=True, data={"url": url, **score_job(text, profile), "job_text": text[:4000]})


class UpdateProfileTool(Tool):
    name = "jobs.update_profile"
    description = (
        "Update the user's job profile. Fields: name, email, phone, remote_preference, salary_preferences, availability (text); "
        "skills, education, projects, experience, certifications, resume_paths, preferred_roles, preferred_locations (lists)."
    )
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"fields": {"type": "object"}}, "required": ["fields"]}

    def run(self, fields: dict, **kwargs) -> ToolResult:
        profile = profile_store.load()
        valid = set(asdict(profile))
        unknown = [k for k in fields if k not in valid]
        for key, value in fields.items():
            if key in valid:
                current = getattr(profile, key)
                setattr(profile, key, value if not isinstance(current, list) else (value if isinstance(value, list) else [value]))
        profile_store.save(profile)
        return ToolResult(success=not unknown, data={"updated": [k for k in fields if k in valid]},
                          error=f"Unknown fields ignored: {unknown}" if unknown else None)


class GetProfileTool(Tool):
    name = "jobs.get_profile"
    description = "Show the saved job profile (local file only)."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data=asdict(profile_store.load()))


class PrepareApplicationTool(Tool):
    name = "jobs.prepare_application"
    description = (
        "Open an application form, fill the fields it can answer from the user's profile, upload the resume, "
        "and STOP before submitting. Returns questions LEO could not answer so the user can decide."
    )
    permission_level = PermissionLevel.PRIVILEGED
    parameters_schema = {"type": "object", "properties": {"job_url": {"type": "string"}}, "required": ["job_url"]}

    def run(self, job_url: str, **kwargs) -> ToolResult:
        profile: UserProfile = profile_store.load()
        try:
            page = _page()
            page.goto(job_url, wait_until="domcontentloaded")
            if page.evaluate(_CAPTCHA_JS):
                return ToolResult(success=False, error="A CAPTCHA/human check is on this page. LEO will not bypass it - please complete it yourself.")
            fields = page.evaluate(_FIELDS_JS)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))

        filled, needs_user = [], []
        for f in fields:
            loc = page.locator(f'[data-leo-idx="{f["idx"]}"]')
            try:
                if f["type"] == "file":
                    if profile.resume_paths and Path(profile.resume_paths[0]).expanduser().exists():
                        loc.set_input_files(str(Path(profile.resume_paths[0]).expanduser()))
                        filled.append({"field": f["label"] or f["name"] or "resume", "value": "resume file"})
                    else:
                        needs_user.append({"field": f["label"] or f["name"] or "file upload", "reason": "no resume file in profile"})
                    continue
                value = map_field_to_profile(f["label"], f["name"], f["type"], profile)
                if value:
                    loc.fill(value, timeout=3000)
                    filled.append({"field": f["label"] or f["name"], "value": value})
                elif f["required"] or f["tag"] == "textarea":
                    needs_user.append({"field": f["label"] or f["name"], "reason": "needs your answer (LEO does not guess)"})
            except Exception as e:  # noqa: BLE001
                needs_user.append({"field": f["label"] or f["name"], "reason": f"could not fill: {e}"})

        record_application({"url": job_url, "status": "prepared_not_submitted"})
        return ToolResult(
            success=True,
            data={"url": job_url, "filled": filled, "questions_for_user": needs_user, "submitted": False},
            verification=f"Filled {len(filled)} field(s); {len(needs_user)} need your input. Not submitted.",
        )


class SubmitApplicationTool(Tool):
    name = "jobs.submit_application"
    description = "Click the submit/apply button on the application currently open. Only after the user has reviewed it."
    permission_level = PermissionLevel.HIGH_RISK
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            page = _page()
            if page.evaluate(_CAPTCHA_JS):
                return ToolResult(success=False, error="A CAPTCHA is present; please complete and submit it yourself.")
            button = page.locator("button[type=submit], input[type=submit], button:has-text('Submit'), button:has-text('Apply')").first
            button.click(timeout=5000)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not submit: {e}")
        record_application({"url": page.url, "status": "submitted"})
        return ToolResult(success=True, data={"url": page.url}, verification="Submit clicked; check the page for the confirmation message.")


class ExtractEmailsTool(Tool):
    name = "jobs.extract_emails"
    description = "Extract email addresses from the current job page for contacting employers directly."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            page = _page()
            text = page.evaluate("document.body ? document.body.innerText : ''")
            # Also check for mailto links
            mailto_links = page.evaluate("""
                Array.from(document.querySelectorAll('a[href^="mailto:"]'))
                    .map(a => a.href.replace('mailto:', ''))
            """)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))

        # Regex for email extraction
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails_from_text = set(re.findall(email_pattern, text))
        emails_from_mailto = set(mailto_links) if mailto_links else set()
        
        all_emails = emails_from_text | emails_from_mailto
        
        # Filter out common non-contact emails
        filtered = []
        exclude_domains = {'example.com', 'test.com', 'localhost', 'noreply', 'no-reply', 'donotreply', 
                          'support@', 'info@', 'admin@', 'hr@', 'careers@', 'jobs@', 'recruiting@'}
        for email in all_emails:
            email_lower = email.lower()
            if not any(ex in email_lower for ex in exclude_domains):
                filtered.append(email)

        return ToolResult(
            success=True,
            data={
                "emails": list(filtered)[:20],  # Limit to 20
                "total_found": len(all_emails)
            }
        )


class SearchJobsNearbyTool(Tool):
    name = "jobs.search_nearby"
    description = "Search for jobs near your current location (uses IP geolocation)."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "role": {"type": "string"},
            "radius_km": {"type": "integer", "description": "Search radius in kilometers", "default": 50}
        },
        "required": ["role"]
    }

    def run(self, role: str, radius_km: int = 50, **kwargs) -> ToolResult:
        # First get location
        from app.computer.system_tools import GetLocationTool
        loc_tool = GetLocationTool()
        loc_result = loc_tool.run()
        
        if not loc_result.success:
            return ToolResult(success=False, error=f"Could not get location: {loc_result.error}")
        
        location = loc_result.data.get("formatted", "")
        if not location or location == "Unknown":
            return ToolResult(success=False, error="Could not determine your location")
        
        # Search with location
        search_tool = SearchJobsTool()
        return search_tool.run(role=role, location=location)
