"""ULPU Provider Registry for dynamically managing language processing provider adapters."""

from typing import Dict, Any, Optional
from core.interfaces.ulpu import IProviderRegistry
from core.errors.exceptions import ProviderError, ULPUConfigurationError


class ProviderRegistry(IProviderRegistry):
    """
    Central registry for registering, looking up, and configuring provider adapters.

    Decouples core ULPU language pipeline from concrete external API or model SDK implementations.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, Dict[str, Any]] = {
            "stt": {},
            "translation": {},
            "tts": {},
            "language_detection": {},
            "audio_processing": {},
        }
        self._default_providers: Dict[str, str] = {}

    def register_provider(self, category: str, name: str, provider_instance: Any) -> None:
        """Register a provider instance for a given category."""
        if not category or not name:
            raise ULPUConfigurationError("Category and provider name must not be empty.")

        cat = category.lower().strip()
        name_clean = name.lower().strip()

        if cat not in self._providers:
            self._providers[cat] = {}

        self._providers[cat][name_clean] = provider_instance

        # Set as default if no default exists for this category
        if cat not in self._default_providers:
            self._default_providers[cat] = name_clean

    def set_default_provider(self, category: str, name: str) -> None:
        """Set the default provider name for a category."""
        cat = category.lower().strip()
        name_clean = name.lower().strip()
        if cat not in self._providers or name_clean not in self._providers[cat]:
            raise ProviderError(name_clean, f"Provider '{name_clean}' is not registered under category '{cat}'.")
        self._default_providers[cat] = name_clean

    def get_provider(self, category: str, name: Optional[str] = None) -> Any:
        """Retrieve active or named provider instance for a category."""
        cat = category.lower().strip()
        if cat not in self._providers:
            raise ProviderError(name or "unknown", f"Unknown provider category '{category}'.")

        target_name = name.lower().strip() if name else self._default_providers.get(cat)
        if not target_name:
            raise ProviderError("none", f"No default provider configured for category '{cat}'.")

        if target_name not in self._providers[cat]:
            raise ProviderError(target_name, f"Provider '{target_name}' not found under category '{cat}'.")

        return self._providers[cat][target_name]

    def list_providers(self, category: Optional[str] = None) -> Dict[str, Any]:
        """List registered provider names by category."""
        if category:
            cat = category.lower().strip()
            return dict(self._providers.get(cat, {}))
        return {cat: list(providers.keys()) for cat, providers in self._providers.items()}
