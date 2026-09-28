"""
Phase 2 - Voice (implemented).

STT: SpeechRecognition + microphone (PyAudio). TTS: pyttsx3 (offline, interruptible).
Wake word: text match on the transcribed phrase (e.g. "leo open chrome").
Needs a real microphone/speakers, so it runs on your PC, not in a server sandbox.
"""
from __future__ import annotations

import threading

from app.core.config import settings


class VoiceUnavailable(RuntimeError):
    pass


class Speaker:
    def __init__(self):
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
        except Exception as e:  # noqa: BLE001
            raise VoiceUnavailable(f"Text-to-speech unavailable: {e}. pip install pyttsx3") from e
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        with self._lock:
            self._engine.say(text)
            self._engine.runAndWait()

    def stop(self) -> None:
        try:
            self._engine.stop()
        except Exception:  # noqa: BLE001
            pass


class Listener:
    def __init__(self):
        try:
            import speech_recognition as sr

            self._sr = sr
            self._rec = sr.Recognizer()
            self._mic = sr.Microphone()
        except Exception as e:  # noqa: BLE001
            raise VoiceUnavailable(
                f"Microphone/STT unavailable: {e}. pip install SpeechRecognition pyaudio"
            ) from e
        with self._mic as source:
            self._rec.adjust_for_ambient_noise(source, duration=0.5)

    def listen_once(self, timeout: float = 8, phrase_limit: float = 15) -> str:
        with self._mic as source:
            try:
                audio = self._rec.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except self._sr.WaitTimeoutError:
                return ""
        try:
            return self._rec.recognize_google(audio)
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as e:
            raise VoiceUnavailable(f"Speech recognition service error: {e}") from e


def strip_wake_word(text: str, wake_word: str | None = None) -> str | None:
    """Return the command after the wake word, '' if only the wake word was said, None if absent."""
    wake = (wake_word or settings.wake_word).lower()
    lowered = text.lower().strip()
    if wake not in lowered.split()[:3] and not lowered.startswith(wake):
        return None
    idx = lowered.find(wake)
    return text[idx + len(wake):].lstrip(" ,.!?:").strip()
