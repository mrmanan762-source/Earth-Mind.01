"""Semantic Preservation, Golden Cases, and Multilingual Pipeline Tests for ULPU."""

import pytest
from core.schemas.ulpu import (
    ULPUTextPipelineResponse,
    ULPUResponseLocalizationResponse,
    TranslationRequest,
    TranslationResponse,
)
from core.interfaces.ulpu import ITranslator
from modules.ulpu.config import ULPUConfig
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import MockLanguageDetector
from modules.ulpu.ulpu_service import UlpuService


class SemanticPassthroughMockTranslator(ITranslator):
    """Mock translator simulating semantic translation while preserving key tokens."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        translated = f"[{request.target_language.upper()}_TRANSLATED] {request.text}"
        return TranslationResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.97,
            metadata={"provider": "semantic_passthrough_translator"},
        )

    def get_provider_name(self) -> str:
        return "semantic_passthrough_translator"

    def is_available(self) -> bool:
        return True


class TestULPUSemanticPreservationAndMultilingual:

    @pytest.fixture
    def semantic_service(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "semantic_translator", SemanticPassthroughMockTranslator())

        cfg = ULPUConfig(translation_provider="semantic_translator")
        return UlpuService(config=cfg, provider_registry=p_registry)

    def test_golden_case_negation_preservation(self, semantic_service):
        input_text = "Do not irrigate the field today."
        res = semantic_service.localize_response(system_response=input_text, target_language="hi")
        assert "not" in res.localized_response.lower() or "Do not" in res.localized_response

    def test_golden_case_uncertainty_preservation(self, semantic_service):
        input_text = "The crop may have a nutrient deficiency."
        res = semantic_service.localize_response(system_response=input_text, target_language="hi")
        assert "may" in res.localized_response.lower()

    def test_golden_case_numbers_and_units_preservation(self, semantic_service):
        input_text = "Apply 20 kg of fertilizer per hectare."
        res = semantic_service.localize_response(system_response=input_text, target_language="hi")
        assert "20" in res.localized_response
        assert "kg" in res.localized_response
        assert "hectare" in res.localized_response

    def test_golden_case_dates_and_timeframe_preservation(self, semantic_service):
        input_text = "Check the field again after 7 days."
        res = semantic_service.localize_response(system_response=input_text, target_language="hi")
        assert "7" in res.localized_response
        assert "days" in res.localized_response

    def test_golden_case_conditional_language_preservation(self, semantic_service):
        input_text = "If the soil remains dry, irrigation may be required."
        res = semantic_service.localize_response(system_response=input_text, target_language="hi")
        assert "If" in res.localized_response
        assert "may" in res.localized_response.lower()

    def test_multilingual_routing_across_registered_languages(self, semantic_service):
        supported_languages = ["en", "hi", "mr", "pa", "te", "ta", "gu", "bn", "kn", "ml"]
        test_query = "Crop health advisory"

        for lang in supported_languages:
            res = semantic_service.process_text(text=test_query, target_language=lang)
            assert res.target_language == lang
            assert len(res.translated_text) > 0
            assert res.system_representation is not None

    def test_non_english_input_pipeline(self, semantic_service):
        hindi_input = "मेरे गेहूं के पत्ते पीले हो रहे हैं।"
        res = semantic_service.process_text(text=hindi_input, target_language="en")

        assert res.original_input == hindi_input
        assert res.detected_language == "hi"
        assert res.target_language == "en"
        assert res.system_representation.original_text == hindi_input
        assert len(res.translated_text) > 0
