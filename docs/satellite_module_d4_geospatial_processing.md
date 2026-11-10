# EarthMind Satellite Intelligence Module — Stage D4: Geospatial Processing Engine

> **Component:** Component 11 — `ISatelliteGeospatialProcessor` (`SatelliteGeospatialProcessor`)
> **Stage:** D4 — Satellite Data Processing
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview
The `SatelliteGeospatialProcessor` ensures exact spatial alignment, georeferencing, Coordinate Reference System (CRS) transformations, and field boundary clipping.

---

## 2. CRS Reprojection & Coordinate Validation
The processor uses `pyproj.Transformer` to convert coordinates and bounding boxes from local projected systems (such as UTM zones, e.g., `EPSG:32643`) to the EarthMind standard geographic CRS (`EPSG:4326` / WGS84).
- Physical coordinate validation: Latitude strictly within `[-90.0, 90.0]`, Longitude strictly within `[-180.0, 180.0]`.
- Out-of-bounds coordinates raise `SatelliteInvalidArgumentError`.

---

## 3. Non-Destructive Field Boundary Clipping
Using `shapely.geometry.Polygon` and `shapely.geometry.Point`, clips raster matrices to target agricultural field boundaries without mutating raw source matrices.
