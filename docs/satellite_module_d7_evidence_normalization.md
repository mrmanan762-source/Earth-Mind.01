# EarthMind Satellite Intelligence Module — Stage D7 Evidence Normalization

> **Stage:** D7 — Final Evidence Validation, Sarvam Integration & B2 Connectivity
> **Status:** COMPLETE
> **Module Component:** `SatelliteEvidenceNormalizer` (`modules/satellite/normalization.py`)

---

## 1. Normalization Purpose & Design Principles

The `SatelliteEvidenceNormalizer` prepares validated satellite evidence for seamless ingestion by EarthMind's B2 Context Manager without loss of scientific information, while strictly preserving original measurements.

### Core Principles

1. **Non-Destructive Transformation:**
   - Normalization operates on a deep copy of `EarthMindSatelliteEvidence`.
   - Raw measurements, original coordinates, and physical pixel values are never overwritten or altered.

2. **Traceable Lineage:**
   - Appends normalization metadata (`normalized: True`, `normalization_version: "1.0"`) to `provenance`.
   - Explicitly records CRS normalization targets (`EPSG:4326`).

3. **Standardized Coordinate Representation:**
   - Confirms coordinates adhere to WGS 84 (`EPSG:4326`) latitude/longitude standards.

4. **Statistical Standard Precision:**
   - Normalizes floating-point statistical metrics (mean, median, standard deviation, percentiles) to 4 decimal places for bounded token efficiency in downstream LLM prompts.

5. **Unit Preservation:**
   - Preserves standard scientific agronomic units: surface reflectance in $[0.0, 1.0]$, vegetation and moisture indices in $[-1.0, 1.0]$.
