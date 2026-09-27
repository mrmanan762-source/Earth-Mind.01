"""Central Language Capability Registry for EarthMind ULPU."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from core.schemas.ulpu import ScriptType
from core.errors.exceptions import UnsupportedLanguageError, ULPUConfigurationError


class LanguageCapability(BaseModel):
    """Container for language capability parameters and supported processing modalities."""
    language_code: str = Field(..., description="ISO 639-1 or 639-3 language code (e.g., 'hi', 'en')")
    language_name: str = Field(..., description="Human-readable language name (e.g., 'Hindi', 'English')")
    script: ScriptType = Field(default=ScriptType.LATIN, description="Primary script used for this language")
    stt_support: bool = Field(default=True, description="Speech-to-Text capability support status")
    translation_support: bool = Field(default=True, description="Translation capability support status")
    tts_support: bool = Field(default=True, description="Text-to-Speech capability support status")
    code_mix_support: bool = Field(default=False, description="Code-mixed text (e.g. Hinglish) capability support status")
    enabled: bool = Field(default=True, description="Whether this language capability is active")


class LanguageRegistry:
    """
    Central registry for managing supported language capabilities in EarthMind.

    Provides registration, capability lookup, and querying without hardcoding
    language logic inside pipeline components.
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, LanguageCapability] = {}
        self._populate_default_languages()

    def _populate_default_languages(self) -> None:
        """Populate initial set of Indic languages and English."""
        defaults = [
            LanguageCapability(
                language_code="en",
                language_name="English",
                script=ScriptType.LATIN,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=True,
                enabled=True,
            ),
            LanguageCapability(
                language_code="hi",
                language_name="Hindi",
                script=ScriptType.DEVANAGARI,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=True,
                enabled=True,
            ),
            LanguageCapability(
                language_code="mr",
                language_name="Marathi",
                script=ScriptType.DEVANAGARI,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="pa",
                language_name="Punjabi",
                script=ScriptType.GURMUKHI,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="te",
                language_name="Telugu",
                script=ScriptType.TELUGU,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="ta",
                language_name="Tamil",
                script=ScriptType.TAMIL,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="gu",
                language_name="Gujarati",
                script=ScriptType.GUJARATI,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="bn",
                language_name="Bengali",
                script=ScriptType.BENGALI,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="kn",
                language_name="Kannada",
                script=ScriptType.KANNADA,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
            LanguageCapability(
                language_code="ml",
                language_name="Malayalam",
                script=ScriptType.MALAYALAM,
                stt_support=True,
                translation_support=True,
                tts_support=True,
                code_mix_support=False,
                enabled=True,
            ),
        ]
        for cap in defaults:
            self.register_language(cap)

    def register_language(self, capability: LanguageCapability) -> None:
        """Register or update a language capability."""
        if not capability.language_code or not capability.language_code.strip():
            raise ULPUConfigurationError("Language code cannot be empty.")
        code = capability.language_code.lower().strip()
        self._capabilities[code] = capability

    def get_language(self, language_code: str) -> LanguageCapability:
        """Retrieve language capability details for a given ISO language code."""
        if not language_code:
            raise UnsupportedLanguageError("empty", "lookup")
        code = language_code.lower().strip()
        if code not in self._capabilities:
            raise UnsupportedLanguageError(code, "lookup")
        return self._capabilities[code]

    def is_supported(self, language_code: str, capability: Optional[str] = None) -> bool:
        """Check if language code is registered, enabled, and supports specific capability."""
        if not language_code:
            return False
        code = language_code.lower().strip()
        if code not in self._capabilities:
            return False
        lang = self._capabilities[code]
        if not lang.enabled:
            return False

        if capability is None:
            return True
        cap_map = {
            "stt": lang.stt_support,
            "translation": lang.translation_support,
            "tts": lang.tts_support,
            "code_mix": lang.code_mix_support,
        }
        return cap_map.get(capability.lower(), False)

    def list_supported_languages(self, enabled_only: bool = True) -> List[LanguageCapability]:
        """List all registered language capabilities."""
        if enabled_only:
            return [cap for cap in self._capabilities.values() if cap.enabled]
        return list(self._capabilities.values())
