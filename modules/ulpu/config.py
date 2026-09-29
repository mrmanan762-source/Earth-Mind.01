"""ULPU Module Configuration Model."""

import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ULPUConfig(BaseModel):
    """Configuration settings for ULPU Language Processing Unit."""
    supported_languages: List[str] = Field(
        default_factory=lambda: [
            lang.strip() for lang in os.getenv("EARTHMIND_ULPU_SUPPORTED_LANGUAGES", "en,hi,mr,pa,te,ta,gu,bn,kn,ml").split(",") if lang.strip()
        ],
        description="List of supported ISO language codes"
    )
    default_source_language: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_DEFAULT_SOURCE_LANG", "hi"),
        description="Default source language code if undetected"
    )
    default_canonical_language: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_DEFAULT_CANONICAL_LANG", "en"),
        description="Canonical system representation language code"
    )
    preferred_script: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_PREFERRED_SCRIPT", "Devanagari"),
        description="Preferred default script"
    )

    # Provider Selections
    stt_provider: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_STT_PROVIDER", "mock_stt"),
        description="Selected Speech-to-Text provider name"
    )
    translation_provider: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_TRANSLATION_PROVIDER", "mock_translation"),
        description="Selected Translation provider name"
    )
    tts_provider: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_TTS_PROVIDER", "mock_tts"),
        description="Selected Text-to-Speech provider name"
    )
    language_detection_provider: str = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_DETECTION_PROVIDER", "mock_detection"),
        description="Selected Language Detection provider name"
    )

    # Fallback Providers List
    translation_fallbacks: List[str] = Field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("EARTHMIND_ULPU_TRANSLATION_FALLBACKS", "").split(",") if p.strip()
        ],
        description="Ordered list of fallback translation provider names"
    )
    language_detection_fallbacks: List[str] = Field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("EARTHMIND_ULPU_DETECTION_FALLBACKS", "").split(",") if p.strip()
        ],
        description="Ordered list of fallback language detection provider names"
    )
    stt_fallbacks: List[str] = Field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("EARTHMIND_ULPU_STT_FALLBACKS", "").split(",") if p.strip()
        ],
        description="Ordered list of fallback STT provider names"
    )
    tts_fallbacks: List[str] = Field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("EARTHMIND_ULPU_TTS_FALLBACKS", "").split(",") if p.strip()
        ],
        description="Ordered list of fallback TTS provider names"
    )

    # Retry and Resilience Settings
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("EARTHMIND_ULPU_MAX_RETRIES", "2")),
        description="Maximum number of retries per provider attempt"
    )
    retry_delay_seconds: float = Field(
        default_factory=lambda: float(os.getenv("EARTHMIND_ULPU_RETRY_DELAY", "0.1")),
        description="Base retry delay in seconds"
    )

    # Thresholds and Timeouts
    timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("EARTHMIND_ULPU_TIMEOUT", "15.0")),
        description="Operation timeout in seconds"
    )
    confidence_threshold: float = Field(
        default_factory=lambda: float(os.getenv("EARTHMIND_ULPU_CONFIDENCE_THRESHOLD", "0.6")),
        description="Minimum confidence threshold required"
    )

    # Voice / Audio Settings
    voice_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "default_voice_gender": os.getenv("EARTHMIND_ULPU_VOICE_GENDER", "female"),
            "sample_rate_hz": int(os.getenv("EARTHMIND_ULPU_SAMPLE_RATE", "22050")),
            "speed": float(os.getenv("EARTHMIND_ULPU_SPEECH_SPEED", "1.0")),
        },
        description="Default voice and audio settings"
    )

    # Feature Flags
    enable_disfluency_removal: bool = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_ENABLE_DISFLUENCY", "true").lower() == "true",
        description="Enable speech disfluency and filler word removal"
    )
    enable_code_mixing_support: bool = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_ENABLE_CODE_MIXING", "true").lower() == "true",
        description="Enable Hinglish / code-mixed text support"
    )
    enable_transliteration: bool = Field(
        default_factory=lambda: os.getenv("EARTHMIND_ULPU_ENABLE_TRANSLITERATION", "true").lower() == "true",
        description="Enable script transliteration if required"
    )

    def validate_config(self) -> bool:
        if not self.supported_languages:
            raise ValueError("ULPU supported_languages list cannot be empty.")
        if self.confidence_threshold < 0.0 or self.confidence_threshold > 1.0:
            raise ValueError(f"Invalid confidence_threshold {self.confidence_threshold}. Must be between 0.0 and 1.0.")
        if self.timeout_seconds <= 0:
            raise ValueError(f"Invalid timeout_seconds {self.timeout_seconds}. Must be > 0.")
        return True
