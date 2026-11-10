"""Temporal and Numerical Processing Engine for EarthMind Satellite Module (Stage D4)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from core.interfaces.satellite import ISatelliteTemporalProcessor
from core.logging.logger import get_logger
from core.schemas.satellite import SatelliteTemporalMetadata
from modules.satellite.errors import SatelliteInvalidArgumentError

logger = get_logger("modules.satellite.temporal_numerical")

CONSTELLATION_REVISIT_DAYS: Dict[str, float] = {
    "SENTINEL-2": 5.0,
    "SENTINEL-2A": 10.0,
    "SENTINEL-2B": 10.0,
    "LANDSAT-8": 16.0,
    "LANDSAT-9": 16.0,
    "LANDSAT-8/9": 8.0,
    "MODIS": 1.0,
    "SENTINEL-1": 6.0,
}

class SatelliteTemporalProcessor(ISatelliteTemporalProcessor):
    def normalize_timestamp(self, ts_input: Union[str, datetime, int, float]) -> str:
        if ts_input is None:
            raise SatelliteInvalidArgumentError("Timestamp input cannot be None")
        dt: Optional[datetime] = None
        if isinstance(ts_input, (int, float)):
            dt = datetime.fromtimestamp(float(ts_input), tz=timezone.utc)
        elif isinstance(ts_input, datetime):
            dt = ts_input.replace(tzinfo=timezone.utc) if ts_input.tzinfo is None else ts_input.astimezone(timezone.utc)
        elif isinstance(ts_input, str):
            clean = ts_input.strip()
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%dT%H%M%S"):
                try:
                    dt = datetime.strptime(clean, fmt)
                    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                    break
                except ValueError:
                    continue
            if dt is None:
                try:
                    dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
                    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                except ValueError as exc:
                    raise SatelliteInvalidArgumentError(f"Cannot parse timestamp: {exc}")
        if dt is None:
            raise SatelliteInvalidArgumentError(f"Unsupported timestamp format: {ts_input}")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def process_temporal(self, acquisition_timestamp: str, constellation: str = "Sentinel-2", start_time: Optional[str] = None, end_time: Optional[str] = None, temporal_coverage_type: str = "SCENE_INSTANTANEOUS") -> SatelliteTemporalMetadata:
        norm_acq = self.normalize_timestamp(acquisition_timestamp)
        norm_start = self.normalize_timestamp(start_time) if start_time else None
        norm_end = self.normalize_timestamp(end_time) if end_time else None
        c_upper = constellation.upper()
        revisit = 5.0
        for k, v in CONSTELLATION_REVISIT_DAYS.items():
            if k in c_upper:
                revisit = v
                break
        return SatelliteTemporalMetadata(
            acquisition_date=norm_acq,
            start_time=norm_start,
            end_time=norm_end,
            revisit_interval_days=revisit,
            temporal_coverage_type=temporal_coverage_type,
        )

    def order_chronologically(self, observations: List[Dict[str, Any]], timestamp_key: str = "acquisition_date") -> List[Dict[str, Any]]:
        if not observations:
            return []
        def get_sort_key(item: Dict[str, Any]) -> str:
            val = item.get(timestamp_key)
            if isinstance(val, dict) and "acquisition_date" in val:
                val = val["acquisition_date"]
            return self.normalize_timestamp(val)
        return sorted(observations, key=get_sort_key)

    def detect_observation_gaps(self, timestamps: List[str], max_allowed_gap_days: float = 16.0) -> List[Dict[str, Any]]:
        if len(timestamps) < 2:
            return []
        sorted_ts = sorted([self.normalize_timestamp(t) for t in timestamps])
        dts = [datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") for t in sorted_ts]
        gaps = []
        for i in range(len(dts) - 1):
            delta = dts[i + 1] - dts[i]
            gap_days = delta.total_seconds() / 86400.0
            if gap_days > max_allowed_gap_days:
                gaps.append({
                    "start_date": sorted_ts[i],
                    "end_date": sorted_ts[i + 1],
                    "gap_duration_days": float(np.round(gap_days, 2)),
                    "is_gap": True,
                })
        return gaps

    def validate_numerical_array(self, data: Any, expected_range: Optional[Tuple[float, float]] = None, expected_shape: Optional[Tuple[int, ...]] = None) -> Tuple[bool, List[str]]:
        warnings: List[str] = []
        try:
            arr = np.asarray(data, dtype=np.float32)
        except Exception as exc:
            return False, [f"Cannot convert to numerical array: {exc}"]
        if expected_shape is not None and arr.shape != expected_shape:
            warnings.append(f"Array shape {arr.shape} does not match expected {expected_shape}")
        finite_vals = arr[np.isfinite(arr)]
        if finite_vals.size == 0:
            return False, ["Array contains no finite numerical values"]
        if expected_range is not None:
            min_b, max_b = expected_range
            min_v, max_v = float(np.min(finite_vals)), float(np.max(finite_vals))
            if min_v < min_b or max_v > max_b:
                warnings.append(f"Values [{min_v:.3f}, {max_v:.3f}] exceed expected [{min_b}, {max_b}]")
        return True, warnings
