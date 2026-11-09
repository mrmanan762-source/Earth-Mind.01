"""Sensor Evidence Synthesis Engine for EarthMind Drone Module (Stage D6).

Implements Component 13 (ISensorEvidenceBuilder).
Assembles the canonical EarthMindDroneSensorEvidence artifact (Contract 5, schema v1.0).
Combines D3 processed measurements, D4 geospatial/temporal coverage, D5 indicators/fusion,
and D6 uncertainty assessments into a traceable, quality-controlled evidence package.

Preserves full lineage, hashes, formulas, limitations, and operational warnings.
Never modifies raw telemetry or invents unverified agricultural diagnoses.
"""

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from core.interfaces.drone import ISensorEvidenceBuilder
from core.logging.logger import get_logger
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    CalibrationStatus,
    DroneCalibrationInfo,
    DroneCollectionInfo,
    DroneFieldInfo,
    DroneProcessingInfo,
    DroneQualityAssessment,
    DroneSensorInputContract,
    DroneSourceInfo,
    DroneUncertaintyAssessment,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SpatialCoverage,
    TemporalCoverage,
)
from modules.drone.uncertainty import UncertaintyAssessor

logger = get_logger("modules.drone.evidence_builder")


class SensorEvidenceBuilder(ISensorEvidenceBuilder):
    """
    Component 13: Sensor evidence synthesis engine.
    Constructs the canonical EarthMindDroneSensorEvidence package with end-to-end provenance.
    """

    def __init__(self, uncertainty_assessor: Optional[UncertaintyAssessor] = None) -> None:
        self._uncertainty_assessor = uncertainty_assessor or UncertaintyAssessor()

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
        """
        Assemble the canonical EarthMindDroneSensorEvidence artifact.
        Conforms strictly to ISensorEvidenceBuilder protocol and Contract 5 schema v1.0.
        """
        evidence_id = f"ev_drone_{uuid.uuid4().hex[:12]}"
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 1. Source Identification
        source_info = DroneSourceInfo(
            source_type=input_data.source_type or "drone_sensor",
            drone_id=input_data.drone_id,
            sensor_id=input_data.sensor_id,
            sensor_type=input_data.sensor_type,
            manufacturer=input_data.manufacturer,
            model=input_data.model,
        )

        # 2. Agricultural Field Context
        field_info = DroneFieldInfo(
            field_id=input_data.field_id,
            farm_id=input_data.farm_id,
            farmer_id=input_data.farmer_id,
            crop=crop,
        )

        # 3. Collection Context
        # Infer nominal flight altitude if available in spatial metadata
        flight_altitude = None
        if spatial.centroid and spatial.centroid.altitude_meters is not None:
            flight_altitude = spatial.centroid.altitude_meters
        elif input_data.spatial_metadata and "altitude_meters" in input_data.spatial_metadata:
            flight_altitude = float(input_data.spatial_metadata["altitude_meters"])

        collection_info = DroneCollectionInfo(
            mission_id=mission_id,
            collection_timestamp=input_data.collection_timestamp,
            ingestion_timestamp=input_data.ingestion_timestamp or now_utc,
            flight_altitude_meters=flight_altitude,
            flight_speed_mps=None,
        )

        # 4. Calibration Assessment
        cal_meta = input_data.calibration_metadata or {}
        panel_used = bool(cal_meta.get("calibration_panel_used", False) or cal_meta.get("panel_used", False))
        sun_sensor_used = bool(cal_meta.get("sun_sensor_used", False) or cal_meta.get("dls_used", False))
        cal_timestamp = cal_meta.get("last_factory_calibration") or cal_meta.get("calibration_timestamp")

        # Determine calibration status if not explicitly passed
        if calibration is not None:
            cal_info = calibration
        else:
            inferred_cal_status = CalibrationStatus.UNCALIBRATED
            if measurements:
                # Use majority calibration status of processed measurements
                statuses = [m.calibration_status for m in measurements]
                if all(s == CalibrationStatus.CALIBRATED for s in statuses):
                    inferred_cal_status = CalibrationStatus.CALIBRATED
                elif any(s == CalibrationStatus.FACTORY_DEFAULT for s in statuses):
                    inferred_cal_status = CalibrationStatus.FACTORY_DEFAULT
                elif any(s == CalibrationStatus.EXPIRED for s in statuses):
                    inferred_cal_status = CalibrationStatus.EXPIRED
                elif any(s == CalibrationStatus.MISSING for s in statuses):
                    inferred_cal_status = CalibrationStatus.MISSING

            cal_info = DroneCalibrationInfo(
                calibration_status=inferred_cal_status,
                panel_used=panel_used,
                sun_sensor_used=sun_sensor_used,
                calibration_timestamp=cal_timestamp,
            )

        # 5. Quality Assessment
        all_warnings = list(warnings or [])
        if quality is not None:
            quality_info = quality
        else:
            # Aggregate measurement quality
            inferred_validity = QualityStatus.VALID
            if not measurements:
                inferred_validity = QualityStatus.INCOMPLETE
                all_warnings.append("No processed measurements present in candidate evidence")
            else:
                m_statuses = [m.quality_status for m in measurements]
                if any(s == QualityStatus.INVALID for s in m_statuses):
                    inferred_validity = QualityStatus.INVALID
                elif any(s == QualityStatus.DEGRADED for s in m_statuses):
                    inferred_validity = QualityStatus.DEGRADED
                elif any(s == QualityStatus.SUSPECT for s in m_statuses):
                    inferred_validity = QualityStatus.SUSPECT

            overall_q = "HIGH"
            if inferred_validity in (QualityStatus.SUSPECT, QualityStatus.DEGRADED):
                overall_q = "NORMAL"
            elif inferred_validity in (QualityStatus.INVALID, QualityStatus.INCOMPLETE):
                overall_q = "DEGRADED"

            quality_info = DroneQualityAssessment(
                input_validity=inferred_validity,
                measurement_quality="HIGH" if inferred_validity == QualityStatus.VALID else "DEGRADED",
                processing_quality="NORMALIZED",
                evidence_completeness="COMPLETE" if (measurements and indicators) else "PARTIAL",
                overall_quality=overall_q,
            )

        # 6. Uncertainty Assessment
        if uncertainty is not None:
            uncertainty_info = uncertainty
        else:
            uncertainty_info = self._uncertainty_assessor.assess_comprehensive_uncertainty(
                quality_assessment=quality_info,
                calibration_status=cal_info.calibration_status,
                panel_used=cal_info.panel_used,
                sun_sensor_used=cal_info.sun_sensor_used,
                spatial_coverage=spatial,
                temporal_coverage=temporal,
                measurements_count=len(measurements),
                indicators_count=len(indicators),
                operational_warnings=all_warnings,
            )

        # 7. Processing Info
        processing_info = DroneProcessingInfo(
            engine_version="1.0.0",
            pipeline="standard_drone_pipeline_v1",
            processing_timestamp=now_utc,
        )

        # 8. Provenance & Cryptographic Trace
        meas_ids = [m.measurement_id for m in measurements]
        ind_ids = [ind.indicator_id for ind in indicators]
        provenance_payload = {
            "evidence_id": evidence_id,
            "drone_id": input_data.drone_id,
            "sensor_id": input_data.sensor_id,
            "source_provenance": input_data.source_provenance,
            "input_timestamp": input_data.collection_timestamp,
            "measurement_ids": meas_ids,
            "indicator_ids": ind_ids,
            "created_at": now_utc,
        }
        provenance_digest = hashlib.sha256(
            json.dumps(provenance_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        provenance_dict = {
            "evidence_hash": provenance_digest,
            "trace_id": input_data.source_provenance.get("trace_id", f"tr_{evidence_id}"),
            "input_provenance": input_data.source_provenance,
            "source_measurements_count": len(measurements),
            "indicators_extracted_count": len(indicators),
        }

        # 9. Agronomic Limitations
        all_limitations = list(limitations or [])
        # Aggregate indicator limitations
        for ind in indicators:
            for lim in ind.limitations:
                if lim not in all_limitations:
                    all_limitations.append(lim)

        if not spatial.has_spatial_metadata:
            all_limitations.append("Spatial boundaries unverified; observations lack absolute GPS coordinates")
        if cal_info.calibration_status != CalibrationStatus.CALIBRATED:
            all_limitations.append("Radiometric calibration incomplete; reflectance values may reflect ambient lighting variations")

        # 10. Overall Evidence Status
        status = EvidenceStatus.SUCCESS
        if quality_info.input_validity == QualityStatus.INVALID:
            status = EvidenceStatus.REJECTED
        elif quality_info.input_validity in (QualityStatus.SUSPECT, QualityStatus.DEGRADED):
            status = EvidenceStatus.DEGRADED
        elif not indicators or not measurements:
            status = EvidenceStatus.PARTIAL

        evidence = EarthMindDroneSensorEvidence(
            contract_name="EarthMindDroneSensorEvidence",
            schema_version="1.0",
            evidence_id=evidence_id,
            source=source_info,
            field=field_info,
            collection=collection_info,
            measurements=measurements,
            indicators=indicators,
            spatial_coverage=spatial,
            temporal_coverage=temporal,
            quality=quality_info,
            uncertainty=uncertainty_info,
            calibration=cal_info,
            processing=processing_info,
            provenance=provenance_dict,
            warnings=all_warnings,
            limitations=all_limitations,
            status=status,
        )

        logger.info(
            f"Assembled EarthMindDroneSensorEvidence '{evidence.evidence_id}' "
            f"with {len(measurements)} measurements and {len(indicators)} indicators. "
            f"Status={evidence.status.value}, Confidence={uncertainty_info.overall_confidence}"
        )

        return evidence
