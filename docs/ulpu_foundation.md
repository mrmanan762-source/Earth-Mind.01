# ULPU (Universal Language Processing Unit) Foundation

## 1. What ULPU Is
ULPU is EarthMind's **Human Language Boundary Layer**. Its responsibility is bi-directional translation and transformation between human multi-modal communication (text/speech in regional languages such as Hindi, Marathi, Telugu, Punjabi, Tamil, English, etc.) and controlled system-language representations (typically normalized English canonical text).

## 2. What ULPU Is NOT
ULPU is strictly a **LANGUAGE PROCESSING** module.
It is **NOT** an agricultural intelligence or decision-making engine.

ULPU MUST NOT perform:
- Crop, disease, or pest diagnosis
- Treatment or fertilizer recommendations
- Irrigation or weather decisions
- Agricultural reasoning, RAG, or web search
- Autonomous decision-making or drone control

**Core Rule:** `LANGUAGE ≠ INTELLIGENCE`. ULPU may transform language, but it must never invent agricultural meaning or convert uncertain language into false certainty.

## 3. Module Boundaries & Architecture
ULPU adheres to EarthMind's five locked architectural principles:
1. **Extensibility / Rubber-Band Principle:** Multi-language & multi-provider framework expandable without core refactoring.
2. **Loose Coupling:** Core logic interacts with external AI/language providers exclusively through abstract interfaces and adapter patterns (`Core -> Provider Interface -> Adapter -> External API/SDK`).
3. **Single Responsibility:** Separates input parsing, audio processing, STT, language detection, normalization, disfluency cleaning, translation, canonicalization, response localization, and TTS.
4. **Controlled Dependencies:** Core ULPU has zero direct dependency on external provider SDKs.
5. **Replaceability + Evolution:** Individual providers (e.g. Sarvam STT, Google Translate, ElevenLabs TTS) can be swapped seamlessly.

## 4. System-Language Representation Contract
ULPU enforces intent preservation through the `SystemLanguageRepresentation` contract (`core/schemas/ulpu.py`):

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

## 5. Error Model
ULPU defines a machine-readable structured error model derived from `EarthMindException` in `core/errors/exceptions.py`:
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

## 6. Language & Provider Registries
- **Language Registry (`modules/ulpu/registry.py`):** Central manager pre-populated with Indic languages (hi, mr, pa, te, ta, gu, bn, kn, ml) and English. Tracks script, STT, translation, TTS, and code-mixing capabilities.
- **Provider Registry (`modules/ulpu/providers/registry.py`):** Dynamic registry for provider instances.
- **Mock Providers (`modules/ulpu/providers/mocks.py`):** In-memory test doubles (`MockSTTProvider`, `MockTranslator`, `MockLanguageDetector`, `MockTTSProvider`, `MockAudioProcessor`) allowing complete unit testing without external API credentials.

## 7. Running ULPU Tests
Run the ULPU test suite:
```bash
python -m pytest tests/test_ulpu_foundation.py
```
Run the full EarthMind test suite:
```bash
python -m pytest
```
