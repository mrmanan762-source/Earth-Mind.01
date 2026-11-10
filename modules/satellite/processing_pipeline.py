"""Processing Pipeline for EarthMind Satellite Module (Stage D4)."""
import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.schemas.satellite import (
    SatelliteDatasetMetadata,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteRawDataReference,
)
from modules.satellite.errors import SatelliteInvalidArgumentError
from modules.satellite.geospatial import SatelliteGeospatialProcessor
from modules.satellite.image_processing import SatelliteImageProcessor
from modules.satellite.quality import SatelliteQualityValidator
from modules.satellite.radar_thermal import SatelliteSARProcessor, SatelliteThermalProcessor
from modules.satellite.spectral import SatelliteSpectralProcessor
from modules.satellite.temporal_numerical import SatelliteTemporalProcessor

class SatelliteProcessingPipeline:
    def __init__(self, image_processor=None, spectral_processor=None, geospatial_processor=None, temporal_processor=None, quality_validator=None):
        self._image_proc = image_processor or SatelliteImageProcessor()
        self._spectral_proc = spectral_processor or SatelliteSpectralProcessor()
        self._geo_proc = geospatial_processor or SatelliteGeospatialProcessor()
        self._temp_proc = temporal_processor or SatelliteTemporalProcessor()
        self._quality_val = quality_validator or SatelliteQualityValidator()
        self._sar_proc = SatelliteSARProcessor()
        self._thermal_proc = SatelliteThermalProcessor()

    @property
    def image_processor(self): return self._image_proc
    @property
    def spectral_processor(self): return self._spectral_proc
    @property
    def geospatial_processor(self): return self._geo_proc
    @property
    def temporal_processor(self): return self._temp_proc
    @property
    def quality_validator(self): return self._quality_val

    def process(self, raw_ref, metadata, raw_band_matrices, target_bands=None, field_id=None, field_boundary=None, target_crs="EPSG:4326"):
        if metadata is None:
            raise SatelliteInvalidArgumentError("metadata cannot be None")
        if not raw_band_matrices:
            raise SatelliteInvalidArgumentError("raw_band_matrices cannot be empty")

        provenance = {
            "pipeline": "SatelliteProcessingPipeline_v1.0",
            "source_dataset_id": metadata.dataset_id,
            "provider_id": metadata.provider_id,
            "steps": [],
        }

        corrected_bands = self._image_proc.apply_atmospheric_correction(raw_band_matrices, metadata)
        provenance["steps"].append("atmospheric_correction_normalized")

        cloud_report = self._image_proc.generate_cloud_mask(corrected_bands, metadata)
        cloud_pct = cloud_report["cloud_cover_percentage"]
        provenance["steps"].append("cloud_mask_generated")

        geo_dict = metadata.geospatial.model_dump()
        if field_id:
            geo_dict["field_id"] = field_id
        processed_geo = self._geo_proc.process_geospatial(geo_dict, target_crs=target_crs)
        provenance["steps"].append("geospatial_crs_validated")

        final_matrices = {}
        for bname, mat in corrected_bands.items():
            arr = np.asarray(mat, dtype=np.float32)
            if field_boundary and len(field_boundary) >= 3:
                clipped = self._geo_proc.clip_to_field_boundary(arr, field_boundary)
                final_matrices[bname] = clipped
            else:
                final_matrices[bname] = arr

        processed_temporal = self._temp_proc.process_temporal(
            acquisition_timestamp=metadata.temporal.acquisition_date,
            constellation=metadata.constellation,
            start_time=metadata.temporal.start_time,
            end_time=metadata.temporal.end_time,
            temporal_coverage_type=metadata.temporal.temporal_coverage_type,
        )
        provenance["steps"].append("temporal_normalized")

        bands_to_process = target_bands or list(final_matrices.keys())
        spectral_band_names = [b for b in bands_to_process if b not in ("SCL", "QA", "QA_PIXEL")]
        if not spectral_band_names:
            spectral_band_names = list(final_matrices.keys())

        processed_spectral_bands = self._spectral_proc.process_spectral_bands(
            raw_ref=raw_ref,
            target_bands=spectral_band_names,
            geospatial_crop=processed_geo,
            band_matrices=final_matrices,
            constellation=metadata.constellation,
        )
        provenance["steps"].append("spectral_bands_calibrated")

        quality_rep = self._quality_val.validate_processed_dataset(
            processed_bands=processed_spectral_bands,
            geospatial=processed_geo,
            temporal=processed_temporal,
            band_matrices=final_matrices,
            cloud_cover_over_target=cloud_pct,
        )
        provenance["quality_validation"] = quality_rep.to_dict()

        proc_status = (
            SatelliteProcessingStatus.PROCESSED
            if quality_rep.status in ("VALID", "VALID_WITH_WARNINGS")
            else SatelliteProcessingStatus.FAILED
        )

        processed_data = SatelliteProcessedData(
            processed_id=f"proc_sat_{uuid.uuid4().hex[:12]}",
            dataset_id=metadata.dataset_id,
            field_id=field_id,
            processing_status=proc_status,
            processing_pipeline="standard_satellite_pipeline_v1",
            engine_version="1.0.0",
            processed_bands=processed_spectral_bands,
            geospatial=processed_geo,
            temporal=processed_temporal,
            quality_status=quality_rep.quality_rating,
            atmospheric_correction_applied=True,
            cloud_mask_applied=True,
            cloud_coverage_over_target=cloud_pct,
            provenance=provenance,
            warnings=list(quality_rep.warnings),
        )

        return processed_data, final_matrices
