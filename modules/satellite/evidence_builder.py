"""Satellite Evidence Synthesis Engine for EarthMind Satellite Module (Stage D6).

Implements Component 17 (ISatelliteEvidenceBuilder) and Component 19 (ISatelliteProvenanceTracker).
Assembles the canonical EarthMindSatelliteEvidence artifact (Contract 8, schema v1.0).
Combines D3 catalog/dataset metadata, D4 geospatial/temporal processed data,
D5 indicators/fusion, and D6 uncertainty assessments into a traceable, quality-controlled artifact.

Core Principles:
- References large raster products via storage URIs/paths rather than embedding heavy matrices in metadata.
- Preserves complete lineage, hashes, formulas, limitations, and operational warnings.
- Embeds deterministic SHA-256 cryptographic provenance digests (evidence_hash).
- Never modifies raw telemetry or invents unsupported agricultural diagnoses.
"""

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from core.interfaces.satellite import ISatelliteEvidenceBuilder, ISatelliteProvenanceTracker
from core.logging.logger import get_logger
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteEvidenceStatus,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteProcessedData,
    SatelliteQualityAssessment,
    SatelliteScopeInfo,
    SatelliteSensorType,
    SatelliteSourceInfo,
    SatelliteTemporalMetadata,
    SatelliteUncertaintyAssessment,
)
from modules.satellite.uncertainty import SatelliteUncertaintyAssessor

logger = get_logger("modules.satellite.evidence_builder")


