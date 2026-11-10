# EarthMind Satellite Intelligence Module — Stage D6: Multi-Source Intelligence Fusion

## 1. Overview
The Multi-Source Intelligence Fusion subsystem is implemented in `modules/satellite/fusion.py` through `SatelliteMultiSourceFusionEngine`, conforming to Component 14 (`ISatelliteMultiSourceFusion`).

It harmonizes observations across:
- Optical multispectral imagery (e.g. Sentinel-2 MSI, Landsat-8/9 OLI)
- Synthetic Aperture Radar (SAR) observations (e.g. Sentinel-1 C-band VV/VH)
- Thermal infrared observations (e.g. Landsat-8 TIRS, MODIS LST)
- Derived agricultural indicators

## 2. Spatial and Temporal Compatibility Validation
- **Spatial Alignment:** Computes centroid Euclidean angular distance. Discrepancies exceeding the configured threshold (default 0.5 degrees) trigger spatial incompatibility warnings.
- **Temporal Alignment:** Validates acquisition timestamp difference in days against configurable limit (default 7.0 days). Incompatible temporal windows trigger temporal mismatch warnings.
- **Resolution & Unit Preservation:** Does not blindly average bands across disparate ground resolutions or differing units.

## 3. Cross-Sensor Conflict Detection
- **Indicator Divergence:** Evaluates duplicate indicators derived across different scenes/sensors. Divergence exceeding threshold (e.g. $|\Delta \text{NDVI mean}| \ge 0.35$) is explicitly captured as a documented conflict.
- **Cross-Modal Discrepancy:** Detects physical contradictions (e.g., optical observations indicating high canopy greenness while SAR radar backscatter indicates bare ground).
- **Missing Information Tracking:** Explicitly identifies when expected modalities (SAR, Thermal, or specific spectral channels) are missing, preventing unverified assumptions.
