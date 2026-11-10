"""Geospatial Processing Engine for EarthMind Satellite Module (Stage D4)."""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon

from core.interfaces.satellite import ISatelliteGeospatialProcessor
from core.logging.logger import get_logger
from core.schemas.satellite import SatelliteGeospatialMetadata
from modules.satellite.errors import SatelliteInvalidArgumentError

logger = get_logger("modules.satellite.geospatial")

class SatelliteGeospatialProcessor(ISatelliteGeospatialProcessor):
    def __init__(self, default_target_crs: str = "EPSG:4326"):
        self._default_crs = default_target_crs
        self._transformers: Dict[Tuple[str, str], Transformer] = {}

    def _get_transformer(self, src_crs_str: str, dst_crs_str: str) -> Transformer:
        key = (src_crs_str.upper(), dst_crs_str.upper())
        if key not in self._transformers:
            try:
                src = CRS.from_user_input(src_crs_str)
                dst = CRS.from_user_input(dst_crs_str)
                self._transformers[key] = Transformer.from_crs(src, dst, always_xy=True)
            except Exception as exc:
                raise SatelliteInvalidArgumentError(f"Unsupported CRS transformation: {exc}")
        return self._transformers[key]

    def validate_crs(self, crs_str: str) -> str:
        try:
            crs_obj = CRS.from_user_input(crs_str)
            auth = crs_obj.to_authority()
            if auth:
                return f"{auth[0]}:{auth[1]}"
            return crs_str
        except Exception as exc:
            raise SatelliteInvalidArgumentError(f"Invalid CRS: {crs_str} ({exc})")

    def process_geospatial(self, raw_coords: Dict[str, Any], target_crs: str = "EPSG:4326") -> SatelliteGeospatialMetadata:
        if not raw_coords:
            raise SatelliteInvalidArgumentError("raw_coords cannot be empty")
        src_crs_str = raw_coords.get("crs", "EPSG:4326")
        validated_src_crs = self.validate_crs(src_crs_str)
        validated_target_crs = self.validate_crs(target_crs)

        if "latitude" in raw_coords and "longitude" in raw_coords:
            x, y = float(raw_coords["longitude"]), float(raw_coords["latitude"])
        elif "x" in raw_coords and "y" in raw_coords:
            x, y = float(raw_coords["x"]), float(raw_coords["y"])
        else:
            raise SatelliteInvalidArgumentError("raw_coords must provide coordinates")

        if validated_src_crs.upper() != validated_target_crs.upper():
            transformer = self._get_transformer(validated_src_crs, validated_target_crs)
            target_x, target_y = transformer.transform(x, y)
        else:
            target_x, target_y = x, y

        if validated_target_crs.upper() in ("EPSG:4326", "WGS84"):
            if not (-90.0 <= target_y <= 90.0 and -180.0 <= target_x <= 180.0):
                raise SatelliteInvalidArgumentError(f"Coordinates out of bounds: lat={target_y}, lon={target_x}")

        target_bbox = None
        raw_bbox = raw_coords.get("bounding_box")
        if raw_bbox and len(raw_bbox) == 4:
            min_x, min_y, max_x, max_y = raw_bbox
            if validated_src_crs.upper() != validated_target_crs.upper():
                transformer = self._get_transformer(validated_src_crs, validated_target_crs)
                t_min_x, t_min_y = transformer.transform(min_x, min_y)
                t_max_x, t_max_y = transformer.transform(max_x, max_y)
                target_bbox = [min(t_min_x, t_max_x), min(t_min_y, t_max_y), max(t_min_x, t_max_x), max(t_min_y, t_max_y)]
            else:
                target_bbox = [float(min_x), float(min_y), float(max_x), float(max_y)]

        res = raw_coords.get("spatial_resolution_meters")
        return SatelliteGeospatialMetadata(
            latitude=float(np.round(target_y, 7)),
            longitude=float(np.round(target_x, 7)),
            bounding_box=target_bbox,
            crs=validated_target_crs,
            spatial_resolution_meters=float(res) if res is not None else None,
            field_id=raw_coords.get("field_id"),
            farm_id=raw_coords.get("farm_id"),
            coverage_area_hectares=raw_coords.get("coverage_area_hectares"),
        )

    def clip_to_field_boundary(self, band_matrix: Any, field_polygon: List[List[float]], raster_extent: Optional[List[float]] = None) -> Any:
        if not field_polygon or len(field_polygon) < 3:
            raise SatelliteInvalidArgumentError("field_polygon must contain at least 3 vertices")
        try:
            poly = Polygon(field_polygon)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_valid or poly.is_empty:
                raise SatelliteInvalidArgumentError("Invalid field boundary geometry")
        except Exception as exc:
            raise SatelliteInvalidArgumentError(f"Invalid polygon geometry: {exc}")

        arr = np.asarray(band_matrix, dtype=np.float32)
        if arr.ndim != 2:
            return arr
        rows, cols = arr.shape
        min_lon, min_lat, max_lon, max_lat = raster_extent or [0.0, 0.0, float(cols), float(rows)]
        x_coords = np.linspace(min_lon, max_lon, cols)
        y_coords = np.linspace(max_lat, min_lat, rows)
        mask = np.zeros((rows, cols), dtype=bool)
        for r in range(rows):
            for c in range(cols):
                pt = Point(x_coords[c], y_coords[r])
                if poly.contains(pt) or poly.touches(pt):
                    mask[r, c] = True
        return np.where(mask, arr, np.nan)
