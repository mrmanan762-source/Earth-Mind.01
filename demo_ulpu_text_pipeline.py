"""Demo Script for ULPU Text Pipeline Execution."""

from modules.ulpu.ulpu_service import UlpuService

def run_demo():
    print("==================================================")
    print("   EARTHMIND ULPU TEXT PIPELINE DEMONSTRATION")
    print("==================================================")

    service = UlpuService()
    input_text = "My wheat leaves are turning yellow. What should I do?"
    target_lang = "hi"

    print(f"Input Text:           '{input_text}'")
    print(f"Requested Target:     '{target_lang}' (Hindi)")

    response = service.process_text(text=input_text, target_language=target_lang)

    print("\n------------------- RESULTS -------------------")
    print(f"Request ID:           {response.request_id}")
    print(f"Detected Language:    {response.detected_language} (Confidence: {response.detection_confidence:.2f})")
    print(f"Normalized Text:      '{response.normalized_text}'")
    print(f"Canonical System Text:'{response.canonical_text}'")
    print(f"Target Language:      {response.target_language}")
    print(f"Translated Output:    '{response.translated_text}'")
    print("System Representation:")
    print(f"  Source Modality:    {response.system_representation.source.modality.value}")
    print(f"  Source Language:    {response.system_representation.source.language}")
    print(f"  Source Script:      {response.system_representation.source.script.value}")
    print(f"  Canonical Text:     '{response.system_representation.canonical_text}'")
    print("==================================================")

if __name__ == "__main__":
    run_demo()
