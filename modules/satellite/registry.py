"""Satellite Data Provider Registry for EarthMind Satellite Module (Stage D2).

Implements ISatelliteProviderRegistry protocol:
- Register provider manifests
- Retrieve providers by stable provider ID
- List registered providers with status filtering
- Enable or disable providers
- Validate provider registration and prevent duplicates
- Check provider availability and capabilities
"""

import threading
from typing import Dict, List, Optional

from core.interfaces.satellite import ISatelliteProviderRegistry
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteProvider,
    SatelliteProviderStatus,
)
from modules.satellite.capabilities import ProviderCapabilityManager
from modules.satellite.errors import (
    SatelliteInvalidArgumentError,
    SatelliteProviderError,
)

logger = get_logger("modules.satellite.registry")


class SatelliteProviderRegistry(ISatelliteProviderRegistry):
    """Central registry of approved satellite data providers."""

    def __init__(self, capability_manager: Optional[ProviderCapabilityManager] = None):
        self._lock = threading.RLock()
        self._providers: Dict[str, SatelliteProvider] = {}
        self._capability_manager = capability_manager or ProviderCapabilityManager()

    @property
    def capability_manager(self) -> ProviderCapabilityManager:
        return self._capability_manager

    def register_provider(self, provider: SatelliteProvider, allow_overwrite: bool = False) -> bool:
        """Register or update a satellite data provider configuration."""
        with self._lock:
            pid = provider.provider_id
            if not pid or not pid.strip():
                raise SatelliteInvalidArgumentError(
                    details="Cannot register satellite provider with empty provider_id.",
                    operation="register_provider",
                )

            if pid in self._providers and not allow_overwrite:
                err_msg = f"Satellite provider with ID '{pid}' is already registered. Duplicate IDs prohibited."
                logger.error(err_msg)
                raise SatelliteProviderError(
                    details=err_msg,
                    provider_id=pid,
                    operation="register_provider",
                )

            if not provider.supported_constellations:
                raise SatelliteInvalidArgumentError(
                    details=f"Provider '{pid}' must declare at least one supported constellation.",
                    operation="register_provider",
                )
            if not provider.supported_sensor_types:
                raise SatelliteInvalidArgumentError(
                    details=f"Provider '{pid}' must declare at least one supported sensor type.",
                    operation="register_provider",
                )
            if not provider.supported_formats:
                raise SatelliteInvalidArgumentError(
                    details=f"Provider '{pid}' must declare at least one supported data format.",
                    operation="register_provider",
                )
            if not provider.attribution_text or not provider.attribution_text.strip():
                raise SatelliteInvalidArgumentError(
                    details=f"Provider '{pid}' must declare mandatory attribution_text.",
                    operation="register_provider",
                )

            self._providers[pid] = provider
            self._capability_manager.register_from_provider_manifest(provider)
            logger.info(f"Successfully registered satellite provider '{pid}' ({provider.provider_name}) with status {provider.status.value}.")
            return True

    def get_provider(self, provider_id: str) -> Optional[SatelliteProvider]:
        """Retrieve provider configuration by unique ID."""
        with self._lock:
            return self._providers.get(provider_id)

    def list_providers(self, status: Optional[str] = None) -> List[SatelliteProvider]:
        """List registered providers, optionally filtered by status."""
        with self._lock:
            if status is None:
                return list(self._providers.values())

            status_upper = status.upper().strip()
            return [p for p in self._providers.values() if p.status.value == status_upper]

    def is_provider_available(self, provider_id: str) -> bool:
        """Check if provider is registered and active."""
        with self._lock:
            prov = self._providers.get(provider_id)
            if not prov:
                return False
            return prov.status == SatelliteProviderStatus.ACTIVE

    def enable_provider(self, provider_id: str) -> bool:
        """Enable a registered provider by setting its status to ACTIVE."""
        with self._lock:
            prov = self._providers.get(provider_id)
            if not prov:
                raise SatelliteProviderError(
                    details=f"Cannot enable unregistered provider '{provider_id}'.",
                    provider_id=provider_id,
                    operation="enable_provider",
                )
            prov_dict = prov.model_dump()
            prov_dict["status"] = SatelliteProviderStatus.ACTIVE
            updated = SatelliteProvider(**prov_dict)
            self._providers[provider_id] = updated
            logger.info(f"Provider '{provider_id}' enabled (status=ACTIVE).")
            return True

    def disable_provider(self, provider_id: str, reason: str = "Administrator requested") -> bool:
        """Disable a registered provider by setting its status to UNAVAILABLE."""
        with self._lock:
            prov = self._providers.get(provider_id)
            if not prov:
                raise SatelliteProviderError(
                    details=f"Cannot disable unregistered provider '{provider_id}'.",
                    provider_id=provider_id,
                    operation="disable_provider",
                )
            prov_dict = prov.model_dump()
            prov_dict["status"] = SatelliteProviderStatus.UNAVAILABLE
            updated = SatelliteProvider(**prov_dict)
            self._providers[provider_id] = updated
            logger.info(f"Provider '{provider_id}' disabled (reason: {reason}).")
            return True

    def unregister_provider(self, provider_id: str) -> bool:
        """Unregister a provider from registry."""
        with self._lock:
            if provider_id in self._providers:
                del self._providers[provider_id]
                logger.info(f"Unregistered satellite provider '{provider_id}'.")
                return True
            return False

    def clear(self) -> None:
        """Clear all registered providers (used in test isolation)."""
        with self._lock:
            self._providers.clear()
