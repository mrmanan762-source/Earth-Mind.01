"""Generic ULPU Core Protocol Interfaces for EarthMind Human Language Boundary Layer."""

from typing import Protocol, Any, Dict, Optional, runtime_checkable
from core.schemas.ulpu import (
    AudioPayload,
    SystemLanguageRepresentation,
    LanguageDetectionRequest,
    LanguageDetectionResponse,
    NormalizationRequest,
    NormalizationResponse,
    DisfluencyRequest,
    DisfluencyResponse,
    STTRequest,
    STTResponse,
    TranslationRequest,
    TranslationResponse,
    CanonicalizationRequest,
    CanonicalizationResponse,
    ResponseLocalizationRequest,
    ResponseLocalizationResponse,
    TTSRequest,
    TTSResponse,
)


@runtime_checkable
class IInputProcessor(Protocol):
    """Protocol for processing raw multi-modal input into SystemLanguageRepresentation."""

    def process_input(
        self,
        request_id: str,
        text: Optional[str] = None,
        audio: Optional[AudioPayload] = None,
        source_language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemLanguageRepresentation:
        """Process raw input text or speech into SystemLanguageRepresentation."""
        ...


@runtime_checkable
class IAudioProcessor(Protocol):
    """Protocol for audio payload validation, inspection, and format conversion."""

    def validate_audio(self, audio: AudioPayload) -> bool:
        """Validate audio payload format and parameters."""
        ...

    def inspect_audio(self, audio: AudioPayload) -> Dict[str, Any]:
        """Inspect audio parameters (duration, sample rate, channels, codec)."""
        ...


@runtime_checkable
class ISTTProvider(Protocol):
    """Protocol for Speech-to-Text provider adapter."""

    def transcribe(self, request: STTRequest) -> STTResponse:
        """Transcribe audio into text."""
        ...

    def get_provider_name(self) -> str:
        """Return provider name."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status."""
        ...


@runtime_checkable
class ILanguageDetector(Protocol):
    """Protocol for language and script detection provider adapter."""

    def detect_language(self, request: LanguageDetectionRequest) -> LanguageDetectionResponse:
        """Detect primary language and script from text or audio snippet."""
        ...

    def get_provider_name(self) -> str:
        """Return provider name."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status."""
        ...


@runtime_checkable
class INormalizer(Protocol):
    """Protocol for language-specific text normalization."""

    def normalize(self, request: NormalizationRequest) -> NormalizationResponse:
        """Normalize input text (script normalization, unicode cleaning, noise removal)."""
        ...


@runtime_checkable
class IDisfluencyProcessor(Protocol):
    """Protocol for removing speech fillers, stutters, and disfluencies."""

    def remove_disfluencies(self, request: DisfluencyRequest) -> DisfluencyResponse:
        """Process and clean disfluencies from text transcript."""
        ...


@runtime_checkable
class ITranslator(Protocol):
    """Protocol for Translation provider adapter."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate text from source language to target language."""
        ...

    def get_provider_name(self) -> str:
        """Return provider name."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status."""
        ...


@runtime_checkable
class ICanonicalizer(Protocol):
    """Protocol for mapping normalized human language to canonical system representation."""

    def canonicalize(self, request: CanonicalizationRequest) -> CanonicalizationResponse:
        """Convert normalized human language text to controlled system-language representation."""
        ...


@runtime_checkable
class IResponseLocalizer(Protocol):
    """Protocol for localizing system response back to target human language and modality."""

    def localize_response(self, request: ResponseLocalizationRequest) -> ResponseLocalizationResponse:
        """Localize system response into human language and optional TTS audio."""
        ...


@runtime_checkable
class ITTSProvider(Protocol):
    """Protocol for Text-to-Speech provider adapter."""

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize text into speech audio bytes."""
        ...

    def get_provider_name(self) -> str:
        """Return provider name."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status."""
        ...


@runtime_checkable
class IProviderRegistry(Protocol):
    """Protocol for managing and selecting ULPU provider adapters dynamically."""

    def register_provider(self, category: str, name: str, provider_instance: Any) -> None:
        """Register a provider instance for a given category."""
        ...

    def get_provider(self, category: str, name: Optional[str] = None) -> Any:
        """Retrieve active or named provider instance for a category."""
        ...
