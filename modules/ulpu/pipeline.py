"""ULPU Text Processing Pipeline Engine."""

import time
import uuid
from typing import Optional, Dict, Any
from core.interfaces.ulpu import (
    ILanguageDetector,
    INormalizer,
    IDisfluencyProcessor,
    ICanonicalizer,
    ITranslator,
    ITTSProvider,
)
from core.schemas.ulpu import (
    ULPUTextPipelineRequest,
    ULPUTextPipelineResponse,
    ULPUResponseLocalizationRequest,
    ULPUResponseLocalizationResponse,
    SystemLanguageRepresentation,
    InputSource,
    InputModality,
    ScriptType,
    LanguageDetectionRequest,
    NormalizationRequest,
    DisfluencyRequest,
    CanonicalizationRequest,
    TranslationRequest,
    ResponseLocalizationRequest,
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
from modules.ulpu.processors.localizer import StandardResponseLocalizer
from modules.ulpu.resilience import ResilientProviderExecutor
from core.logging.logger import get_logger

logger = get_logger("modules.ulpu.pipeline")


class ULPUTextPipelineEngine:
    """
    Engine orchestrating ULPU text processing pipeline with resilience,
    traceability, latency measurement, and fallback handling.
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
        """Execute the text pipeline orchestrator with full resilience and observability."""
        pipeline_start_time = time.monotonic()
        request_id = request.request_id or f"ulpu_req_{uuid.uuid4().hex[:10]}"
        raw_text = request.text
        target_lang = request.target_language.lower().strip()

        logger.info(f"[{request_id}] Starting ULPU text pipeline. Target language: '{target_lang}'")

        # 1. Input Validation
        if not raw_text or not raw_text.strip():
            raise InvalidInputError("Text input cannot be empty or whitespace-only.")

        if not self.language_registry.is_supported(target_lang, "translation"):
            raise UnsupportedLanguageError(target_lang, "translation")

        # 2. Resilient Language Detection
        detection_executor = ResilientProviderExecutor(
            provider_registry=self.provider_registry,
            category="language_detection",
            primary_provider_name=self.config.language_detection_provider,
            fallback_provider_names=self.config.language_detection_fallbacks,
            max_retries=self.config.max_retries,
            retry_delay_seconds=self.config.retry_delay_seconds,
            timeout_seconds=self.config.timeout_seconds,
        )

        def _call_detector(provider: ILanguageDetector):
            return provider.detect_language(LanguageDetectionRequest(text=raw_text))

        detection_res, detection_resilience_meta = detection_executor.execute(
            func_caller=_call_detector,
            request_id=request_id,
            operation_name="language_detection",
        )

        detected_lang = detection_res.detected_language
        confidence = detection_res.confidence
        script = detection_res.script

        logger.info(f"[{request_id}] Language detected: '{detected_lang}' ({script}) with confidence {confidence:.2f}")

        if confidence < self.config.confidence_threshold:
            raise LowConfidenceError("language_detection", confidence, self.config.confidence_threshold)

        if not self.language_registry.is_supported(detected_lang):
            raise UnsupportedLanguageError(detected_lang, "source_language")

        # 3. Text Normalization
        norm_start = time.monotonic()
        norm_req = NormalizationRequest(text=raw_text, language=detected_lang, script=script)
        norm_res = self.normalizer.normalize(norm_req)
        normalized_text = norm_res.normalized_text
        norm_latency_ms = round((time.monotonic() - norm_start) * 1000, 2)

        # 4. Disfluency Processing
        dis_start = time.monotonic()
        dis_req = DisfluencyRequest(text=normalized_text, language=detected_lang)
        dis_res = self.disfluency_processor.remove_disfluencies(dis_req)
        cleaned_text = dis_res.cleaned_text
        dis_latency_ms = round((time.monotonic() - dis_start) * 1000, 2)

        # 5. Canonicalization
        canon_start = time.monotonic()
        canon_req = CanonicalizationRequest(
            normalized_text=cleaned_text,
            source_language=detected_lang,
            script=script,
        )
        canon_res = self.canonicalizer.canonicalize(canon_req)
        canonical_text = canon_res.canonical_text
        canon_latency_ms = round((time.monotonic() - canon_start) * 1000, 2)

        # 6. Build System Language Representation
        transformation_metadata = {
            "normalization_changes": norm_res.changes_made,
            "normalization_latency_ms": norm_latency_ms,
            "disfluencies_removed": dis_res.disfluencies_removed,
            "disfluency_latency_ms": dis_latency_ms,
            "canonicalization_target": canon_res.target_language,
            "canonicalization_latency_ms": canon_latency_ms,
            "detection_resilience": detection_resilience_meta,
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

        # 7. Resilient Translation to Target Language
        if detected_lang.lower() == target_lang.lower():
            translated_text = cleaned_text
            translation_resilience_meta = {"same_language_pass_through": True}
        else:
            trans_executor = ResilientProviderExecutor(
                provider_registry=self.provider_registry,
                category="translation",
                primary_provider_name=self.config.translation_provider,
                fallback_provider_names=self.config.translation_fallbacks,
                max_retries=self.config.max_retries,
                retry_delay_seconds=self.config.retry_delay_seconds,
                timeout_seconds=self.config.timeout_seconds,
            )

            text_to_translate = canonical_text if detected_lang.lower() == "en" else cleaned_text

            def _call_translator(provider: ITranslator):
                return provider.translate(
                    TranslationRequest(
                        text=text_to_translate,
                        source_language=detected_lang,
                        target_language=target_lang,
                    )
                )

            trans_res, translation_resilience_meta = trans_executor.execute(
                func_caller=_call_translator,
                request_id=request_id,
                operation_name="translation",
            )
            translated_text = trans_res.translated_text

        transformation_metadata["translation_resilience"] = translation_resilience_meta
        transformation_metadata["total_pipeline_latency_ms"] = round((time.monotonic() - pipeline_start_time) * 1000, 2)

        logger.info(f"[{request_id}] Pipeline complete ({detected_lang} -> {target_lang})")

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

    def localize_response(self, request: ULPUResponseLocalizationRequest) -> ULPUResponseLocalizationResponse:
        """Execute resilient response localization from system response to target farmer language."""
        loc_start_time = time.monotonic()
        request_id = request.request_id or f"ulpu_loc_{uuid.uuid4().hex[:10]}"
        system_response = request.system_response
        source_lang = request.source_language.lower().strip()
        target_lang = request.target_language.lower().strip()

        logger.info(f"[{request_id}] Localizing system response ({source_lang} -> {target_lang})")

        # 1. Validation
        if not system_response or not system_response.strip():
            raise InvalidInputError("System response text cannot be empty or whitespace-only.")

        if not self.language_registry.is_supported(source_lang):
            raise UnsupportedLanguageError(source_lang, "source_language")

        if not self.language_registry.is_supported(target_lang, "translation"):
            raise UnsupportedLanguageError(target_lang, "target_language")

        # 2. Resilient Localization via ResilientProviderExecutor
        tts_provider: Optional[ITTSProvider] = None
        if request.target_modality == InputModality.AUDIO:
            tts_provider = self.provider_registry.get_provider(
                "tts", self.config.tts_provider
            )

        if source_lang == target_lang:
            translator: ITranslator = self.provider_registry.get_provider(
                "translation", self.config.translation_provider
            )
            localizer = StandardResponseLocalizer(translator=translator, tts_provider=tts_provider)
            loc_res = localizer.localize_response(
                ResponseLocalizationRequest(
                    system_response=system_response,
                    target_language=target_lang,
                    target_modality=request.target_modality,
                    voice_id=request.voice_id,
                )
            )
            localized_text = loc_res.localized_text
            audio_output = loc_res.audio_output
            translation_resilience_meta = {"same_language_pass_through": True}
        else:
            trans_executor = ResilientProviderExecutor(
                provider_registry=self.provider_registry,
                category="translation",
                primary_provider_name=self.config.translation_provider,
                fallback_provider_names=self.config.translation_fallbacks,
                max_retries=self.config.max_retries,
                retry_delay_seconds=self.config.retry_delay_seconds,
                timeout_seconds=self.config.timeout_seconds,
            )

            def _call_translator_for_localization(provider: ITranslator):
                localizer = StandardResponseLocalizer(translator=provider, tts_provider=tts_provider)
                return localizer.localize_response(
                    ResponseLocalizationRequest(
                        system_response=system_response,
                        target_language=target_lang,
                        target_modality=request.target_modality,
                        voice_id=request.voice_id,
                    )
                )

            loc_res, translation_resilience_meta = trans_executor.execute(
                func_caller=_call_translator_for_localization,
                request_id=request_id,
                operation_name="response_localization",
            )
            localized_text = loc_res.localized_text
            audio_output = loc_res.audio_output

        transformation_metadata = {
            "request_id": request_id,
            "source_language": source_lang,
            "target_language": target_lang,
            "target_modality": request.target_modality.value,
            "translation_resilience": translation_resilience_meta,
            "total_localization_latency_ms": round((time.monotonic() - loc_start_time) * 1000, 2),
            "context_metadata": request.context_metadata,
        }

        return ULPUResponseLocalizationResponse(
            request_id=request_id,
            original_response=system_response,
            source_language=source_lang,
            target_language=target_lang,
            localized_response=localized_text,
            confidence=1.0 if source_lang == target_lang else 0.96,
            transformation_metadata=transformation_metadata,
            uncertainty=[],
            audio_output=audio_output,
        )
