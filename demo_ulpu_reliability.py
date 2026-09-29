"""Demo Script for ULPU Reliability, Provider Retry, and Fallback Execution."""

from modules.ulpu.config import ULPUConfig
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import (
    MockLanguageDetector,
    ConfigurableFailureMockTranslator,
)
from modules.ulpu.ulpu_service import UlpuService
from core.errors.exceptions import TranslationError

def run_reliability_demo():
    print("==================================================================")
    print("   EARTHMIND ULPU RELIABILITY & FALLBACK DEMONSTRATION")
    print("==================================================================")

    # 1. Setup Provider Registry with Primary (Failing) and Fallback (Successful) Translators
    p_registry = ProviderRegistry()
    p_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())

    primary_failing_trans = ConfigurableFailureMockTranslator(
        provider_name="primary_failing_translator",
        mode="always_fail",
    )
    fallback_success_trans = ConfigurableFailureMockTranslator(
        provider_name="fallback_backup_translator",
        mode="success",
        translation_prefix="[FALLBACK_SUCCESS_HINDI]",
    )

    p_registry.register_provider("translation", "primary_failing_translator", primary_failing_trans)
    p_registry.register_provider("translation", "fallback_backup_translator", fallback_success_trans)

    config = ULPUConfig(
        translation_provider="primary_failing_translator",
        translation_fallbacks=["fallback_backup_translator"],
        max_retries=1,
        retry_delay_seconds=0.01,
    )

    service = UlpuService(config=config, provider_registry=p_registry)

    # Demo Scenario 1: Primary Fails -> Retries -> Fallback Succeeds
    print("\n--- SCENARIO 1: PRIMARY PROVIDER FAILS -> FALLBACK SUCCEEDS ---")
    input_text = "My wheat crop needs fertilizer recommendation."

    response = service.process_text(text=input_text, target_language="hi")

    print("\n[RESULT]")
    print(f"Request ID:               {response.request_id}")
    print(f"Original Input:           '{response.original_input}'")
    print(f"Target Language:          {response.target_language}")
    print(f"Translated Output:        '{response.translated_text}'")

    resilience_meta = response.transformation_metadata.get("translation_resilience", {})
    print(f"Primary Provider Config:  '{resilience_meta.get('primary_provider')}'")
    print(f"Final Provider Used:      '{resilience_meta.get('final_provider')}'")
    print(f"Fallback Used?:           {resilience_meta.get('fallback_used')}")
    print(f"Failed Providers Log:     {resilience_meta.get('failed_providers')}")

    # Demo Scenario 2: Primary and Fallback Both Fail -> Structured Error
    print("\n------------------------------------------------------------------")
    print("--- SCENARIO 2: ALL PROVIDERS FAIL -> CONTROLLED STRUCTURED ERROR ---")
    print("------------------------------------------------------------------")

    all_failing_registry = ProviderRegistry()
    all_failing_registry.register_provider("language_detection", "mock_detection", MockLanguageDetector())
    all_failing_registry.register_provider("translation", "primary_failing", ConfigurableFailureMockTranslator("primary_failing", "always_fail"))
    all_failing_registry.register_provider("translation", "fallback_failing", ConfigurableFailureMockTranslator("fallback_failing", "always_fail"))

    all_failing_config = ULPUConfig(
        translation_provider="primary_failing",
        translation_fallbacks=["fallback_failing"],
        max_retries=1,
        retry_delay_seconds=0.01,
    )

    failing_service = UlpuService(config=all_failing_config, provider_registry=all_failing_registry)

    try:
        failing_service.process_text(text="Test crop query", target_language="hi")
    except TranslationError as e:
        print("\n[CONTROLLED ERROR CAPTURED]")
        print(f"Error Type:     {type(e).__name__}")
        print(f"Error Code:     {e.error_contract.error_code}")
        print(f"Module:         {e.error_contract.module}")
        print(f"Operation:      {e.error_contract.operation}")
        print(f"Error Message:  {e.error_contract.message}")

    print("==================================================================")

if __name__ == "__main__":
    run_reliability_demo()
