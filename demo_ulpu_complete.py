"""Final Complete Demonstration Script for EarthMind ULPU."""

from modules.ulpu.config import ULPUConfig
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import (
    MockLanguageDetector,
    ConfigurableFailureMockTranslator,
)
from modules.ulpu.ulpu_service import UlpuService
from core.errors.exceptions import TranslationError


def run_complete_ulpu_demonstration():
    print("==================================================================")
    print("      EARTHMIND ULPU COMPLETE SYSTEM DEMONSTRATION")
    print("==================================================================")

    service = UlpuService()

    # ------------------------------------------------------------------
    # DEMO 1: FULL CONVERSATIONAL ROUNDTRIP (ENGLISH INPUT -> HINDI OUTPUT)
    # ------------------------------------------------------------------
    print("\n------------------------------------------------------------------")
    print(" DEMO 1: FULL CONVERSATIONAL ROUNDTRIP (ENGLISH -> HINDI)")
    print("------------------------------------------------------------------")

    farmer_input = "My wheat leaves are turning yellow. What should I do?"
    farmer_target_lang = "hi"

    print(f"\nStep 1: Farmer Input (English): '{farmer_input}'")
    input_pipeline_res = service.process_text(text=farmer_input, target_language=farmer_target_lang)

    print("\nStep 2: ULPU Input Pipeline Processing:")
    print(f"        Detected Language:  {input_pipeline_res.detected_language} (Confidence: {input_pipeline_res.detection_confidence:.2f})")
    print(f"        Normalized Text:    '{input_pipeline_res.normalized_text}'")
    print(f"        Canonical System:   '{input_pipeline_res.canonical_text}'")
    print(f"        System Rep ID:      '{input_pipeline_res.system_representation.request_id}'")

    simulated_earthmind_response = "The crop may be experiencing a nutrient deficiency. Consider checking soil nutrient levels before taking corrective action."
    print("\nStep 3: Simulated EarthMind Core Reasoning Intelligence Response:")
    print(f"        System Response:    '{simulated_earthmind_response}'")

    print(f"\nStep 4: ULPU Response Localization to Farmer Language ('{farmer_target_lang}'):")
    roundtrip_loc_res = service.localize_response(
        system_response=simulated_earthmind_response,
        target_language=farmer_target_lang,
        source_language="en",
        request_id=input_pipeline_res.request_id,
    )

    print(f"\nStep 5: Final Farmer-Facing Localized Output:")
    print(f"        Output Text:        '{roundtrip_loc_res.localized_response}'")

    # ------------------------------------------------------------------
    # DEMO 2: NON-ENGLISH INPUT PIPELINE (HINDI INPUT)
    # ------------------------------------------------------------------
    print("\n------------------------------------------------------------------")
    print(" DEMO 2: NON-ENGLISH INPUT PROCESSING (HINDI INPUT)")
    print("------------------------------------------------------------------")

    hindi_input = "मेरे गेहूं के पत्ते पीले हो रहे हैं।"
    print(f"\nInput Text (Hindi):         '{hindi_input}'")

    non_en_res = service.process_text(text=hindi_input, target_language="en")

    print("\n[RESULT]")
    print(f"Request ID:                 {non_en_res.request_id}")
    print(f"Detected Language:          {non_en_res.detected_language} (Confidence: {non_en_res.detection_confidence:.2f})")
    print(f"Target Language:            {non_en_res.target_language}")
    print(f"Canonical System Text:      '{non_en_res.canonical_text}'")
    print(f"Translated Output:          '{non_en_res.translated_text}'")

    # ------------------------------------------------------------------
    # DEMO 3: RELIABILITY & FALLBACK SCENARIO (PRIMARY FAILS -> FALLBACK SUCCEEDS)
    # ------------------------------------------------------------------
    print("\n------------------------------------------------------------------")
    print(" DEMO 3: RELIABILITY & FALLBACK (PRIMARY FAILS -> FALLBACK SUCCEEDS)")
    print("------------------------------------------------------------------")

    resilient_registry = ProviderRegistry()
    resilient_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
    resilient_registry.register_provider(
        "translation",
        "primary_failing_trans",
        ConfigurableFailureMockTranslator("primary_failing_trans", "always_fail"),
    )
    resilient_registry.register_provider(
        "translation",
        "fallback_backup_trans",
        ConfigurableFailureMockTranslator("fallback_backup_trans", "success", "[FALLBACK_SUCCESS_HINDI]"),
    )

    resilient_cfg = ULPUConfig(
        translation_provider="primary_failing_trans",
        translation_fallbacks=["fallback_backup_trans"],
        max_retries=1,
        retry_delay_seconds=0.01,
    )

    resilient_service = UlpuService(config=resilient_cfg, provider_registry=resilient_registry)

    fallback_res = resilient_service.process_text("Wheat irrigation advice", target_language="hi")

    print("\n[RESULT]")
    print(f"Translated Output:          '{fallback_res.translated_text}'")
    res_meta = fallback_res.transformation_metadata.get("translation_resilience", {})
    print(f"Primary Configured:         '{res_meta.get('primary_provider')}'")
    print(f"Final Provider Used:        '{res_meta.get('final_provider')}'")
    print(f"Fallback Used?:             {res_meta.get('fallback_used')}")

    # ------------------------------------------------------------------
    # DEMO 4: ALL PROVIDERS FAIL -> CONTROLLED STRUCTURED ERROR
    # ------------------------------------------------------------------
    print("\n------------------------------------------------------------------")
    print(" DEMO 4: ALL PROVIDERS FAIL -> CONTROLLED STRUCTURED ERROR")
    print("------------------------------------------------------------------")

    failing_registry = ProviderRegistry()
    failing_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
    failing_registry.register_provider("translation", "failing_1", ConfigurableFailureMockTranslator("failing_1", "always_fail"))
    failing_registry.register_provider("translation", "failing_2", ConfigurableFailureMockTranslator("failing_2", "always_fail"))

    failing_cfg = ULPUConfig(
        translation_provider="failing_1",
        translation_fallbacks=["failing_2"],
        max_retries=1,
        retry_delay_seconds=0.01,
    )

    failing_service = UlpuService(config=failing_cfg, provider_registry=failing_registry)

    try:
        failing_service.process_text("Wheat irrigation advice", target_language="hi")
    except TranslationError as e:
        print("\n[CONTROLLED STRUCTURED ERROR CAPTURED]")
        print(f"Error Code:     {e.error_contract.error_code}")
        print(f"Module:         {e.error_contract.module}")
        print(f"Operation:      {e.error_contract.operation}")
        print(f"Message:        {e.error_contract.message}")

    print("\n==================================================================")
    print("      ALL ULPU DEMONSTRATION SCENARIOS COMPLETED SUCCESSFULLY")
    print("==================================================================")


if __name__ == "__main__":
    run_complete_ulpu_demonstration()
