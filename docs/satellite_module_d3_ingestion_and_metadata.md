# EarthMind Satellite Intelligence Module — Stage D3: Ingestion and Metadata Extraction

## 1. Overview
The Ingestion and Metadata Extraction subsystem implements format sniffing, data integrity verification, raw storage persistence, and normalized metadata generation without performing image interpretation or calculating vegetation indices.

## 2. Format Detection Engine (`modules/satellite/formats.py`)
Conforming to `ISatelliteIngestionDetector.detect_format`, `SatelliteFormatDetector` inspects magic bytes, file signatures, and extensions:
- **GeoTIFF / COG**: Magic bytes `II*\x00` (little-endian) and `MM\x00*` (big-endian), supplemented with `.cog.tif` extension checking.
- **NetCDF**: Magic signatures `CDF\x01`, `CDF\x02`, and `\x89HDF\r\n\x1a\n` with `.nc` / `.nc4` extensions.
- **HDF5**: Magic signature `\x89HDF\r\n\x1a\n` with `.h5` / `.hdf5` extensions.
- **SAFE Packages**: Magic signature `PK\x03\x04` for zipped `.SAFE.zip` archives or directory name inspection for unpacked Sentinel SAFE structures.
- **GeoJSON & JSON**: Text payload inspection detecting `"type": "FeatureCollection"` or standard JSON objects.
- **CSV**: Text structure sniffing detecting header row, commas, and newlines.
- **Raw Binary**: Fallback byte stream representation.
- **Defensive Safeguards**: Implements maximum sample size limits to prevent Denial of Service and rejects empty or corrupted samples with `SatelliteUnsupportedFormatError`.

## 3. Raw Data Ingestion Engine (`modules/satellite/ingestion.py`)
Conforming to `ISatelliteIngestionDetector.ingest_raw_data`, the `SatelliteIngestionEngine`:
1. Validates `dataset_id`, `provider_id`, and non-empty byte buffer.
2. Checks maximum asset size limits (`max_download_size_bytes`).
3. Calculates SHA-256 cryptographic hash of raw data, validating against provider-supplied checksums if provided.
4. Detects effective format via `SatelliteFormatDetector`.
5. Persists raw bytes and metadata pointers in `ISatelliteCacheStorageAdapter`.
6. Generates immutable `SatelliteRawDataReference` (Contract 5) containing storage URI, byte count, SHA-256 hash, and retention expiry timestamp.

## 4. Metadata Extraction Engine (`modules/satellite/metadata_extractor.py`)
Conforming to `ISatelliteMetadataExtractor` (Component 6), `SatelliteMetadataExtractor`:
- Extracts normalized geospatial bounds and spatial resolution.
- Normalizes temporal observation timestamps to UTC ISO 8601.
- Identifies constellation, platform, instrument, and processing level (e.g. Sentinel-2A / MSI / LEVEL-2A).
- Normalizes cloud cover percentage.
- Extracts available spectral band metadata (band name, band type, wavelength, resolution, calibration flag).
- Injects mandatory licensing attribution statements.
