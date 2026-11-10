"""Temporal Analysis Engine for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional
import numpy as np

class SatelliteTemporalAnalyzer:
    def build_time_series(self, observations: List[Dict[str, Any]], indicator_key: str = "mean") -> Dict[str, Any]:
        if not observations:
            return {"observation_count": 0, "dates": [], "values": [], "trend": "INSUFFICIENT_DATA", "summary": {}}
        parsed_obs = []
        for obs in observations:
            d = obs.get("date") or obs.get("acquisition_date")
            v = obs.get("value") or obs.get(indicator_key)
            if d is not None and v is not None and np.isfinite(float(v)):
                parsed_obs.append((d, float(v)))
        parsed_obs.sort(key=lambda x: x[0])
        dates = [p[0] for p in parsed_obs]
        values = [p[1] for p in parsed_obs]
        if len(values) < 2:
            trend = "STABLE_OR_SINGLE_OBSERVATION"
            slope = 0.0
        else:
            x = np.arange(len(values))
            slope, _ = np.polyfit(x, values, 1)
            trend = "INCREASING" if slope > 0.02 else "DECREASING" if slope < -0.02 else "STABLE"
        return {
            "observation_count": len(dates),
            "dates": dates,
            "values": values,
            "trend": trend,
            "slope": float(np.round(float(slope), 5)) if len(values) >= 2 else 0.0,
            "summary": {
                "mean": float(np.round(float(np.mean(values)), 4)) if values else 0.0,
                "min": float(np.round(float(np.min(values)), 4)) if values else 0.0,
                "max": float(np.round(float(np.max(values)), 4)) if values else 0.0,
                "std_dev": float(np.round(float(np.std(values)), 4)) if values else 0.0,
                "delta_first_to_last": float(np.round(values[-1] - values[0], 4)) if values else 0.0,
            },
        }
