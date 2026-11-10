# EarthMind Satellite Intelligence Module — Stage D5: Geospatial Analysis Engine

> **Component:** `SatelliteSpatialAnalyzer`
> **Stage:** D5 — Spectral, Geospatial & Temporal Analysis
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview

The `SatelliteSpatialAnalyzer` computes zonal statistics, spatial heterogeneity, area coverage in hectares, and evaluates boundary containment against native sensor spatial resolution.

---

## 2. Area Coverage Calculations

Land surface area in hectares is calculated deterministically from pixel counts and ground sampling distance (GSD):

$$\text{Area}_{\text{hectares}} = \frac{N_{\text{pixels}} \cdot (\text{GSD}_{\text{meters}})^2}{10,000}$$

For example:
- 100 pixels at Sentinel-2 native 10m resolution = $100 \times 100\,\text{m}^2 = 10,000\,\text{m}^2 = 1.0\,\text{hectare}$.
- 100 pixels at Landsat 30m resolution = $100 \times 900\,\text{m}^2 = 90,000\,\text{m}^2 = 9.0\,\text{hectares}$.

---

## 3. Zonal Statistics

Supports computing zonal metrics across user-specified sub-zones (e.g. `zone_north`, `zone_lowland`, or irrigated sectors):
- Zonal valid pixel counts
- Zonal mean, minimum, maximum, and standard deviation
- Zonal area in hectares
