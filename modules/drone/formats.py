"""Data Format Capability Registry for EarthMind Drone Module (Stage D2).

Manages supported raw data formats, MIME sniffing, magic byte detection,
and adapter capability associations.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.logging.logger import get_logger
from core.schemas.drone import DroneDataFormat
from modules.drone.errors import UnsupportedFormatError

logger = get_logger("modules.drone.formats")


class FormatCapability(BaseModel):
    """Metadata describing a supported drone data format capability."""
    format: DroneDataFormat
    mime_types: List[str] = Field(default_factory=list)
    file_extensions: List[str] = Field(default_factory=list)
    magic_bytes_signatures: List[bytes] = Field(default_factory=list)
    is_binary: bool = True
    description: str = ""
    required_adapter_category: str = "general"


class DataFormatRegistry:
    """Registry maintaining recognized drone sensor data formats and sniffing capabilities."""

    def __init__(self):
        self._formats: Dict[DroneDataFormat, FormatCapability] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        """Register default approved EarthMind drone data format capabilities."""
        # 1. GeoTIFF / TIFF
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.GEOTIFF,
                mime_types=["image/tiff", "image/geotiff"],
                file_extensions=[".tif", ".tiff", ".geotiff"],
                magic_bytes_signatures=[b"II*\x00", b"MM\x00*"],  # Little-endian and Big-endian TIFF
                is_binary=True,
                description="Georeferenced raster imagery",
                required_adapter_category="multispectral",
            )
        )

        # 2. NetCDF
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.NETCDF,
                mime_types=["application/x-netcdf", "application/netcdf"],
                file_extensions=[".nc", ".nc4", ".netcdf"],
                magic_bytes_signatures=[b"CDF\x01", b"CDF\x02", b"\x89HDF\r\n\x1a\n"],  # Classic and NetCDF4/HDF5
                is_binary=True,
                description="Network Common Data Form scientific array",
                required_adapter_category="environmental",
            )
        )

        # 3. HDF5
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.HDF5,
                mime_types=["application/x-hdf5", "application/x-hdf"],
                file_extensions=[".h5", ".hdf5"],
                magic_bytes_signatures=[b"\x89HDF\r\n\x1a\n"],
                is_binary=True,
                description="Hierarchical Data Format v5",
                required_adapter_category="hyperspectral",
            )
        )

        # 4. CSV
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.CSV,
                mime_types=["text/csv", "application/csv", "text/plain"],
                file_extensions=[".csv"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="Comma-separated values telemetry",
                required_adapter_category="environmental",
            )
        )

        # 5. JSON
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.JSON,
                mime_types=["application/json", "text/json", "application/geo+json"],
                file_extensions=[".json", ".geojson"],
                magic_bytes_signatures=[],
                is_binary=False,
                description="JavaScript Object Notation / GeoJSON",
                required_adapter_category="general",
            )
        )

        # 6. LAS / LAZ
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.LAS,
                mime_types=["application/vnd.las", "application/octet-stream"],
                file_extensions=[".las", ".laz"],
                magic_bytes_signatures=[b"LASF"],
                is_binary=True,
                description="ASPRS LAS LiDAR point cloud",
                required_adapter_category="lidar",
            )
        )

        # 7. POINT_CLOUD
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.POINT_CLOUD,
                mime_types=["application/octet-stream", "text/plain"],
                file_extensions=[".pcd", ".ply", ".xyz"],
                magic_bytes_signatures=[b"ply\n", b"# .PCD"],
                is_binary=True,
                description="3D point cloud format",
                required_adapter_category="lidar",
            )
        )

        # 8. RAW_BINARY
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.RAW_BINARY,
                mime_types=["application/octet-stream"],
                file_extensions=[".bin", ".raw", ".dat"],
                magic_bytes_signatures=[],
                is_binary=True,
                description="Raw binary hardware telemetry stream",
                required_adapter_category="general",
            )
        )

        # 9. JPEG_METADATA
        self.register_capability(
            FormatCapability(
                format=DroneDataFormat.JPEG_METADATA,
                mime_types=["image/jpeg"],
                file_extensions=[".jpg", ".jpeg"],
                magic_bytes_signatures=[b"\xff\xd8\xff"],
                is_binary=True,
                description="JPEG image with EXIF/XMP spatial telemetry tags",
                required_adapter_category="camera",
            )
        )

    def register_capability(self, capability: FormatCapability) -> None:
        """Register or update a format capability."""
        self._formats[capability.format] = capability
        logger.debug(f"Registered format capability: {capability.format.value}")

    def get_capability(self, data_format: DroneDataFormat) -> Optional[FormatCapability]:
        """Retrieve capability definition for a specific DroneDataFormat."""
        return self._formats.get(data_format)

    def list_supported_formats(self) -> List[DroneDataFormat]:
        """Return list of all registered DroneDataFormat enums."""
        return list(self._formats.keys())

    def is_supported(self, data_format: Any) -> bool:
        """Check if format enum is recognized and supported."""
        if isinstance(data_format, str):
            try:
                data_format = DroneDataFormat(data_format)
            except ValueError:
                return False
        return data_format in self._formats

    def detect_format_from_bytes(self, sample_bytes: bytes, filename_hint: Optional[str] = None) -> DroneDataFormat:
        """Detect DroneDataFormat by inspecting magic bytes, with fallback to filename extension."""
        if not sample_bytes and not filename_hint:
            raise UnsupportedFormatError(
                data_format="EMPTY_PAYLOAD",
                details="Cannot detect format from empty payload and no filename hint."
            )

        # 1. Magic byte sniffing
        if sample_bytes:
            for fmt, cap in self._formats.items():
                for sig in cap.magic_bytes_signatures:
                    if sample_bytes.startswith(sig):
                        return fmt

            # Plain text check for JSON or CSV
            stripped = sample_bytes.lstrip()
            if stripped.startswith(b"{") or stripped.startswith(b"["):
                return DroneDataFormat.JSON
            try:
                text_sample = sample_bytes[:1024].decode("utf-8", errors="ignore")
                if "," in text_sample and "\n" in text_sample and not any(ord(c) < 32 and c not in "\r\n\t" for c in text_sample):
                    return DroneDataFormat.CSV
            except Exception:
                pass

        # 2. Filename extension fallback
        if filename_hint:
            ext = "." + filename_hint.split(".")[-1].lower() if "." in filename_hint else ""
            for fmt, cap in self._formats.items():
                if ext in cap.file_extensions:
                    return fmt

        # If magic bytes / extension unrecognized:
        detected_name = filename_hint or "UNKNOWN_STREAM"
        raise UnsupportedFormatError(
            data_format=detected_name,
            details=f"Format '{detected_name}' is not supported by EarthMind Drone Module."
        )

    def validate_payload_format(self, declared_format: DroneDataFormat, payload_sample: Optional[bytes] = None) -> bool:
        """Validate that a declared format is supported and matches payload sample signatures if provided."""
        cap = self.get_capability(declared_format)
        if not cap:
            raise UnsupportedFormatError(
                data_format=declared_format.value,
                details=f"Declared format '{declared_format.value}' is not registered."
            )

        if payload_sample and cap.magic_bytes_signatures:
            # If magic byte signatures exist for format, ensure payload starts with one of them
            matched = any(payload_sample.startswith(sig) for sig in cap.magic_bytes_signatures)
            if not matched:
                raise UnsupportedFormatError(
                    data_format=declared_format.value,
                    details=f"Payload bytes do not match expected magic signature for format '{declared_format.value}'."
                )

        return True
