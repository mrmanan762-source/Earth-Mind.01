"""Satellite Data Ingestion Engine for EarthMind Satellite Module (Stage D3).

Implements Component 5 (ISatelliteIngestionDetector).
Handles:
- Safe ingestion of raw satellite data bytes or files
- Format detection via `SatelliteFormatDetector`
- SHA-256 cryptographic integrity hash calculation
- Safe storage persistence via `ISatelliteCacheStorageAdapter`
- Emits immutable `SatelliteRawDataReference` pointers
- Container & payload size boundary validation
"""

import hashlib
import time
import uuid
from typing import Any, Dict, Optional

from core.interfaces.satellite import (
    ISatelliteCacheStorageAdapter,
    ISatelliteIngestionDetector,
    ISatelliteMetadataExtractor,
)
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataFormat,
    SatelliteDatasetMetadata,
    SatelliteRawDataReference,
)
from modules.satellite.errors import (
    SatelliteIngestionError,
    SatelliteInvalidArgumentError,
    SatelliteUnsupportedFormatError,
)
from modules.satellite.formats import SatelliteFormatDetector
from modules.satellite.metadata_extractor import SatelliteMetadataExtractor
from modules.satellite.storage import InMemorySatelliteStorageAdapter

logger = get_logger("modules.satellite.ingestion")


class SatelliteIngestionEngine(ISatelliteIngestionDetector):
    """Component 5: Ingestion gateway and format detection for satellite assets."""

    def __init__(
        self,
        storage_adapter: Optional[ISatelliteCacheStorageAdapter] = None,
        format_detector: Optional[SatelliteFormatDetector] = None,
        metadata_extractor: Optional[SatelliteMetadataExtractor] = None,
        max_file_size_bytes: int = 1024 * 1024 * 1024,  # 1 GB
        retention_days: int = 7,
    ):
        self._storage = storage_adapter or InMemorySatelliteStorageAdapter()
        self._format_detector = format_detector or SatelliteFormatDetector()
        self._metadata_extractor = metadata_extractor or SatelliteMetadataExtractor()
        self._max_file_size_bytes = max_file_size_bytes
        self._retention_days = retention_days

    @property
    def storage_adapter(self) -> ISatelliteCacheStorageAdapter:
        return self._storage

    @property
    def format_detector(self) -> SatelliteFormatDetector:
        return self._format_detector

    def detect_format(self, payload_sample: bytes, file_name: Optional[str] = None) -> SatelliteDataFormat:
        """Detect satellite data format using configured detector."""
        return self._format_detector.detect_format(payload_sample=payload_sample, file_name=file_name)

    def ingest_raw_data(
        self,
        dataset_id: str,
        provider_id: str,
        data_bytes: bytes,
        data_format: SatelliteDataFormat,
        file_name: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        manifest_payload: Optional[Dict[str, Any]] = None,
    ) -> SatelliteRawDataReference:
        """
        Safely ingest raw satellite asset bytes, verify integrity, persist, and return reference.
        Conforms to ISatelliteIngestionDetector.
        """
        if not dataset_id or not dataset_id.strip():
            raise SatelliteInvalidArgumentError(
                details="dataset_id cannot be empty during raw data ingestion.",
                operation="ingest_raw_data",
            )
        if not provider_id or not provider_id.strip():
            raise SatelliteInvalidArgumentError(
                details="provider_id cannot be empty during raw data ingestion.",
                operation="ingest_raw_data",
            )
        if data_bytes is None:
            raise SatelliteIngestionError(
                details=f"Raw data bytes cannot be None for dataset '{dataset_id}'.",
                operation="ingest_raw_data",
            )

        size_bytes = len(data_bytes)
        if size_bytes == 0:
            raise SatelliteIngestionError(
                details=f"Cannot ingest empty byte stream (0 bytes) for dataset '{dataset_id}'.",
                operation="ingest_raw_data",
            )

        if size_bytes > self._max_file_size_bytes:
            raise SatelliteIngestionError(
                details=f"Asset size ({size_bytes} bytes) exceeds maximum limit of {self._max_file_size_bytes} bytes.",
                operation="ingest_raw_data",
            )

        # 1. Compute SHA-256
        sha256_hash = hashlib.sha256(data_bytes).hexdigest()
        if expected_sha256 and expected_sha256.lower().strip() != sha256_hash.lower().strip():
            raise SatelliteIngestionError(
                details=f"Integrity check failed: expected hash {expected_sha256}, got {sha256_hash}.",
                operation="ingest_raw_data",
            )

        # 2. Format validation / detection
        try:
            detected_format = self._format_detector.detect_format(
                payload_sample=data_bytes[:1024],
                file_name=file_name,
            )
            effective_format = data_format if data_format != SatelliteDataFormat.RAW_BINARY else detected_format
        except SatelliteUnsupportedFormatError:
            effective_format = data_format

        # 3. Create raw reference ID and storage URI
        ref_id = f"ref_{uuid.uuid4().hex[:12]}"
        storage_uri = f"earthmind://satellite/raw/{provider_id}/{dataset_id}/{ref_id}"

        # 4. Retention timestamp
        expires_ts = time.time() + (self._retention_days * 86400.0)
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_ts))

        raw_ref = SatelliteRawDataReference(
            reference_id=ref_id,
            dataset_id=dataset_id,
            provider_id=provider_id,
            storage_uri=storage_uri,
            data_format=effective_format,
            size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            retention_expires_at=expires_at,
        )

        # 5. Persist reference and bytes in storage adapter
        try:
            self._storage.store_raw_reference(raw_ref)
            if hasattr(self._storage, "store_raw_payload"):
                self._storage.store_raw_payload(ref_id, data_bytes)
        except Exception as exc:
            raise SatelliteIngestionError(
                details=f"Failed to persist raw asset in storage adapter: {exc}",
                operation="ingest_raw_data",
            ) from exc

        logger.info(f"Ingested raw satellite asset '{dataset_id}' ({size_bytes} bytes, format={effective_format.value}, ref={ref_id}).")
        return raw_ref

    def ingest_and_extract(
        self,
        dataset_id: str,
        provider_id: str,
        data_bytes: bytes,
        data_format: SatelliteDataFormat,
        file_name: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        manifest_payload: Optional[Dict[str, Any]] = None,
    ) -> SatelliteDatasetMetadata:
        """Combined pipeline: Ingest raw data, store payload, and extract validated metadata."""
        raw_ref = self.ingest_raw_data(
            dataset_id=dataset_id,
            provider_id=provider_id,
            data_bytes=data_bytes,
            data_format=data_format,
            file_name=file_name,
            expected_sha256=expected_sha256,
            manifest_payload=manifest_payload,
        )

        return self._metadata_extractor.extract_metadata(
            raw_ref=raw_ref,
            manifest_payload=manifest_payload,
        )
