"""Operational Telemetry and Diagnostics for EarthMind Satellite Module (Stage D2).

Implements ISatelliteDiagnostics protocol:
- Module lifecycle status tracking
- Granular provider states: REGISTERED, INITIALIZED, AVAILABLE, UNAVAILABLE, DISABLED, FAILED
- Configuration validity reporting
- Telemetry metrics recording (latency, counters)
- Secret masking and bounded length protection in diagnostic logs
"""

import threading
import time
from typing import Any, Dict, List, Optional

from core.interfaces.satellite import ISatelliteDiagnostics
from core.logging.logger import get_logger

logger = get_logger("modules.satellite.diagnostics")


class SatelliteDiagnostics(ISatelliteDiagnostics):
    """Diagnostics and telemetry collector for the Satellite Module."""

    def __init__(self, max_error_history: int = 100):
        self._lock = threading.RLock()
        self._max_error_history = max_error_history
        self._counters: Dict[str, int] = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_rejected": 0,
            "requests_failed": 0,
            "catalog_searches_total": 0,
            "catalog_searches_failed": 0,
            "acquisitions_total": 0,
            "acquisitions_failed": 0,
            "retries_total": 0,
        }
        self._gauges: Dict[str, float] = {}
        self._recent_errors: List[Dict[str, Any]] = []
        self._provider_statuses: Dict[str, str] = {}
        self._module_lifecycle_state: str = "INITIALIZED"

    def set_lifecycle_state(self, state: str) -> None:
        """Update current lifecycle state."""
        with self._lock:
            self._module_lifecycle_state = state

    def update_provider_status(self, provider_id: str, status: str) -> None:
        """Update tracked operational status of a provider."""
        with self._lock:
            self._provider_statuses[provider_id] = status.upper().strip()

    def record_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a telemetry or diagnostic metric."""
        with self._lock:
            if metric_name in self._counters:
                self._counters[metric_name] += int(value)
            else:
                self._gauges[metric_name] = float(value)

    def record_error(
        self,
        operation: str,
        error_code: str,
        message: str,
        provider_id: Optional[str] = None,
    ) -> None:
        """Record an error event with safe sanitization and bounded length."""
        with self._lock:
            self._counters["requests_failed"] += 1

            sanitized_msg = self._sanitize_message(message)
            if len(sanitized_msg) > 256:
                sanitized_msg = sanitized_msg[:253] + "..."

            err_record = {
                "timestamp": time.time(),
                "operation": operation,
                "error_code": error_code,
                "provider_id": provider_id,
                "message": sanitized_msg,
            }
            self._recent_errors.append(err_record)
            if len(self._recent_errors) > self._max_error_history:
                self._recent_errors.pop(0)

    def get_health_status(self) -> Dict[str, Any]:
        """Return operational health status dictionary adhering to ISatelliteDiagnostics."""
        with self._lock:
            is_healthy = self._module_lifecycle_state in ("INITIALIZED", "RUNNING")
            return {
                "module": "satellite",
                "status": "HEALTHY" if is_healthy else "DEGRADED",
                "lifecycle_state": self._module_lifecycle_state,
                "providers": dict(self._provider_statuses),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "recent_errors_count": len(self._recent_errors),
                "recent_errors": list(self._recent_errors[-5:]),
            }

    def _sanitize_message(self, msg: str) -> str:
        """Scrub potential tokens, keys, passwords from message."""
        scrubbed = msg
        sensitive_keywords = ["key", "secret", "token", "password", "bearer"]
        for word in sensitive_keywords:
            if word in scrubbed.lower():
                import re
                scrubbed = re.sub(
                    rf"({word}[=:\s]+)[^\s,;]+",
                    r"\1***",
                    scrubbed,
                    flags=re.IGNORECASE,
                )
        return scrubbed
