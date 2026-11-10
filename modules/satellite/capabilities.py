"""Provider Capability Management for EarthMind Satellite Intelligence Module (Stage D2).

Represents and validates satellite data provider capabilities across:
- Optical multispectral imagery
- Optical hyperspectral imagery
- Synthetic Aperture Radar (SAR)
- Thermal infrared
- Altimeter / numerical datasets
- Atmospheric sounder datasets
- Geospatial metadata and reprojection
- Historical and temporal observation coverage
"""

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataFormat,
    SatelliteProvider,
    SatelliteSensorType,
)

logger = get_logger("modules.satellite.capabilities")


class ProviderCapabilityProfile(BaseModel):
    """Granular capability profile declared by a satellite provider adapter."""
    provider_id: str = Field(..., description="Unique provider ID")
    supported_sensor_types: List[SatelliteSensorType] = Field(default_factory=list)
    supported_constellations: List[str] = Field(default_factory=list)
    supported_formats: List[SatelliteDataFormat] = Field(default_factory=list)
    supports_optical: bool = Field(False, description="Supports optical multispectral/hyperspectral imagery")
    supports_sar: bool = Field(False, description="Supports Synthetic Aperture Radar imagery")
    supports_thermal: bool = Field(False, description="Supports Thermal infrared imagery")
    supports_numerical: bool = Field(False, description="Supports numerical or agroclimatology satellite datasets")
    supports_historical: bool = Field(True, description="Supports querying historical archives")
    temporal_coverage_start: Optional[str] = Field(None, description="Earliest archive year or ISO date")
    max_spatial_resolution_meters: Optional[float] = Field(None, description="Best spatial resolution available")


class ProviderCapabilityManager:
    """Manages provider capability discovery, lookup, and validation."""

    def __init__(self):
        self._profiles: Dict[str, ProviderCapabilityProfile] = {}

    def register_profile(self, profile: ProviderCapabilityProfile) -> None:
        """Register or update a provider capability profile."""
        self._profiles[profile.provider_id] = profile
        logger.debug(f"Registered capability profile for provider '{profile.provider_id}'")

    def register_from_provider_manifest(self, provider: SatelliteProvider) -> ProviderCapabilityProfile:
        """Derive and register a capability profile from a SatelliteProvider manifest."""
        supports_optical = any(
            st in (SatelliteSensorType.OPTICAL_MULTISPECTRAL, SatelliteSensorType.OPTICAL_HYPERSPECTRAL)
            for st in provider.supported_sensor_types
        )
        supports_sar = SatelliteSensorType.SYNTHETIC_APERTURE_RADAR in provider.supported_sensor_types
        supports_thermal = SatelliteSensorType.THERMAL_INFRARED in provider.supported_sensor_types
        supports_numerical = any(
            st in (SatelliteSensorType.ALTIMETER, SatelliteSensorType.RADIOMETER, SatelliteSensorType.ATMOSPHERIC_SOUNDER)
            for st in provider.supported_sensor_types
        )

        profile = ProviderCapabilityProfile(
            provider_id=provider.provider_id,
            supported_sensor_types=provider.supported_sensor_types,
            supported_constellations=provider.supported_constellations,
            supported_formats=provider.supported_formats,
            supports_optical=supports_optical,
            supports_sar=supports_sar,
            supports_thermal=supports_thermal,
            supports_numerical=supports_numerical,
            supports_historical=True,
        )
        self.register_profile(profile)
        return profile

    def get_profile(self, provider_id: str) -> Optional[ProviderCapabilityProfile]:
        """Retrieve capability profile for a provider."""
        return self._profiles.get(provider_id)

    def supports_sensor_type(self, provider_id: str, sensor_type: SatelliteSensorType) -> bool:
        """Check if provider supports a specific sensor type."""
        profile = self._profiles.get(provider_id)
        if not profile:
            return False
        return sensor_type in profile.supported_sensor_types

    def supports_constellation(self, provider_id: str, constellation: str) -> bool:
        """Check if provider supports a specific satellite constellation/mission."""
        profile = self._profiles.get(provider_id)
        if not profile:
            return False
        c_lower = constellation.lower().strip()
        return any(c_lower in sc.lower() or sc.lower() in c_lower for sc in profile.supported_constellations)

    def supports_format(self, provider_id: str, data_format: SatelliteDataFormat) -> bool:
        """Check if provider supports a specific data format."""
        profile = self._profiles.get(provider_id)
        if not profile:
            return False
        return data_format in profile.supported_formats

    def list_capable_providers(
        self,
        sensor_type: Optional[SatelliteSensorType] = None,
        constellation: Optional[str] = None,
        data_format: Optional[SatelliteDataFormat] = None,
    ) -> List[str]:
        """List provider IDs satisfying all given capability filters."""
        matching = []
        for pid, profile in self._profiles.items():
            if sensor_type and sensor_type not in profile.supported_sensor_types:
                continue
            if constellation and not self.supports_constellation(pid, constellation):
                continue
            if data_format and data_format not in profile.supported_formats:
                continue
            matching.append(pid)
        return sorted(matching)
