"""Drone Processing Engine for EarthMind Drone Module (Stage D3).

Coordinates Component 4 (RawDataParser), Component 5 (DataQualityValidator),
and Component 6 (CalibrationEngine + UnitNormalizer) into the full D3 pipeline.
Emits versioned ProcessedSensorMeasurementContract records while preserving
unmodified raw values, calibration status, quality classification, and end-to-end lineage.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces.drone import ICalibrationNormalizer, IRawDataProcessor
from core.logging.logger import get_logger
from core.schemas.drone import (
    CalibrationStatus,
    DroneSensorInputContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorMetadataContract,
    SpatialCoordinates,
)
from modules.drone.calibration import CalibrationAssessment, CalibrationEngine
from modules.drone.errors import (
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
    InvalidSensorDataError,
    QualityValidationFailedError,
    UnitConversionFailedError,
)
from modules.drone.normalization import UnitNormalizer
from modules.drone.parser import RawDataParser
from modules.drone.quality import DataQualityReport, DataQualityValidator

logger = get_logger("modules.drone.processing")


class CalibrationNormalizerAdapter(ICalibrationNormalizer):
    """Component 6 Implementation conforming to ICalibrationNormalizer protocol."""

    def __init__(
        self,
        calibration_engine: Optional[CalibrationEngine] = None,
        unit_normalizer: Optional[UnitNormalizer] = None,
    ):
        self._cal_engine = calibration_engine or CalibrationEngine()
        self._unit_norm = unit_normalizer or UnitNormalizer()

    def normalize_measurement(
        self,
        raw_measurement: Dict[str, Any],
        calibration_metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedSensorMeasurementContract:
        """Apply calibration parameters and normalize units to scientific standard."""
        channel = raw_measurement.get("channel") or raw_measurement.get("channel_name") or "unknown"
        val = raw_measurement.get("value") if "value" in raw_measurement else raw_measurement.get("original_value")
        orig_unit = str(raw_measurement.get("unit") or raw_measurement.get("original_unit") or "raw_dn")
        src_sensor = raw_measurement.get("source_sensor") or "synthetic_sensor"
        timestamp = raw_measurement.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Evaluate calibration
        cal_eval = self._cal_engine.evaluate_calibration(calibration_metadata, observation_timestamp=timestamp)
        calibrated_val, cal_method = self._cal_engine.apply_calibration_transform(float(val), channel, cal_eval)

        # Normalize unit
        norm_val, norm_unit, norm_method = self._unit_norm.normalize(calibrated_val, orig_unit, channel)

        return ProcessedSensorMeasurementContract(
            measurement_id=f"meas_{uuid.uuid4().hex[:12]}",
            measurement_type=raw_measurement.get("measurement_type", "sensor_reading"),
            channel_name=channel,
            original_value=val,
            original_unit=orig_unit,
            processed_value=norm_val,
            normalized_unit=norm_unit,
            processing_method=f"{cal_method} -> {norm_method}",
            calibration_status=cal_eval.status,
            timestamp=timestamp,
            quality_status=raw_measurement.get("quality_status", QualityStatus.VALID),
            source_sensor=src_sensor,
            provenance={
                "calibration_assessment": cal_eval.model_dump(),
                "normalization_method": norm_method,
            },
        )


class DroneProcessingEngine:
    """Core D3 Processing Coordinator orchestrating Parsing, Quality, Calibration, and Normalization."""

    def __init__(
        self,
        parser: Optional[RawDataParser] = None,
        quality_validator: Optional[DataQualityValidator] = None,
        calibration_engine: Optional[CalibrationEngine] = None,
        unit_normalizer: Optional[UnitNormalizer] = None,
    ):
        self._parser = parser or RawDataParser()
        self._quality_validator = quality_validator or DataQualityValidator()
        self._calibration_engine = calibration_engine or CalibrationEngine()
        self._unit_normalizer = unit_normalizer or UnitNormalizer()
        self._normalizer_adapter = CalibrationNormalizerAdapter(
            self._calibration_engine, self._unit_normalizer
        )

    @property
    def parser(self) -> RawDataParser:
        return self._parser

    @property
    def quality_validator(self) -> DataQualityValidator:
        return self._quality_validator

    @property
    def calibration_engine(self) -> CalibrationEngine:
        return self._calibration_engine

    @property
    def unit_normalizer(self) -> UnitNormalizer:
        return self._unit_normalizer

    @property
    def normalizer_adapter(self) -> CalibrationNormalizerAdapter:
        return self._normalizer_adapter

    def process_sensor_input(
        self,
        input_contract: DroneSensorInputContract,
        sensor_profile: Optional[SensorMetadataContract] = None,
    ) -> Tuple[List[ProcessedSensorMeasurementContract], DataQualityReport, CalibrationAssessment]:
        """
        Execute full D3 processing pipeline from raw input contract.

        Returns:
            Tuple[List[ProcessedSensorMeasurementContract], DataQualityReport, CalibrationAssessment]
        """
        raw_payload = input_contract.raw_payload
        data_format = input_contract.data_format

        # Step 1: Parse Raw Payload
        parsed_data = self._parser.parse_raw_data(raw_payload, data_format)

        raw_measurements = parsed_data.get("measurements", [])
        if not raw_measurements:
            raise InsufficientDroneDataError(
                details=f"No individual measurements extracted from {data_format.value} payload.",
                operation="process_sensor_input",
            )

        # Normalize measurement items to have 'channel' and 'value'
        extracted_measurements = []
        for item in raw_measurements:
            if "channel" in item and "value" in item:
                extracted_measurements.append(dict(item))
            else:
                # Tabular row e.g. {"thermal_ir": 77.0}
                for k, v in item.items():
                    extracted_measurements.append({
                        "channel": k,
                        "value": v,
                        "unit": item.get("unit", "raw_dn"),
                    })

        # Merge unit metadata if declared at input contract level
        if input_contract.unit_metadata:
            for m in extracted_measurements:
                ch = m.get("channel") or m.get("channel_name")
                if ch and ch in input_contract.unit_metadata and (not m.get("unit") or m.get("unit") == "raw_dn"):
                    m["unit"] = input_contract.unit_metadata[ch]

        # Step 2: Quality & Validation
        expected_channels = sensor_profile.supported_measurements if sensor_profile else None
        quality_report = self._quality_validator.evaluate_measurements(
            extracted_measurements,
            collection_timestamp=input_contract.collection_timestamp,
            expected_channels=expected_channels,
        )

        # Step 3: Calibration Evaluation
        cal_assessment = self._calibration_engine.evaluate_calibration(
            calibration_metadata=input_contract.calibration_metadata,
            sensor_profile=sensor_profile.model_dump() if sensor_profile else None,
            observation_timestamp=input_contract.collection_timestamp,
        )

        # Step 4: Normalization & Measurement Contract Generation
        processed_records: List[ProcessedSensorMeasurementContract] = []

        # Create mapping of validation status per channel
        validation_map = {item.channel: item for item in quality_report.items}

        spatial_ref: Optional[SpatialCoordinates] = None
        if input_contract.spatial_metadata:
            try:
                lat = input_contract.spatial_metadata.get("latitude")
                lon = input_contract.spatial_metadata.get("longitude")
                if lat is not None and lon is not None:
                    spatial_ref = SpatialCoordinates(
                        latitude=float(lat),
                        longitude=float(lon),
                        altitude_meters=input_contract.spatial_metadata.get("altitude_meters"),
                    )
            except Exception:
                pass

        for m in extracted_measurements:
            ch_name = m.get("channel") or m.get("channel_name") or "unknown"
            orig_val = m.get("value") if "value" in m else m.get("original_value")
            orig_unit = str(m.get("unit") or m.get("original_unit") or "raw_dn")

            val_item = validation_map.get(ch_name)
            item_quality = val_item.quality_status if val_item else QualityStatus.VALID

            # Apply calibration
            cal_val = orig_val
            cal_method = "none"
            if isinstance(orig_val, (int, float)):
                cal_val, cal_method = self._calibration_engine.apply_calibration_transform(
                    float(orig_val), ch_name, cal_assessment
                )

            # Apply unit normalization
            proc_val = cal_val
            norm_unit = orig_unit
            norm_method = "identity"

            warnings_list = list(cal_assessment.warnings)
            if val_item and val_item.warnings:
                warnings_list.extend(val_item.warnings)

            if isinstance(cal_val, (int, float)):
                try:
                    norm_v, n_unit, n_method = self._unit_normalizer.normalize(
                        float(cal_val), orig_unit, channel_name=ch_name
                    )
                    proc_val = norm_v
                    norm_unit = n_unit
                    norm_method = n_method
                except UnitConversionFailedError as uce:
                    # In D3 we must not silently discard, record warning or set degraded
                    warnings_list.append(f"Unit conversion failed: {uce.message}")
                    item_quality = QualityStatus.DEGRADED
                    proc_val = float(cal_val)

            elif isinstance(orig_val, (list, tuple)):
                # If array / list, compute normalized representative value (e.g. mean) for scalar processed_value
                valid_floats = [float(x) for x in orig_val if isinstance(x, (int, float))]
                if valid_floats:
                    mean_val = sum(valid_floats) / len(valid_floats)
                    try:
                        proc_val, norm_unit, norm_method = self._unit_normalizer.normalize(
                            mean_val, orig_unit, channel_name=ch_name
                        )
                        norm_method = f"array_mean -> {norm_method}"
                    except Exception:
                        proc_val = mean_val
                else:
                    proc_val = 0.0

            processed_contract = ProcessedSensorMeasurementContract(
                measurement_id=f"meas_{uuid.uuid4().hex[:12]}",
                measurement_type=sensor_profile.sensor_category.value if sensor_profile else "sensor_reading",
                channel_name=ch_name,
                original_value=orig_val,
                original_unit=orig_unit,
                processed_value=float(proc_val),
                normalized_unit=norm_unit,
                processing_method=f"{cal_method} -> {norm_method}",
                calibration_status=cal_assessment.status,
                timestamp=input_contract.collection_timestamp,
                spatial_reference=spatial_ref,
                quality_status=item_quality,
                source_sensor=input_contract.sensor_id,
                provenance={
                    "drone_id": input_contract.drone_id,
                    "input_format": data_format.value,
                    "warnings": warnings_list,
                    "trace_hash": str(hash(f"{input_contract.sensor_id}_{ch_name}_{input_contract.collection_timestamp}")),
                },
            )
            processed_records.append(processed_contract)

        logger.info(
            f"Successfully processed {len(processed_records)} measurements for sensor '{input_contract.sensor_id}' "
            f"(quality={quality_report.overall_status.value}, cal={cal_assessment.status.value})."
        )

        return processed_records, quality_report, cal_assessment
