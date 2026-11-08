"""Sensor Adapter Infrastructure for EarthMind Drone Module (Stage D2).

Defines the adapter protocol, registration registry, capability checking,
and reference synthetic adapters. Enables EarthMind to support diverse drone
sensors and manufacturers without changing core ingestion logic.
"""

import abc
import threading
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneDataFormat,
    DroneSensorInputContract,
    SensorCategory,
    SensorMetadataContract,
)
from modules.drone.errors import (
    DroneInvalidArgumentError,
    UnsupportedFormatError,
    UnsupportedSensorError,
)

logger = get_logger("modules.drone.adapters")


@runtime_checkable
class ISensorAdapter(Protocol):
    """Protocol that all drone sensor hardware and format adapters must satisfy."""

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter instance."""
        ...

    @property
    def adapter_version(self) -> str:
        """Adapter implementation version string."""
        ...

    @property
    def supported_category(self) -> SensorCategory:
        """Hardware sensor category handled by this adapter."""
        ...

    @property
    def supported_formats(self) -> List[DroneDataFormat]:
        """List of raw data formats handled by this adapter."""
        ...

    def is_compatible(self, input_data: DroneSensorInputContract, sensor_meta: SensorMetadataContract) -> bool:
        """Check whether this adapter can process the given input and sensor profile."""
        ...

    def is_available(self) -> bool:
        """Check if adapter runtime dependencies and libraries are available."""
        ...

    def parse_header(self, input_data: DroneSensorInputContract) -> Dict[str, Any]:
        """Inspect and parse high-level header metadata without heavy computation."""
        ...


class BaseSensorAdapter(abc.ABC):
    """Abstract base class for drone sensor adapters."""

    def __init__(
        self,
        adapter_id: str,
        adapter_version: str = "1.0.0",
        supported_category: SensorCategory = SensorCategory.OTHER,
        supported_formats: Optional[List[DroneDataFormat]] = None,
    ):
        self._adapter_id = adapter_id
        self._adapter_version = adapter_version
        self._supported_category = supported_category
        self._supported_formats = supported_formats or []

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    @property
    def supported_category(self) -> SensorCategory:
        return self._supported_category

    @property
    def supported_formats(self) -> List[DroneDataFormat]:
        return list(self._supported_formats)

    def is_available(self) -> bool:
        """Default availability check; subclasses override for hardware/SDK dependencies."""
        return True

    def is_compatible(self, input_data: DroneSensorInputContract, sensor_meta: SensorMetadataContract) -> bool:
        """Verify format and category compatibility."""
        if input_data.data_format not in self._supported_formats:
            return False
        if sensor_meta.sensor_category != self._supported_category:
            return False
        return True

    @abc.abstractmethod
    def parse_header(self, input_data: DroneSensorInputContract) -> Dict[str, Any]:
        """Extract header summary and channels."""
        raise NotImplementedError


class SyntheticMultispectralSensorAdapter(BaseSensorAdapter):
    """
    Reference synthetic adapter for multispectral sensor payloads (e.g. GeoTIFF, CSV).
    Used for foundational verification without requiring physical drone hardware.
    """

    def __init__(self, adapter_id: str = "adapter_synthetic_multispectral_v1"):
        super().__init__(
            adapter_id=adapter_id,
            adapter_version="1.0.0",
            supported_category=SensorCategory.MULTISPECTRAL,
            supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.CSV, DroneDataFormat.JSON],
        )

    def parse_header(self, input_data: DroneSensorInputContract) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "detected_channels": ["blue", "green", "red", "nir"],
            "format": input_data.data_format.value,
            "drone_id": input_data.drone_id,
            "sensor_id": input_data.sensor_id,
            "synthetic_mode": True,
        }


class SyntheticThermalSensorAdapter(BaseSensorAdapter):
    """Reference synthetic adapter for thermal sensor payloads."""

    def __init__(self, adapter_id: str = "adapter_synthetic_thermal_v1"):
        super().__init__(
            adapter_id=adapter_id,
            adapter_version="1.0.0",
            supported_category=SensorCategory.THERMAL,
            supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.CSV, DroneDataFormat.JSON],
        )

    def parse_header(self, input_data: DroneSensorInputContract) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "detected_channels": ["thermal_ir"],
            "format": input_data.data_format.value,
            "drone_id": input_data.drone_id,
            "sensor_id": input_data.sensor_id,
            "synthetic_mode": True,
        }


class SensorAdapterRegistry:
    """Registry maintaining registered hardware and format sensor adapters."""

    def __init__(self):
        self._lock = threading.RLock()
        self._adapters: Dict[str, ISensorAdapter] = {}
        # Register reference synthetic adapters
        self.register_adapter(SyntheticMultispectralSensorAdapter())
        self.register_adapter(SyntheticThermalSensorAdapter())

    def register_adapter(self, adapter: ISensorAdapter) -> None:
        """Register a sensor adapter instance."""
        if not adapter.adapter_id:
            raise DroneInvalidArgumentError(
                details="Adapter must have a non-empty adapter_id.",
                operation="register_adapter",
            )
        with self._lock:
            self._adapters[adapter.adapter_id] = adapter
            logger.info(f"Registered drone sensor adapter: {adapter.adapter_id} (category={adapter.supported_category.value})")

    def unregister_adapter(self, adapter_id: str) -> bool:
        """Unregister an adapter by ID."""
        with self._lock:
            if adapter_id in self._adapters:
                del self._adapters[adapter_id]
                logger.info(f"Unregistered sensor adapter: {adapter_id}")
                return True
            return False

    def get_adapter(self, adapter_id: str) -> Optional[ISensorAdapter]:
        """Retrieve an adapter by ID."""
        with self._lock:
            return self._adapters.get(adapter_id)

    def list_adapters(self) -> List[ISensorAdapter]:
        """List all registered adapters."""
        with self._lock:
            return list(self._adapters.values())

    def find_adapter(
        self,
        input_data: DroneSensorInputContract,
        sensor_meta: SensorMetadataContract,
    ) -> ISensorAdapter:
        """Find the most compatible registered adapter for an input package and sensor manifest."""
        with self._lock:
            for adapter in self._adapters.values():
                if not adapter.is_available():
                    continue
                if adapter.is_compatible(input_data, sensor_meta):
                    return adapter

        # If no adapter matched:
        raise UnsupportedSensorError(
            sensor_id=sensor_meta.sensor_id,
            details=f"No compatible adapter registered for sensor category '{sensor_meta.sensor_category.value}' and format '{input_data.data_format.value}'."
        )

    def health_check(self) -> Dict[str, Any]:
        """Check availability of registered adapters."""
        with self._lock:
            status_map = {
                aid: {
                    "available": a.is_available(),
                    "category": a.supported_category.value,
                    "version": a.adapter_version,
                    "formats": [f.value for f in a.supported_formats],
                }
                for aid, a in self._adapters.items()
            }
            return {
                "total_adapters": len(self._adapters),
                "adapters": status_map,
            }
