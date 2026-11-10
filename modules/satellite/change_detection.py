"""Change Detection Engine for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional
import numpy as np
from modules.satellite.errors import SatelliteInvalidArgumentError

class SatelliteChangeDetector:
    def compute_pixel_difference(self, matrix_t1: np.ndarray, matrix_t2: np.ndarray, date_t1: str, date_t2: str, threshold_change: float = 0.05) -> Dict[str, Any]:
        if matrix_t1 is None or matrix_t2 is None:
            raise SatelliteInvalidArgumentError("Both matrix_t1 and matrix_t2 must be provided")
        m1 = np.asarray(matrix_t1, dtype=np.float32)
        m2 = np.asarray(matrix_t2, dtype=np.float32)
        if m1.shape != m2.shape:
            raise SatelliteInvalidArgumentError(f"Matrix shapes mismatch: {m1.shape} vs {m2.shape}")
        valid_mask = np.isfinite(m1) & np.isfinite(m2)
        valid_count = int(np.sum(valid_mask))
        if valid_count == 0:
            return {"date_t1": date_t1, "date_t2": date_t2, "status": "NO_VALID_OVERLAPPING_PIXELS", "delta_matrix": np.full_like(m1, np.nan), "summary": {}}
        delta = np.where(valid_mask, m2 - m1, np.nan)
        valid_deltas = delta[valid_mask]
        total = float(valid_count)
        return {
            "date_t1": date_t1,
            "date_t2": date_t2,
            "status": "COMPUTED",
            "delta_matrix": delta,
            "summary": {
                "mean_delta": float(np.round(float(np.mean(valid_deltas)), 4)),
                "min_delta": float(np.round(float(np.min(valid_deltas)), 4)),
                "max_delta": float(np.round(float(np.max(valid_deltas)), 4)),
                "std_dev_delta": float(np.round(float(np.std(valid_deltas)), 4)),
                "increased_pixel_percentage": float(np.round(np.sum(delta > threshold_change) / total * 100.0, 2)),
                "decreased_pixel_percentage": float(np.round(np.sum(delta < -threshold_change) / total * 100.0, 2)),
                "stable_pixel_percentage": float(np.round(np.sum(np.abs(delta) <= threshold_change) / total * 100.0, 2)),
                "valid_overlapping_pixels": valid_count,
            },
            "limitations": [
                "Observed changes represent spectral radiometric differences between acquisition dates.",
                "Changes MUST NOT automatically be attributed to crop disease, drought, or pest infestation without on-ground agronomic context.",
            ],
        }
