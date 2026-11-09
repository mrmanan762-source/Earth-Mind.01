"""Geospatial Processing Engine for EarthMind Drone Module (Stage D4).

Implements Component 7 (IGeospatialProcessor) conforming strictly to EarthMind architecture:
- Parses and validates coordinates across multiple formats (dicts, objects, tuples, DMS).
- Supports standard Coordinate Reference Systems (CRS) (EPSG:4326, EPSG:3857, UTM zones) using pyproj.
- Re-projects coordinates to EPSG:4326 while preserving original coordinates and declared CRS.
- Evaluates spatial coverage (bounding box, centroid, area) without fabricating data.
- Performs non-destructive field boundary containment checks using shapely (outside points trigger warnings/flags, never deletion).
- Rejects invalid coordinates with GeolocationInvalidError.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon

from core.errors.exceptions import GeolocationInvalidError
from core.interfaces.drone import IGeospatialProcessor
from core.logging.logger import get_logger
from core.schemas.drone import (
    FieldBoundaryContract,
    GeospatialCoordinateContract,
    ProcessedSensorMeasurementContract,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    SpatialProcessingReport,
)

logger = get_logger("modules.drone.geospatial")


class GeospatialProcessor(IGeospatialProcessor):
    """Component 7: Geospatial coordinates and field alignment engine."""

    def __init__(self, default_crs: str = "EPSG:4326"):
        self._default_crs = default_crs
        self._transformers: Dict[Tuple[str, str], Transformer] = {}

    def _get_transformer(self, src_crs_str: str, dst_crs_str: str) -> Transformer:
        """Cache pyproj transformers for performance."""
        key = (src_crs_str.upper(), dst_crs_str.upper())
        if key not in self._transformers:
            try:
                src_crs = CRS.from_user_input(src_crs_str)
                dst_crs = CRS.from_user_input(dst_crs_str)
                self._transformers[key] = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
            except Exception as exc:
                raise GeolocationInvalidError(
                    details=f"Unsupported or invalid CRS transformation from '{src_crs_str}' to '{dst_crs_str}': {exc}",
                    operation="get_transformer",
                )
        return self._transformers[key]

    def parse_coordinate_metadata(
        self,
        raw_coords: Any,
        declared_crs: Optional[str] = None,
    ) -> GeospatialCoordinateContract:
        """
        Parse and validate geographic point coordinates from dictionary, tuple, object, or string.
        Transforms to canonical EPSG:4326 if needed, preserving original values and original CRS.
        """
        if raw_coords is None:
            raise GeolocationInvalidError(
                details="Spatial coordinates payload is None.",
                operation="parse_coordinate_metadata",
            )

        orig_lat: Optional[float] = None
        orig_lon: Optional[float] = None
        orig_alt: Optional[float] = None
        crs_str = declared_crs or self._default_crs

        if isinstance(raw_coords, SpatialCoordinates):
            orig_lat = raw_coords.latitude
            orig_lon = raw_coords.longitude
            orig_alt = raw_coords.altitude_meters
            crs_str = raw_coords.crs or crs_str

        elif isinstance(raw_coords, dict):
            # Try latitude / longitude, then lat / lon, then y / x
            for lat_key in ("latitude", "lat", "y", "northing"):
                if lat_key in raw_coords and raw_coords[lat_key] is not None:
                    orig_lat = self._to_float(raw_coords[lat_key])
                    break

            for lon_key in ("longitude", "lon", "lng", "x", "easting"):
                if lon_key in raw_coords and raw_coords[lon_key] is not None:
                    orig_lon = self._to_float(raw_coords[lon_key])
                    break

            for alt_key in ("altitude_meters", "altitude", "alt", "elevation", "z"):
                if alt_key in raw_coords and raw_coords[alt_key] is not None:
                    orig_alt = self._to_float(raw_coords[alt_key])
                    break

            if "crs" in raw_coords and raw_coords["crs"]:
                crs_str = str(raw_coords["crs"])

        elif isinstance(raw_coords, (list, tuple)):
            if len(raw_coords) < 2:
                raise GeolocationInvalidError(
                    details=f"Coordinate sequence must contain at least 2 items, got {len(raw_coords)}.",
                    operation="parse_coordinate_metadata",
                )
            orig_lat = self._to_float(raw_coords[0])
            orig_lon = self._to_float(raw_coords[1])
            if len(raw_coords) >= 3 and raw_coords[2] is not None:
                orig_alt = self._to_float(raw_coords[2])

        else:
            raise GeolocationInvalidError(
                details=f"Unsupported coordinate data type: {type(raw_coords).__name__}",
                operation="parse_coordinate_metadata",
            )

        if orig_lat is None or orig_lon is None:
            raise GeolocationInvalidError(
                details=f"Could not extract both latitude and longitude from: {raw_coords}",
                operation="parse_coordinate_metadata",
            )

        if math.isnan(orig_lat) or math.isnan(orig_lon) or math.isinf(orig_lat) or math.isinf(orig_lon):
            raise GeolocationInvalidError(
                details="Coordinates contain NaN or infinite values.",
                operation="parse_coordinate_metadata",
            )

        # Standardize CRS string
        norm_crs = crs_str.strip().upper()
        if not norm_crs.startswith("EPSG:"):
            # Check if it's an EPSG number
            if norm_crs.isdigit():
                norm_crs = f"EPSG:{norm_crs}"
            elif norm_crs == "WGS84":
                norm_crs = "EPSG:4326"

        is_transformed = False
        transform_name = "identity"
        norm_lat = orig_lat
        norm_lon = orig_lon

        if norm_crs == "EPSG:4326":
            # Validate bounds for WGS84
            if not (-90.0 <= orig_lat <= 90.0):
                raise GeolocationInvalidError(
                    details=f"Latitude {orig_lat} is outside valid range [-90.0, 90.0].",
                    operation="parse_coordinate_metadata",
                )
            if not (-180.0 <= orig_lon <= 180.0):
                raise GeolocationInvalidError(
                    details=f"Longitude {orig_lon} is outside valid range [-180.0, 180.0].",
                    operation="parse_coordinate_metadata",
                )
        else:
            # Re-project to EPSG:4326
            try:
                transformer = self._get_transformer(norm_crs, "EPSG:4326")
                # always_xy=True expects (x, y) = (lon/easting, lat/northing)
                trans_x, trans_y = transformer.transform(orig_lon, orig_lat)
                norm_lon = float(trans_x)
                norm_lat = float(trans_y)
                is_transformed = True
                transform_name = f"reproject_{norm_crs}_to_EPSG:4326"
            except Exception as exc:
                raise GeolocationInvalidError(
                    details=f"Failed to transform coordinates from {norm_crs} to EPSG:4326: {exc}",
                    operation="parse_coordinate_metadata",
                )

            # Validate re-projected WGS84 bounds
            if not (-90.0 <= norm_lat <= 90.0) or not (-180.0 <= norm_lon <= 180.0):
                raise GeolocationInvalidError(
                    details=f"Transformed coordinates (lat={norm_lat}, lon={norm_lon}) outside valid range [-90, 90] / [-180, 180].",
                    operation="parse_coordinate_metadata",
                )

        return GeospatialCoordinateContract(
            original_latitude=orig_lat,
            original_longitude=orig_lon,
            original_altitude=orig_alt,
            original_crs=crs_str,
            latitude=norm_lat,
            longitude=norm_lon,
            altitude_meters=orig_alt,
            crs="EPSG:4326",
            transformation_applied=transform_name,
            is_transformed=is_transformed,
        )

    def _to_float(self, val: Any) -> float:
        """Convert float or DMS string representation to decimal float."""
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            val_str = val.strip()
            # Try direct float conversion
            try:
                return float(val_str)
            except ValueError:
                pass
            # Try DMS (degrees minutes seconds) regex: e.g. 28°36'50"N or 77°12'32"E
            dms_match = re.match(r"^(\d+)[°\s]+(\d+)['\s]+([0-9.]+)?[\"\s]*([NSEWnsew])?$", val_str)
            if dms_match:
                deg = float(dms_match.group(1))
                minute = float(dms_match.group(2))
                sec = float(dms_match.group(3) or 0.0)
                hemi = (dms_match.group(4) or "").upper()
                dd = deg + (minute / 60.0) + (sec / 3600.0)
                if hemi in ("S", "W"):
                    dd = -dd
                return dd

        raise GeolocationInvalidError(
            details=f"Cannot parse value '{val}' as numeric coordinate.",
            operation="_to_float",
        )

    def check_field_boundary(
        self,
        coords: List[GeospatialCoordinateContract],
        field_boundary: Union[FieldBoundaryContract, Dict[str, Any]],
    ) -> Tuple[bool, int, int, List[str]]:
        """
        Evaluate if points fall within the provided field boundary polygon.
        Non-destructive check: returns (all_inside, inside_count, outside_count, warnings).
        Measurements are never dropped.
        """
        warnings: List[str] = []
        if isinstance(field_boundary, dict):
            field_contract = FieldBoundaryContract(**field_boundary)
        else:
            field_contract = field_boundary

        polygon_coords = field_contract.polygon_coordinates
        if len(polygon_coords) < 3:
            warnings.append(f"Field boundary polygon has fewer than 3 vertices ({len(polygon_coords)}).")
            return False, 0, len(coords), warnings

        # Build Polygon in EPSG:4326
        # Transform boundary polygon vertices if not in EPSG:4326
        boundary_crs = field_contract.crs.strip().upper()
        norm_boundary_crs = boundary_crs if boundary_crs.startswith("EPSG:") else f"EPSG:{boundary_crs}"
        transformer: Optional[Transformer] = None
        if norm_boundary_crs != "EPSG:4326":
            try:
                transformer = self._get_transformer(norm_boundary_crs, "EPSG:4326")
            except Exception as exc:
                warnings.append(f"Failed to resolve transformer for field boundary CRS '{norm_boundary_crs}': {exc}")
                return False, 0, len(coords), warnings

        poly_points: List[Tuple[float, float]] = []
        coord_format = field_contract.coordinate_format.upper()
        for pt in polygon_coords:
            if len(pt) < 2:
                continue
            if coord_format == "LAT_LON":
                lat_val, lon_val = pt[0], pt[1]
            else:  # LON_LAT
                lon_val, lat_val = pt[0], pt[1]

            if transformer:
                try:
                    lon_val, lat_val = transformer.transform(lon_val, lat_val)
                except Exception:
                    pass

            # Shapely Point(x, y) = (lon, lat)
            poly_points.append((float(lon_val), float(lat_val)))

        if len(poly_points) < 3:
            warnings.append("Insufficient valid vertices to form a polygon.")
            return False, 0, len(coords), warnings

        try:
            poly = Polygon(poly_points)
            if not poly.is_valid:
                # Attempt to repair buffer(0) if minor self-intersection
                poly = poly.buffer(0)
            if not poly.is_valid or poly.is_empty:
                warnings.append(f"Invalid field boundary geometry for field '{field_contract.field_id}'.")
                return False, 0, len(coords), warnings
        except Exception as exc:
            warnings.append(f"Error constructing boundary polygon: {exc}")
            return False, 0, len(coords), warnings

        inside_count = 0
        outside_count = 0

        for c in coords:
            # In Shapely (x, y) = (lon, lat)
            pt = Point(c.longitude, c.latitude)
            if poly.contains(pt) or poly.touches(pt):
                inside_count += 1
            else:
                outside_count += 1

        all_inside = (outside_count == 0 and inside_count > 0)
        if outside_count > 0:
            warnings.append(
                f"Field boundary check: {outside_count} of {len(coords)} points are outside field '{field_contract.field_id}' boundary."
            )

        return all_inside, inside_count, outside_count, warnings

    def process_spatial(
        self,
        raw_coords: Optional[Dict[str, Any]],
        field_id: Optional[str] = None,
        field_boundary: Optional[Union[FieldBoundaryContract, Dict[str, Any]]] = None,
    ) -> SpatialCoverage:
        """
        Process GPS coordinates, bounding boxes, and field boundary intersection.
        Adheres to IGeospatialProcessor protocol.
        """
        if not raw_coords:
            return SpatialCoverage(
                has_spatial_metadata=False,
                centroid=None,
                bounding_box=None,
                area_hectares=None,
                crs=self._default_crs,
                field_id=field_id,
            )

        coord_contract = self.parse_coordinate_metadata(raw_coords)
        centroid = SpatialCoordinates(
            latitude=coord_contract.latitude,
            longitude=coord_contract.longitude,
            altitude_meters=coord_contract.altitude_meters,
            crs=coord_contract.crs,
        )

        bbox: Optional[SpatialBoundingBox] = None
        # Check if bounding box coordinates were supplied in raw_coords
        if all(k in raw_coords for k in ("min_latitude", "max_latitude", "min_longitude", "max_longitude")):
            try:
                min_c = self.parse_coordinate_metadata({
                    "lat": raw_coords["min_latitude"],
                    "lon": raw_coords["min_longitude"],
                    "crs": raw_coords.get("crs", self._default_crs),
                })
                max_c = self.parse_coordinate_metadata({
                    "lat": raw_coords["max_latitude"],
                    "lon": raw_coords["max_longitude"],
                    "crs": raw_coords.get("crs", self._default_crs),
                })
                bbox = SpatialBoundingBox(
                    min_latitude=min(min_c.latitude, max_c.latitude),
                    max_latitude=max(min_c.latitude, max_c.latitude),
                    min_longitude=min(min_c.longitude, max_c.longitude),
                    max_longitude=max(min_c.longitude, max_c.longitude),
                    crs="EPSG:4326",
                )
            except Exception:
                pass

        if bbox is None:
            # Single coordinate point bounding box
            bbox = SpatialBoundingBox(
                min_latitude=coord_contract.latitude,
                max_latitude=coord_contract.latitude,
                min_longitude=coord_contract.longitude,
                max_longitude=coord_contract.longitude,
                crs="EPSG:4326",
            )

        area_ha = raw_coords.get("area_hectares")
        if area_ha is not None:
            try:
                area_ha = float(area_ha)
            except (ValueError, TypeError):
                area_ha = None

        return SpatialCoverage(
            has_spatial_metadata=True,
            centroid=centroid,
            bounding_box=bbox,
            area_hectares=area_ha,
            crs="EPSG:4326",
            field_id=field_id,
        )

    def evaluate_measurements_spatial(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        field_boundary: Optional[Union[FieldBoundaryContract, Dict[str, Any]]] = None,
        declared_crs: Optional[str] = None,
    ) -> SpatialProcessingReport:
        """
        Evaluate full geospatial report across a collection of processed measurements.
        Preserves original coordinates while populating spatial report metrics.
        """
        if not measurements:
            return SpatialProcessingReport(
                has_spatial_metadata=False,
                crs_detected=declared_crs,
                crs_target="EPSG:4326",
                is_transformed=False,
                total_points_evaluated=0,
                warnings=["No measurements provided for spatial evaluation."],
            )

        points: List[GeospatialCoordinateContract] = []
        is_transformed_any = False
        detected_crs_set = set()
        warnings_list: List[str] = []
        errors_list: List[str] = []

        for m in measurements:
            if m.spatial_reference:
                try:
                    c = self.parse_coordinate_metadata(
                        m.spatial_reference,
                        declared_crs=m.spatial_reference.crs or declared_crs,
                    )
                    points.append(c)
                    detected_crs_set.add(c.original_crs)
                    if c.is_transformed:
                        is_transformed_any = True
                except GeolocationInvalidError as exc:
                    errors_list.append(f"Measurement '{m.measurement_id}' invalid spatial metadata: {exc.details}")
                except Exception as exc:
                    errors_list.append(f"Measurement '{m.measurement_id}' error parsing coordinates: {exc}")

        if not points:
            return SpatialProcessingReport(
                has_spatial_metadata=False,
                crs_detected=list(detected_crs_set)[0] if detected_crs_set else declared_crs,
                crs_target="EPSG:4326",
                is_transformed=False,
                total_points_evaluated=0,
                warnings=warnings_list or ["Measurements do not contain valid spatial coordinates."],
                errors=errors_list,
            )

        min_lat = min(p.latitude for p in points)
        max_lat = max(p.latitude for p in points)
        min_lon = min(p.longitude for p in points)
        max_lon = max(p.longitude for p in points)

        bbox = SpatialBoundingBox(
            min_latitude=min_lat,
            max_latitude=max_lat,
            min_longitude=min_lon,
            max_longitude=max_lon,
            crs="EPSG:4326",
        )

        mean_lat = sum(p.latitude for p in points) / len(points)
        mean_lon = sum(p.longitude for p in points) / len(points)
        mean_alt = None
        alts = [p.altitude_meters for p in points if p.altitude_meters is not None]
        if alts:
            mean_alt = sum(alts) / len(alts)

        centroid = SpatialCoordinates(
            latitude=mean_lat,
            longitude=mean_lon,
            altitude_meters=mean_alt,
            crs="EPSG:4326",
        )

        field_checked = False
        is_inside = None
        in_count = 0
        out_count = 0

        if field_boundary:
            field_checked = True
            is_inside, in_count, out_count, boundary_warnings = self.check_field_boundary(points, field_boundary)
            warnings_list.extend(boundary_warnings)

        return SpatialProcessingReport(
            has_spatial_metadata=True,
            crs_detected=", ".join(sorted(detected_crs_set)) if detected_crs_set else declared_crs,
            crs_target="EPSG:4326",
            is_transformed=is_transformed_any,
            bounding_box=bbox,
            centroid=centroid,
            field_boundary_checked=field_checked,
            is_within_field_boundary=is_inside,
            total_points_evaluated=len(points),
            points_within_boundary=in_count,
            points_outside_boundary=out_count,
            warnings=warnings_list,
            errors=errors_list,
        )
