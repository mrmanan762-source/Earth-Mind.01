# EarthMind Real Agricultural Knowledge Corpus Foundation (R2)

This directory houses the initial real agricultural knowledge corpus for EarthMind's RAG system.

## Directory Structure

```text
data/
└── knowledge/
    ├── raw/              # Raw, unaltered source artifacts (.txt, .md, .json, etc.)
    ├── manifest/         # Machine-readable corpus manifest (corpus_manifest.json)
    └── README.md         # Documentation for the corpus foundation
```

## Corpus Scope & Categories

The prototype corpus covers 8 authoritative agricultural categories:
1. General Agriculture (ICAR Good Agricultural Practices & Crop Production Strategies)
2. Crop Knowledge (ICAR Rice Cultivation & Package of Practices)
3. Crop Diseases / Pests (ICAR-NCIPM Integrated Pest Management for Wheat & Vegetables)
4. Soil / Soil Health (Soil Health Card Scheme & Soil Nutrient Guidelines)
5. Irrigation / Water Management (PMKSY Micro-Irrigation & Water Conservation Guidelines)
6. Fertilizer / Nutrient Management (ICAR-IISS Balanced Nutrient Management & Neem Coated Urea)
7. Government / Agricultural Guidelines (PM-KISAN & KVK Extension Advisory Guidelines)
8. Regional / Indian Agricultural Practices (Rainfed & Dryland Farming Practices in India)

## C.2 Pipeline Compatibility

This corpus foundation maps seamlessly into C.2 canonical domain models:
`Source` → `Artifact` → `Document` → `DocumentVersion` → `Section` → `KnowledgeUnit` → `Chunk`

R2 preserves original raw artifacts, SHA-256 cryptographic checksums, source attribution, licensing/copyright status, and source assessment signals without performing vector embeddings or Qdrant indexing.
