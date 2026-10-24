"""Health and diagnostics reporting for EarthMind application architecture.

Clearly distinguishes:
1. Process Health: Process alive status, uptime, RSS memory usage.
2. Dependency Health: Operational status of individual subsystems and vector stores (Qdrant, embedding provider, sparse provider, reranker, model layer).
3. End-to-End Readiness: True capability to serve RAG queries end-to-end (requiring critical dependencies to be operational, not merely process liveness).
"""

import os
import sys
import time
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from core.logging.logger import get_logger

logger = get_logger("core.observability.health")

_PROCESS_START_TIME = time.time()


class SubsystemHealth(BaseModel):
    """Health status representation for a single subsystem or dependency."""

    name: str = Field(..., description="Name of the subsystem or dependency")
    status: str = Field("UNKNOWN", description="Status string: HEALTHY, DEGRADED, UNHEALTHY, DISABLED")
    available: bool = Field(False, description="Boolean flag indicating operational availability")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic details or error messages")


class SystemHealthReport(BaseModel):
    """Complete system health report distinguishing process health, dependency health, and readiness."""

    process_healthy: bool = Field(True, description="True if process is alive and initialized")
    uptime_seconds: float = Field(..., description="Process uptime in seconds")
    memory_rss_bytes: Optional[int] = Field(None, description="Resident Set Size memory usage in bytes")
    readiness_status: str = Field("NOT_READY", description="Overall readiness: READY, DEGRADED_READY, NOT_READY")
    is_ready_e2e: bool = Field(False, description="Strict boolean indicating full end-to-end RAG query capability")
    dependencies: Dict[str, SubsystemHealth] = Field(default_factory=dict, description="Subsystem dependency statuses")
    timestamp: float = Field(default_factory=time.time, description="Timestamp of health check execution")


class HealthDiagnostics:
    """Evaluates process health, dependency health, and end-to-end system readiness."""

    @staticmethod
    def get_process_health() -> Dict[str, Any]:
        """Collect lightweight process health telemetry."""
        uptime = round(time.time() - _PROCESS_START_TIME, 2)
        rss_bytes = None

        try:
            # Try resource stdlib module first
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                rss_bytes = usage.ru_maxrss
            else:
                rss_bytes = usage.ru_maxrss * 1024
        except Exception:
            pass

        return {
            "process_alive": True,
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
            "uptime_seconds": uptime,
            "memory_rss_bytes": rss_bytes,
        }

    @classmethod
    def evaluate_system_health(
        self,
        qdrant_adapter: Optional[Any] = None,
        embedding_provider: Optional[Any] = None,
        sparse_provider: Optional[Any] = None,
        reranker_provider: Optional[Any] = None,
        reasoning_model: Optional[Any] = None,
    ) -> SystemHealthReport:
        """
        Evaluate full system health and end-to-end readiness.

        Strict Readiness Rule:
        Do NOT report end-to-end readiness as healthy merely because the process is alive.
        Readiness requires operational vector storage and query embedding capabilities.
        """
        proc_info = self.get_process_health()
        deps: Dict[str, SubsystemHealth] = {}

        # 1. Qdrant / Vector Store Health
        qdrant_healthy = False
        if qdrant_adapter is not None:
            try:
                available = bool(qdrant_adapter.is_available() if hasattr(qdrant_adapter, "is_available") else qdrant_adapter.health_check())
                qdrant_healthy = available
                deps["qdrant"] = SubsystemHealth(
                    name="qdrant",
                    status="HEALTHY" if available else "UNHEALTHY",
                    available=available,
                    details={"backend": getattr(qdrant_adapter, "adapter_type", "qdrant")},
                )
            except Exception as e:
                deps["qdrant"] = SubsystemHealth(
                    name="qdrant",
                    status="UNHEALTHY",
                    available=False,
                    details={"error": str(e)},
                )
        else:
            deps["qdrant"] = SubsystemHealth(
                name="qdrant",
                status="UNKNOWN",
                available=False,
                details={"message": "No Qdrant adapter attached"},
            )

        # 2. Embedding Provider Health
        emb_healthy = False
        if embedding_provider is not None:
            try:
                available = bool(embedding_provider.is_available())
                emb_healthy = available
                deps["embedding_provider"] = SubsystemHealth(
                    name="embedding_provider",
                    status="HEALTHY" if available else "UNHEALTHY",
                    available=available,
                    details={"provider": getattr(embedding_provider, "provider_name", "embedding")},
                )
            except Exception as e:
                deps["embedding_provider"] = SubsystemHealth(
                    name="embedding_provider",
                    status="UNHEALTHY",
                    available=False,
                    details={"error": str(e)},
                )
        else:
            deps["embedding_provider"] = SubsystemHealth(
                name="embedding_provider",
                status="UNKNOWN",
                available=False,
                details={"message": "No embedding provider attached"},
            )

        # 3. Sparse Representation Provider Health
        if sparse_provider is not None:
            try:
                available = bool(sparse_provider.is_available())
                deps["sparse_provider"] = SubsystemHealth(
                    name="sparse_provider",
                    status="HEALTHY" if available else "DEGRADED",
                    available=available,
                    details={"provider": getattr(sparse_provider, "provider_name", "sparse")},
                )
            except Exception as e:
                deps["sparse_provider"] = SubsystemHealth(
                    name="sparse_provider",
                    status="DEGRADED",
                    available=False,
                    details={"error": str(e)},
                )

        # 4. Reranker Health
        if reranker_provider is not None:
            try:
                available = bool(reranker_provider.is_available() if hasattr(reranker_provider, "is_available") else True)
                deps["reranker"] = SubsystemHealth(
                    name="reranker",
                    status="HEALTHY" if available else "DEGRADED",
                    available=available,
                    details={"provider": getattr(reranker_provider, "provider_name", "reranker")},
                )
            except Exception as e:
                deps["reranker"] = SubsystemHealth(
                    name="reranker",
                    status="DEGRADED",
                    available=False,
                    details={"error": str(e)},
                )

        # 5. Reasoning Model Health
        if reasoning_model is not None:
            try:
                st = reasoning_model.status() if hasattr(reasoning_model, "status") else {"ready": True}
                is_ready = bool(st.get("ready", True) if isinstance(st, dict) else st)
                deps["reasoning_model"] = SubsystemHealth(
                    name="reasoning_model",
                    status="HEALTHY" if is_ready else "DEGRADED",
                    available=is_ready,
                    details=st if isinstance(st, dict) else {},
                )
            except Exception as e:
                deps["reasoning_model"] = SubsystemHealth(
                    name="reasoning_model",
                    status="DEGRADED",
                    available=False,
                    details={"error": str(e)},
                )

        # Determine Strict Readiness Semantics
        # Critical dependencies for baseline RAG: Qdrant AND Embedding Provider
        if qdrant_healthy and emb_healthy:
            # Check if optional components are degraded
            any_degraded = any(d.status == "DEGRADED" or not d.available for k, d in deps.items() if k not in ("qdrant", "embedding_provider"))
            if any_degraded:
                readiness_status = "DEGRADED_READY"
                is_ready_e2e = True
            else:
                readiness_status = "READY"
                is_ready_e2e = True
        else:
            readiness_status = "NOT_READY"
            is_ready_e2e = False

        return SystemHealthReport(
            process_healthy=True,
            uptime_seconds=proc_info["uptime_seconds"],
            memory_rss_bytes=proc_info["memory_rss_bytes"],
            readiness_status=readiness_status,
            is_ready_e2e=is_ready_e2e,
            dependencies=deps,
        )
