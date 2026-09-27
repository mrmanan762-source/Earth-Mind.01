"""Unit and End-to-End Pipeline Tests for ULPU Text Pipeline."""

import pytest
from core.schemas.ulpu import (
    ULPUTextPipelineResponse,
    TranslationRequest,
    TranslationResponse,
)
from core.interfaces.ulpu import ITranslator
from core.errors.exceptions import (
    InvalidInputError,
    UnsupportedLanguageError,
    LowConfidenceError,
    TranslationError,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.registry import LanguageRegistry
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import MockLanguageDetector, MockTranslator
from modules.ulpu.ulpu_service import UlpuService


class AlternativeMockTranslator(ITranslator):
    """Alternative mock translator implementation for testing provider replaceability."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translated_text=f"ALT_TRANSLATION_({request.target_language}): {request.text}",
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.99,
            metadata={"provider": "alt_mock_translator"},
        )

    def get_provider_name(self) -> str:
        return "alt_mock_translator"

    def is_available(self) -> bool:
        return True


class FailingTranslator(ITranslator):
    """Failing translator for testing error handling."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise TranslationError("failing_translator", request.source_language, request.target_language, "Service down")

    def get_provider_name(self) -> str:
        return "failing_translator"

    def is_available(self) -> bool:
        return False


class TestULPUTextPipeline:

    def test_basic_english_detection(self):
        service = UlpuService()
        res = service.process_text("Hello, how are you?", target_language="en")
        assert res.detected_language == "en"
        assert res.detection_confidence >= 0.6

    def test_english_to_hindi_pipeline(self):
        service = UlpuService()
        text = "My wheat leaves are turning yellow."
        res = service.process_text(text, target_language="hi")

        assert isinstance(res, ULPUTextPipelineResponse)
        assert res.original_input == text
        assert res.detected_language == "en"
        assert res.target_language == "hi"
        assert len(res.translated_text) > 0
        assert res.system_representation is not None
        assert res.canonical_text == text

    def test_english_to_marathi_pipeline(self):
        service = UlpuService()
        text = "When to irrigate wheat crop?"
        res = service.process_text(text, target_language="mr")

        assert res.target_language == "mr"
        assert len(res.translated_text) > 0

    def test_invalid_input_empty_or_whitespace(self):
        service = UlpuService()
        with pytest.raises(InvalidInputError):
            service.process_text("", target_language="hi")

        with pytest.raises(InvalidInputError):
            service.process_text("   ", target_language="hi")

    def test_unsupported_target_language(self):
        service = UlpuService()
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            service.process_text("Wheat farming", target_language="invalid_lang_code")
        assert exc_info.value.error_contract.metadata["language_code"] == "invalid_lang_code"

    def test_low_confidence_detection_error(self):
        low_conf_detector = MockLanguageDetector()
        low_conf_detector.detect_language = lambda req: MockLanguageDetector().detect_language(req).model_copy(update={"confidence": 0.2})

        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", low_conf_detector)
        p_registry.register_provider("translation", "mock_translation", MockTranslator())

        service = UlpuService(provider_registry=p_registry)

        with pytest.raises(LowConfidenceError) as exc_info:
            service.process_text("Test query", target_language="hi")
        assert exc_info.value.error_contract.metadata["confidence"] == 0.2

    def test_translation_failure_handling(self):
        failing_trans = FailingTranslator()
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "failing_trans", failing_trans)

        cfg = ULPUConfig(translation_provider="failing_trans")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        with pytest.raises(TranslationError):
            service.process_text("Wheat crop", target_language="hi")

    def test_provider_replacement(self):
        alt_trans = AlternativeMockTranslator()
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "alt_mock", alt_trans)

        cfg = ULPUConfig(translation_provider="alt_mock")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        res = service.process_text("Fertilizer dosage", target_language="hi")
        assert "ALT_TRANSLATION_(hi):" in res.translated_text

    def test_end_to_end_demo_query(self):
        service = UlpuService()
        demo_text = "My wheat leaves are turning yellow. What should I do?"
        res = service.process_text(demo_text, target_language="hi")

        assert res.original_input == demo_text
        assert res.detected_language == "en"
        assert res.target_language == "hi"
        assert res.system_representation.original_text == demo_text
        assert res.system_representation.canonical_text == demo_text
        assert res.system_representation.source.language == "en"
