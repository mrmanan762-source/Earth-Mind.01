"""Raw Data Parsing Engine for EarthMind Drone Module (Stage D3).

Implements Component 4 (IRawDataProcessor).
Parses supported raw sensor data formats into structured channel records.
Validates file structure, encoding, required fields, and payload integrity.
Rejects malformed, truncated, unsupported, or ambiguous payloads safely.
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Union

from core.interfaces.drone import IRawDataProcessor
from core.logging.logger import get_logger
from core.schemas.drone import DroneDataFormat
from modules.drone.errors import (
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
    InvalidSensorDataError,
    UnsupportedFormatError,
)

logger = get_logger("modules.drone.parser")


class RawDataParser(IRawDataProcessor):
    """Component 4: Raw payload parser and structural validator."""

    def __init__(self, max_payload_chars: int = 5_000_000):
        self._max_payload_chars = max_payload_chars

    def parse_raw_data(self, payload: Any, data_format: DroneDataFormat) -> Dict[str, Any]:
        """
        Parse raw payload into structured channel records.

        Args:
            payload: bytes, string, or parsed dictionary / list.
            data_format: DroneDataFormat enum.

        Returns:
            Dict[str, Any] containing:
                - format: str (data_format value)
                - channels: Dict[str, Any] mapping channel names to values/arrays
                - measurements: List[Dict[str, Any]] individual measurement dictionaries
                - metadata: Dict[str, Any] parsed header/payload attributes
                - sample_count: int
        """
        if payload is None:
            raise InsufficientDroneDataError(
                details="Raw sensor payload is None or empty.",
                operation="parse_raw_data",
            )

        if isinstance(data_format, str):
            try:
                data_format = DroneDataFormat(data_format)
            except ValueError:
                raise UnsupportedFormatError(
                    data_format=str(data_format),
                    details=f"Format '{data_format}' is not recognized.",
                    operation="parse_raw_data",
                )

        # Dispatch based on format
        if data_format == DroneDataFormat.JSON:
            return self._parse_json(payload)
        elif data_format == DroneDataFormat.CSV:
            return self._parse_csv(payload)
        elif data_format == DroneDataFormat.RAW_BINARY:
            return self._parse_raw_binary(payload)
        elif data_format in (DroneDataFormat.GEOTIFF, DroneDataFormat.NETCDF, DroneDataFormat.HDF5, DroneDataFormat.LAS, DroneDataFormat.POINT_CLOUD, DroneDataFormat.JPEG_METADATA):
            # For formats when supplied as structured synthetic payload or binary stream
            if isinstance(payload, dict):
                return self._parse_structured_dict(payload, data_format)
            elif isinstance(payload, (bytes, bytearray)):
                return self._parse_raster_or_binary_buffer(payload, data_format)
            else:
                raise InvalidSensorDataError(
                    details=f"Unsupported payload type '{type(payload).__name__}' for format {data_format.value}.",
                    operation="parse_raw_data",
                )
        else:
            raise UnsupportedFormatError(
                data_format=data_format.value,
                details=f"Parser engine does not currently implement parser for '{data_format.value}'.",
                operation="parse_raw_data",
            )

    def _parse_json(self, payload: Any) -> Dict[str, Any]:
        """Parse and validate JSON payload."""
        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvalidSensorDataError(
                    details=f"JSON payload is not valid UTF-8: {exc}",
                    operation="parse_raw_data",
                )

        if isinstance(payload, str):
            payload_str = payload.strip()
            if not payload_str:
                raise InsufficientDroneDataError(
                    details="Empty JSON string payload.",
                    operation="parse_raw_data",
                )
            if len(payload_str) > self._max_payload_chars:
                raise InvalidSensorDataError(
                    details=f"JSON payload exceeds max characters limit ({len(payload_str)} > {self._max_payload_chars}).",
                    operation="parse_raw_data",
                )
            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError as exc:
                raise InvalidSensorDataError(
                    details=f"Malformed JSON payload: {exc.msg} at line {exc.lineno} col {exc.colno}",
                    operation="parse_raw_data",
                )
        elif isinstance(payload, (dict, list)):
            data = payload
        else:
            raise InvalidSensorDataError(
                details=f"Invalid payload type for JSON parsing: {type(payload).__name__}",
                operation="parse_raw_data",
            )

        if isinstance(data, list):
            # List of observation points
            if not data:
                raise InsufficientDroneDataError(
                    details="JSON list payload is empty.",
                    operation="parse_raw_data",
                )
            measurements = []
            channels: Dict[str, List[Any]] = {}
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    raise InvalidSensorDataError(
                        details=f"JSON list item {idx} is not a key-value object.",
                        operation="parse_raw_data",
                    )
                measurements.append(item)
                for k, v in item.items():
                    channels.setdefault(k, []).append(v)

            return {
                "format": DroneDataFormat.JSON.value,
                "channels": channels,
                "measurements": measurements,
                "metadata": {"type": "item_list", "item_count": len(measurements)},
                "sample_count": len(measurements),
            }

        elif isinstance(data, dict):
            # Dict payload: could be nested {channels: ..., metadata: ...} or direct key-values
            if not data:
                raise InsufficientDroneDataError(
                    details="JSON dictionary payload is empty.",
                    operation="parse_raw_data",
                )

            metadata = data.get("metadata", {})
            channels = {}
            measurements = []

            if "channels" in data and isinstance(data["channels"], dict):
                channels = data["channels"]
                # Convert channels map into measurement list
                for ch_name, val in channels.items():
                    measurements.append({
                        "channel": ch_name,
                        "value": val,
                        "unit": data.get("units", {}).get(ch_name, data.get("unit_metadata", {}).get(ch_name, "raw_dn")),
                    })
            elif "measurements" in data and isinstance(data["measurements"], list):
                measurements = data["measurements"]
                for item in measurements:
                    if isinstance(item, dict):
                        ch = item.get("channel") or item.get("channel_name") or item.get("name")
                        if ch:
                            channels[ch] = item.get("value") or item.get("original_value")
            else:
                # Flat channel key-values
                for k, v in data.items():
                    if k not in ("metadata", "units", "unit_metadata", "calibration", "calibration_metadata"):
                        channels[k] = v
                        unit = data.get("units", {}).get(k, "raw_dn")
                        measurements.append({"channel": k, "value": v, "unit": unit})

            return {
                "format": DroneDataFormat.JSON.value,
                "channels": channels,
                "measurements": measurements,
                "metadata": metadata if isinstance(metadata, dict) else {},
                "sample_count": len(measurements),
            }

        raise InvalidSensorDataError(
            details="Unsupported JSON root structure.",
            operation="parse_raw_data",
        )

    def _parse_csv(self, payload: Any) -> Dict[str, Any]:
        """Parse and validate CSV tabular payload."""
        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvalidSensorDataError(
                    details=f"CSV payload is not valid UTF-8: {exc}",
                    operation="parse_raw_data",
                )

        if not isinstance(payload, str):
            raise InvalidSensorDataError(
                details=f"Expected string or bytes for CSV payload, got {type(payload).__name__}.",
                operation="parse_raw_data",
            )

        payload_str = payload.strip()
        if not payload_str:
            raise InsufficientDroneDataError(
                details="Empty CSV payload.",
                operation="parse_raw_data",
            )

        reader = csv.reader(io.StringIO(payload_str))
        try:
            rows = list(reader)
        except csv.Error as exc:
            raise InvalidSensorDataError(
                details=f"CSV parsing error: {exc}",
                operation="parse_raw_data",
            )

        if not rows:
            raise InsufficientDroneDataError(
                details="CSV contains no records.",
                operation="parse_raw_data",
            )

        headers = [h.strip() for h in rows[0]]
        if not headers or all(not h for h in headers):
            raise InvalidSensorDataError(
                details="CSV header row is missing or empty.",
                operation="parse_raw_data",
            )

        # Check for duplicated headers
        if len(headers) != len(set(headers)):
            raise InvalidSensorDataError(
                details=f"CSV contains duplicate column headers: {headers}",
                operation="parse_raw_data",
            )

        data_rows = rows[1:]
        if not data_rows:
            raise InsufficientDroneDataError(
                details="CSV contains header row but zero data rows.",
                operation="parse_raw_data",
            )

        channels: Dict[str, List[Any]] = {h: [] for h in headers}
        measurements: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(data_rows, start=1):
            if not row or (len(row) == 1 and not row[0].strip()):
                continue  # skip trailing empty row
            if len(row) != len(headers):
                raise InvalidSensorDataError(
                    details=f"CSV row {row_idx} column count ({len(row)}) does not match header count ({len(headers)}).",
                    operation="parse_raw_data",
                )
            row_dict = {}
            for col_idx, col_name in enumerate(headers):
                raw_cell = row[col_idx].strip()
                # Try parsing float / int
                parsed_val: Any = raw_cell
                if raw_cell:
                    try:
                        if "." in raw_cell or "e" in raw_cell.lower():
                            parsed_val = float(raw_cell)
                        else:
                            parsed_val = int(raw_cell)
                    except ValueError:
                        parsed_val = raw_cell

                channels[col_name].append(parsed_val)
                row_dict[col_name] = parsed_val
            measurements.append(row_dict)

        if not measurements:
            raise InsufficientDroneDataError(
                details="CSV contains no valid non-empty data rows.",
                operation="parse_raw_data",
            )

        return {
            "format": DroneDataFormat.CSV.value,
            "channels": channels,
            "measurements": measurements,
            "metadata": {"columns": headers, "row_count": len(measurements)},
            "sample_count": len(measurements),
        }

    def _parse_raw_binary(self, payload: Any) -> Dict[str, Any]:
        """Parse raw binary sensor telemetry stream."""
        if not isinstance(payload, (bytes, bytearray)):
            raise InvalidSensorDataError(
                details=f"Expected bytes for RAW_BINARY format, got {type(payload).__name__}.",
                operation="parse_raw_data",
            )

        raw_bytes = bytes(payload)
        if len(raw_bytes) == 0:
            raise InsufficientDroneDataError(
                details="Empty raw binary payload.",
                operation="parse_raw_data",
            )

        # Basic binary telemetry parser: expects minimum 4-byte header or sequence of 16-bit unsigned ints
        if len(raw_bytes) < 4:
            raise InvalidSensorDataError(
                details=f"Truncated binary payload (length {len(raw_bytes)} bytes < 4 bytes).",
                operation="parse_raw_data",
            )

        # Unpack as 16-bit uint samples
        num_samples = len(raw_bytes) // 2
        import struct
        samples = struct.unpack(f"<{num_samples}H", raw_bytes[: num_samples * 2])

        measurements = [{"sample_index": i, "value": v, "unit": "raw_dn"} for i, v in enumerate(samples)]
        return {
            "format": DroneDataFormat.RAW_BINARY.value,
            "channels": {"raw_stream": list(samples)},
            "measurements": measurements,
            "metadata": {"byte_length": len(raw_bytes), "sample_count": num_samples},
            "sample_count": num_samples,
        }

    def _parse_structured_dict(self, payload: Dict[str, Any], data_format: DroneDataFormat) -> Dict[str, Any]:
        """Handle structured synthetic or pre-parsed dictionary for raster/specialized formats."""
        if not payload:
            raise InsufficientDroneDataError(
                details=f"Empty dictionary payload for {data_format.value}.",
                operation="parse_raw_data",
            )

        channels = payload.get("channels") or payload.get("bands") or {}
        if not channels and "values" in payload:
            channels = {"default": payload["values"]}

        measurements = []
        if isinstance(channels, dict):
            for k, v in channels.items():
                unit = payload.get("units", {}).get(k, "raw_dn")
                measurements.append({"channel": k, "value": v, "unit": unit})
        elif isinstance(channels, list):
            for idx, item in enumerate(channels):
                if isinstance(item, dict):
                    measurements.append(item)
                else:
                    measurements.append({"channel": f"band_{idx+1}", "value": item, "unit": "raw_dn"})

        return {
            "format": data_format.value,
            "channels": channels if isinstance(channels, dict) else {f"band_{i+1}": b for i, b in enumerate(channels)},
            "measurements": measurements,
            "metadata": payload.get("metadata", {}),
            "sample_count": len(measurements),
        }

    def _parse_raster_or_binary_buffer(self, payload: bytes, data_format: DroneDataFormat) -> Dict[str, Any]:
        """Handle raw buffer for GeoTIFF / NetCDF / HDF5 / LAS."""
        if len(payload) == 0:
            raise InsufficientDroneDataError(
                details=f"Empty buffer for {data_format.value}.",
                operation="parse_raw_data",
            )

        # Validate minimum header size
        if len(payload) < 8:
            raise InvalidSensorDataError(
                details=f"Truncated buffer ({len(payload)} bytes) for {data_format.value}.",
                operation="parse_raw_data",
            )

        # Extract mock raster band summary without full external GDAL dependency
        return {
            "format": data_format.value,
            "channels": {"buffer_size_bytes": len(payload)},
            "measurements": [{"channel": "raw_buffer", "value": len(payload), "unit": "bytes"}],
            "metadata": {"raw_size": len(payload), "format": data_format.value},
            "sample_count": 1,
        }
