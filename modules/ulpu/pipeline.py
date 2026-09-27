"""ULPU Text Processing Pipeline Engine."""

import uuid
from typing import Optional, Dict, Any
from core.interfaces.ulpu import (
    ILanguageDetector,
    INormalizer,
    IDisfluencyProcessor,
    ICanonicalizer,
    ITranslator,
)
from core.schemas.ulpu import (
    ULPUTextPipelineRequest,
    ULPUTextPipelineResponse,
    SystemLanguageRepresentation,
    InputSource,
    InputModality,
    ScriptType,
    LanguageDetectionRequest,
    NormalizationRequest,
    DisfluencyRequest,
    CanonicalizationRequest,
    TranslationRequest,
)
from core.errors.exceptions import (
    InvalidInputError,
    UnsupportedLanguageError,
    LowConfidenceError,
    TranslationError,
    ProviderError,
)
from modules.ulpu.config import ULPUConfig
from modules.ulpu.registry import LanguageRegistry
from modules.ulpu.providers.registry import ProviderRegistry
from modules.ulpu.processors.normalizer import StandardNormalizer
from modules.ulpu.processors.disfluency import StandardDisfluencyProcessor
from modules.ulpu.processors.canonicalizer import StandardCanonicalizer
from core.logging.logger import get_logger

logger = get_logger("modules.ulpu.pipeline")


class ULPUTextPipelineEngine:
    """
    Engine orchestrating ULPU text processing pipeline:
    Input Validation -> Language Detection -> Normalization -> Disfluency Cleaning
    -> Canonicalization -> System Language Representation -> Translation -> Output Response
    """

    def __init__(
        self,
        config: Optional[ULPUConfig] = None,
        language_registry: Optional[LanguageRegistry] = None,
        provider_registry: Optional[ProviderRegistry] = None,
        normalizer: Optional[INormalizer] = None,
        disfluency_processor: Optional[IDisfluencyProcessor] = None,
        canonicalizer: Optional[ICanonicalizer] = None,
    ) -> None:
        self.config = config or ULPUConfig()
        self.config.validate_config()
        self.language_registry = language_registry or LanguageRegistry()
        self.provider_registry = provider_registry or ProviderRegistry()

        self.normalizer = normalizer or StandardNormalizer()
        self.disfluency_processor = disfluency_processor or StandardDisfluencyProcessor()
        self.canonicalizer = canonicalizer or StandardCanonicalizer()

    def process(self, request: ULPUTextPipelineRequest) -> ULPUTextPipelineResponse:
        """Execute the text pipeline orchestrator."""
        request_id = request.request_id or f"ulpu_req_{uuid.uuid4().hex[:10]}"
        raw_text = request.text
        target_lang = request.target_language.lower().strip()

        logger.info(f"[{request_id}] Starting ULPU text pipeline. Target language: '{target_lang}'")

        # 1. Input Validation
        if not raw_text or not raw_text.strip():
            raise InvalidInputError("Text input cannot be empty or whitespace-only.")

        if not self.language_registry.is_supported(target_lang, "translation"):
            raise UnsupportedLanguageError(target_lang, "translation")

        # 2. Language Detection
        detector: ILanguageDetector = self.provider_registry.get_provider(
            "language_detection", self.config.language_detection_provider
        )
        detection_req = LanguageDetectionRequest(text=raw_text)
        detection_res = detector.detect_language(detection_req)

        detected_lang = detection_res.detected_language
        confidence = detection_res.confidence
        script = detection_res.script

        logger.info(f"[{request_id}] Language detected: '{detected_lang}' ({script}) with confidence {confidence:.2f}")

        if confidence < self.config.confidence_threshold:
            raise LowConfidenceError("language_detection", confidence, self.config.confidence_threshold)

        if not self.language_registry.is_supported(detected_lang):
            raise UnsupportedLanguageError(detected_lang, "source_language")

        # 3. Text Normalization
        norm_req = NormalizationRequest(text=raw_text, language=detected_lang, script=script)
        norm_res = self.normalizer.normalize(norm_req)
        normalized_text = norm_res.normalized_text

        # 4. Disfluency Processing
        dis_req = DisfluencyRequest(text=normalized_text, language=detected_lang)
        dis_res = self.disfluency_processor.remove_disfluencies(dis_req)
        cleaned_text = dis_res.cleaned_text

        # 5. Canonicalization
        canon_req = CanonicalizationRequest(
            normalized_text=cleaned_text,
            source_language=detected_lang,
            script=script,
        )
        canon_res = self.canonicalizer.canonicalize(canon_req)
        canonical_text = canon_res.canonical_text

        # 6. Build System Language Representation
        transformation_metadata = {
            "normalization_changes": norm_res.changes_made,
            "disfluencies_removed": dis_res.disfluencies_removed,
            "canonicalization_target": canon_res.target_language,
            "detection_provider": detector.get_provider_name(),
        }

        system_representation = SystemLanguageRepresentation(
            request_id=request_id,
            source=InputSource(
                modality=InputModality.TEXT,
                language=detected_lang,
                script=script,
            ),
            original_text=raw_text,
            normalized_text=cleaned_text,
            canonical_text=canonical_text,
            language_confidence=confidence,
            transformation_metadata=transformation_metadata,
            uncertainty=[],
        )

        # 7. Translation to Target Language
        translator: ITranslator = self.provider_registry.get_provider(
            "translation", self.config.translation_provider
        )

        # If source language and target language are identical, no translation API call needed
        if detected_lang.lower() == target_lang.lower():
            translated_text = cleaned_text
        else:
            trans_req = TranslationRequest(
                text=canonical_text if detected_lang.lower() == "en" else cleaned_text,
                source_language=detected_lang,
                target_language=target_lang,
            )
            try:
                trans_res = translator.translate(trans_req)
                translated_text = trans_res.translated_text
            except Exception as e:
                if isinstance(e, (TranslationError, ProviderError)):
                    raise
                raise TranslationError(translator.get_provider_name(), detected_lang, target_lang, str(e))

        logger.info(f"[{request_id}] Translation complete ({detected_lang} -> {target_lang})")

        # 8. Return Pipeline Response
        return ULPUTextPipelineResponse(
            request_id=request_id,
            original_input=raw_text,
            detected_language=detected_lang,
            detection_confidence=confidence,
            normalized_text=cleaned_text,
            canonical_text=canonical_text,
            target_language=target_lang,
            translated_text=translated_text,
            system_representation=system_representation,
            transformation_metadata=transformation_metadata,
            errors=[],
        )
