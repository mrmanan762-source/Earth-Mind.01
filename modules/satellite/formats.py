"""Satellite Data Format Capability Registry and Detection Engine (Stage D3).

Implements format capabilities and sniffing for satellite datasets conforming to
ISatelliteIngestionDetector.detect_format.

Supports:
- GeoTIFF / TIFF
- Cloud-Optimized GeoTIFF (COG)
- NetCDF (Classic & NetCDF4/HDF5)
- HDF5
- SAFE packages (Sentinel zip or directory structure)
- ZARR metadata/stores
- JSON / GeoJSON
- CSV
- Raw Binary streams
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.logging.logger import get_logger
from core.schemas.satellite import SatelliteDataFormat
from modules.satellite.errors import SatelliteUnsupportedFormatError

logger = get_logger("modules.satellite.formats")


class SatelliteFormatCapability(BaseModel):
    """Metadata describing a supported satellite data format capability."""
    format: SatelliteDataFormat
    mime_types: List[str] = Field(default_factory=list)
    file_extensions: List[str] = Field(default_factory=list)
    magic_bytes_signatures: List[bytes] = Field(default_factory=list)
    is_binary: bool = True
    description: str = ""
    typical_container: str = "single_file"


class SatelliteFormatDetector:
    """Detects satellite asset formats via magic bytes, headers, and extensions."""

    def __init__(self, max_sample_bytes: int = 10 * 1024 * 1024):
        self._max_sample_bytes = max_sample_bytes
        self._capabilities: Dict[SatelliteDataFormat, SatelliteFormatCapability] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        """Register all D1 supported satellite data formats."""
        # 1. GeoTIFF
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.GEOTIFF,
                mime_types=["image/tiff", "image/geotiff"],
                file_extensions=[".tif", ".tiff", ".geotiff"],
                magic_bytes_signatures=[b"II*\x00", b"MM\x00*"],
                is_binary=True,
                description="Georeferenced Tagged Image File Format raster",
                typical_container="single_file",
            )
        )

        # 2. COG (Cloud Optimized GeoTIFF)
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.COG,
                mime_types=["image/tiff; application=geotiff; profile=cloud-optimized", "image/tiff"],
                file_extensions=[".cog.tif", ".cog.tiff", ".tif", ".tiff"],
                magic_bytes_signatures=[b"II*\x00", b"MM\x00*"],
                is_binary=True,
                description="Cloud Optimized GeoTIFF with internal tiling and overviews",
                typical_container="single_file",
            )
        )

        # 3. NetCDF
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.NETCDF,
                mime_types=["application/x-netcdf", "application/netcdf"],
                file_extensions=[".nc", ".nc4", ".netcdf"],
                magic_bytes_signatures=[b"CDF\x01", b"CDF\x02", b"\x89HDF\r\n\x1a\n"],
                is_binary=True,
                description="Network Common Data Form multidimensional array",
                typical_container="single_file",
            )
        )

        # 4. HDF5
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.HDF5,
                mime_types=["application/x-hdf5", "application/x-hdf"],
                file_extensions=[".h5", ".hdf5", ".he5"],
                magic_bytes_signatures=[b"\x89HDF\r\n\x1a\n"],
                is_binary=True,
                description="Hierarchical Data Format version 5 scientific container",
                typical_container="single_file",
            )
        )

        # 5. SAFE (Sentinel Standard Archive Format for Europe)
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.SAFE,
                mime_types=["application/zip", "application/x-safe"],
                file_extensions=[".safe", ".zip"],
                magic_bytes_signatures=[b"PK\x03\x04"],  # Standard ZIP signature for .SAFE.zip packages
                is_binary=True,
                description="Standard Archive Format for Europe package for Copernicus Sentinel",
                typical_container="package_archive",
            )
        )

        # 6. ZARR
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.ZARR,
                mime_types=["application/x-zarr"],
                file_extensions=[".zarr", ".zgroup", ".zarray", ".zmetadata"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="Zarr chunked, compressed N-dimensional array storage",
                typical_container="directory_store",
            )
        )

        # 7. JSON
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.JSON,
                mime_types=["application/json", "text/json"],
                file_extensions=[".json"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="JavaScript Object Notation / STAC Item / STAC Collection",
                typical_container="single_file",
            )
        )

        # 8. GEOJSON
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.GEOJSON,
                mime_types=["application/geo+json"],
                file_extensions=[".geojson"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="GeoJSON spatial feature collection",
                typical_container="single_file",
            )
        )

        # 9. CSV
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.CSV,
                mime_types=["text/csv", "application/csv", "text/plain"],
                file_extensions=[".csv"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="Comma-separated values numerical observation telemetry",
                typical_container="single_file",
            )
        )

        # 10. RAW_BINARY
        self.register_capability(
            SatelliteFormatCapability(
                format=SatelliteDataFormat.RAW_BINARY,
                mime_types=["application/octet-stream"],
                file_extensions=[".bin", ".raw", ".dat"],
                magic_bytes_signatures=[],
                is_binary=True,
                description="Raw binary telemetry stream or uncalibrated instrument dump",
                typical_container="single_file",
            )
        )

    def register_capability(self, capability: SatelliteFormatCapability) -> None:
        """Register or update a format capability."""
        self._capabilities[capability.format] = capability

    def get_capability(self, data_format: SatelliteDataFormat) -> Optional[SatelliteFormatCapability]:
        """Retrieve capability details for a format."""
        return self._capabilities.get(data_format)

    def list_supported_formats(self) -> List[SatelliteDataFormat]:
        """Return list of supported format enums."""
        return list(self._capabilities.keys())

    def detect_format(self, payload_sample: bytes, file_name: Optional[str] = None) -> SatelliteDataFormat:
        """
        Detect satellite data format from magic bytes, header, or file extension.
        Conforms to ISatelliteIngestionDetector.detect_format.
        """
        if not payload_sample and not file_name:
            raise SatelliteUnsupportedFormatError(
                data_format="EMPTY_PAYLOAD",
                details="Cannot detect format from empty payload sample and missing file name.",
            )

        if len(payload_sample) > self._max_sample_bytes:
            raise SatelliteUnsupportedFormatError(
                data_format=file_name or "LARGE_PAYLOAD",
                details=f"Payload sample size ({len(payload_sample)} bytes) exceeds maximum allowable limit of {self._max_sample_bytes} bytes.",
            )

        # 1. Check for SAFE package directory name
        if file_name and (file_name.endswith(".SAFE") or ".SAFE/" in file_name or ".SAFE\\" in file_name):
            return SatelliteDataFormat.SAFE

        # 2. Check magic byte signatures
        if payload_sample:
            # Check TIFF / GeoTIFF / COG
            if payload_sample.startswith(b"II*\x00") or payload_sample.startswith(b"MM\x00*"):
                if file_name and (".cog" in file_name.lower()):
                    return SatelliteDataFormat.COG
                return SatelliteDataFormat.GEOTIFF

            # Check NetCDF / HDF5
            if payload_sample.startswith(b"CDF\x01") or payload_sample.startswith(b"CDF\x02"):
                return SatelliteDataFormat.NETCDF
            if payload_sample.startswith(b"\x89HDF\r\n\x1a\n"):
                if file_name and file_name.lower().endswith((".nc", ".nc4")):
                    return SatelliteDataFormat.NETCDF
                return SatelliteDataFormat.HDF5

            # Check ZIP / SAFE archive
            if payload_sample.startswith(b"PK\x03\x04"):
                if file_name and (".SAFE" in file_name.upper() or "SENTINEL" in file_name.upper()):
                    return SatelliteDataFormat.SAFE
                # General zip containing satellite assets or SAFE package
                if file_name and file_name.lower().endswith(".safe"):
                    return SatelliteDataFormat.SAFE
                return SatelliteDataFormat.SAFE

            # Check Text: JSON, GeoJSON, CSV, ZARR
            stripped = payload_sample.lstrip()
            if stripped.startswith(b"{") or stripped.startswith(b"["):
                try:
                    text_str = stripped[:2048].decode("utf-8")
                    if '"type": "FeatureCollection"' in text_str or '"type": "Feature"' in text_str or '"type":"FeatureCollection"' in text_str:
                        return SatelliteDataFormat.GEOJSON
                    if "zarr_format" in text_str or ".zmetadata" in (file_name or ""):
                        return SatelliteDataFormat.ZARR
                    return SatelliteDataFormat.JSON
                except Exception:
                    return SatelliteDataFormat.JSON

            # Check CSV pattern
            try:
                text_sample = payload_sample[:1024].decode("utf-8", errors="ignore")
                if "," in text_sample and "\n" in text_sample and not any(ord(c) < 32 and c not in "\r\n\t" for c in text_sample[:256]):
                    return SatelliteDataFormat.CSV
            except Exception:
                pass

        # 3. Extension fallback
        if file_name:
            lower = file_name.lower()
            if lower.endswith(".cog.tif") or lower.endswith(".cog.tiff"):
                return SatelliteDataFormat.COG
            if lower.endswith(".geojson"):
                return SatelliteDataFormat.GEOJSON
            if lower.endswith(".json"):
                return SatelliteDataFormat.JSON
            if lower.endswith(".tif") or lower.endswith(".tiff") or lower.endswith(".geotiff"):
                return SatelliteDataFormat.GEOTIFF
            if lower.endswith(".nc") or lower.endswith(".nc4") or lower.endswith(".netcdf"):
                return SatelliteDataFormat.NETCDF
            if lower.endswith(".h5") or lower.endswith(".hdf5") or lower.endswith(".he5"):
                return SatelliteDataFormat.HDF5
            if lower.endswith(".safe") or lower.endswith(".safe.zip"):
                return SatelliteDataFormat.SAFE
            if lower.endswith(".zarr") or lower.endswith(".zmetadata"):
                return SatelliteDataFormat.ZARR
            if lower.endswith(".csv"):
                return SatelliteDataFormat.CSV
            if lower.endswith(".bin") or lower.endswith(".raw") or lower.endswith(".dat"):
                return SatelliteDataFormat.RAW_BINARY

        # Check if raw binary is appropriate fallback
        if payload_sample and len(payload_sample) > 0:
            return SatelliteDataFormat.RAW_BINARY

        target_name = file_name or "UNKNOWN"
        raise SatelliteUnsupportedFormatError(
            data_format=target_name,
            details=f"Unrecognized or unsupported satellite data format for '{target_name}'.",
        )
