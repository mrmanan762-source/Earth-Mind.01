# EarthMind RAG Stage R10 — Multi-Source Live Web Search Integration

## 1. Overview & Objective

Stage R10 implements the **Multi-Source Live Web Search Integration** layer for EarthMind RAG. It provides an extensible, provider-independent subsystem enabling the retrieval pipeline to obtain real-time, external web evidence for user queries processed by Stage R9 Query Processing, safely feeding Stage R11 Evidence Builder and Stage R12 Evidence Validator into Stage R13 and the B2 Context Manager.

### Target Multi-Source Architecture
```text
                       Stage R9 Query Processing
                                 │
                                 ▼
                     Stage R10 Web Search Engine
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
   Primary Web Search       Wikipedia API      Scholarly APIs
  (Brave Search / API)       (MediaWiki)    (Crossref / OpenAlex)
            │                    │                    │
            └────────────────────┬────────────────────┘
                                 │
                                 ▼
           URL Canonicalization & Cross-Provider Deduplication
                                 │
                                 ▼
               Agricultural Authoritative Domain Boost
               (ICAR, SAUs, Agri Depts, FAO, ICRISAT, etc.)
                                 │
                                 ▼
              Optional Safe Public Web Page Extraction
                        (SafeContentFetcher)
                                 │
                                 ▼
              Stage R11 Evidence Builder (EvidenceItem)
                                 │
                                 ▼
             Stage R12 Evidence Validator Gate (Validation)
                                 │
                                 ▼
           Stage R13 RAG Provider ──► B2 Context Manager
```

---

## 2. Hard Architectural Invariants & Governance

> **CRITICAL ARCHITECTURAL RULES:**
> 1. **Web Search ≠ Knowledge Base:** Web search results are current-query transient evidence for Stage R11 Evidence Builder. They are **NEVER** automatically published to the permanent Knowledge Base, **NEVER** written to the Qdrant vector index, **NEVER** stored in SQLite canonical repositories, and **NEVER** saved to Memory.
> 2. **Untrusted Data Plane:** Web-page content and search snippets are untrusted data. Embedded instructions within retrieved web pages are strictly treated as data context and never as system or developer instructions.
> 3. **Graceful Partial Failure:** If a supplementary search provider (such as Wikipedia or Crossref) experiences downtime, rate limits, or timeouts, the search engine records the error in `provider_statuses` and `partial_errors`, retaining all successful results without failing the request.

---

## 3. Implemented Search Providers

All providers adhere to the `IWebSearchProvider` protocol in `core/interfaces/web_search.py`:

### A. Primary General Web Search — Brave Search API
- **Module:** `modules/knowledge_base/web_search/providers/brave_provider.py` (`BraveWebSearchProvider`)
- **API Endpoint:** `https://api.search.brave.com/res/v1/web/search`
- **Authentication:** `X-Subscription-Token` header using `EARTHMIND_BRAVE_API_KEY`.
- **Capabilities:** Web search, snippet and description extraction, publication dates, freshness filtering, safe search, country and language localization.
- **Error Mapping:** Maps HTTP 401/403 to `WebSearchAuthenticationError`, 429 to `WebSearchRateLimitError`, and 5xx to `WebSearchProviderUnavailableError`.

### B. Encyclopedic Search — Wikipedia (MediaWiki API)
- **Module:** `modules/knowledge_base/web_search/providers/wikipedia_provider.py` (`WikipediaSearchProvider`)
- **API Endpoint:** `https://en.wikipedia.org/w/api.php` (supports automatic language subdomain adaptation, e.g. `hi.wikipedia.org`).
- **Capabilities:** Action API search, clean HTML snippet stripping, full canonical article URL construction, categorized under `result_type="encyclopedic"`.
- **Role:** Supplementary background information; never overrides official agricultural authorities.

### C. Scientific Literature — Crossref & OpenAlex APIs
- **Module:** `modules/knowledge_base/web_search/providers/scholarly_provider.py`
  1. **`CrossrefSearchProvider`:** Queries Crossref REST API (`https://api.crossref.org/works`) for peer-reviewed literature metadata, DOIs, author attribution, publication years, journals, and abstracts.
  2. **`OpenAlexSearchProvider`:** Queries OpenAlex API (`https://api.openalex.org/works`) for open-access scientific works, reconstructs abstracts from inverted indexes, extracts landing page URLs, and tracks citation counts.
- **Attribution:** Categorized under `result_type="scholarly"`.

