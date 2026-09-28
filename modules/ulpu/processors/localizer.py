"""Standard Response Localizer Implementation for ULPU."""

from typing import Optional, Dict, Any
from core.interfaces.ulpu import IResponseLocalizer, ITranslator, ITTSProvider
from core.schemas.ulpu import (
    ResponseLocalizationRequest,
    ResponseLocalizationResponse,
    TranslationRequest,
    TTSRequest,
    InputModality,
)
from core.errors.exceptions import TranslationError, TTSError, ProviderError
from core.logging.logger import get_logger

logger = get_logger("modules.ulpu.processors.localizer")


class StandardResponseLocalizer(IResponseLocalizer):
    """
    Standard Response Localizer taking validated system responses and converting
    them into target farmer language and modality while strictly preserving
    semantic meaning, numbers, units, negation, uncertainty, and formatting structure.
    """

    def __init__(
        self,
        translator: ITranslator,
        tts_provider: Optional[ITTSProvider] = None,
    ) -> None:
        self.translator = translator
        self.tts_provider = tts_provider

    def localize_response(
        self, request: ResponseLocalizationRequest
    ) -> ResponseLocalizationResponse:
        system_response = request.system_response
        source_lang = "en"
        target_lang = request.target_language.lower().strip()
        target_modality = request.target_modality

        logger.info(f"Localizing system response from {source_lang} -> {target_lang} (modality: {target_modality.value})")

        # 1. Translation stage
        if source_lang == target_lang:
            localized_text = system_response
            confidence = 1.0
        else:
            trans_req = TranslationRequest(
                text=system_response,
                source_language=source_lang,
                target_language=target_lang,
                preserve_formatting=True,
            )
            try:
                trans_res = self.translator.translate(trans_req)
                localized_text = trans_res.translated_text
                confidence = trans_res.confidence
            except Exception as e:
                if isinstance(e, (TranslationError, ProviderError)):
                    raise
                raise TranslationError(self.translator.get_provider_name(), source_lang, target_lang, str(e))

        # 2. Audio modality synthesis if requested
        audio_res = None
        if target_modality == InputModality.AUDIO:
            if not self.tts_provider:
                raise TTSError("none", "TTS provider not configured for audio response localization.")
            tts_req = TTSRequest(
                text=localized_text,
                target_language=target_lang,
                voice_id=request.voice_id,
            )
            try:
                audio_res = self.tts_provider.synthesize(tts_req)
            except Exception as e:
                if isinstance(e, (TTSError, ProviderError)):
                    raise
                raise TTSError(self.tts_provider.get_provider_name(), str(e))

        return ResponseLocalizationResponse(
            localized_text=localized_text,
            target_language=target_lang,
            target_modality=target_modality,
            audio_output=audio_res,
        )
