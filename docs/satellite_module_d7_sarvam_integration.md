# EarthMind Satellite Intelligence Module — Stage D7 Sarvam-105B Integration

> **Stage:** D7 — Final Evidence Validation, Sarvam Integration & B2 Connectivity
> **Status:** COMPLETE
> **Component:** Component 22 (`ISatelliteSarvamContextFormatter`) & `SarvamSatelliteIntegration`

---

## 1. Role Separation & Boundary Guarantees

Sarvam-105B remains EarthMind's primary AI reasoning engine. The Satellite Module operates strictly as an objective observation and intelligence provider.

| System Component | Core Responsibilities | Explicit Limitations |
| :--- | :--- | :--- |
| **Satellite Module** | Acquisition, preprocessing, spectral indices, agronomic feature extraction, uncertainty assessment, evidence validation. | **Strictly prohibited** from making root-cause crop disease diagnoses, prescribing chemical treatments, or making final agricultural decisions. |
| **Sarvam-105B** | Multi-source context synthesis, agricultural reasoning, cross-correlation with weather/soil/farm history, user advisory formulation. | Relies on B2 Context Manager for grounded evidence; does not access raw satellite raster arrays directly. |

---

## 2. Structured Observation Summary Formatter

The `SatelliteSarvamContextFormatter` (`modules/satellite/normalization.py`) generates concise, scientifically accurate, and non-diagnostic text summaries tailored for Sarvam-105B reasoning:

- **Identity & Mission:** Constellation, platform, instrument, and acquisition date.
- **Geographic Scope:** Target centroid coordinates and agricultural field identifier.
- **Atmospheric & Quality Status:** Cloud cover percentage, atmospheric correction status, and native resolution.
- **Vegetation & Moisture Observations:** Extracted indicators (NDVI, NDRE, NDWI variants, EVI) with statistical distributions.
- **Uncertainty & Operational Limitations:** Revisit intervals, sensor penetration limits, and data quality confidence levels.
- **Attribution:** Provider licensing statement.
