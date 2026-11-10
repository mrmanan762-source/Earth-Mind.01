# EarthMind Satellite Intelligence Module — Stage D4: Image Processing Engine

> **Component:** Component 9 — `ISatelliteImageryProcessor` (`SatelliteImageProcessor`)
> **Stage:** D4 — Satellite Data Processing
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview
The `SatelliteImageProcessor` implements Component 9 of the EarthMind Satellite Intelligence Module:
- Ingesting, parsing, and validating satellite raster datasets across supported formats (GeoTIFF, COG, numeric arrays, dicts).
- Memory-aware chunked and windowed raster reading.
- NoData value identification and masking.
- Atmospheric correction validation and Bottom-Of-Atmosphere (BOA) surface reflectance normalization.
- Pixel-level cloud, shadow, and cirrus mask generation.

---

## 2. Windowed Processing
To protect against multi-gigabyte satellite scenes exhausting available container memory, `read_raster` supports optional `window=(row_start, row_end, col_start, col_end)` parameters to load spatial subsets on demand.

---

## 3. Atmospheric Correction & Reflectance Scaling
Scales raw digital numbers (e.g., DN / 10000 for Sentinel-2 MSI) into dimensionless surface reflectance in the physical range `[0.0, 1.0]`.

---

## 4. Cloud Masking
Cloud mask generation detects obscured pixels using dedicated SCL bands or spectral threshold heuristics, and quantifies cloud coverage over the target agricultural field.
