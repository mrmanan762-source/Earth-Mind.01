# EarthMind Satellite Intelligence Module — Stage D6: Uncertainty Assessment

## 1. Overview
The Uncertainty Assessment Engine is implemented in `modules/satellite/uncertainty.py` via `SatelliteUncertaintyAssessor`, conforming to Component 15 (`ISatelliteUncertaintyAssessor`).

It evaluates transparent, defensible uncertainty metrics across:
- Data Quality and cloud cover interference.
- Atmospheric correction (Bottom-Of-Atmosphere BOA surface reflectance vs Top-Of-Atmosphere TOA radiance).
- Spatial resolution limitations and mixed-pixel effects.
- Temporal observation gaps and scene revisit latency.
- Cross-source sensor discrepancies and conflicts.

## 2. Discrete Categorical Confidence Levels
To prevent fabricated confidence percentages or unsupported statistical certainty, uncertainty is categorized into four discrete, defensible states:
- `HIGH`: Overall confidence $\ge 0.85$ (clean cloud-free L2A imagery, high spatial resolution, fresh observation $<7$ days).
- `MEDIUM`: Overall confidence between $0.60$ and $0.85$ (minor cloud noise, aging timestamp $7-20$ days, or slight spatial coarseness).
- `LOW`: Overall confidence between $0.30$ and $0.60$ (uncalibrated TOA radiance, moderate cloud cover, or stale observation $>20$ days).
- `INSUFFICIENT_EVIDENCE`: Overall confidence $< 0.30$ or critical failure (cloud obscuration $>50\%$, missing essential bands, or corrupted metadata).

## 3. Uncertainty Sources & Limitations
Every assessment explicitly compiles qualitative uncertainty statements in `uncertainty_sources` and operational `limitations`, ensuring Sarvam-105B and human agronomists understand exact observation boundaries.
