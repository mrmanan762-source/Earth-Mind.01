"""DroneService for EarthMind Drone Module (Stage D2: Core Foundation).

Central coordinator and service facade wiring together Gateway, Registry,
Adapters, Formats, Storage, Diagnostics, and Camera Router.
"""

from typing import Any, Dict, List, Optional, Union

from core.config.settings import DroneConfig, settings
from core.interfaces.drone import (
    IDroneDataGateway,
    IDroneDiagnostics,
    IDroneStorageAdapter,
    ISensorRegistry,
)
from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneCameraRoutingContract,
    DroneIngestionResult,
    DroneSensorInputContract,
    SensorCategory,
    SensorMetadataContract,
)
from modules.drone.adapters import SensorAdapterRegistry
from modules.drone.camera_router import CameraDataRouter
from modules.drone.diagnostics import DroneDiagnostics
from modules.drone.formats import DataFormatRegistry
from modules.drone.gateway import DroneDataGateway
from modules.drone.lifecycle import IngestionLifecycleTracker
from modules.drone.processing import DroneProcessingEngine
from modules.drone.geospatial import GeospatialProcessor
from modules.drone.temporal import TemporalProcessor
from modules.drone.spatiotemporal import SpatioTemporalAssociator
from modules.drone.spectral import SpectralAnalysisEngine
from modules.drone.numerical import NumericalAnalysisEngine
from modules.drone.indicators import IndicatorExtractionEngine
from modules.drone.fusion import MultiSensorFusionEngine
from modules.drone.uncertainty import UncertaintyAssessor
from modules.drone.evidence_builder import SensorEvidenceBuilder
from modules.drone.evidence_validator import SensorEvidenceValidator, EvidenceValidationResult
from modules.drone.sarvam_integration import SarvamDroneIntegration, DroneContextProvider
from modules.drone.registry import SensorRegistry
from modules.drone.storage import InMemoryDroneStorageAdapter
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    DroneCalibrationInfo,
    DroneQualityAssessment,
    DroneUncertaintyAssessment,
    EarthMindDroneSensorEvidence,
    FieldBoundaryContract,
    FusedSensorMeasurementContract,
    MultiSensorFusionReportContract,
    NumericalAnalysisResultContract,
    ProcessedSensorMeasurementContract,
    SpatialBoundingBox,
    SpatialCoverage,
    SpatioTemporalAssociationContract,
    SpectralAnalysisResultContract,
    TemporalCoverage,
)

logger = get_logger("modules.drone.service")


