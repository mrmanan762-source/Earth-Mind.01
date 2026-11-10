# EarthMind Satellite Intelligence Module — Stage D6: Agricultural Intelligence Extraction

## 1. Overview
Stage D6 implements objective agricultural intelligence extraction via `SatelliteAgriculturalIntelligenceEngine` in `modules/satellite/intelligence.py`. It integrates calibrated spectral bands, multi-index indicators, spatial heterogeneity metrics, and multi-temporal change trends into coherent agronomic features.

## 2. Supported Agricultural Indicators & Features
- **Canopy Vigor Observations:**
  - `NDVI` (Normalized Difference Vegetation Index): Standard canopy greenness and vigor proxy.
  - `NDRE` (Normalized Difference Red Edge): Chlorophyll content proxy and early canopy stress indicator.
  - `EVI` (Enhanced Vegetation Index): High-biomass index resistant to soil background and atmospheric aerosols.
  - Summary distributions: mean, min, max, std dev, median, and coefficient of variation (CV).
- **Canopy Moisture Proxies:**
  - `NDWI_GAO` (NIR - SWIR): Vegetation canopy liquid water content proxy.
  - `NDWI_MCFEETERS` (Green - NIR): Surface water delineation proxy.
- **Geospatial & Spatial Heterogeneity:**
  - Validated field area in hectares calculated from ground sampling distance (GSD).
  - Intra-field spatial variation and zonal distributions across field polygons.
- **Temporal Dynamics:**
  - Multi-scene linear slope trajectory modeling.
  - Pixel-level change detection ($\Delta = T2 - T1$).

## 3. Strict Non-Diagnostic Guardrails
Every extracted feature adheres strictly to EarthMind non-diagnostic principles:
1. **No Root-Cause Diagnoses:** Satellite spectral changes alone cannot diagnose whether canopy stress is caused by fungal rust, bacterial blight, moisture deficit, or nutrient deficiency.
2. **No Chemical Prescriptions:** The Satellite Module never outputs pesticide sprays or fertilizer application rates.
3. **No Direct Soil Moisture Claims:** Spectral water indices are documented strictly as canopy moisture proxies, not volumetric soil moisture.
4. **Sarvam-105B Reasoning Context:** All observations are provided as clean factual evidence for Sarvam-105B to evaluate in combination with farmer context, weather, and corpus knowledge.
