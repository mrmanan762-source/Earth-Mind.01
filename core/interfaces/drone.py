"""Interface definitions for EarthMind Drone Module (Stage D1).

Defines protocol interfaces for all 18 logical components and adapters:
1. IDroneDataGateway
2. ISensorRegistry
3. IDataFormatDetector
4. IRawDataProcessor
5. IDataQualityValidator
6. ICalibrationNormalizer
7. IGeospatialProcessor
8. ITemporalProcessor
9. ISpectralNumericalAnalyzer
10. IIndicatorExtractor
11. IMultiSensorFusionEngine
12. IUncertaintyAssessor
13. ISensorEvidenceBuilder
14. ISensorEvidenceValidator
15. ISarvamDroneIntegration
16. IProvenanceManager
17. IDroneStorageAdapter
18. IDroneDiagnostics
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.drone import (
    AgriculturalIndicatorContract,
    DroneCameraRoutingContract,
    DroneDataFormat,
    DroneSensorInputContract,
    EarthMindDroneSensorEvidence,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorCategory,
    SensorMetadataContract,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)


@runtime_checkable
class IDroneDataGateway(Protocol):
    """Component 1: Ingestion gateway interface."""

    def ingest_sensor_data(self, request: DroneSensorInputContract) -> Dict[str, Any]:
        """Ingest incoming raw sensor payload and assign trace metadata."""
        ...


@runtime_checkable
class ISensorRegistry(Protocol):
    """Component 2: Sensor hardware capability registry."""

    def register_sensor(self, metadata: SensorMetadataContract) -> bool:
        """Register or update a sensor hardware capability manifest."""
        ...

    def get_sensor(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve sensor capability manifest by sensor ID."""
        ...

    def is_supported(self, sensor_id: str, measurement: str) -> bool:
        """Check if a sensor supports a given measurement channel."""
        ...


@runtime_checkable
class IDataFormatDetector(Protocol):
    """Component 3: Raw format sniffing engine."""

    def detect_format(self, payload_sample: bytes, file_name: Optional[str] = None) -> DroneDataFormat:
        """Detect raw data format from sample bytes and optional filename."""
        ...


@runtime_checkable
class IRawDataProcessor(Protocol):
    """Component 4: Raw payload parser."""

    def parse_raw_data(self, payload: Any, data_format: DroneDataFormat) -> Dict[str, Any]:
        """Parse raw file or binary buffer into structured channel matrices."""
        ...


@runtime_checkable
class IDataQualityValidator(Protocol):
    """Component 5: Measurement sanity and physical plausibility validator."""

    def validate_quality(self, measurements: List[Dict[str, Any]]) -> QualityStatus:
        """Validate physical limits and integrity of extracted measurements."""
        ...


