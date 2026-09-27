"""Tests for ULPU Foundation, Contracts, Error Model, Configuration, and Registries."""

import pytest
from pydantic import ValidationError
from core.schemas.ulpu import (
    SystemLanguageRepresentation,
    InputSource,
    InputModality,
    ScriptType,
    AudioPayload,
    STTRequest,
    STTResponse,
    TranslationRequest,
    TranslationResponse,
    TTSRequest,
    TTSResponse,
    LanguageDetectionRequest,
    LanguageDetectionResponse,
)
from core.interfaces.ulpu import (
    ISTTProvider,
    ILanguageDetector,
    ITranslator,
    ITTSProvider,
    IAudioProcessor,
    IProviderRegistry,
)
from core.errors.exceptions import (
    EarthMindException,
    ULPUError,
    InvalidInputError,
    UnsupportedLanguageError,
    AudioProcessingError,
    STTError,
    TranslationError,
    TTSError,
    ProviderError,
    ULPUTimeoutError,
    LowConfidenceError,
    ULPUConfigurationError,
    InternalULPUError,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.registry import LanguageCapability, LanguageRegistry
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.providers.mocks import (
    MockAudioProcessor,
    MockSTTProvider,
    MockLanguageDetector,
    MockTranslator,
    MockTTSProvider,
)
from modules.ulpu.ulpu_service import UlpuService


# 1. Contract Tests
class TestULPUContracts:

    def test_system_language_representation_valid(self):
        repr_obj = SystemLanguageRepresentation(
            request_id="req_123",
            source=InputSource(modality=InputModality.TEXT, language="hi", script=ScriptType.DEVANAGARI),
            original_text="मक्के की फसल में खाद कब डालें?",
            normalized_text="मक्के की फसल में खाद कब डालें?",
            canonical_text="When to apply fertilizer to corn crop?",
            language_confidence=0.98,
            transformation_metadata={"step": "normalization"},
            uncertainty=[],
        )
        assert repr_obj.request_id == "req_123"
        assert repr_obj.source.language == "hi"
        assert repr_obj.source.script == ScriptType.DEVANAGARI
        assert repr_obj.original_text == "मक्के की फसल में खाद कब डालें?"
        assert repr_obj.canonical_text == "When to apply fertilizer to corn crop?"
        assert repr_obj.language_confidence == 0.98

    def test_system_language_representation_validation_error(self):
        with pytest.raises(ValidationError):
            SystemLanguageRepresentation(
                request_id="req_123",
                source={"modality": "text", "language": "hi"},
                # Missing original_text
            )

    def test_audio_payload_validation(self):
        payload = AudioPayload(
            audio_bytes=b"dummy_audio_bytes",
            audio_format="wav",
            sample_rate_hz=16000,
            channels=1,
            duration_seconds=3.2,
        )
        assert payload.sample_rate_hz == 16000
        assert payload.audio_format == "wav"

        with pytest.raises(ValidationError):
            AudioPayload(sample_rate_hz=-100)


# 2. Error Model Tests
class TestULPUErrorModel:

    def test_error_hierarchy(self):
        err = InvalidInputError("Text is empty")
        assert isinstance(err, ULPUError)
        assert isinstance(err, EarthMindException)
        assert err.error_contract.error_code == "INVALID_INPUT"
        assert err.error_contract.module == "ulpu"

    def test_unsupported_language_error(self):
        err = UnsupportedLanguageError("xyz", "stt")
        assert err.error_contract.error_code == "UNSUPPORTED_LANGUAGE"
        assert err.error_contract.metadata["language_code"] == "xyz"
        assert err.error_contract.metadata["capability"] == "stt"

    def test_low_confidence_error(self):
        err = LowConfidenceError("translation", 0.45, 0.60)
        assert err.error_contract.error_code == "LOW_CONFIDENCE"
        assert err.error_contract.metadata["confidence"] == 0.45
        assert err.error_contract.metadata["threshold"] == 0.60

    def test_distinguishable_error_categories(self):
        errors = [
            InvalidInputError("bad input"),
            UnsupportedLanguageError("fr"),
            AudioProcessingError("corrupted audio"),
            STTError("mock_stt", "failed"),
            TranslationError("mock_trans", "hi", "en", "failed"),
            TTSError("mock_tts", "failed"),
            ProviderError("mock_p", "unavailable"),
            ULPUTimeoutError("transcribe", 10.0),
            LowConfidenceError("detect", 0.2, 0.8),
            ULPUConfigurationError("invalid config"),
            InternalULPUError("crash"),
        ]
        codes = [e.error_contract.error_code for e in errors]
        assert len(codes) == len(set(codes)), "All ULPU error codes must be unique"


# 3. Configuration Tests
class TestULPUConfiguration:

    def test_default_config_loading(self):
        cfg = ULPUConfig()
        assert cfg.validate_config() is True
        assert "hi" in cfg.supported_languages
        assert "en" in cfg.supported_languages
        assert cfg.default_canonical_language == "en"
        assert cfg.confidence_threshold == 0.6

    def test_invalid_config_rejection(self):
        with pytest.raises(ValueError, match="supported_languages list cannot be empty"):
            ULPUConfig(supported_languages=[]).validate_config()

        with pytest.raises(ValueError, match="confidence_threshold"):
            ULPUConfig(confidence_threshold=1.5).validate_config()

        with pytest.raises(ValueError, match="timeout_seconds"):
            ULPUConfig(timeout_seconds=-5.0).validate_config()


# 4. Language Registry Tests
class TestLanguageRegistry:

    def test_registry_default_population(self):
        registry = LanguageRegistry()
        assert registry.is_supported("hi") is True
        assert registry.is_supported("en") is True
        assert registry.is_supported("mr") is True
        assert registry.is_supported("pa") is True

        hi_cap = registry.get_language("hi")
        assert hi_cap.language_name == "Hindi"
        assert hi_cap.script == ScriptType.DEVANAGARI
        assert hi_cap.code_mix_support is True

    def test_capability_specific_query(self):
        registry = LanguageRegistry()
        assert registry.is_supported("hi", "stt") is True
        assert registry.is_supported("hi", "translation") is True
        assert registry.is_supported("hi", "tts") is True
        assert registry.is_supported("mr", "code_mix") is False

    def test_unsupported_language_lookup(self):
        registry = LanguageRegistry()
        assert registry.is_supported("unsupported_lang") is False
        with pytest.raises(UnsupportedLanguageError):
            registry.get_language("unsupported_lang")

    def test_dynamic_language_registration(self):
        registry = LanguageRegistry()
        custom = LanguageCapability(
            language_code="or",
            language_name="Odia",
            script=ScriptType.OTHER,
            stt_support=True,
            translation_support=True,
            tts_support=False,
            enabled=True,
        )
        registry.register_language(custom)
        assert registry.is_supported("or") is True
        assert registry.is_supported("or", "tts") is False


# 5. Provider Abstraction & Mock Provider Tests
class TestProviderAbstraction:

    def test_mock_providers_satisfy_protocols(self):
        assert isinstance(MockAudioProcessor(), IAudioProcessor)
        assert isinstance(MockSTTProvider(), ISTTProvider)
        assert isinstance(MockLanguageDetector(), ILanguageDetector)
        assert isinstance(MockTranslator(), ITranslator)
        assert isinstance(MockTTSProvider(), ITTSProvider)

    def test_provider_registry_operations(self):
        p_registry = ProviderRegistry()
        mock_stt = MockSTTProvider()
        p_registry.register_provider("stt", "mock_stt", mock_stt)

        fetched = p_registry.get_provider("stt", "mock_stt")
        assert fetched is mock_stt
        assert fetched.get_provider_name() == "mock_stt"

        default_fetched = p_registry.get_provider("stt")
        assert default_fetched is mock_stt

    def test_provider_registry_error_handling(self):
        p_registry = ProviderRegistry()
        with pytest.raises(ProviderError):
            p_registry.get_provider("stt", "non_existent")

    def test_mock_stt_execution(self):
        stt = MockSTTProvider(mock_transcript="धान में पानी कब लगाएं?")
        payload = AudioPayload(audio_bytes=b"123", audio_format="wav")
        req = STTRequest(audio=payload, language_hint="hi")
        res = stt.transcribe(req)

        assert res.transcript == "धान में पानी कब लगाएं?"
        assert res.confidence == 0.95
        assert res.detected_language == "hi"

    def test_mock_translator_execution(self):
        translator = MockTranslator()
        req = TranslationRequest(
            text="मक्के की फसल में खाद कब डालें?",
            source_language="hi",
            target_language="en",
        )
        res = translator.translate(req)
        assert res.translated_text == "When to apply fertilizer to corn crop?"
        assert res.source_language == "hi"
        assert res.target_language == "en"

    def test_mock_language_detector_execution(self):
        detector = MockLanguageDetector()
        req = LanguageDetectionRequest(text="मक्के की फसल")
        res = detector.detect_language(req)
        assert res.detected_language == "hi"
        assert res.script == ScriptType.DEVANAGARI

        req_en = LanguageDetectionRequest(text="Corn crop fertilizer")
        res_en = detector.detect_language(req_en)
        assert res_en.detected_language == "en"

    def test_mock_tts_execution(self):
        tts = MockTTSProvider()
        req = TTSRequest(text="When to apply fertilizer", target_language="en")
        res = tts.synthesize(req)
        assert res.audio_bytes.startswith(b"MOCK_TTS_AUDIO")
        assert res.duration_seconds > 0.0


# 6. Service Integration Foundation Test
class TestUlpuServiceFoundation:

    def test_service_initialization(self):
        service = UlpuService()
        assert service.config is not None
        assert service.language_registry.is_supported("hi") is True
        assert service.provider_registry.get_provider("stt", "mock_stt") is not None

    def test_create_system_representation_helper(self):
        service = UlpuService()
        sys_repr = service.create_system_representation(
            request_id="req_test_1",
            original_text="सोयाबीन बुवाई का समय",
            source_language="hi",
            script=ScriptType.DEVANAGARI,
            canonical_text="Soybean sowing time",
        )
        assert isinstance(sys_repr, SystemLanguageRepresentation)
        assert sys_repr.request_id == "req_test_1"
        assert sys_repr.original_text == "सोयाबीन बुवाई का समय"
        assert sys_repr.canonical_text == "Soybean sowing time"
