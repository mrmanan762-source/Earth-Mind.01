"""Multi-Source Satellite Fusion Engine for EarthMind Satellite Module (Stage D5)."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.interfaces.satellite import ISatelliteMultiSourceFusion
from core.schemas.satellite import SatelliteProcessedData
from modules.satellite.errors import SatelliteInvalidArgumentError

class SatelliteMultiSourceFusionEngine(ISatelliteMultiSourceFusion):
    def __init__(self, max_temporal_delta_days: float = 7.0):
        self._max_temporal_delta_days = max_temporal_delta_days

    def evaluate_spatial_compatibility(self, obs1: SatelliteProcessedData, obs2: SatelliteProcessedData) -> Tuple[bool, float]:
        g1, g2 = obs1.geospatial, obs2.geospatial
        dist_deg = float(np.sqrt((g1.latitude - g2.latitude)**2 + (g1.longitude - g2.longitude)**2))
        return dist_deg < 0.5, dist_deg

    def evaluate_temporal_compatibility(self, obs1: SatelliteProcessedData, obs2: SatelliteProcessedData) -> Tuple[bool, float]:
        t1 = obs1.temporal.acquisition_date.replace("Z", "")
        t2 = obs2.temporal.acquisition_date.replace("Z", "")
        try:
            d1 = datetime.fromisoformat(t1)
            d2 = datetime.fromisoformat(t2)
            delta = abs((d2 - d1).total_seconds()) / 86400.0
            return delta <= self._max_temporal_delta_days, float(np.round(delta, 2))
        except Exception:
            return False, 999.0

    def fuse_constellations(self, observations: List[SatelliteProcessedData]) -> Dict[str, Any]:
        if not observations:
            raise SatelliteInvalidArgumentError("observations list cannot be empty for fusion")
        if len(observations) == 1:
            return {
                "fusion_status": "SINGLE_OBSERVATION",
                "constellations_included": [observations[0].dataset_id],
                "optical_bands": list(observations[0].processed_bands.keys()),
                "provenance": {"source_count": 1, "datasets": [observations[0].dataset_id]},
            }
        base = observations[0]
        sources = [base.dataset_id]
        bands = dict(base.processed_bands)
        warnings = []
        for other in observations[1:]:
            s_ok, dist = self.evaluate_spatial_compatibility(base, other)
            if not s_ok:
                warnings.append(f"Observation '{other.dataset_id}' spatial centroid differs by {dist:.3f} deg.")
            t_ok, delta = self.evaluate_temporal_compatibility(base, other)
            if not t_ok:
                warnings.append(f"Observation '{other.dataset_id}' temporal delta {delta} days > {self._max_temporal_delta_days}.")
            sources.append(other.dataset_id)
            for bname, bobj in other.processed_bands.items():
                if bname not in bands:
                    bands[f"{other.dataset_id}_{bname}"] = bobj
        return {
            "fusion_status": "FUSED",
            "constellations_included": sources,
            "total_bands_available": len(bands),
            "warnings": warnings,
            "provenance": {"source_count": len(observations), "datasets": sources, "base_dataset_id": base.dataset_id},
        }
