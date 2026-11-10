"""Preliminary Quality Validator for Satellite Module (Stage D3).

Implements Component 7 (ISatellitePreValidator).
Evaluates scene cloud cover, missing bands, bounding boxes, coordinate bounds,
and assigns preliminary SatelliteDataQuality classifications.
"""

from typing import List, Optional

from core.interfaces.satellite import ISatellitePreValidator
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataQuality,
    SatelliteDatasetMetadata,
)

logger = get_logger("modules.satellite.pre_validator")


class SatellitePreValidator(ISatellitePreValidator):
    """Component 7: Pre-processing validator for physical limits and preliminary quality."""

    def __init__(
        self,
        cloud_excellent_threshold: float = 5.0,
        cloud_good_threshold: float = 15.0,
        cloud_acceptable_threshold: float = 30.0,
        cloud_obscured_threshold: float = 70.0,
    ):
        self.cloud_excellent_threshold = cloud_excellent_threshold
        self.cloud_good_threshold = cloud_good_threshold
        self.cloud_acceptable_threshold = cloud_acceptable_threshold
        self.cloud_obscured_threshold = cloud_obscured_threshold

    def validate_preliminary_quality(
        self,
        dataset_metadata: SatelliteDatasetMetadata,
    ) -> SatelliteDataQuality:
        """
        Evaluate scene cloud cover, missing bands, coordinate sanity, and assign quality.
        Conforms to ISatellitePreValidator.
        """
        if not dataset_metadata:
            return SatelliteDataQuality.INVALID

        # Check geospatial sanity
        geo = dataset_metadata.geospatial
        if not (-90.0 <= geo.latitude <= 90.0 and -180.0 <= geo.longitude <= 180.0):
            logger.warning(f"Invalid centroid coordinates for dataset {dataset_metadata.dataset_id}: ({geo.latitude}, {geo.longitude})")
            return SatelliteDataQuality.INVALID

        if geo.bounding_box:
            min_lon, min_lat, max_lon, max_lat = geo.bounding_box
            if min_lat > max_lat or min_lon > max_lon:
                logger.warning(f"Malformed bounding box for dataset {dataset_metadata.dataset_id}: {geo.bounding_box}")
                return SatelliteDataQuality.INVALID

        # Check cloud cover thresholds
        cc = dataset_metadata.cloud_cover_percentage
        if cc < 0.0 or cc > 100.0:
            return SatelliteDataQuality.INVALID

        if cc >= self.cloud_obscured_threshold:
            return SatelliteDataQuality.CLOUD_OBSCURED

        # Check band presence if optical multispectral
        if dataset_metadata.available_bands:
            # Verify band statistics or identifiers
            for b in dataset_metadata.available_bands:
                if not b.band_id or not b.band_id.strip():
                    return SatelliteDataQuality.INCOMPLETE

        if cc <= self.cloud_excellent_threshold:
            return SatelliteDataQuality.EXCELLENT
        elif cc <= self.cloud_good_threshold:
            return SatelliteDataQuality.GOOD
        elif cc <= self.cloud_acceptable_threshold:
            return SatelliteDataQuality.ACCEPTABLE
        else:
            return SatelliteDataQuality.DEGRADED