### D. Safe Public Web Page Content Retriever (`SafeContentFetcher`)
- **Module:** `modules/knowledge_base/web_search/content_fetcher.py`
- **SSRF Defense:** Resolves DNS and blocks private IP networks (RFC 1918, RFC 3927 link-local, loopback, IPv6 local, and cloud metadata endpoints such as `169.254.169.254` and `metadata.google.internal`).
- **Redirect Protection:** Disallows unvalidated redirects; re-validates destination hostnames and IPs on every hop.
- **Resource Protection:** Enforces strict connection/read timeouts and payload size limits (default 1MB).
- **Execution Safety:** Parses HTML and extracts clean readable text using BeautifulSoup, completely discarding `<script>`, `<style>`, `<iframe>`, and tracking tags without executing JavaScript.

---

## 4. Agricultural Authoritative Source Prioritization

`WebSearchEngine` prioritizes verified official agricultural and research sources:
- **Indian National Institutes:** ICAR (`icar.org.in`), IARI (`iari.res.in`), IIPR, CICR, CPRI, IIWBR, DRMR, DOGR, NRRI, CRIDA.
- **Ministries & Extension:** `agricoop.gov.in`, `agriwelfare.gov.in`, `farmer.gov.in`, `kvk.icar.gov.in`.
- **State Agricultural Universities (SAUs):** PAU (`pau.edu`), TNAU (`tnau.ac.in`), UAS Bangalore, ANGRAU, PJTSAU, BAU Sabour, RPCAU, CCSHAU, SKNAU.
- **International CGIAR Centers & Agencies:** FAO (`fao.org`), CGIAR (`cgiar.org`), IRRI, CIMMYT, ICRISAT.

Matching results are assigned `result_type="agricultural"` and receive an automatic score boost (`trusted_domain_boost`), ensuring official extension bulletins and research take precedence over unverified blogs.

---

## 5. Configuration & Environment Variables

Configure Stage R10 in `.env` (or environment):

```bash
# Primary search provider: 'brave', 'api', or 'fake'
EARTHMIND_WEB_SEARCH_PROVIDER=brave
EARTHMIND_WEB_SEARCH_TIMEOUT=10.0
EARTHMIND_WEB_SEARCH_MAX_RESULTS=10
EARTHMIND_WEB_SEARCH_SAFE_SEARCH=true
EARTHMIND_WEB_SEARCH_USER_AGENT="EarthMind-RAG/1.0 (+https://github.com/earthmind)"

# Primary: Brave Search API
EARTHMIND_BRAVE_API_KEY=your_brave_api_key_here
EARTHMIND_BRAVE_ENDPOINT=https://api.search.brave.com/res/v1/web/search
EARTHMIND_BRAVE_COUNTRY=in
EARTHMIND_BRAVE_SEARCH_LANG=en
EARTHMIND_BRAVE_ENABLE_LLM_CONTEXT=false

# Supplementary: Wikipedia
EARTHMIND_WIKIPEDIA_ENABLED=true
EARTHMIND_WIKIPEDIA_ENDPOINT=https://en.wikipedia.org/w/api.php
EARTHMIND_WIKIPEDIA_MAX_RESULTS=3

# Supplementary: Scientific Literature
EARTHMIND_CROSSREF_ENABLED=true
EARTHMIND_CROSSREF_ENDPOINT=https://api.crossref.org/works
EARTHMIND_CROSSREF_MAILTO=research@earthmind.org
EARTHMIND_CROSSREF_MAX_RESULTS=3

EARTHMIND_OPENALEX_ENABLED=true
EARTHMIND_OPENALEX_ENDPOINT=https://api.openalex.org/works
EARTHMIND_OPENALEX_EMAIL=research@earthmind.org
EARTHMIND_OPENALEX_MAX_RESULTS=3

# Safe Page Text Fetching
EARTHMIND_WEB_FETCH_CONTENT=false
EARTHMIND_WEB_FETCH_TIMEOUT=5.0
EARTHMIND_WEB_FETCH_MAX_BYTES=1048576

# Trusted Agricultural Domain Score Boost
EARTHMIND_TRUSTED_DOMAIN_BOOST=0.2
```

---

## 6. Manual Setup Instructions for Manan

To activate live Brave Web Search in production or local development:

1. **Obtain API Key:**
   - Navigate to [Brave Search API Portal](https://brave.com/search/api/).
   - Sign up or log in. Select an appropriate API plan (free tier offers 2,000 queries/month).
   - If activating any paid tier, obtain proper adult/guardian approval prior to entering payment information.
2. **Configure Environment:**
   - In your local `.env` or deployment environment, set:
     ```bash
     EARTHMIND_WEB_SEARCH_PROVIDER=brave
     EARTHMIND_BRAVE_API_KEY=<your_subscription_token_here>
     ```
   - **SECURITY WARNING:** Never paste your API key into ordinary chat, issue trackers, pull requests, or Git commits.
   - When running offline or without an API key, set `EARTHMIND_WEB_SEARCH_PROVIDER=fake` to use the deterministic offline simulator.
