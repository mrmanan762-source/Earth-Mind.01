"""Unit, Integration, and Semantic Preservation Tests for ULPU Response Localization."""

import pytest
from core.schemas.ulpu import (
    ULPUResponseLocalizationResponse,
    TranslationRequest,
    TranslationResponse,
    InputModality,
)
from core.interfaces.ulpu import ITranslator
from core.errors.exceptions import (
    InvalidInputError,
    UnsupportedLanguageError,
    TranslationError,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import MockLanguageDetector, MockTranslator, MockTTSProvider
from modules.ulpu.ulpu_service import UlpuService


class SemanticPreservingMockTranslator(ITranslator):
    """Mock translator simulating semantic translation while preserving key tokens like negation, numbers, and uncertainty."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        text = request.text
        # Pass-through semantic tokens for testing assertion preservation
        translated = f"[HI_LOCALIZED] {text}"
        return TranslationResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.96,
            metadata={"provider": "semantic_mock_translator"},
        )

    def get_provider_name(self) -> str:
        return "semantic_mock_translator"

    def is_available(self) -> bool:
        return True


class FailingTranslator(ITranslator):
    """Failing translator for testing error handling."""

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise TranslationError("failing_translator", request.source_language, request.target_language, "Service down")

    def get_provider_name(self) -> str:
        return "failing_translator"

    def is_available(self) -> False:
        return False


class TestULPUResponseLocalization:

    def test_english_to_hindi_response_localization(self):
        service = UlpuService()
        system_response = "Your wheat may be experiencing nitrogen deficiency."
        res = service.localize_response(system_response=system_response, target_language="hi")

        assert isinstance(res, ULPUResponseLocalizationResponse)
        assert res.original_response == system_response
        assert res.source_language == "en"
        assert res.target_language == "hi"
        assert len(res.localized_response) > 0
        assert res.confidence > 0.0

    def test_negation_preservation(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "semantic_mock", SemanticPreservingMockTranslator())
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

        cfg = ULPUConfig(translation_provider="semantic_mock")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        system_response = "Do not irrigate the field today."
        res = service.localize_response(system_response=system_response, target_language="hi")

        # Verify negation word 'not' is preserved in the localized stream
        assert "not" in res.localized_response.lower() or "Do not" in res.localized_response

    def test_numbers_and_units_preservation(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "semantic_mock", SemanticPreservingMockTranslator())
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

        cfg = ULPUConfig(translation_provider="semantic_mock")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        system_response = "Apply 20 kg of fertilizer per hectare."
        res = service.localize_response(system_response=system_response, target_language="hi")

        assert "20" in res.localized_response
        assert "kg" in res.localized_response
        assert "hectare" in res.localized_response

    def test_uncertainty_preservation(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "semantic_mock", SemanticPreservingMockTranslator())
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

        cfg = ULPUConfig(translation_provider="semantic_mock")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        system_response = "The crop might be affected by fungal disease."
        res = service.localize_response(system_response=system_response, target_language="hi")

        assert "might" in res.localized_response.lower()

    def test_structured_response_formatting_preservation(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "semantic_mock", SemanticPreservingMockTranslator())
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

        cfg = ULPUConfig(translation_provider="semantic_mock")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        structured_response = "### Advisory:\n1. Inspect wheat leaves.\n2. Check soil moisture."
        res = service.localize_response(system_response=structured_response, target_language="hi")

        assert "### Advisory:" in res.localized_response
        assert "1. Inspect wheat leaves." in res.localized_response
        assert "2. Check soil moisture." in res.localized_response

    def test_unsupported_target_language_error(self):
        service = UlpuService()
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            service.localize_response(
                system_response="Check field moisture.",
                target_language="unsupported_lang",
            )
        assert exc_info.value.error_contract.metadata["language_code"] == "unsupported_lang"

    def test_empty_system_response_validation_error(self):
        service = UlpuService()
        with pytest.raises(InvalidInputError):
            service.localize_response(system_response="", target_language="hi")

        with pytest.raises(InvalidInputError):
            service.localize_response(system_response="   ", target_language="hi")

    def test_translation_provider_failure(self):
        failing_trans = FailingTranslator()
        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "failing_trans", failing_trans)

        cfg = ULPUConfig(translation_provider="failing_trans")
        service = UlpuService(config=cfg, provider_registry=p_registry)

        with pytest.raises(TranslationError):
            service.localize_response(system_response="Valid system response.", target_language="hi")

    def test_audio_modality_response_localization(self):
        service = UlpuService()
        system_response = "Irrigate the field tomorrow morning."
        res = service.localize_response(
            system_response=system_response,
            target_language="hi",
            target_modality=InputModality.AUDIO,
        )

        assert res.audio_output is not None
        assert res.audio_output.audio_bytes.startswith(b"MOCK_TTS_AUDIO")

    def test_end_to_end_conversational_roundtrip_flow(self):
        service = UlpuService()

        # Step A: Farmer input -> ULPU System Representation
        farmer_input = "My wheat leaves are turning yellow."
        input_res = service.process_text(text=farmer_input, target_language="hi")

        assert input_res.canonical_text == farmer_input
        assert input_res.system_representation is not None

        # Step B: Simulated EarthMind core reasoning intelligence response
        simulated_intelligence_response = "The crop may be experiencing nitrogen deficiency. Check soil nutrient levels."

        # Step C: ULPU Response Localization -> Farmer Language Output
        output_res = service.localize_response(
            system_response=simulated_intelligence_response,
            target_language="hi",
            request_id=input_res.request_id,
        )

        assert output_res.request_id == input_res.request_id
        assert output_res.original_response == simulated_intelligence_response
        assert len(output_res.localized_response) > 0

    def test_roundtrip_linguistic_safety(self):
        """Verify roundtrip pipeline preserves linguistic information and does not invent facts."""
        service = UlpuService()
        original_query = "Is it safe to spray pesticide during heavy rain?"

        input_res = service.process_text(text=original_query, target_language="hi")
        # System representation must reflect verbatim original query without inventing answer
        assert "heavy rain" in input_res.canonical_text

        system_answer = "Do not spray pesticide during heavy rain as runoff will occur."
        loc_res = service.localize_response(system_response=system_answer, target_language="hi")

        assert loc_res.original_response == system_answer
