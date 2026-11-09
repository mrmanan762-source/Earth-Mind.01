"""EarthMind Drone Module (Stage D2: Core Foundation).

Exports:
- DroneModule, DroneService
- Gateway: DroneDataGateway
- Registry: SensorRegistry
- Formats: DataFormatRegistry, FormatCapability
- Adapters: ISensorAdapter, BaseSensorAdapter, SensorAdapterRegistry, SyntheticMultispectralSensorAdapter, SyntheticThermalSensorAdapter
- Lifecycle: IngestionLifecycleTracker, IngestionStatus
- Diagnostics: DroneDiagnostics
- Camera Router: CameraDataRouter
- Storage: InMemoryDroneStorageAdapter
- Schemas & Contracts: All D1 & D2 schemas and exceptions
"""

from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.gateway import DroneDataGateway
from modules.drone.registry import SensorRegistry
from modules.drone.formats import DataFormatRegistry, FormatCapability
from modules.drone.adapters import (
    ISensorAdapter,
    BaseSensorAdapter,
    SensorAdapterRegistry,
    SyntheticMultispectralSensorAdapter,
    SyntheticThermalSensorAdapter,
)
from modules.drone.lifecycle import IngestionLifecycleTracker
from modules.drone.diagnostics import DroneDiagnostics
from modules.drone.camera_router import CameraDataRouter
from modules.drone.storage import InMemoryDroneStorageAdapter
from modules.drone.parser import RawDataParser
from modules.drone.quality import DataQualityValidator, DataQualityReport, MeasurementValidationItem
from modules.drone.calibration import CalibrationEngine, CalibrationAssessment
from modules.drone.normalization import UnitNormalizer
from modules.drone.processing import DroneProcessingEngine, CalibrationNormalizerAdapter
from modules.drone.geospatial import GeospatialProcessor
from modules.drone.temporal import TemporalProcessor
from modules.drone.spatiotemporal import SpatioTemporalAssociator
from modules.drone.spectral import SpectralAnalysisEngine, STANDARD_SPECTRAL_BANDS
from modules.drone.numerical import NumericalAnalysisEngine
from modules.drone.indicators import IndicatorExtractionEngine, INDICATOR_CATALOG
from modules.drone.fusion import MultiSensorFusionEngine
from modules.drone.errors import (
    DroneError,
    DroneInvalidArgumentError,
    UnsupportedSensorError,
    UnsupportedFormatError,
    InvalidSensorDataError,
    SensorMetadataMissingError,
    CalibrationUnavailableError,
    UnitConversionFailedError,
    GeolocationInvalidError,
    TimestampInvalidError,
    InsufficientDroneDataError,
    QualityValidationFailedError,
    IndicatorProcessingFailedError,
    SensorConflictError,
    EvidenceValidationFailedError,
    DroneStorageUnavailableError,
    DroneStorageError,
    DroneProcessingTimeoutError,
    DroneInternalError,
)
from core.schemas.drone import (
    SensorCategory,
    DroneDataFormat,
    QualityStatus,
    CalibrationStatus,
    EvidenceStatus,
    IngestionStatus,
    DroneErrorCode,
    SpatialCoordinates,
    SpatialBoundingBox,
    SpatialCoverage,
    TemporalCoverage,
    DroneSensorInputContract,
    SensorMetadataContract,
    ProcessedSensorMeasurementContract,
    AgriculturalIndicatorContract,
    EarthMindDroneSensorEvidence,
    DroneCameraRoutingContract,
    DroneSarvamIntegrationContract,
    DroneErrorContract,
    DroneIngestionResult,
    GeospatialCoordinateContract,
    FieldBoundaryContract,
    SpatialProcessingReport,
    TemporalProcessingReport,
    SpatioTemporalAssociationContract,
    SpectralBandMetadataContract,
    SpectralAnalysisResultContract,
    NumericalAnalysisResultContract,
    FusedSensorMeasurementContract,
    MultiSensorFusionReportContract,
)
from core.interfaces.drone import (
    IDroneDataGateway,
    ISensorRegistry,
    IDataFormatDetector,
    IRawDataProcessor,
    IDataQualityValidator,
    ICalibrationNormalizer,
    IGeospatialProcessor,
    ITemporalProcessor,
    ISpectralNumericalAnalyzer,
    IIndicatorExtractor,
    IMultiSensorFusionEngine,
    IUncertaintyAssessor,
    ISensorEvidenceBuilder,
    ISensorEvidenceValidator,
    ISarvamDroneIntegration,
    IProvenanceManager,
    IDroneStorageAdapter,
    IDroneDiagnostics,
)