class DroneService:
    """Core Drone Service coordinating foundational and processing drone components."""

    def __init__(
        self,
        config: Optional[DroneConfig] = None,
        storage_adapter: Optional[IDroneStorageAdapter] = None,
        vision_service: Optional[Any] = None,
        processing_engine: Optional[DroneProcessingEngine] = None,
    ):
        self._config = config or getattr(settings, "drone", DroneConfig())
        self._storage_adapter = storage_adapter or InMemoryDroneStorageAdapter()
        self._lifecycle_tracker = IngestionLifecycleTracker()
        self._sensor_registry = SensorRegistry(storage_adapter=self._storage_adapter)
        self._format_registry = DataFormatRegistry()
        self._adapter_registry = SensorAdapterRegistry()
        self._diagnostics = DroneDiagnostics()
        self._camera_router = CameraDataRouter(vision_service=vision_service)
        self._processing_engine = processing_engine or DroneProcessingEngine()
        self._geospatial_processor = GeospatialProcessor()
        self._temporal_processor = TemporalProcessor()
        self._spatiotemporal_associator = SpatioTemporalAssociator(
            geospatial_processor=self._geospatial_processor,
            temporal_processor=self._temporal_processor,
        )
        self._spectral_engine = SpectralAnalysisEngine()
        self._numerical_engine = NumericalAnalysisEngine()
        self._indicator_engine = IndicatorExtractionEngine(spectral_engine=self._spectral_engine)
        self._fusion_engine = MultiSensorFusionEngine()
        self._uncertainty_assessor = UncertaintyAssessor()
        self._evidence_builder = SensorEvidenceBuilder(uncertainty_assessor=self._uncertainty_assessor)
        self._evidence_validator = SensorEvidenceValidator()
        self._sarvam_integration = SarvamDroneIntegration(validator=self._evidence_validator)

        self._gateway = DroneDataGateway(
            sensor_registry=self._sensor_registry,
            format_registry=self._format_registry,
            adapter_registry=self._adapter_registry,
            lifecycle_tracker=self._lifecycle_tracker,
            max_payload_size_bytes=self._config.max_payload_size_bytes,
            gateway_enabled=self._config.gateway_enabled and self._config.enabled,
        )

    # ------------------------------------------------------------------------
    # Properties & Component Access
    # ------------------------------------------------------------------------
    @property
    def config(self) -> DroneConfig:
        return self._config

    @property
    def gateway(self) -> DroneDataGateway:
        return self._gateway

    @property
    def registry(self) -> SensorRegistry:
        return self._sensor_registry

    @property
    def format_registry(self) -> DataFormatRegistry:
        return self._format_registry

    @property
    def adapter_registry(self) -> SensorAdapterRegistry:
        return self._adapter_registry

    @property
    def storage(self) -> IDroneStorageAdapter:
        return self._storage_adapter

    @property
    def diagnostics(self) -> DroneDiagnostics:
        return self._diagnostics

    @property
    def camera_router(self) -> CameraDataRouter:
        return self._camera_router

    @property
    def processing_engine(self) -> DroneProcessingEngine:
        return self._processing_engine

    @property
    def geospatial_processor(self) -> GeospatialProcessor:
        return self._geospatial_processor

    @property
    def temporal_processor(self) -> TemporalProcessor:
        return self._temporal_processor

    @property
    def spatiotemporal_associator(self) -> SpatioTemporalAssociator:
        return self._spatiotemporal_associator

    @property
    def spectral_engine(self) -> SpectralAnalysisEngine:
        return self._spectral_engine

    @property
    def numerical_engine(self) -> NumericalAnalysisEngine:
        return self._numerical_engine

    @property
    def indicator_engine(self) -> IndicatorExtractionEngine:
        return self._indicator_engine

    @property
    def fusion_engine(self) -> MultiSensorFusionEngine:
        return self._fusion_engine

    @property
    def uncertainty_assessor(self) -> UncertaintyAssessor:
        return self._uncertainty_assessor

    @property
    def evidence_builder(self) -> SensorEvidenceBuilder:
        return self._evidence_builder

    @property
    def evidence_validator(self) -> SensorEvidenceValidator:
        return self._evidence_validator

    @property
    def sarvam_integration(self) -> SarvamDroneIntegration:
        return self._sarvam_integration

    # ------------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------------
    def process_sensor_data(
        self, input_data: DroneSensorInputContract
    ) -> Dict[str, Any]:
        """Process raw drone sensor package into normalized ProcessedSensorMeasurementContracts."""
        self._diagnostics.record_metric("processings_total", 1.0)
        sensor_profile = self._sensor_registry.get_sensor(input_data.sensor_id)
        measurements, quality_report, cal_assessment = self._processing_engine.process_sensor_input(
            input_contract=input_data,
            sensor_profile=sensor_profile,
        )
        self._diagnostics.record_metric("measurements_processed", float(len(measurements)))

        return {
            "sensor_id": input_data.sensor_id,
            "drone_id": input_data.drone_id,
            "measurements_count": len(measurements),
            "quality_status": quality_report.overall_status.value,
            "calibration_status": cal_assessment.status.value,
            "measurements": [m.model_dump() for m in measurements],
            "quality_report": quality_report.model_dump(),
            "calibration_assessment": cal_assessment.model_dump(),
        }

    # ------------------------------------------------------------------------
    # Stage D4: Geospatial & Temporal Operations
    # ------------------------------------------------------------------------
    def associate_spatiotemporal(
        self,
        drone_id: str,
        sensor_id: str,
        measurements: List[ProcessedSensorMeasurementContract],
        field_id: Optional[str] = None,
        field_boundary: Optional[Union[FieldBoundaryContract, Dict[str, Any]]] = None,
        declared_crs: Optional[str] = None,
        gap_threshold_seconds: Optional[float] = None,
    ) -> SpatioTemporalAssociationContract:
        """Associate processed sensor measurements with validated geospatial & temporal context."""
        self._diagnostics.record_metric("spatiotemporal_associations_total", 1.0)
        association = self._spatiotemporal_associator.associate(
            drone_id=drone_id,
            sensor_id=sensor_id,
            measurements=measurements,
            field_id=field_id,
            field_boundary=field_boundary,
            declared_crs=declared_crs,
            gap_threshold_seconds=gap_threshold_seconds,
        )
        return association

    # ------------------------------------------------------------------------
    # Stage D5: Spectral, Numerical, Indicators & Fusion Operations
    # ------------------------------------------------------------------------
    def analyze_spectral(self, band_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze spectral band inputs and compute summary statistics."""
        self._diagnostics.record_metric("spectral_analyses_total", 1.0)
        return self._spectral_engine.analyze_bands(band_data)

    def process_numerical(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        channel_name: str,
    ) -> NumericalAnalysisResultContract:
        """Process numerical channel measurements and calculate summary statistics."""
        self._diagnostics.record_metric("numerical_analyses_total", 1.0)
        return self._numerical_engine.process_measurements(measurements, channel_name=channel_name)

    def process_thermal_summary(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        channel_name: str = "thermal_ir",
    ) -> NumericalAnalysisResultContract:
        """Process thermal IR measurements preserving units and range checks."""
        self._diagnostics.record_metric("thermal_analyses_total", 1.0)
        return self._numerical_engine.process_thermal_summary(measurements, channel_name=channel_name)

    def extract_indicator(
        self,
        indicator_name: str,
        measurements: List[ProcessedSensorMeasurementContract],
    ) -> AgriculturalIndicatorContract:
        """Extract a single agricultural vegetation/water indicator (e.g. NDVI, NDRE, NDWI)."""
        self._diagnostics.record_metric("indicator_extractions_total", 1.0)
        sensor_meta = None
        if measurements:
            sensor_meta = self._sensor_registry.get_sensor(measurements[0].source_sensor)
        return self._indicator_engine.extract_indicator(
            indicator_name=indicator_name,
            measurements=measurements,
            sensor_metadata=sensor_meta,
        )

    def extract_available_indicators(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
    ) -> List[AgriculturalIndicatorContract]:
        """Extract all possible agricultural indicators supported by the present measurements."""
        self._diagnostics.record_metric("available_indicators_total", 1.0)
        sensor_meta = None
        if measurements:
            sensor_meta = self._sensor_registry.get_sensor(measurements[0].source_sensor)
        return self._indicator_engine.extract_available_indicators(
            measurements=measurements,
            sensor_metadata=sensor_meta,
        )

    def fuse_sensor_data(
        self,
        sensor_streams: Dict[str, List[ProcessedSensorMeasurementContract]],
        drone_id: str = "drone_default",
        field_id: Optional[str] = None,
    ) -> MultiSensorFusionReportContract:
        """Spatially and temporally fuse concurrent multi-sensor streams."""
        self._diagnostics.record_metric("sensor_fusions_total", 1.0)
        return self._fusion_engine.fuse_measurements(
            sensor_streams=sensor_streams,
            drone_id=drone_id,
            field_id=field_id,
        )

    # ------------------------------------------------------------------------
    # Stage D6: Uncertainty, Evidence & Sarvam Integration Operations
    # ------------------------------------------------------------------------
    def assess_uncertainty(
        self,
        quality_assessment: DroneQualityAssessment,
        calibration_status: Any,
        panel_used: bool,
        sun_sensor_used: bool,
        spatial_coverage: Optional[SpatialCoverage] = None,
        temporal_coverage: Optional[TemporalCoverage] = None,
        measurements_count: int = 0,
        indicators_count: int = 0,
        operational_warnings: Optional[List[str]] = None,
    ) -> DroneUncertaintyAssessment:
        """Assess multi-dimensional uncertainty without fabricated confidence."""
        self._diagnostics.record_metric("uncertainty_assessments_total", 1.0)
        return self._uncertainty_assessor.assess_comprehensive_uncertainty(
            quality_assessment=quality_assessment,
            calibration_status=calibration_status,
            panel_used=panel_used,
            sun_sensor_used=sun_sensor_used,
            spatial_coverage=spatial_coverage,
            temporal_coverage=temporal_coverage,
            measurements_count=measurements_count,
            indicators_count=indicators_count,
            operational_warnings=operational_warnings,
        )

    def build_evidence(
        self,
        input_data: DroneSensorInputContract,
        measurements: List[ProcessedSensorMeasurementContract],
        indicators: List[AgriculturalIndicatorContract],
        spatial: SpatialCoverage,
        temporal: TemporalCoverage,
        quality: Optional[DroneQualityAssessment] = None,
        uncertainty: Optional[DroneUncertaintyAssessment] = None,
        calibration: Optional[DroneCalibrationInfo] = None,
        warnings: Optional[List[str]] = None,
        limitations: Optional[List[str]] = None,
        mission_id: Optional[str] = None,
        crop: Optional[str] = None,
    ) -> EarthMindDroneSensorEvidence:
        """Build canonical EarthMindDroneSensorEvidence packet."""
        self._diagnostics.record_metric("evidence_builds_total", 1.0)
        evidence = self._evidence_builder.build_evidence(
            input_data=input_data,
            measurements=measurements,
            indicators=indicators,
            spatial=spatial,
            temporal=temporal,
            quality=quality,
            uncertainty=uncertainty,
            calibration=calibration,
            warnings=warnings,
            limitations=limitations,
            mission_id=mission_id,
            crop=crop,
        )
        return evidence

    def validate_evidence(
        self, evidence: EarthMindDroneSensorEvidence, strict: bool = False
    ) -> EvidenceValidationResult:
        """Validate candidate sensor evidence packet."""
        self._diagnostics.record_metric("evidence_validations_total", 1.0)
        if strict:
            return self._evidence_validator.validate_or_raise(evidence)
        return self._evidence_validator.evaluate(evidence)

    def deliver_evidence_to_context(
        self,
        evidence: EarthMindDroneSensorEvidence,
        context_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Deliver validated sensor evidence to B2 Context Manager."""
        self._diagnostics.record_metric("sarvam_deliveries_total", 1.0)
        return self._sarvam_integration.deliver_to_context_manager(
            evidence=evidence,
            context_manager=context_manager,
        )

    # ------------------------------------------------------------------------
    # Ingestion Operations
    # ------------------------------------------------------------------------
    def ingest_sensor_data(self, input_data: DroneSensorInputContract) -> DroneIngestionResult:
        """Ingest incoming raw drone sensor package."""
        self._diagnostics.record_metric("ingestions_total", 1.0)
        result = self._gateway.process_ingestion(input_data)

        if result.accepted:
            self._diagnostics.record_metric("ingestions_accepted", 1.0)
        else:
            if result.error and result.error.error_code == "INTERNAL_ERROR":
                self._diagnostics.record_metric("ingestions_failed", 1.0)
            else:
                self._diagnostics.record_metric("ingestions_rejected", 1.0)

            if result.error:
                self._diagnostics.record_error(
                    operation="ingest_sensor_data",
                    error_code=result.error.error_code.value if hasattr(result.error.error_code, "value") else str(result.error.error_code),
                    message=result.error.message,
                )

        return result

    def route_camera_data(self, camera_contract: DroneCameraRoutingContract) -> Dict[str, Any]:
        """Route drone camera frame to Vision module."""
        self._diagnostics.record_metric("camera_routes_total", 1.0)
        return self._camera_router.route_camera_data(camera_contract)

    def register_sensor(self, metadata: SensorMetadataContract) -> bool:
        """Register a sensor profile."""
        return self._sensor_registry.register_sensor(metadata)

    def get_sensor(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve sensor profile."""
        return self._sensor_registry.get_sensor(sensor_id)

    def list_sensors(self, category: Optional[SensorCategory] = None) -> List[SensorMetadataContract]:
        """List active sensor profiles."""
        return self._sensor_registry.list_sensors(category=category)

    def check_health(self) -> Dict[str, Any]:
        """Comprehensive composite health check across all D2 components."""
        gw_health = self._gateway.health_check()
        reg_health = self._sensor_registry.health_check()
        adapt_health = self._adapter_registry.health_check()
        diag_health = self._diagnostics.get_health_status()
        storage_health = self._storage_adapter.health_check() if hasattr(self._storage_adapter, "health_check") else {"status": "UNKNOWN"}

        is_healthy = (
            self._config.enabled
            and gw_health.get("status") == "HEALTHY"
            and reg_health.get("status") == "HEALTHY"
            and diag_health.get("status") == "HEALTHY"
        )

        return {
            "status": "HEALTHY" if is_healthy else "DEGRADED",
            "module_enabled": self._config.enabled,
            "gateway": gw_health,
            "registry": reg_health,
            "adapters": adapt_health,
            "storage": storage_health,
            "diagnostics": diag_health,
        }
