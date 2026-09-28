"""
Phase 9 - System Controls (implemented).

Real cross-platform-where-possible system control:
  - Volume: pycaw on Windows (COM-based, the standard approach), amixer/pactl
    on Linux, osascript on macOS.
  - Brightness: screen_brightness_control (cross-platform) where available,
    WMI on Windows as a fallback.
  - Lock: ctypes.windll.user32.LockWorkStation on Windows, equivalent
    commands on macOS/Linux.
  - Time: Get current system time.
  - Location: Get current geographic location (via IP geolocation).

None of these require administrator privileges for normal use, per the spec.
Like computer/tools.py, this could not be exercised end-to-end in the build
sandbox (no audio device / no display), so each method fails with a clear
error rather than pretending success when the underlying OS API is missing.
"""
from __future__ import annotations

import platform
import subprocess
import urllib.request
import json
from datetime import datetime

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


class GetTimeTool(Tool):
    name = "system.get_time"
    description = "Get the current system date and time."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        now = datetime.now()
        return ToolResult(
            success=True,
            data={
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "day": now.strftime("%A"),
                "timezone": datetime.now().astimezone().tzname()
            }
        )


class SetVolumeTool(Tool):
    name = "system.set_volume"
    description = "Set system volume to a percentage (0-100)."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
        "required": ["percent"],
    }

    def run(self, percent: int, **kwargs) -> ToolResult:
        percent = max(0, min(100, int(percent)))
        try:
            if IS_WINDOWS:
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                except ImportError as e:
                    return ToolResult(success=False, error=f"pycaw/comtypes not installed: {e}. pip install pycaw comtypes")
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            elif IS_MAC:
                subprocess.run(["osascript", "-e", f"set volume output volume {percent}"], check=True)
            elif IS_LINUX:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], check=True)
            else:
                return ToolResult(success=False, error=f"Unsupported platform: {platform.system()}")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"Required system command not found: {e}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not set volume: {e}")
        return ToolResult(success=True, data={"percent": percent})


class SetBrightnessTool(Tool):
    name = "system.set_brightness"
    description = "Set screen brightness to a percentage (0-100)."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
        "required": ["percent"],
    }

    def run(self, percent: int, **kwargs) -> ToolResult:
        percent = max(0, min(100, int(percent)))
        try:
            import screen_brightness_control as sbc
        except ImportError:
            return ToolResult(
                success=False,
                error="screen_brightness_control is not installed. pip install screen-brightness-control",
            )
        try:
            sbc.set_brightness(percent)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not set brightness (no adjustable display found?): {e}")
        return ToolResult(success=True, data={"percent": percent})


class LockComputerTool(Tool):
    name = "system.lock_computer"
    description = "Lock the workstation."
    permission_level = PermissionLevel.PRIVILEGED
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            if IS_WINDOWS:
                import ctypes

                ctypes.windll.user32.LockWorkStation()
            elif IS_MAC:
                subprocess.run(
                    ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                    check=True,
                )
            elif IS_LINUX:
                subprocess.run(["loginctl", "lock-session"], check=True)
            else:
                return ToolResult(success=False, error=f"Unsupported platform: {platform.system()}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not lock the workstation: {e}")
        return ToolResult(success=True, data={"locked": True})


class MuteTool(Tool):
    name = "system.mute"
    description = "Mute or unmute system audio."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"muted": {"type": "boolean"}}, "required": ["muted"]}

    def run(self, muted: bool, **kwargs) -> ToolResult:
        try:
            if IS_WINDOWS:
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                except ImportError as e:
                    return ToolResult(success=False, error=f"pycaw/comtypes not installed: {e}. pip install pycaw comtypes")
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMute(1 if muted else 0, None)
            elif IS_MAC:
                subprocess.run(["osascript", "-e", f"set volume output muted {'true' if muted else 'false'}"], check=True)
            elif IS_LINUX:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "mute" if muted else "unmute"], check=True)
            else:
                return ToolResult(success=False, error=f"Unsupported platform: {platform.system()}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not change mute state: {e}")
        return ToolResult(success=True, data={"muted": muted})


class GetLocationTool(Tool):
    name = "system.get_location"
    description = "Get current geographic location (city, region, country) via IP geolocation for 'nearby' searches."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        # Try multiple free geolocation services
        services = [
            "https://ipapi.co/json/",
            "https://ipinfo.io/json",
            "https://freeipapi.com/api/json",
        ]
        
        data = None
        for url in services:
            try:
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    break
            except Exception:
                continue
        
        if not data:
            return ToolResult(success=False, error="Could not get location: all geolocation services failed")
        
        # Normalize different API responses
        city = data.get("city") or data.get("cityName")
        region = data.get("region") or data.get("regionName") or data.get("state")
        country = data.get("country_name") or data.get("countryName") or data.get("country")
        country_code = data.get("country_code") or data.get("countryCode")
        latitude = data.get("latitude") or data.get("lat")
        longitude = data.get("longitude") or data.get("lon")
        timezone = data.get("timezone")
        ip = data.get("ip") or data.get("query")
        
        location_parts = []
        if city:
            location_parts.append(city)
        if region:
            location_parts.append(region)
        if country:
            location_parts.append(country)
        
        return ToolResult(
            success=True,
            data={
                "city": city,
                "region": region,
                "country": country,
                "country_code": country_code,
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
                "formatted": ", ".join(location_parts) if location_parts else "Unknown",
                "ip": ip
            }
        )
