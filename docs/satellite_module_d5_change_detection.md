# EarthMind Satellite Intelligence Module — Stage D5: Change Detection Engine

> **Component:** `SatelliteChangeDetector`
> **Stage:** D5 — Spectral, Geospatial & Temporal Analysis
> **Standard:** EarthMind Architecture Specification v1.0

---

## 1. Overview

The `SatelliteChangeDetector` performs pixel-level and zonal comparisons between two compatible satellite acquisitions over the same geographic location.

$$\Delta_{\text{pixel}} = \text{Matrix}_{T2} - \text{Matrix}_{T1}$$

---

## 2. Categorization & Metrics

For a given sensitivity threshold (default $\tau = 0.05$):
- **Increased Pixels:** $\Delta > \tau$
- **Decreased Pixels:** $\Delta < -\tau$
- **Stable Pixels:** $|\Delta| \le \tau$

Statistical summaries report mean $\Delta$, minimum $\Delta$, maximum $\Delta$, standard deviation of $\Delta$, and area percentage per category.

---

## 3. Strict Non-Diagnostic Principle

Observed negative changes in vegetation indices indicate spectral decline, but **must never** automatically be labeled as crop disease, insect damage, moisture stress, or herbicide burn. Ground diagnosis is strictly reserved for farmer ground truth and Sarvam-105B reasoning via B2 Context Manager.
