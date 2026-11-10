# EarthMind Satellite Intelligence Module — Stage D4: Temporal & Numerical Processing

> **Component:** Component 12 — `ISatelliteTemporalProcessor` (`SatelliteTemporalProcessor`), SAR & Thermal Processors
> **Stage:** D4 — Satellite Data Processing
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview
Temporal and numerical processing ensures chronological consistency, constellation revisit interval modeling, observation gap detection, and sensor-specific numerical calibration for radar (SAR) and thermal datasets.

---

## 2. Temporal Processing Capabilities
1. ISO 8601 UTC Normalization (`YYYY-MM-DDTHH:MM:SSZ`).
2. Revisit interval modeling (Sentinel-2: 5d, Landsat: 16d, MODIS: 1d, Sentinel-1: 6d).
3. Observation gap detection without fabricating synthetic data.

---

## 3. SAR & Thermal Foundations
- `SatelliteSARProcessor`: Converts linear amplitude to backscatter dB (`sigma0_dB = 10 * log10(power)`).
- `SatelliteThermalProcessor`: Converts raw DN/Kelvin to Celsius (`C = K - 273.15`).
