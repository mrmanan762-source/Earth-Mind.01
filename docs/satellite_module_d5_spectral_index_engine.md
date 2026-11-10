# EarthMind Satellite Intelligence Module — Stage D5: Spectral Index Engine

> **Component:** Component 13 — `ISatelliteIndicatorExtractor` (`SatelliteSpectralIndexEngine`)
> **Stage:** D5 — Spectral, Geospatial & Temporal Analysis
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview

The `SatelliteSpectralIndexEngine` calculates reproducible, formula-based agricultural spectral indices from calibrated, analysis-ready satellite bands produced by Stage D4.

Indices are calculated strictly when the required spectral bands are physically present and calibrated.

---

## 2. Canonical Spectral Indices

### 2.1 NDVI (Normalized Difference Vegetation Index)
$$\text{NDVI} = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}$$
- **Required Bands:** `NIR`, `RED`
- **Application:** Evaluates relative chlorophyll absorption and green canopy density.
- **Valid Range:** `[-1.0, 1.0]`

### 2.2 NDRE (Normalized Difference Red Edge Index)
$$\text{NDRE} = \frac{\text{NIR} - \text{RedEdge}_1}{\text{NIR} + \text{RedEdge}_1}$$
- **Required Bands:** `NIR`, `RED_EDGE_1` (e.g. Sentinel-2 B05)
- **Application:** Highly sensitive to chlorophyll content in dense, mature canopies where NDVI saturates.
- **Valid Range:** `[-1.0, 1.0]`

### 2.3 NDWI — Green-NIR Variant (McFeeters)
$$\text{NDWI}_{\text{McFeeters}} = \frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$$
- **Required Bands:** `GREEN`, `NIR`
- **Application:** Delineates open surface water bodies, irrigation ponds, and standing water.
- **Valid Range:** `[-1.0, 1.0]`

### 2.4 NDWI — NIR-SWIR Variant (Gao / Canopy Moisture)
$$\text{NDWI}_{\text{Gao}} = \frac{\text{NIR} - \text{SWIR}_1}{\text{NIR} + \text{SWIR}_1}$$
- **Required Bands:** `NIR`, `SWIR_1` (e.g. Sentinel-2 B11, Landsat-8 B6)
- **Application:** Measures liquid water thickness in vegetation canopies.
- **Valid Range:** `[-1.0, 1.0]`

### 2.5 EVI (Enhanced Vegetation Index)
$$\text{EVI} = 2.5 \cdot \frac{\text{NIR} - \text{Red}}{\text{NIR} + 6 \cdot \text{Red} - 7.5 \cdot \text{Blue} + 1.0}$$
- **Required Bands:** `NIR`, `RED`, `BLUE`
- **Application:** High-biomass index with reduced atmospheric aerosol scattering and soil background influence.
- **Valid Range:** `[-1.0, 1.5]`

---

## 3. Mathematical Safeguards

1. **Division-by-Zero Handling**:
   Where denominators approach zero ($|\text{denom}| \le 10^{-6}$), results are evaluated as `np.nan` instead of raising exceptions or producing infinity.
2. **Missing Band Rejection**:
   Never silently substitutes missing bands. Missing inputs immediately raise `SatelliteIndicatorProcessingError`.
3. **NDWI Variant Distinction**:
   The engine strictly maintains `NDWI_GREEN_NIR` and `NDWI_NIR_SWIR` as separate indicators with distinct identities, definitions, and agronomic interpretations.
