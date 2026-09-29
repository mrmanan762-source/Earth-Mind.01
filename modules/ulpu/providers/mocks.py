"""Mock Provider Adapters for ULPU Testing & Offline Execution."""

from typing import Dict, Any, Optional
from core.interfaces.ulpu import (
    ISTTProvider,
    ILanguageDetector,
    ITranslator,
    ITTSProvider,
    IAudioProcessor,
)
from core.schemas.ulpu import (
    AudioPayload,
    STTRequest,
    STTResponse,
    LanguageDetectionRequest,
    LanguageDetectionResponse,
    TranslationRequest,
    TranslationResponse,
    TTSRequest,
    TTSResponse,
    ScriptType,
)


class MockAudioProcessor(IAudioProcessor):
    """Mock audio processor for inspecting and validating audio payloads in tests."""

    def validate_audio(self, audio: AudioPayload) -> bool:
        if audio is None:
            return False
        if audio.audio_bytes is None and audio.file_path is None:
            return False
        return audio.sample_rate_hz > 0

    def inspect_audio(self, audio: AudioPayload) -> Dict[str, Any]:
        return {
            "format": audio.audio_format,
            "sample_rate_hz": audio.sample_rate_hz,
            "channels": audio.channels,
            "duration_seconds": audio.duration_seconds or 2.5,
            "mock_inspected": True,
        }


class MockSTTProvider(ISTTProvider):
    """Mock Speech-to-Text provider for automated testing."""

    def __init__(self, mock_transcript: str = "मक्के की फसल में खाद कब डालें?") -> None:
        self.mock_transcript = mock_transcript

    def transcribe(self, request: STTRequest) -> STTResponse:
        return STTResponse(
            transcript=self.mock_transcript,
            confidence=0.95,
            detected_language=request.language_hint or "hi",
            metadata={"provider": "mock_stt", "audio_format": request.audio.audio_format},
        )

    def get_provider_name(self) -> str:
        return "mock_stt"

    def is_available(self) -> bool:
        return True


class ConfigurableFailureMockTranslator(ITranslator):
    """Failure-injection mock translator for reliability and fallback testing."""

    def __init__(
        self,
        provider_name: str = "configurable_mock_translator",
        mode: str = "success",  # "success", "fail_once", "always_fail", "timeout"
        translation_prefix: str = "[CONFIGURABLE_TRANSLATED]",
    ) -> None:
        self.provider_name = provider_name
        self.mode = mode
        self.translation_prefix = translation_prefix
        self.call_count = 0

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        self.call_count += 1
        if self.mode == "always_fail":
            from core.errors.exceptions import TranslationError
            raise TranslationError(self.provider_name, request.source_language, request.target_language, "Forced failure mode")

        elif self.mode == "fail_once":
            if self.call_count == 1:
                from core.errors.exceptions import TranslationError
                raise TranslationError(self.provider_name, request.source_language, request.target_language, "Forced transient failure (call 1)")

        elif self.mode == "timeout":
            from core.errors.exceptions import ULPUTimeoutError
            raise ULPUTimeoutError("translation", 5.0)

        translated = f"{self.translation_prefix} ({request.target_language}): {request.text}"
        return TranslationResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.96,
            metadata={"provider": self.provider_name, "mode": self.mode, "calls": self.call_count},
        )

    def get_provider_name(self) -> str:
        return self.provider_name

    def is_available(self) -> bool:
        return self.mode != "always_fail"


class ConfigurableFailureMockDetector(ILanguageDetector):
    """Failure-injection mock detector for reliability testing."""

    def __init__(
        self,
        provider_name: str = "configurable_mock_detector",
        mode: str = "success",  # "success", "fail_once", "always_fail", "low_confidence"
        default_language: str = "en",
    ) -> None:
        self.provider_name = provider_name
        self.mode = mode
        self.default_language = default_language
        self.call_count = 0

    def detect_language(self, request: LanguageDetectionRequest) -> LanguageDetectionResponse:
        self.call_count += 1
        if self.mode == "always_fail":
            from core.errors.exceptions import ProviderError
            raise ProviderError(self.provider_name, "Language detector service down")

        elif self.mode == "fail_once":
            if self.call_count == 1:
                from core.errors.exceptions import ProviderError
                raise ProviderError(self.provider_name, "Transient language detector error")

        confidence = 0.20 if self.mode == "low_confidence" else 0.98

        return LanguageDetectionResponse(
            detected_language=self.default_language,
            script=ScriptType.LATIN,
            confidence=confidence,
            alternative_languages=[],
            metadata={"provider": self.provider_name, "mode": self.mode, "calls": self.call_count},
        )

    def get_provider_name(self) -> str:
        return self.provider_name

    def is_available(self) -> bool:
        return self.mode != "always_fail"


class MockLanguageDetector(ILanguageDetector):
    """Mock Language Detector for automated testing."""

    def __init__(self, default_language: str = "hi", default_script: ScriptType = ScriptType.DEVANAGARI) -> None:
        self.default_language = default_language
        self.default_script = default_script

    def detect_language(self, request: LanguageDetectionRequest) -> LanguageDetectionResponse:
        text = request.text or ""
        # Simple heuristic for testing
        if any("\u0900" <= char <= "\u097F" for char in text):
            lang = "hi"
            script = ScriptType.DEVANAGARI
        elif text.isascii() and len(text) > 0:
            lang = "en"
            script = ScriptType.LATIN
        else:
            lang = self.default_language
            script = self.default_script

        return LanguageDetectionResponse(
            detected_language=lang,
            script=script,
            confidence=0.98,
            alternative_languages=[{"en": 0.02}],
            metadata={"provider": "mock_detection"},
        )

    def get_provider_name(self) -> str:
        return "mock_detection"

    def is_available(self) -> bool:
        return True


class MockTranslator(ITranslator):
    """Mock Translation provider for automated testing."""

    def __init__(self, translations: Optional[Dict[str, str]] = None) -> None:
        self.translations = translations or {
            "मक्के की फसल में खाद कब डालें?": "When to apply fertilizer to corn crop?",
            "गेहूं में सिंचाई कब करें?": "When to irrigate wheat?",
            "When to apply fertilizer to corn crop?": "मक्के की फसल में खाद कब डालें?",
        }

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        text = request.text
        if text in self.translations:
            translated = self.translations[text]
        else:
            translated = f"[MockTranslated: {request.source_language}->{request.target_language}] {text}"

        return TranslationResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.96,
            metadata={"provider": "mock_translation"},
        )

    def get_provider_name(self) -> str:
        return "mock_translation"

    def is_available(self) -> bool:
        return True


class MockTTSProvider(ITTSProvider):
    """Mock Text-to-Speech provider for automated testing."""

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        mock_bytes = f"MOCK_TTS_AUDIO({request.text})".encode("utf-8")
        return TTSResponse(
            audio_bytes=mock_bytes,
            audio_format=request.audio_format,
            sample_rate_hz=request.sample_rate_hz,
            duration_seconds=2.0,
            metadata={"provider": "mock_tts", "voice_id": request.voice_id or "default_hindi_female"},
        )

    def get_provider_name(self) -> str:
        return "mock_tts"

    def is_available(self) -> bool:
        return True
