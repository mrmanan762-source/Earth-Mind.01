# EarthMind Satellite Intelligence Module — Architecture Specification v1.0

> **Status:** Founder-Approved Architecture v1.0 Locked & Authoritative
> **Stage:** D1 — Architecture & Contract Lock
> **Primary Intelligence Model:** Sarvam-105B
> **Context Integration:** B2 Context Manager
> **Cross-Module Boundaries:** Drone Module, Vision Module, Memory Module, C.2 Knowledge Base

---

## 1. Executive Summary & Purpose

The **EarthMind Satellite Intelligence Module** is a modular Earth observation data processing and intelligence layer that transforms raw satellite observations, multispectral imagery, and radar telemetry into validated, structured, spatially and temporally contextualized evidence.

Its purpose is to provide **Sarvam-105B** with macro-level environmental and agricultural monitoring capabilities required to reason over crop health, canopy development, vegetative vigor, soil moisture dynamics, and regional climate conditions across farms and fields. It accomplishes this without requiring Sarvam-105B or downstream orchestrators to parse multi-gigabyte raster files, reproject complex coordinate systems, or perform raw spectral band mathematics.

The Satellite Module strictly does **not** perform final agricultural diagnoses, prescribe chemical interventions or dosages, or formulate automated farm management decisions.

---

## 2. Six Architectural Layers & 24 Logical Components

The Satellite Module is organized into 6 architectural layers comprising 24 logical components:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Layer 6: EarthMind Integration                  │
│  [21] B2 Context Adapter  [22] Sarvam Formatter  [23] Cross-Module  [24] Diagnostics│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Validated Evidence
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Layer 5: Evidence & Validation                  │
│  [17] Evidence Builder    [18] Evidence Validator [19] Provenance    [20] Governance Gate│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Indicators & Features
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Layer 4: Satellite Intelligence                 │
│  [13] Indicator Extractor [14] Multi-Source Fusion [15] Uncertainty [16] Agronomic Features│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Calibrated & Masked Bands
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Layer 3: Satellite Data Processing              │
│  [9] Imagery Processor    [10] Spectral Processor [11] Geospatial    [12] Temporal Processor│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Raw Data References & Manifests
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Layer 2: Data Ingestion & Management            │
│  [5] Ingestion Detector   [6] Metadata Extractor  [7] Pre-Validator  [8] Cache Storage│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Discovery & Assets
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Layer 1: Satellite Data Access                  │
│  [1] Provider Registry    [2] Provider Adapter    [3] Catalog Discovery [4] Data Acquisition│
└────────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Satellite Data Access
1. **Satellite Provider Registry (`ISatelliteProviderRegistry`):** Catalogs registered satellite data providers (Copernicus SciHub/CDSE, USGS EROS, NASA CMR, ISRO Bhuvan/Bhoonidhi, AWS Open Data), managing operational statuses, supported constellations, and licensing constraints.
2. **Satellite Provider Adapter (`ISatelliteProviderAdapter`):** Standardizes provider communication via STAC APIs, OpenSearch, OData, or S3 bucket interfaces, abstracting provider-specific schemas.
3. **Satellite Catalog and Discovery (`ISatelliteCatalogDiscovery`):** Searches across multiple satellite catalogs given a spatial boundary, timeframe, and cloud cover threshold, ranking optimal granules for acquisition.
4. **Satellite Data Acquisition (`ISatelliteDataAcquisition`):** Orchestrates the acquisition of scene assets, coordinates downloads, and validates transfer integrity.

### Layer 2: Data Ingestion & Management
5. **Ingestion & Format Detection (`ISatelliteIngestionDetector`):** Safely handles downloaded or streamed satellite assets, detects file formats (GeoTIFF, COG, NetCDF, HDF5, SAFE), and creates immutable data reference pointers.
6. **Metadata Extraction (`ISatelliteMetadataExtractor`):** Extracts orbital parameters, processing levels (L1C, L2A), sensor geometries, sun angles, and scene cloud covers from raster headers and metadata XML/JSON files.
7. **Quality & Pre-validation (`ISatellitePreValidator`):** Performs sanity checks on acquired scenes, verifying physical boundaries, checking for corrupted blocks, and assessing preliminary cloud coverage.
8. **Cache & Storage Adapters (`ISatelliteCacheStorageAdapter`):** Provides provider-independent caching and persistence abstractions for scene references, calibrated bands, and metadata without holding large rasters in memory.

### Layer 3: Satellite Data Processing
9. **Imagery & Numerical Processing (`ISatelliteImageryProcessor`):** Applies atmospheric corrections (BOA/Surface Reflectance verification) and generates pixel-level cloud, cloud shadow, and cirrus masks.
10. **Spectral Processing (`ISatelliteSpectralProcessor`):** Extracts, calibrates, and normalizes spectral bands (Blue, Green, Red, RedEdge, NIR, SWIR, Thermal, SAR) to canonical reflectance or backscatter units.
11. **Geospatial Processing (`ISatelliteGeospatialProcessor`):** Handles CRS reprojections (normalizing to WGS84 EPSG:4326), computes exact bounding boxes, and clips rasters to farm/field boundaries.
12. **Temporal Processing (`ISatelliteTemporalProcessor`):** Normalizes observation timestamps to UTC, tracks sensor revisit intervals, and models temporal decay and confidence.

