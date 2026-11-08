"""Drone Diagnostics for EarthMind Drone Module (Stage D2).

Implements Component 18 (IDroneDiagnostics).
Provides thread-safe in-memory metrics, health inspection, and failure tracking
without leaking credentials or raw payloads.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from core.interfaces.drone import IDroneDiagnostics
from core.logging.logger import get_logger

logger = get_logger("modules.drone.diagnostics")


class DroneDiagnostics(IDroneDiagnostics):
    """Telemetry, health diagnostics, and metrics manager for the Drone Module."""

    def __init__(self):
        self._lock = threading.RLock()
        self._start_time = time.time()
        self._counters: Dict[str, float] = {
            "ingestions_total": 0.0,
            "ingestions_accepted": 0.0,
            "ingestions_rejected": 0.0,
            "ingestions_failed": 0.0,
            "camera_routes_total": 0.0,
        }
        self._recent_errors: List[Dict[str, Any]] = []
        self._max_errors_history = 50

    def record_metric(self, metric_name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Record or increment a diagnostic counter/metric."""
        with self._lock:
            if metric_name not in self._counters:
                self._counters[metric_name] = 0.0
            self._counters[metric_name] += value

    def record_error(self, operation: str, error_code: str, message: str) -> None:
        """Record an error event in diagnostics history without sensitive payloads."""
        with self._lock:
            # Mask or sanitize message if needed
            safe_msg = message[:200]
            event = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "operation": operation,
                "error_code": error_code,
                "message": safe_msg,
            }
            self._recent_errors.append(event)
            if len(self._recent_errors) > self._max_errors_history:
                self._recent_errors.pop(0)

    def get_health_status(self) -> Dict[str, Any]:
        """Return operational health status dictionary conforming to IDroneDiagnostics."""
        with self._lock:
            uptime = time.time() - self._start_time
            total = self._counters.get("ingestions_total", 0.0)
            failed = self._counters.get("ingestions_failed", 0.0)
            failure_rate = (failed / total) if total > 0 else 0.0

            overall_status = "HEALTHY"
            if failure_rate > 0.5 and total >= 5:
                overall_status = "DEGRADED"

            return {
                "status": overall_status,
                "uptime_seconds": round(uptime, 2),
                "counters": dict(self._counters),
                "recent_error_count": len(self._recent_errors),
                "failure_rate": round(failure_rate, 4),
            }

    def get_diagnostics_summary(self) -> Dict[str, Any]:
        """Return extended diagnostics telemetry."""
        with self._lock:
            health = self.get_health_status()
            health["recent_errors"] = list(self._recent_errors[-10:])
            return health
