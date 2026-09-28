"""Demo Script for ULPU Response Localization and Conversational Roundtrip Execution."""

from modules.ulpu.ulpu_service import UlpuService

def run_response_localization_demo():
    print("==================================================================")
    print("   EARTHMIND ULPU RESPONSE LOCALIZATION DEMONSTRATION")
    print("==================================================================")

    service = UlpuService()

    # 1. System Response Localization Demo
    system_response = "Your wheat may be experiencing nitrogen deficiency. Consider checking soil nutrient levels."
    target_lang = "hi"

    print("\n--- STAGE 1: SYSTEM RESPONSE LOCALIZATION ---")
    print(f"Original System Response: '{system_response}'")
    print(f"Target Farmer Language:   '{target_lang}' (Hindi)")

    loc_response = service.localize_response(
        system_response=system_response,
        target_language=target_lang,
        source_language="en",
    )

    print("\n[RESULT]")
    print(f"Request ID:               {loc_response.request_id}")
    print(f"Source Language:          {loc_response.source_language}")
    print(f"Target Language:          {loc_response.target_language}")
    print(f"Localized Response Text:  '{loc_response.localized_response}'")
    print(f"Confidence Score:         {loc_response.confidence:.2f}")

    # 2. Complete End-to-End Conversational Roundtrip Demo
    print("\n------------------------------------------------------------------")
    print("--- STAGE 2: FULL END-TO-END CONVERSATIONAL ROUNDTRIP DEMO ---")
    print("------------------------------------------------------------------")

    farmer_input = "My wheat leaves are turning yellow."
    farmer_target_lang = "hi"

    print(f"\nStep 1: Farmer Input (English): '{farmer_input}'")
    input_pipeline_res = service.process_text(text=farmer_input, target_language=farmer_target_lang)

    print(f"Step 2: ULPU System Language Representation Produced:")
    print(f"        Canonical Text: '{input_pipeline_res.canonical_text}'")
    print(f"        Request ID:     '{input_pipeline_res.request_id}'")

    print("\nStep 3: Simulated EarthMind Core Reasoning Intelligence Response:")
    simulated_earthmind_response = "The crop may be experiencing a nutrient deficiency. Consider checking soil nutrient levels."
    print(f"        Validated System Response: '{simulated_earthmind_response}'")

    print(f"\nStep 4: ULPU Localizes System Response back to Farmer Language ('{farmer_target_lang}'):")
    roundtrip_loc_res = service.localize_response(
        system_response=simulated_earthmind_response,
        target_language=farmer_target_lang,
        source_language="en",
        request_id=input_pipeline_res.request_id,
    )

    print(f"\nStep 5: Final Farmer-Facing Localized Output:")
    print(f"        '{roundtrip_loc_res.localized_response}'")
    print("==================================================================")

if __name__ == "__main__":
    run_response_localization_demo()