### Layer 4: Satellite Intelligence
13. **Intelligence & Indicator Extraction (`ISatelliteIndicatorExtractor`):** Calculates standardized vegetation and moisture indices (NDVI, NDRE, NDWI, EVI) only when required bands are physically verified.
14. **Multi-Source Fusion (`ISatelliteMultiSourceFusion`):** Spatially and temporally harmonizes observations from complementary constellations (e.g. Sentinel-2 optical + Sentinel-1 SAR, Landsat + Sentinel-2).
15. **Uncertainty Assessment (`ISatelliteUncertaintyAssessor`):** Quantifies spatial, temporal, spectral, and cloud-interference uncertainty across observations without fabricating confidence values.
16. **Agronomic Feature Extraction (`ISatelliteAgronomicFeatureExtractor`):** Synthesizes objective agronomic indicators (canopy density, vigor trend, moisture status) from verified indicators.

### Layer 5: Evidence & Validation
17. **Evidence Builder (`ISatelliteEvidenceBuilder`):** Synthesizes processed bands, indicators, uncertainty ratings, and provenance into the canonical `EarthMindSatelliteEvidence` artifact.
18. **Evidence Validator (`ISatelliteEvidenceValidator`):** Final validation gate ensuring candidate evidence strictly satisfies schema version 1.0 rules and rejects corrupted or silent incomplete data.
19. **Provenance Tracker (`ISatelliteProvenanceTracker`):** Maintains complete cryptographic and operational lineage from source provider scene ID to final evidence.
20. **Governance Gate (`ISatelliteGovernanceGate`):** Enforces tenant isolation, verifies license attribution requirements, and prevents unauthorized data promotion into Memory or C.2 Knowledge Base.

### Layer 6: EarthMind Integration
21. **B2 Context Manager Integration (`ISatelliteB2ContextAdapter`):** Bridges validated satellite evidence into B2 Context Manager via `ContextItem` encapsulation, respecting token budgeting and prioritization.
22. **Sarvam Context Formatter (`ISatelliteSarvamContextFormatter`):** Translates structured satellite evidence into concise, grounded contextual text tailored for Sarvam-105B agricultural reasoning.
23. **Cross-Module Data Sharing (`ISatelliteCrossModuleDataSharing`):** Exposes clean, read-only data sharing contracts with the Drone Module (macro-zoning context) and Vision Module (spectral correlation context).
24. **Monitoring & Diagnostics (`ISatelliteDiagnostics`):** Tracks operational telemetry, acquisition latencies, provider availability, cache hit ratios, and error rates.

---

## 3. Module Responsibilities & Explicit Non-Responsibilities

### 3.1 Responsibilities
1. Satellite data provider catalog querying and discovery.
2. Ingesting and verifying open-access satellite data products (Sentinel-2, Landsat-8/9, MODIS, Sentinel-1).
3. Extracting and verifying spatial, temporal, and spectral metadata.
4. Atmospheric correction validation and cloud/shadow masking.
5. Coordinate reference system reprojection to WGS84 (EPSG:4326).
6. Field-level spatial clipping without loss of original coordinates.
7. Calculating standard agricultural indicators (NDVI, NDRE, NDWI) from verified bands.
8. Harmonizing multi-sensor and multi-temporal observations.
9. Quantifying observation uncertainty and data quality.
10. Assembling and validating versioned `EarthMindSatelliteEvidence` artifacts.
11. Formatting evidence for B2 Context Manager without bypassing B2.
12. Maintaining complete cryptographic provenance and provider attribution.

### 3.2 Explicit Non-Responsibilities
- **Autonomous agricultural diagnosis:** Identifying plant pathogens, insect pests, or nutrient deficiencies (owned by B3 Reasoning / Sarvam-105B).
- **Chemical or fertilizer prescription:** Recommending pesticide dosages, spray schedules, or fertilizer quantities (owned by B4 Planning / B3 Reasoning).
- **Physical drone flight or local camera interpretation:** Flight operations or RGB photo interpretation (owned by Drone Module and Vision Module).
- **Permanent storage or knowledge base modification:** Auto-promoting satellite observations into General Memory or C.2 Knowledge Base (strictly governed by C.3 boundaries).
- **Direct LLM prompting:** Bypassing B2 Context Manager to directly invoke Sarvam-105B.

---

## 4. Integration Boundaries

### 4.1 Sarvam-105B & B2 Context Manager
All satellite intelligence reaches **Sarvam-105B** exclusively through the **B2 Context Manager**. The Satellite Module packages validated evidence into `SatelliteIntegrationResponse`, which transforms into a `ContextItem` with priority, privacy level (`FARM_PRIVATE`), bounded token footprint (~350 tokens), and explicit confidence metrics.

### 4.2 Cross-Module Relationship with Drone and Vision Modules
- **Drone Module:** Satellite data provides macro-level field zoning (e.g. low-vigor clusters across a 50-hectare farm), enabling targeted drone sensor flight planning.
- **Vision Module:** Satellite data provides temporal multispectral context (e.g., vegetative index drop over past 15 days) to correlate with close-up leaf disease photos.
- All cross-module interactions occur via versioned data contracts without shared mutable state.
