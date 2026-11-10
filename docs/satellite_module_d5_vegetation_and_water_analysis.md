# EarthMind Satellite Intelligence Module — Stage D5: Vegetation & Water Analysis

> **Component:** `VegetationWaterAnalyzer`
> **Stage:** D5 — Spectral, Geospatial & Temporal Analysis
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview

The `VegetationWaterAnalyzer` generates objective statistical distributions for canopy vigor and water-related spectral indicators over agricultural target fields.

---

## 2. Statistical Metrics

The analyzer computes 12 key distributional metrics over valid finite pixels:
- **Central Tendency:** Mean, Median
- **Extremes:** Minimum, Maximum
- **Spread & Dispersion:** Standard Deviation, Variance, Coefficient of Variation (CV)
- **Percentiles:** 10th (p10), 25th (p25), 75th (p75), 90th (p90)
- **Pixel Counts:** Valid pixels, invalid/NoData pixels, coverage percentage

---

## 3. Strict Non-Diagnostic Boundaries

In accordance with EarthMind system boundaries:
1. **Soil Moisture vs Canopy Moisture**:
   Spectral water measurements ($\text{NDWI}_{\text{Gao}}$) measure leaf water absorption, not volumetric soil moisture ($m^3/m^3$). The analyzer explicitly prohibits equating spectral water indicators with direct soil moisture probe measurements.
2. **Non-Diagnostic Canopy Observations**:
   Low vegetation indices are classified descriptively (e.g. `SPARSE_OR_EMERGING` or `HIGH_VARIABILITY`). The engine **never** generates unsupported conclusions of crop disease, fungal infection, pest damage, or nutrient deficiencies without grounded agronomic context from Sarvam-105B via B2 Context Manager.
