"""ULPU Core Schemas & System Language Representation Contracts for EarthMind."""

from enum import Enum
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class InputModality(str, Enum):
    """Supported input/output modalities."""
    TEXT = "text"
    AUDIO = "audio"


class ScriptType(str, Enum):
    """Supported writing scripts, with focus on Indic and Latin scripts."""
    LATIN = "Latin"
    DEVANAGARI = "Devanagari"
    GURMUKHI = "Gurmukhi"
    TELUGU = "Telugu"
    TAMIL = "Tamil"
    GUJARATI = "Gujarati"
    BENGALI = "Bengali"
    KANNADA = "Kannada"
    MALAYALAM = "Malayalam"
    ARABIC = "Arabic"
    OTHER = "Other"


class InputSource(BaseModel):
    """Source input parameters describing modality, language, and script."""
    modality: InputModality = Field(default=InputModality.TEXT, description="Input modality (text or audio)")
    language: str = Field(..., description="ISO language code (e.g., 'hi', 'en', 'mr')")
    script: ScriptType = Field(default=ScriptType.LATIN, description="Script type")


class AudioPayload(BaseModel):
    """Audio data payload container."""
    audio_bytes: Optional[bytes] = Field(default=None, description="Raw audio byte content")
    file_path: Optional[str] = Field(default=None, description="File path to audio record")
    audio_format: str = Field(default="wav", description="Audio format identifier (wav, mp3, flac, ogg)")
    sample_rate_hz: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds")

    @field_validator("sample_rate_hz")
    @classmethod
    def validate_sample_rate(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("sample_rate_hz must be positive")
        return v


class SystemLanguageRepresentation(BaseModel):
    """
    Core data contract for controlled system-language representation in EarthMind.

    ULPU guarantees intent-preserving representation from human text/speech into
    a normalized and canonical form for downstream processing.
    """
    request_id: str = Field(..., description="Unique request/trace identity")
    source: InputSource = Field(..., description="Source modality, language, and script")
    original_text: str = Field(..., description="Original verbatim user input text or STT transcript")
    normalized_text: str = Field(default="", description="Cleaned, normalized text")
    canonical_text: str = Field(default="", description="Controlled system-language representation (typically English canonical text)")
    language_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score for language detection/processing")
    transformation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Detailed trace of language transformations applied")
    uncertainty: List[str] = Field(default_factory=list, description="Explicit record of ambiguous phrasing or linguistic uncertainties")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of representation creation")

    @field_validator("original_text")
    @classmethod
    def validate_original_text(cls, v: str) -> str:
        if v is None:
            raise ValueError("original_text cannot be None")
        return v


# Provider Requests & Responses

class LanguageDetectionRequest(BaseModel):
    """Request for language and script detection."""
    text: Optional[str] = Field(default=None, description="Text snippet to analyze")
    audio: Optional[AudioPayload] = Field(default=None, description="Audio payload to analyze")
    top_k: int = Field(default=3, ge=1, description="Number of top candidate languages to return")


class LanguageDetectionResponse(BaseModel):
    """Response from language detection provider."""
    detected_language: str = Field(..., description="Primary detected ISO language code")
    script: ScriptType = Field(default=ScriptType.LATIN, description="Detected script type")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    alternative_languages: List[Dict[str, float]] = Field(default_factory=list, description="Alternative detected candidate scores")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider metadata")


class NormalizationRequest(BaseModel):
    """Request for text normalization."""
    text: str = Field(..., description="Text to normalize")
    language: str = Field(..., description="Language code")
    script: Optional[ScriptType] = Field(default=None, description="Script type")


class NormalizationResponse(BaseModel):
    """Response from text normalizer."""
    normalized_text: str = Field(..., description="Normalized text")
    changes_made: List[str] = Field(default_factory=list, description="Log of normalization transformations applied")


class DisfluencyRequest(BaseModel):
    """Request for disfluency cleaning."""
    text: str = Field(..., description="Text containing potential speech disfluencies")
    language: str = Field(..., description="Language code")


class DisfluencyResponse(BaseModel):
    """Response from disfluency processor."""
    cleaned_text: str = Field(..., description="Text with disfluencies, fillers, and stutters removed")
    disfluencies_removed: List[str] = Field(default_factory=list, description="List of removed filler words or fragments")


class STTRequest(BaseModel):
    """Request for speech-to-text processing."""
    audio: AudioPayload = Field(..., description="Audio input payload")
    language_hint: Optional[str] = Field(default=None, description="Optional target language hint")
    prompt_hint: Optional[str] = Field(default=None, description="Domain/vocabulary prompt hint")


class STTResponse(BaseModel):
    """Response from STT provider."""
    transcript: str = Field(..., description="Transcribed text string")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Transcription confidence score")
    detected_language: Optional[str] = Field(default=None, description="Detected language during transcription")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider metadata")


class TranslationRequest(BaseModel):
    """Request for text translation."""
    text: str = Field(..., description="Text to translate")
    source_language: str = Field(..., description="Source ISO language code")
    target_language: str = Field(..., description="Target ISO language code")
    preserve_formatting: bool = Field(default=True, description="Whether to preserve linebreaks and formatting")
    domain_hint: Optional[str] = Field(default=None, description="Optional domain hint")


class TranslationResponse(BaseModel):
    """Response from translation provider."""
    translated_text: str = Field(..., description="Translated text output")
    source_language: str = Field(..., description="Confirmed source language code")
    target_language: str = Field(..., description="Confirmed target language code")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Translation confidence score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider metadata")


class CanonicalizationRequest(BaseModel):
    """Request to convert normalized text into canonical system representation."""
    normalized_text: str = Field(..., description="Normalized text")
    source_language: str = Field(..., description="Source language code")
    script: Optional[ScriptType] = Field(default=None, description="Source script")


class CanonicalizationResponse(BaseModel):
    """Response from canonicalizer."""
    canonical_text: str = Field(..., description="Canonical system text representation")
    target_language: str = Field(default="en", description="Canonical system language code")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Canonicalization confidence")


class ResponseLocalizationRequest(BaseModel):
    """Request to convert system response back to target human language and modality."""
    system_response: str = Field(..., description="Validated system output response")
    target_language: str = Field(..., description="Target language code")
    target_script: Optional[ScriptType] = Field(default=None, description="Target script")
    target_modality: InputModality = Field(default=InputModality.TEXT, description="Target modality")
    voice_id: Optional[str] = Field(default=None, description="Optional voice ID for TTS")


class TTSRequest(BaseModel):
    """Request for text-to-speech synthesis."""
    text: str = Field(..., description="Text to synthesize into speech")
    target_language: str = Field(..., description="Language code")
    voice_id: Optional[str] = Field(default=None, description="Optional voice ID")
    audio_format: str = Field(default="wav", description="Desired audio format")
    sample_rate_hz: int = Field(default=22050, description="Sample rate in Hz")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech playback speed multiplier")


class TTSResponse(BaseModel):
    """Response from text-to-speech provider."""
    audio_bytes: bytes = Field(..., description="Synthesized audio byte stream")
    audio_format: str = Field(default="wav", description="Audio format")
    sample_rate_hz: int = Field(default=22050, description="Sample rate in Hz")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Audio duration")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider metadata")


class ResponseLocalizationResponse(BaseModel):
    """Response from response localizer."""
    localized_text: str = Field(..., description="Localized human language text")
    target_language: str = Field(..., description="Target language code")
    target_modality: InputModality = Field(..., description="Target modality")
    audio_output: Optional[TTSResponse] = Field(default=None, description="TTS output if target_modality is AUDIO")
