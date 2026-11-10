# EarthMind Satellite Intelligence Module — Stage D7 Failure Handling & Recovery

> **Stage:** D7 — Final Evidence Validation, Sarvam Integration & B2 Connectivity
> **Status:** COMPLETE
> **Module Error Handling:** `core.errors.exceptions` & `modules.satellite.errors`

---

## 1. Fail-Closed Integration Principles

1. **Never Report False Success:**
   - If evidence validation, governance checks, or B2 delivery fail, the integration immediately raises an explicit typed error or returns a failure report.
   - Fallback satellite observations are never fabricated.

2. **Validation Gate Failures:**
   - Uncalibrated data, inverted bounding boxes, out-of-bounds spectral values, or missing provenance hashes raise `EvidenceValidationFailedError`.
   - Invalid evidence is blocked before entering the staged buffer and never reaches B2 Context Manager or Sarvam-105B.

3. **B2 Context Manager Unavailability:**
   - When B2 Context Manager is unconfigured, unreachable, or timed out, delivery raises `ContextProviderError` with `provider_name="satellite_provider"`.

4. **Tenant Isolation Failures:**
   - Cross-tenant evidence injection or retrieval attempts fail closed, raising `EvidenceValidationFailedError` with tenant isolation diagnostics.

5. **Sanitized Error Reporting:**
   - Provider credentials, internal API keys, and underlying infrastructure details are masked and excluded from error messages and application responses.
