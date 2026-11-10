# EarthMind Satellite Intelligence Module — Stage D6: Output Contracts & Validation

## 1. Authoritative Output Contract: EarthMindSatelliteEvidence (Contract 8 v1.0)
The Satellite Intelligence Module emits validated instances of `EarthMindSatelliteEvidence` defined in `core/schemas/satellite.py`.

```json
{
  "contract_name": "EarthMindSatelliteEvidence",
  "schema_version": "1.0",
  "evidence_id": "ev_sat_c01928a3f81e",
  "source": {
    "provider_id": "copernicus_cdse",
    "constellation": "Sentinel-2",
    "platform": "Sentinel-2A",
    "instrument": "MSI",
    "sensor_type": "OPTICAL_MULTISPECTRAL",
    "dataset_id": "S2A_MSIL2A_20250328",
    "processing_level": "LEVEL-2A"
  },
  "scope": {
    "tenant_id": "tenant_icar_01",
    "farmer_id": "farmer_10842",
    "farm_id": "farm_karnal_main",
    "field_id": "field_karnal_01",
    "crop": "Wheat"
  },
  "geospatial": {
    "latitude": 29.6857,
    "longitude": 76.9905,
    "bounding_box": [76.9850, 29.6800, 76.9960, 29.6910],
    "crs": "EPSG:4326",
    "spatial_resolution_meters": 10.0,
    "coverage_area_hectares": 12.4
  },
  "temporal": {
    "acquisition_date": "2025-03-28T05:16:49Z",
    "revisit_interval_days": 5.0,
    "temporal_coverage_type": "SCENE_INSTANTANEOUS"
  },
  "indicators": [
    {
      "indicator_id": "sat_ind_ndvi_001",
      "indicator_name": "NDVI",
      "definition": "Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
      "calculation_method": "standard_band_ratio",
      "required_bands": ["RED", "NIR"],
      "source_dataset_id": "S2A_MSIL2A_20250328",
      "result_statistics": {
        "mean": 0.76,
        "min": 0.42,
        "max": 0.86,
        "std_dev": 0.08,
        "cv": 0.105
      },
      "unit": "unitless_ratio",
      "quality_status": "EXCELLENT",
      "limitations": ["Saturates at high biomass (LAI > 4)"]
    }
  ],
  "band_summaries": {
    "RED": {"mean": 0.065, "min": 0.030, "max": 0.140},
    "NIR": {"mean": 0.485, "min": 0.220, "max": 0.590}
  },
  "quality": {
    "overall_quality": "EXCELLENT",
    "cloud_cover_percentage": 1.5,
    "is_atmospheric_corrected": true,
    "resolution_fidelity": "NATIVE",
    "evidence_completeness": "COMPLETE"
  },
  "uncertainty": {
    "spatial_confidence": 1.0,
    "temporal_confidence": 0.98,
    "spectral_confidence": 0.95,
    "overall_confidence": 0.98,
    "uncertainty_sources": []
  },
  "license_attribution": "Contains modified Copernicus Sentinel data (2025), processed by EarthMind",
  "provenance": {
    "evidence_hash": "a4b7...e92",
    "pipeline": "standard_satellite_pipeline_v1",
    "engine_version": "1.0.0"
  },
  "warnings": [],
  "limitations": [
    "Macro 10m resolution indicates aggregate canopy vigor; cannot detect individual leaf symptoms."
  ],
  "status": "SUCCESS"
}
```

## 2. Validation & Governance Gate
- `SatelliteEvidenceValidator` strictly validates schema fields, coordinate ranges, physical limits, unit definitions, and uncertainty consistency.
- `SatelliteGovernanceGate` enforces tenant-level access isolation and blocks unauthorized promotion to User Memory, General Memory, or Knowledge Base collections.