class SatelliteEvidenceBuilder(ISatelliteEvidenceBuilder, ISatelliteProvenanceTracker):
    """
    Component 17 & 19: Satellite evidence synthesis and provenance tracking engine.
    Constructs the canonical EarthMindSatelliteEvidence package conforming to Contract 8 schema v1.0.
    """

    def __init__(
        self,
        uncertainty_assessor: Optional[SatelliteUncertaintyAssessor] = None,
    ) -> None:
        self._uncertainty_assessor = uncertainty_assessor or SatelliteUncertaintyAssessor()

    def record_provenance(
        self,
        dataset_id: str,
        provider_id: str,
        transformation_step: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Protocol method conforming to ISatelliteProvenanceTracker.
        Records an immutable transformation step in the satellite evidence lineage.
        """
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        step_payload = {
            "dataset_id": dataset_id,
            "provider_id": provider_id,
            "transformation_step": transformation_step,
            "timestamp": now_utc,
            "metadata": metadata,
        }
        digest = hashlib.sha256(json.dumps(step_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return {
            "step": transformation_step,
            "step_hash": digest,
            "recorded_at": now_utc,
            "payload": step_payload,
        }

    def build_evidence(
        self,
        request: SatelliteDataRequest,
        processed_data: SatelliteProcessedData,
        indicators: List[SatelliteIndicator],
        provider_id: str = "copernicus_cdse",
        constellation: str = "Sentinel-2",
        platform: str = "Sentinel-2A",
        instrument: str = "MSI",
        sensor_type: SatelliteSensorType = SatelliteSensorType.OPTICAL_MULTISPECTRAL,
        processing_level: str = "LEVEL-2A",
        license_attribution: str = "Contains modified Copernicus Sentinel data (2025), processed by EarthMind",
        uncertainty: Optional[SatelliteUncertaintyAssessment] = None,
        band_summaries: Optional[Dict[str, Dict[str, float]]] = None,
        operational_warnings: Optional[List[str]] = None,
        agronomic_limitations: Optional[List[str]] = None,
        conflicting_observations: Optional[List[str]] = None,
        revisit_age_days: float = 0.0,
    ) -> EarthMindSatelliteEvidence:
        """
        Assemble the canonical EarthMindSatelliteEvidence artifact.
        Conforms strictly to ISatelliteEvidenceBuilder protocol and Contract 8 schema v1.0.
        """
        evidence_id = f"ev_sat_{uuid.uuid4().hex[:12]}"
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 1. Source Information
        source_info = SatelliteSourceInfo(
            provider_id=provider_id,
            constellation=constellation,
            platform=platform,
            instrument=instrument,
            sensor_type=sensor_type,
            dataset_id=processed_data.dataset_id,
            processing_level=processing_level,
        )

        # 2. Scope Information
        scope_info = SatelliteScopeInfo(
            tenant_id=request.tenant_id,
            farmer_id=request.farmer_id,
            farm_id=request.farm_id,
            field_id=request.field_id or processed_data.field_id,
            crop=getattr(request, "crop", None),
        )

        # 3. Geospatial & Temporal Metadata (D4 validated)
        geospatial = processed_data.geospatial
        temporal = processed_data.temporal

        # 4. Band Summaries from processed spectral bands
        summaries: Dict[str, Dict[str, float]] = {}
        if band_summaries is not None:
            summaries = band_summaries
        else:
            for b_name, b_obj in processed_data.processed_bands.items():
                if b_obj.statistics:
                    summaries[b_name] = b_obj.statistics

        # 5. Quality Assessment
        all_warnings = list(operational_warnings or [])
        all_warnings.extend(processed_data.warnings)

        cloud_pct = processed_data.cloud_coverage_over_target
        is_boa = processed_data.atmospheric_correction_applied

        evidence_comp = "COMPLETE" if indicators and processed_data.processed_bands else (
            "PARTIAL" if (indicators or processed_data.processed_bands) else "INCOMPLETE"
        )

        quality_info = SatelliteQualityAssessment(
            overall_quality=processed_data.quality_status,
            cloud_cover_percentage=cloud_pct,
            is_atmospheric_corrected=is_boa,
            resolution_fidelity="NATIVE" if geospatial.spatial_resolution_meters else "UNKNOWN",
            evidence_completeness=evidence_comp,
        )

        # 6. Uncertainty Assessment
        if uncertainty is not None:
            uncertainty_info = uncertainty
        else:
            uncertainty_info = self._uncertainty_assessor.assess_comprehensive_uncertainty(
                quality_status=processed_data.quality_status,
                geospatial=geospatial,
                temporal=temporal,
                cloud_cover_target=cloud_pct,
                is_atmospheric_corrected=is_boa,
                revisit_age_days=revisit_age_days,
                bands_count=len(processed_data.processed_bands),
                indicators_count=len(indicators),
                sensor_type=sensor_type.value,
                operational_warnings=all_warnings,
                conflicting_observations=conflicting_observations,
            )

        # 7. Agronomic Limitations
        limitations = list(agronomic_limitations or [])
        # Aggregate indicator-specific limitations
        for ind in indicators:
            for lim in ind.limitations:
                if lim not in limitations:
                    limitations.append(lim)

        if geospatial.spatial_resolution_meters and geospatial.spatial_resolution_meters >= 10.0:
            limitations.append(
                f"Macro {geospatial.spatial_resolution_meters:.0f}m resolution indicates aggregate canopy vigor; "
                "cannot detect individual leaf symptoms or isolated sub-meter pests."
            )

        # 8. Provenance & Cryptographic Trace
        ind_ids = [ind.indicator_id for ind in indicators]
        provenance_payload = {
            "evidence_id": evidence_id,
            "dataset_id": processed_data.dataset_id,
            "provider_id": provider_id,
            "tenant_id": request.tenant_id,
            "pipeline": processed_data.processing_pipeline,
            "engine_version": processed_data.engine_version,
            "indicator_ids": ind_ids,
            "created_at": now_utc,
        }
        provenance_digest = hashlib.sha256(
            json.dumps(provenance_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        provenance_dict = {
            "evidence_hash": provenance_digest,
            "pipeline": processed_data.processing_pipeline,
            "engine_version": processed_data.engine_version,
            "processing_lineage": processed_data.provenance,
            "indicators_count": len(indicators),
            "bands_count": len(processed_data.processed_bands),
        }

        # 9. Overall Evidence Status
        status = SatelliteEvidenceStatus.SUCCESS
        if processed_data.quality_status == SatelliteDataQuality.INVALID:
            status = SatelliteEvidenceStatus.REJECTED
        elif processed_data.quality_status in (SatelliteDataQuality.DEGRADED, SatelliteDataQuality.CLOUD_OBSCURED):
            status = SatelliteEvidenceStatus.DEGRADED
        elif not indicators or not processed_data.processed_bands:
            status = SatelliteEvidenceStatus.PARTIAL

        evidence = EarthMindSatelliteEvidence(
            contract_name="EarthMindSatelliteEvidence",
            schema_version="1.0",
            evidence_id=evidence_id,
            source=source_info,
            scope=scope_info,
            geospatial=geospatial,
            temporal=temporal,
            indicators=indicators,
            band_summaries=summaries,
            quality=quality_info,
            uncertainty=uncertainty_info,
            license_attribution=license_attribution,
            provenance=provenance_dict,
            warnings=all_warnings,
            limitations=limitations,
            status=status,
        )

        logger.info(
            f"Synthesized EarthMindSatelliteEvidence '{evidence.evidence_id}' "
            f"for dataset '{processed_data.dataset_id}' with {len(indicators)} indicators. "
            f"Status={evidence.status.value}, Overall Confidence={uncertainty_info.overall_confidence}"
        )

        return evidence
