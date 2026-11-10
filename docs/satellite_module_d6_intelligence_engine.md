# EarthMind Satellite Intelligence Module — Stage D6: Intelligence Engine

## 1. Architectural Scope & Purpose
The Satellite Intelligence Engine operates within Layer 4 (Satellite Intelligence) and Layer 5 (Evidence & Validation) of the EarthMind Satellite Module architecture. It transforms calibrated spectral bands and indicators (D4/D5) into structured, traceable satellite intelligence.

Primary Architectural Boundaries:
- Satellite Module provides objective satellite observations and indicators.
- Sarvam-105B remains EarthMind's primary reasoning engine.
- Satellite Module strictly does NOT assert final root-cause diagnoses, chemical prescriptions, or fertilizer doses.

## 2. Core Implemented Components
1. `SatelliteAgriculturalIntelligenceEngine` (`modules/satellite/intelligence.py`):
   - Conforms to Component 16 (`ISatelliteAgronomicFeatureExtractor`).
   - Synthesizes spectral vigor indicators (NDVI, NDRE, EVI), canopy moisture indicators (NDWI Gao vs McFeeters), geospatial coverage in hectares, and temporal trends.
2. `SatelliteEvidenceBuilder` (`modules/satellite/evidence_builder.py`):
   - Conforms to Component 17 (`ISatelliteEvidenceBuilder`) and Component 19 (`ISatelliteProvenanceTracker`).
   - Produces the authoritative `EarthMindSatelliteEvidence` artifact (Contract 8 v1.0).
   - Stores raster files via URI storage references (`storage_uri`) rather than memory arrays.
   - Generates SHA-256 cryptographic provenance digests (`evidence_hash`).
3. `SatelliteEvidenceValidator` (`modules/satellite/evidence_validator.py`):
   - Conforms to Component 18 (`ISatelliteEvidenceValidator`).
   - Enforces an 8-stage verification checklist covering contract schema, spatiotemporal bounds, physical index limits, unit validity, and uncertainty consistency.
4. `SatelliteGovernanceGate` (`modules/satellite/evidence_validator.py`):
   - Conforms to Component 20 (`ISatelliteGovernanceGate`).
   - Strictly validates tenant isolation and prohibits automatic promotion to User Memory, General Memory, or C.2 Knowledge Base.

## 3. Storage and Raster References
Large satellite raster matrices are persisted using the existing storage abstraction (`ISatelliteCacheStorageAdapter`). Within evidence metadata and indicator records, raster bands are referenced via immutable URI pointers (`sat_storage://...`), preventing high memory footprints and network transmission bottlenecks.
