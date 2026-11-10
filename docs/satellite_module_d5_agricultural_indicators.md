# EarthMind Satellite Intelligence Module — Stage D5: Agricultural Indicators

> **Component:** `SatelliteIndicatorGenerator`, `SatelliteMultiSourceFusionEngine` (Component 14)
> **Stage:** D5 — Spectral, Geospatial & Temporal Analysis
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview

Stage D5 outputs standardized agricultural indicators conforming to Contract 7 (`SatelliteIndicator`). Each indicator encapsulates:
- Canonical indicator name and mathematical definition.
- Applied algorithm and calculation method version.
- Required spectral band dependencies.
- Origin dataset identifier.
- Summary statistical metrics over the target agricultural area.
- Scientific unit.
- Quality rating and known physical/agronomic limitations.

---

## 2. Supported Agricultural Indicators

1. **NDVI**: Normalized Difference Vegetation Index (Unit: `unitless_ratio`).
2. **NDRE**: Normalized Difference Red Edge Index (Unit: `unitless_ratio`).
3. **NDWI_GREEN_NIR**: McFeeters Surface Water Index (Unit: `unitless_ratio`).
4. **NDWI_NIR_SWIR**: Gao Canopy Moisture Index (Unit: `unitless_ratio`).
5. **EVI**: Enhanced Vegetation Index (Unit: `unitless_ratio`).
6. **LAND_SURFACE_TEMPERATURE**: Thermal Infrared Radiometric Surface Temperature (Unit: `degrees_celsius`).

---

## 3. Multi-Source Satellite Fusion (Component 14)

The `SatelliteMultiSourceFusionEngine` harmonizes disparate observations (e.g., optical Sentinel-2 + Landsat-8/9 thermal + Sentinel-1 SAR):
- Validates spatial centroid alignment within 0.5 degrees.
- Validates temporal proximity within configurable maximum delta (default 7 days).
- Retains individual source dataset IDs and sensor metadata in the provenance trail.
- Does not interpolate or fabricate missing channels.
