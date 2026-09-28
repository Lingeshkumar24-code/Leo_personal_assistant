"""
Phase 2 - Voice System (implemented, lightweight backends).

TTS: pyttsx3 (offline, cross-platform, no API key needed).
STT: SpeechRecognition using the device microphone + Google's free web
     speech API for transcription (needs internet, no key required for
     short clips) - swap the recognizer call for Whisper/faster-whisper
     later if you want fully offline, higher-accuracy STT.
Wake word: a simple keyword-spotting loop over short STT clips. This is not
     a dedicated low-power wake-word engine (like openWakeWord) - it is a
     real, working substitute suitable for a desktop assistant, at the cost
     of a bit more CPU than a proper wake-word model.

Honesty note: none of this could be exercised end-to-end in the build
sandbox, which has no microphone or audio output device. The code follows
each library's documented API and will run as-is on a machine with a mic
and speakers; every method still fails loudly (not silently) if no audio
device is present.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings


class VoiceError(RuntimeError):
    pass


class WakeWordDetector(ABC):
    @abstractmethod
    def listen_for_wake_word(self) -> bool:
        """Block until the wake word is heard; return True."""
        raise NotImplementedError


class SpeechToText(ABC):
    @abstractmethod
    def transcribe_from_microphone(self, timeout: float = 8.0) -> str:
        raise NotImplementedError

    @abstractmethod
    def transcribe_file(self, audio_path: str) -> str:
        raise NotImplementedError


class TextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str, interruptible: bool = True) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError


class Pyttsx3TextToSpeech(TextToSpeech):
    def __init__(self):
        try:
            import pyttsx3
        except ImportError as e:
            raise VoiceError("pyttsx3 is not installed. pip install pyttsx3") from e
        try:
            self._engine = pyttsx3.init()
        except Exception as e:  # noqa: BLE001
            raise VoiceError(
                f"Could not initialize a text-to-speech engine: {e}. "
                "On Linux this usually means eSpeak/eSpeak-ng isn't installed "
                "(apt install espeak-ng); Windows/macOS use their built-in engines."
            ) from e
        self._speaking = False

    def speak(self, text: str, interruptible: bool = True) -> None:
        self._speaking = True
        self._engine.say(text)
        self._engine.runAndWait()
        self._speaking = False

    def stop(self) -> None:
        if self._speaking:
            self._engine.stop()
            self._speaking = False


class GoogleSpeechRecognitionSTT(SpeechToText):
    def __init__(self):
        try:
            import speech_recognition as sr
        except ImportError as e:
            raise VoiceError("SpeechRecognition is not installed. pip install SpeechRecognition") from e
        self._sr = sr
        self._recognizer = sr.Recognizer()

    def transcribe_from_microphone(self, timeout: float = 8.0) -> str:
        try:
            with self._sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout)
        except OSError as e:
            raise VoiceError(f"No microphone available: {e}") from e
        try:
            return self._recognizer.recognize_google(audio)
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as e:
            raise VoiceError(f"Speech recognition service error: {e}") from e

    def transcribe_file(self, audio_path: str) -> str:
        with self._sr.AudioFile(audio_path) as source:
            audio = self._recognizer.record(source)
        try:
            return self._recognizer.recognize_google(audio)
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as e:
            raise VoiceError(f"Speech recognition service error: {e}") from e


class KeywordSpottingWakeWord(WakeWordDetector):
    """
    Listens in short bursts and checks whether the configured wake word
    (settings.wake_word, default "leo") appears in the transcription.
    Simple and real, though noisier/slower than a dedicated wake-word model.
    """

    def __init__(self, stt: SpeechToText | None = None):
        self._stt = stt or GoogleSpeechRecognitionSTT()
        self._wake_word = settings.wake_word.lower()

    def listen_for_wake_word(self) -> bool:
        text = self._stt.transcribe_from_microphone(timeout=5.0)
        return self._wake_word in text.lower()


def get_tts() -> TextToSpeech:
    return Pyttsx3TextToSpeech()


def get_stt() -> SpeechToText:
    return GoogleSpeechRecognitionSTT()


def get_wake_word_detector() -> WakeWordDetector:
    return KeywordSpottingWakeWord()
