"""EarthMind ULPU Service Foundation."""

from typing import Optional, Dict, Any
from core.schemas.ulpu import (
    AudioPayload,
    SystemLanguageRepresentation,
    InputSource,
    InputModality,
    ScriptType,
    ULPUTextPipelineRequest,
    ULPUTextPipelineResponse,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.registry import LanguageRegistry
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import (
    MockAudioProcessor,
    MockSTTProvider,
    MockLanguageDetector,
    MockTranslator,
    MockTTSProvider,
)
from modules.ulpu.pipeline import ULPUTextPipelineEngine
from core.logging.logger import get_logger

logger = get_logger("modules.ulpu.service")


class UlpuService:
    """
    ULPU Service Foundation managing language processing capabilities,
    provider selections, and contract abstractions.
    """

    def __init__(
        self,
        config: Optional[ULPUConfig] = None,
        language_registry: Optional[LanguageRegistry] = None,
        provider_registry: Optional[ProviderRegistry] = None,
    ) -> None:
        self.config = config or ULPUConfig()
        self.config.validate_config()
        self.language_registry = language_registry or LanguageRegistry()
        self.provider_registry = provider_registry or ProviderRegistry()

        # Initialize default mock providers into registry if empty
        self._initialize_default_providers()

    def _initialize_default_providers(self) -> None:
        """Register default mock providers into provider registry."""
        if not self.provider_registry.list_providers("audio_processing"):
            self.provider_registry.register_provider("audio_processing", "mock_audio", MockAudioProcessor())

        if not self.provider_registry.list_providers("stt"):
            self.provider_registry.register_provider("stt", "mock_stt", MockSTTProvider())

        if not self.provider_registry.list_providers("language_detection"):
            self.provider_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

        if not self.provider_registry.list_providers("translation"):
            self.provider_registry.register_provider("translation", "mock_translation", MockTranslator())

        if not self.provider_registry.list_providers("tts"):
            self.provider_registry.register_provider("tts", "mock_tts", MockTTSProvider())

    def create_system_representation(
        self,
        request_id: str,
        original_text: str,
        source_language: str = "hi",
        script: ScriptType = ScriptType.DEVANAGARI,
        normalized_text: str = "",
        canonical_text: str = "",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemLanguageRepresentation:
        """Utility method to construct a valid SystemLanguageRepresentation contract."""
        return SystemLanguageRepresentation(
            request_id=request_id,
            source=InputSource(
                modality=InputModality.TEXT,
                language=source_language,
                script=script,
            ),
            original_text=original_text,
            normalized_text=normalized_text or original_text,
            canonical_text=canonical_text or original_text,
            language_confidence=confidence,
            transformation_metadata=metadata or {},
            uncertainty=[],
        )

    def process_text(
        self,
        text: str,
        target_language: str = "hi",
        request_id: Optional[str] = None,
    ) -> ULPUTextPipelineResponse:
        """
        Process English or multi-lingual text input through the functional ULPU pipeline.
        """
        engine = ULPUTextPipelineEngine(
            config=self.config,
            language_registry=self.language_registry,
            provider_registry=self.provider_registry,
        )
        try:
            req = ULPUTextPipelineRequest(
                text=text,
                target_language=target_language,
                request_id=request_id,
            )
        except Exception as e:
            from core.errors.exceptions import InvalidInputError
            raise InvalidInputError(str(e))
        return engine.process(req)