__all__ = [
    "DroneModule",
    "DroneService",
    "DroneDataGateway",
    "SensorRegistry",
    "DataFormatRegistry",
    "FormatCapability",
    "ISensorAdapter",
    "BaseSensorAdapter",
    "SensorAdapterRegistry",
    "SyntheticMultispectralSensorAdapter",
    "SyntheticThermalSensorAdapter",
    "IngestionLifecycleTracker",
    "DroneDiagnostics",
    "CameraDataRouter",
    "InMemoryDroneStorageAdapter",
    "RawDataParser",
    "DataQualityValidator",
    "DataQualityReport",
    "MeasurementValidationItem",
    "CalibrationEngine",
    "CalibrationAssessment",
    "UnitNormalizer",
    "DroneProcessingEngine",
    "CalibrationNormalizerAdapter",
    "GeospatialProcessor",
    "TemporalProcessor",
    "SpatioTemporalAssociator",
    "SpectralAnalysisEngine",
    "STANDARD_SPECTRAL_BANDS",
    "NumericalAnalysisEngine",
    "IndicatorExtractionEngine",
    "INDICATOR_CATALOG",
    "MultiSensorFusionEngine",
    "DroneError",
    "DroneInvalidArgumentError",
    "UnsupportedSensorError",
    "UnsupportedFormatError",
    "InvalidSensorDataError",
    "SensorMetadataMissingError",
    "CalibrationUnavailableError",
    "UnitConversionFailedError",
    "GeolocationInvalidError",
    "TimestampInvalidError",
    "InsufficientDroneDataError",
    "QualityValidationFailedError",
    "IndicatorProcessingFailedError",
    "SensorConflictError",
    "EvidenceValidationFailedError",
    "DroneStorageUnavailableError",
    "DroneStorageError",
    "DroneProcessingTimeoutError",
    "DroneInternalError",
    "SensorCategory",
    "DroneDataFormat",
    "QualityStatus",
    "CalibrationStatus",
    "EvidenceStatus",
    "IngestionStatus",
    "DroneErrorCode",
    "SpatialCoordinates",
    "SpatialBoundingBox",
    "SpatialCoverage",
    "TemporalCoverage",
    "DroneSensorInputContract",
    "SensorMetadataContract",
    "ProcessedSensorMeasurementContract",
    "AgriculturalIndicatorContract",
    "EarthMindDroneSensorEvidence",
    "DroneCameraRoutingContract",
    "DroneSarvamIntegrationContract",
    "DroneErrorContract",
    "DroneIngestionResult",
    "GeospatialCoordinateContract",
    "FieldBoundaryContract",
    "SpatialProcessingReport",
    "TemporalProcessingReport",
    "SpatioTemporalAssociationContract",
    "SpectralBandMetadataContract",
    "SpectralAnalysisResultContract",
    "NumericalAnalysisResultContract",
    "FusedSensorMeasurementContract",
    "MultiSensorFusionReportContract",
    "IDroneDataGateway",
    "ISensorRegistry",
    "IDataFormatDetector",
    "IRawDataProcessor",
    "IDataQualityValidator",
    "ICalibrationNormalizer",
    "IGeospatialProcessor",
    "ITemporalProcessor",
    "ISpectralNumericalAnalyzer",
    "IIndicatorExtractor",
    "IMultiSensorFusionEngine",
    "IUncertaintyAssessor",
    "ISensorEvidenceBuilder",
    "ISensorEvidenceValidator",
    "ISarvamDroneIntegration",
    "IProvenanceManager",
    "IDroneStorageAdapter",
    "IDroneDiagnostics",
]
