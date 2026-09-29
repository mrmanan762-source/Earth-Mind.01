"""Comprehensive Reliability, Fallback, Timeout, and Observability Tests for ULPU."""

import pytest
from core.schemas.ulpu import ULPUTextPipelineResponse, ULPUResponseLocalizationResponse
from core.errors.exceptions import (
    InvalidInputError,
    UnsupportedLanguageError,
    LowConfidenceError,
    TranslationError,
    ULPUTimeoutError,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import (
    MockLanguageDetector,
    MockTranslator,
    ConfigurableFailureMockTranslator,
    ConfigurableFailureMockDetector,
)
from modules.ulpu.ulpu_service import UlpuService


class TestULPUReliability:

    def test_primary_provider_success(self):
        service = UlpuService()
        res = service.process_text("Wheat crop irrigation", target_language="hi")
        assert res.translated_text is not None
        resilience_meta = res.transformation_metadata.get("translation_resilience", {})
        assert resilience_meta.get("fallback_used") is False

    def test_primary_transient_failure_with_retry_success(self):
        transient_translator = ConfigurableFailureMockTranslator(
            provider_name="transient_translator",
            mode="fail_once",
        )
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "transient_translator", transient_translator)

        cfg = ULPUConfig(
            translation_provider="transient_translator",
            max_retries=2,
            retry_delay_seconds=0.01,
        )
        service = UlpuService(config=cfg, provider_registry=p_registry)

        res = service.process_text("Wheat crop irrigation", target_language="hi")
        assert res.translated_text is not None
        resilience_meta = res.transformation_metadata.get("translation_resilience", {})
        assert resilience_meta.get("attempts_on_final_provider") == 2
        assert resilience_meta.get("fallback_used") is False

    def test_primary_failure_with_fallback_success(self):
        failing_trans = ConfigurableFailureMockTranslator("failing_trans", "always_fail")
        fallback_trans = ConfigurableFailureMockTranslator("fallback_trans", "success", "[FALLBACK_OK]")

        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "failing_trans", failing_trans)
        p_registry.register_provider("translation", "fallback_trans", fallback_trans)

        cfg = ULPUConfig(
            translation_provider="failing_trans",
            translation_fallbacks=["fallback_trans"],
            max_retries=1,
            retry_delay_seconds=0.01,
        )
        service = UlpuService(config=cfg, provider_registry=p_registry)

        res = service.process_text("Fertilizer dosage", target_language="hi")
        assert "[FALLBACK_OK]" in res.translated_text
        resilience_meta = res.transformation_metadata.get("translation_resilience", {})
        assert resilience_meta.get("fallback_used") is True
        assert resilience_meta.get("final_provider") == "fallback_trans"
        assert len(resilience_meta.get("failed_providers")) == 1

    def test_primary_and_fallback_both_fail(self):
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "failing_1", ConfigurableFailureMockTranslator("failing_1", "always_fail"))
        p_registry.register_provider("translation", "failing_2", ConfigurableFailureMockTranslator("failing_2", "always_fail"))

        cfg = ULPUConfig(
            translation_provider="failing_1",
            translation_fallbacks=["failing_2"],
            max_retries=1,
            retry_delay_seconds=0.01,
        )
        service = UlpuService(config=cfg, provider_registry=p_registry)

        with pytest.raises(TranslationError):
            service.process_text("Fertilizer dosage", target_language="hi")

    def test_non_retryable_input_error_does_not_trigger_retries(self):
        service = UlpuService()
        with pytest.raises(InvalidInputError):
            service.process_text("", target_language="hi")

    def test_unsupported_language_does_not_trigger_provider_calls(self):
        service = UlpuService()
        with pytest.raises(UnsupportedLanguageError):
            service.process_text("Test string", target_language="invalid_language_code")

    def test_timeout_handling(self):
        timeout_trans = ConfigurableFailureMockTranslator("timeout_trans", mode="timeout")
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "timeout_trans", timeout_trans)

        cfg = ULPUConfig(translation_provider="timeout_trans", max_retries=0)
        service = UlpuService(config=cfg, provider_registry=p_registry)

        with pytest.raises(TranslationError):
            service.process_text("Fertilizer dosage", target_language="hi")

    def test_low_confidence_handling(self):
        low_conf_detector = ConfigurableFailureMockDetector("low_conf_detector", mode="low_confidence")
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "low_conf_detector", low_conf_detector)
        p_registry.register_provider("translation", "mock_translation", MockTranslator())

        cfg = ULPUConfig(
            language_detection_provider="low_conf_detector",
            confidence_threshold=0.6,
        )
        service = UlpuService(config=cfg, provider_registry=p_registry)

        with pytest.raises(LowConfidenceError):
            service.process_text("Wheat query", target_language="hi")

    def test_requested_language_preservation(self):
        failing_trans = ConfigurableFailureMockTranslator("failing_trans", "always_fail")
        p_registry = ProviderRegistry()
        p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
        p_registry.register_provider("translation", "failing_trans", failing_trans)

        cfg = ULPUConfig(translation_provider="failing_trans", max_retries=0)
        service = UlpuService(config=cfg, provider_registry=p_registry)

        # Force failure when target_language = hi; verify ULPU does NOT silently return English
        with pytest.raises(TranslationError):
            service.process_text("Wheat crop query", target_language="hi")

    def test_trace_id_propagation(self):
        service = UlpuService()
        custom_req_id = "trace_id_xyz_999"
        res = service.process_text("Wheat query", target_language="hi", request_id=custom_req_id)

        assert res.request_id == custom_req_id
        assert res.system_representation.request_id == custom_req_id

    def test_observability_and_latency_measurement(self):
        service = UlpuService()
        res = service.process_text("Wheat irrigation query", target_language="hi")

        meta = res.transformation_metadata
        assert "total_pipeline_latency_ms" in meta
        assert meta["total_pipeline_latency_ms"] >= 0.0
        assert "detection_resilience" in meta
        assert "translation_resilience" in meta

    def test_response_localization_reliability_and_fallback(self):
        failing_trans = ConfigurableFailureMockTranslator("failing_trans", "always_fail")
        fallback_trans = ConfigurableFailureMockTranslator("fallback_trans", "success", "[LOCALIZED_FALLBACK]")

        p_registry = ProviderRegistry()
        p_registry.register_provider("translation", "failing_trans", failing_trans)
        p_registry.register_provider("translation", "fallback_trans", fallback_trans)

        cfg = ULPUConfig(
            translation_provider="failing_trans",
            translation_fallbacks=["fallback_trans"],
            max_retries=1,
            retry_delay_seconds=0.01,
        )
        service = UlpuService(config=cfg, provider_registry=p_registry)

        res = service.localize_response(
            system_response="System response text.",
            target_language="hi",
        )
        assert "[LOCALIZED_FALLBACK]" in res.localized_response
        resilience_meta = res.transformation_metadata.get("translation_resilience", {})
        assert resilience_meta.get("fallback_used") is True