@runtime_checkable
class ICalibrationNormalizer(Protocol):
    """Component 6: Radiometric calibration and unit normalization engine."""

    def normalize_measurement(
        self,
        raw_measurement: Dict[str, Any],
        calibration_metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedSensorMeasurementContract:
        """Apply calibration parameters and normalize units to scientific standard."""
        ...


@runtime_checkable
class IGeospatialProcessor(Protocol):
    """Component 7: Geospatial coordinates and field alignment engine."""

    def process_spatial(
        self,
        raw_coords: Optional[Dict[str, Any]],
        field_id: Optional[str] = None,
    ) -> SpatialCoverage:
        """Process GPS coordinates, bounding boxes, and field boundary intersection."""
        ...


@runtime_checkable
class ITemporalProcessor(Protocol):
    """Component 8: Temporal coverage and sampling normalization."""

    def process_temporal(
        self,
        collection_timestamp: str,
        end_timestamp: Optional[str] = None,
    ) -> TemporalCoverage:
        """Validate UTC timestamps, mission durations, and sampling intervals."""
        ...


@runtime_checkable
class ISpectralNumericalAnalyzer(Protocol):
    """Component 9: Numerical statistics and spectral band processing."""

    def analyze_bands(
        self,
        band_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute band summary statistics, histograms, and spectral reflectance arrays."""
        ...


@runtime_checkable
class IIndicatorExtractor(Protocol):
    """Component 10: Agricultural indicator extraction engine."""

    def extract_indicator(
        self,
        indicator_name: str,
        measurements: List[ProcessedSensorMeasurementContract],
        sensor_metadata: Optional[SensorMetadataContract] = None,
    ) -> AgriculturalIndicatorContract:
        """Extract a single standardized agricultural indicator (NDVI, NDRE, etc.)."""
        ...

    def extract_available_indicators(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        sensor_metadata: Optional[SensorMetadataContract] = None,
    ) -> List[AgriculturalIndicatorContract]:
        """Extract all possible indicators supported by present measurements."""
        ...


@runtime_checkable
class IMultiSensorFusionEngine(Protocol):
    """Component 11: Multi-sensor co-registration and fusion engine."""

    def fuse_sensors(
        self,
        sensor_streams: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Align and fuse concurrent sensor streams from the same drone mission."""
        ...


@runtime_checkable
class IUncertaintyAssessor(Protocol):
    """Component 12: Multi-dimensional uncertainty and confidence assessor."""

    def assess_uncertainty(
        self,
        quality_status: QualityStatus,
        calibration_present: bool,
        has_spatial: bool,
        has_temporal: bool,
    ) -> Dict[str, Any]:
        """Assess transparent confidence dimensions across quality signals."""
        ...


@runtime_checkable
class ISensorEvidenceBuilder(Protocol):
    """Component 13: Sensor evidence synthesis engine."""

    def build_evidence(
        self,
        input_data: DroneSensorInputContract,
        measurements: List[ProcessedSensorMeasurementContract],
        indicators: List[AgriculturalIndicatorContract],
        spatial: SpatialCoverage,
        temporal: TemporalCoverage,
    ) -> EarthMindDroneSensorEvidence:
        """Assemble the canonical EarthMindDroneSensorEvidence artifact."""
        ...


@runtime_checkable
class ISensorEvidenceValidator(Protocol):
    """Component 14: Evidence validation gate."""

    def validate_evidence(self, evidence: EarthMindDroneSensorEvidence) -> bool:
        """Validate candidate sensor evidence against schema v1.0 constraints."""
        ...


@runtime_checkable
class ISarvamDroneIntegration(Protocol):
    """Component 15: Bridge interface for B2 Context Manager and Sarvam-105B."""

    def format_for_context(self, evidence: EarthMindDroneSensorEvidence) -> Any:
        """Transform validated evidence into B2-compliant ContextItem."""
        ...


@runtime_checkable
class IProvenanceManager(Protocol):
    """Component 16: End-to-end lineage and hash tracking manager."""

    def record_provenance(
        self,
        source_id: str,
        transformation_name: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Record a transformation step in the measurement lineage."""
        ...


@runtime_checkable
class IDroneStorageAdapter(Protocol):
    """Component 17: Storage adapter abstraction for persistence."""

    def store_evidence(self, evidence: EarthMindDroneSensorEvidence) -> str:
        """Persist validated evidence and return storage identifier."""
        ...

    def get_evidence(self, evidence_id: str) -> Optional[EarthMindDroneSensorEvidence]:
        """Retrieve stored evidence by ID."""
        ...

    def store_sensor_profile(self, profile: SensorMetadataContract) -> bool:
        """Persist a sensor hardware capability manifest."""
        ...

    def get_sensor_profile(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve a sensor profile by ID."""
        ...


@runtime_checkable
class IDroneDiagnostics(Protocol):
    """Component 18: Operational telemetry, health, and metrics."""

    def get_health_status(self) -> Dict[str, Any]:
        """Return operational health status dictionary."""
        ...

    def record_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a telemetry or diagnostic metric."""
        ...
