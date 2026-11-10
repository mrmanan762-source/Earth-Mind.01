"""Satellite Catalog Discovery Engine for EarthMind Satellite Module (Stage D3).

Implements Component 3 (ISatelliteCatalogDiscovery).
Responsibilities:
- Accepts validated SatelliteDataRequest
- Identifies registered providers matching requested constellations & sensor types
- Dispatches catalog queries across eligible providers
- Merges, ranks, and normalizes discovery responses
- Selects optimal dataset (lowest cloud cover, closest temporal alignment, highest resolution)
- Reports unsupported searches and unavailable providers safely
"""

import time
from typing import Any, Dict, List, Optional

from core.interfaces.satellite import ISatelliteCatalogDiscovery
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteProvider,
)
from modules.satellite.adapters import SatelliteAdapterRegistry
from modules.satellite.capabilities import ProviderCapabilityManager
from modules.satellite.catalog import SatelliteDataCatalog
from modules.satellite.errors import (
    SatelliteInvalidArgumentError,
    SatelliteProviderUnavailableError,
)
from modules.satellite.registry import SatelliteProviderRegistry

logger = get_logger("modules.satellite.discovery")


class SatelliteDiscoveryEngine(ISatelliteCatalogDiscovery):
    """Component 3: Search and discovery engine across multiple satellite catalogs."""

    def __init__(
        self,
        provider_registry: SatelliteProviderRegistry,
        adapter_registry: SatelliteAdapterRegistry,
        capability_manager: ProviderCapabilityManager,
        catalog: Optional[SatelliteDataCatalog] = None,
    ):
        self._provider_registry = provider_registry
        self._adapter_registry = adapter_registry
        self._capability_manager = capability_manager
        self._catalog = catalog or SatelliteDataCatalog()

    def discover_datasets(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        """
        Search across all eligible registered providers and rank suitable datasets.
        Conforms to ISatelliteCatalogDiscovery.discover_datasets.
        """
        if not request:
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest cannot be None.",
                operation="discover_datasets",
            )

        # 1. First, search local catalog for historical/known datasets
        local_matches = self._catalog.search_spatial_temporal(
            latitude=request.geospatial.latitude,
            longitude=request.geospatial.longitude,
            target_date=request.temporal_window.acquisition_date,
            max_cloud_cover=request.max_cloud_cover_percentage,
            constellations=request.target_constellations,
        )

        # 2. Determine eligible providers based on request criteria
        eligible_providers = self._resolve_eligible_providers(request)
        if not eligible_providers and not local_matches:
            logger.warning(f"No active provider supports requested constellations: {request.target_constellations}")
            return []

        all_candidates: List[SatelliteDatasetMetadata] = list(local_matches)
        seen_ids = {m.dataset_id for m in local_matches}

        # 3. Query external provider adapters
        for prov_id in eligible_providers:
            adapter = self._adapter_registry.get_adapter(prov_id)
            if not adapter or not adapter.is_available:
                logger.info(f"Skipping unavailable provider '{prov_id}' during catalog discovery.")
                continue

            try:
                prov_results = adapter.search_catalog(request)
                for item in prov_results:
                    if item.dataset_id not in seen_ids:
                        all_candidates.append(item)
                        seen_ids.add(item.dataset_id)
                        # Register in local catalog
                        self._catalog.register_dataset(item, allow_update=True)
            except Exception as exc:
                logger.warning(f"Provider '{prov_id}' search failed: {exc}")

        # 4. Filter by request cloud cover threshold
        filtered = [
            c for c in all_candidates
            if c.cloud_cover_percentage <= request.max_cloud_cover_percentage
        ]

        # 5. Deterministic ranking:
        # Score based on cloud cover (primary) and spatial resolution (secondary)
        filtered.sort(
            key=lambda c: (
                c.cloud_cover_percentage,
                c.geospatial.spatial_resolution_meters or 10.0,
            )
        )

        logger.info(f"Discovery completed for request '{request.request_id}': found {len(filtered)} candidate scenes.")
        return filtered

    def select_optimal_dataset(
        self,
        candidates: List[SatelliteDatasetMetadata],
        request: SatelliteDataRequest,
    ) -> Optional[SatelliteDatasetMetadata]:
        """
        Select the highest-quality, lowest cloud-cover dataset from candidates.
        Conforms to ISatelliteCatalogDiscovery.select_optimal_dataset.
        """
        if not candidates:
            return None

        # Filter candidates meeting cloud threshold
        eligible = [
            c for c in candidates
            if c.cloud_cover_percentage <= request.max_cloud_cover_percentage
        ]
        if not eligible:
            return None

        target_date_str = request.temporal_window.acquisition_date.split("T")[0]
        try:
            target_ts = time.mktime(time.strptime(target_date_str, "%Y-%m-%d"))
        except Exception:
            target_ts = time.time()

        def _score(candidate: SatelliteDatasetMetadata) -> float:
            # Lower score is better
            # Component 1: Cloud cover (weight 1.0 per %)
            cloud_score = candidate.cloud_cover_percentage

            # Component 2: Temporal distance in days (weight 0.5 per day)
            temporal_score = 0.0
            try:
                cand_date_str = candidate.temporal.acquisition_date.split("T")[0]
                cand_ts = time.mktime(time.strptime(cand_date_str, "%Y-%m-%d"))
                diff_days = abs(target_ts - cand_ts) / 86400.0
                temporal_score = diff_days * 0.5
            except Exception:
                temporal_score = 10.0

            # Component 3: Prefer LEVEL-2A (surface reflectance) over LEVEL-1C
            level_penalty = 0.0 if "2A" in candidate.processing_level.upper() else 10.0

            return cloud_score + temporal_score + level_penalty

        ranked = sorted(eligible, key=_score)
        optimal = ranked[0]
        logger.info(f"Selected optimal dataset '{optimal.dataset_id}' for request '{request.request_id}'.")
        return optimal

    def _resolve_eligible_providers(self, request: SatelliteDataRequest) -> List[str]:
        """Resolve list of active provider IDs capable of satisfying request."""
        target_constellations = request.target_constellations or ["Sentinel-2", "Landsat-8/9"]
        candidate_pids = set()

        for constellation in target_constellations:
            pids = self._capability_manager.list_capable_providers(constellation=constellation)
            for pid in pids:
                if self._provider_registry.is_provider_available(pid):
                    candidate_pids.add(pid)

        # Fallback if no specific constellation matched: all active providers
        if not candidate_pids:
            for p in self._provider_registry.list_providers():
                if self._provider_registry.is_provider_available(p.provider_id):
                    candidate_pids.add(p.provider_id)

        return list(candidate_pids)
