# EarthMind Satellite Intelligence Module — Stage D4: Spectral Band Processing

> **Component:** Component 10 — `ISatelliteSpectralProcessor` (`SatelliteSpectralProcessor`)
> **Stage:** D4 — Satellite Data Processing
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview
The `SatelliteSpectralProcessor` standardizes raw satellite sensor bands across disparate Earth observation missions. It maps constellation-specific designations into canonical `SatelliteBandType` enumerations while preserving:
- Central wavelengths in nanometers.
- Full Width at Half Maximum (FWHM) bandwidths in nanometers.
- Ground sampling distances (spatial resolutions in meters).
- Summary statistics over valid finite pixels.

---

## 2. Constellation Band Mapping Registry
Supports Sentinel-2 MSI (B01-B12), Landsat-8/9 OLI/TIRS (B1-B11), and generic optical/thermal bands.

---

## 3. Strict Missing Band Handling
In accordance with EarthMind scientific reliability standards, `SatelliteSpectralProcessor` never silently substitutes missing bands. If a required band is requested but absent from the scene matrices, a `SatelliteProcessingError` is raised immediately.
