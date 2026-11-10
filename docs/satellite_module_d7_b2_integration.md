# EarthMind Satellite Intelligence Module — Stage D7 B2 Context Manager Integration

> **Stage:** D7 — Final Evidence Validation, Sarvam Integration & B2 Connectivity
> **Status:** COMPLETE
> **Component:** Component 21 (`ISatelliteB2ContextAdapter`) & `SatelliteContextProvider`

---

## 1. Overview and Architecture

The integration between the Satellite Module and EarthMind's B2 Context Manager adheres strictly to established system contracts and boundary protocols.

```
Satellite Data Providers (Copernicus, ISRO, NASA)
                     ↓
         D3 Data Acquisition & Ingestion
                     ↓
        D4 Processing (Image & Spectral)
                     ↓
        D5 Analysis (Indices & Moisture)
                     ↓
       D6 Intelligence & Uncertainty Engine
                     ↓
       D7 Final Validation & Governance Gate
                     ↓
         Satellite Integration Interface
                     ↓
          B2 Context Manager (Collector)
                     ↓
           Sarvam-105B Reasoning
```

---

## 2. Integration Protocols & Contracts

1. **Protocol Implementation (`SatelliteContextProvider`):**
   - Implements `modules.context.interfaces.ContextProvider`.
   - `provider_name = "satellite_provider"`.
   - Coordinates with `SarvamSatelliteIntegration` to retrieve matching staged evidence items for a given `ContextRequest`.

2. **Bridge Contract (`SatelliteIntegrationResponse` - Contract 9):**
   - Conforms to Contract 9 specification in `core/schemas/satellite.py`.
   - Converts validated evidence into a standard B2 `ContextItem` via `to_context_item()`.
   - Marks privacy level as `FARM_PRIVATE` and entity type as `"satellite_evidence"`.
   - Establishes bounded token estimate (default 350 tokens) for LLM context budgeting.

3. **System Lifecycle Wiring (`app/main.py`):**
   - In `app/main.py`, `satellite_module.context_provider` is registered with `context_module.manager.register_provider()`.
   - Ensures zero manual wiring required during startup.
