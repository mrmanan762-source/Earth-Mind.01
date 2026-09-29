# ULPU (Universal Language Processing Unit) Specification & Architecture

## 1. Executive Summary & Purpose
ULPU is EarthMind's **Human Language Boundary Layer**. Its sole responsibility is bi-directional translation and transformation between human multi-modal communication (text/speech in regional languages such as Hindi, Marathi, Telugu, Punjabi, Tamil, English, etc.) and controlled system-language representations (typically normalized English canonical text).

## 2. Mandatory Boundary (`LANGUAGE ≠ INTELLIGENCE`)
ULPU is strictly a **LANGUAGE PROCESSING** module.
It is **NOT** an agricultural intelligence, RAG, or decision-making engine.

ULPU MUST NOT perform:
- Crop, disease, or pest diagnosis
- Treatment or fertilizer recommendations
- Irrigation or weather decisions
- Agricultural reasoning, RAG, or web search
- Autonomous decision-making or drone control

**Core Rule:** `LANGUAGE ≠ INTELLIGENCE`. ULPU changes language, not intelligence. ULPU must never invent agricultural meaning or convert uncertain language into false certainty.

---

## 3. Five EarthMind Principles Adherence
1. **Extensibility / Rubber-Band Principle:** Multi-language & multi-provider framework expandable without core refactoring. Adding a new language or provider requires zero changes to core pipeline logic.
2. **Loose Coupling:** Core logic interacts with external AI/language providers exclusively through abstract interfaces and adapter patterns (`Core -> Provider Interface -> Adapter -> External API/SDK`). ULPU is completely decoupled from EarthMind intelligence internals.
3. **Single Responsibility:** Separates input parsing, audio processing, STT, language detection, normalization, disfluency cleaning, translation, canonicalization, response localization, and TTS into independent protocols and processors.
4. **Controlled Dependencies:** Core ULPU has zero direct dependency on external provider SDKs.
5. **Replaceability + Evolution:** Individual providers (e.g. Sarvam STT, Google Translate, ElevenLabs TTS) can be swapped dynamically via `ProviderRegistry`.

---

## 4. End-to-End Conversational Pipeline Flow

```
                FARMER
                   │
                   ▼
          Human Language Input
                   │
                   ▼
                 ULPU
  (Validation -> Detection -> Normalization ->
   Disfluency Cleaning -> Canonicalization)
                   │
                   ▼
       System Language Representation
                   │
                   ▼
          EARTHMIND INTELLIGENCE
                   │
                   ▼
        Validated System Response
                   │
                   ▼
                 ULPU
  (Validation -> Source/Target Lookup ->
   Semantic-Preserving Response Localization)
                   │
                   ▼
       Farmer's Target Language
                   │
                   ▼
                FARMER
```

---

## 5. Core Contracts & Data Models

### 5.1 SystemLanguageRepresentation Contract (`core/schemas/ulpu.py`)
```python
class SystemLanguageRepresentation(BaseModel):
    request_id: str
    source: InputSource  # modality, language, script
    original_text: str  # verbatim input
    normalized_text: str  # cleaned text
    canonical_text: str  # system-language representation
    language_confidence: float
    transformation_metadata: Dict[str, Any]
    uncertainty: List[str]
    timestamp: datetime
```

### 5.2 Input Pipeline Schemas
- `ULPUTextPipelineRequest`: `text`, `target_language`, `request_id`, `source_language_hint`
- `ULPUTextPipelineResponse`: `request_id`, `original_input`, `detected_language`, `detection_confidence`, `normalized_text`, `canonical_text`, `target_language`, `translated_text`, `system_representation`, `transformation_metadata`, `errors`

### 5.3 Response Localization Schemas
- `ULPUResponseLocalizationRequest`: `system_response`, `source_language`, `target_language`, `request_id`, `target_modality`, `voice_id`, `context_metadata`
- `ULPUResponseLocalizationResponse`: `request_id`, `original_response`, `source_language`, `target_language`, `localized_response`, `confidence`, `transformation_metadata`, `uncertainty`, `audio_output`

---

## 6. Provider Protocols & Registries

### 6.1 Core Protocols (`core/interfaces/ulpu.py`)
1. `IInputProcessor`
2. `IAudioProcessor`
3. `ISTTProvider`
4. `ILanguageDetector`
5. `INormalizer`
6. `IDisfluencyProcessor`
7. `ITranslator`
8. `ICanonicalizer`
9. `IResponseLocalizer`
10. `ITTSProvider`
11. `IProviderRegistry`

### 6.2 Registries (`modules/ulpu/`)
- **Language Registry (`modules/ulpu/registry.py`):** Central manager pre-populated with Indic languages (`en`, `hi`, `mr`, `pa`, `te`, `ta`, `gu`, `bn`, `kn`, `ml`). Tracks script type, STT, translation, TTS, and code-mixing capabilities.
- **Provider Registry (`modules/ulpu/providers/registry.py`):** Dynamic registry for category provider adapters.
- **Mock Adapters (`modules/ulpu/providers/mocks.py`):** Test doubles (`MockSTTProvider`, `MockTranslator`, `MockLanguageDetector`, `MockTTSProvider`, `MockAudioProcessor`, `ConfigurableFailureMockTranslator`, `ConfigurableFailureMockDetector`).

---

## 7. Reliability, Fallbacks & Observability

### 7.1 Resilient Execution Engine (`modules/ulpu/resilience.py`)
- **Bounded Retry:** Retries transient failures up to `max_retries` with exponential backoff. Non-retryable validation errors (`InvalidInputError`, `UnsupportedLanguageError`) short-circuit immediately.
- **Ordered Provider Fallbacks:** If primary provider fails after retries, automatically attempts configured fallbacks (`translation_fallbacks`, `language_detection_fallbacks`).
- **No Silent Language Replacement:** If localization to target language fails across all providers, raises a structured `TranslationError` or `ProviderError` instead of silently returning unrequested languages (e.g. English).
- **Traceability & Observability:** Propagates `request_id` across all stages and records latency timings (`stage_latency_ms`, `total_pipeline_latency_ms`) and resilience traces (`primary_provider`, `final_provider`, `fallback_used`, `failed_providers`).

---

## 8. Error Model (`core/errors/exceptions.py`)
Structured, machine-readable exception hierarchy derived from `EarthMindException`:
- `ULPUError`
- `InvalidInputError`
- `UnsupportedLanguageError`
- `AudioProcessingError`
- `STTError`
- `TranslationError`
- `TTSError`
- `ProviderError`
- `ULPUTimeoutError`
- `LowConfidenceError`
- `ULPUConfigurationError`
- `InternalULPUError`

---

## 9. Testing & Validation

### Running ULPU Test Suite
Run all ULPU tests:
```bash
python -m pytest tests/test_ulpu_foundation.py tests/test_ulpu_text_pipeline.py tests/test_ulpu_response_localization.py tests/test_ulpu_reliability.py tests/test_ulpu_semantic_preservation.py
```

Run full EarthMind repository test suite:
```bash
python -m pytest
```

### Demonstrations
Run complete ULPU end-to-end demonstration:
```bash
python demo_ulpu_complete.py
```
