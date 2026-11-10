# EarthMind Satellite Intelligence Module — Stage D7 Security and Data Governance

> **Stage:** D7 — Final Evidence Validation, Sarvam Integration & B2 Connectivity
> **Status:** COMPLETE
> **Component:** Component 20 (`ISatelliteGovernanceGate`) & Credential Governance

---

## 1. Security Architecture & Boundary Isolation

### Tenant Data Isolation
- Satellite evidence artifacts are bound to an explicit `tenant_id` inside `SatelliteScopeInfo`.
- `SatelliteGovernanceGate` strictly checks incoming evidence against the active execution context.
- Requests attempting to stage or retrieve evidence across mismatched tenants are rejected.

### Farm Privacy & Memory Isolation
- Satellite observation `ContextItem`s are classified as `PrivacyLevel.FARM_PRIVATE`.
- **Zero Automatic Promotion:** Satellite evidence is strictly prevented from automatic ingestion into:
  - User Memory (private farmer memory)
  - General Memory (shared system memory)
  - C.2 Knowledge Base (canonical agronomic corpus)
- Any evidence bearing `auto_promote_to_kb` or `auto_promote_to_memory` flags is rejected by `SatelliteGovernanceGate`.

### Provider Licensing & Attribution
- EarthMind satellite evidence enforces mandatory attribution statements for data providers:
  - Copernicus CDSE: `"Contains modified Copernicus Sentinel data [year]"`
  - NASA Earthdata: `"NASA/USGS Landsat data courtesy of the U.S. Geological Survey"`
  - ISRO Bhuvan: `"ISRO / NRSC Open Data Access"`
- Unattributed evidence is rejected during evidence validation.

### Secret Masking & Credentials
- Provider credentials (e.g., `EARTHMIND_SATELLITE_COPERNICUS_CLIENT_ID`) are read exclusively on the backend from environment variables.
- Secrets are masked in settings (`to_safe_dict()`), diagnostics, logs, and integration responses.
