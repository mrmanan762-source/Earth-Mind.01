# EarthMind RAG Stage R10 — Multi-Source Live Web Search Integration

## 1. Overview & Objective

Stage R10 implements the **Multi-Source Live Web Search Integration** layer for EarthMind RAG. It provides an extensible, provider-independent subsystem enabling the retrieval pipeline to obtain real-time, external web evidence for user queries processed by Stage R9 Query Processing, safely feeding Stage R11 Evidence Builder and Stage R12 Evidence Validator into Stage R13 and the B2 Context Manager.

### Target Multi-Source Architecture
```text
                                 Stage R9 Query Processing
                                            │
                                            ▼
                               Stage R10 Web Search Engine
            ┌───────────────────┬───────────┼───────────┬───────────────────┐
            ▼                   ▼           ▼           ▼                   ▼
    Primary Search          Wikipedia    Wikidata    Scholarly          NASA POWER
 (Brave/Tavily/Gemini/API) (MediaWiki)   (SPARQL) (Crossref/OpenAlex) (Agroclimatology)
            │                   │           │           │                   │
            └───────────────────┴─────┬─────┴───────────┴───────────────────┘
                                      │
                                      ▼
             URL Canonicalization & Cross-Provider Deduplication
           (Exempts structured Wikidata & numerical NASA POWER data)
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
> 3. **Graceful Partial Failure:** If a supplementary search provider (such as Wikipedia, Wikidata, or NASA POWER) experiences downtime, rate limits, or timeouts, the search engine records the error in `provider_statuses` and `partial_errors`, retaining all successful results without failing the request.
> 4. **Data-Type Separation:** Structured facts (Wikidata entities) and numerical agroclimatological data (NASA POWER) are not ordinary web search results and must never be collapsed or lost during URL deduplication.

---

## 3. Provider Catalog & Implementations

All providers adhere to the `IWebSearchProvider` protocol in `core/interfaces/web_search.py`.

### A. Free Public API Providers (Fully Implemented & Active)

#### 1. Wikipedia — MediaWiki API
- **Module:** `modules/knowledge_base/web_search/providers/wikipedia_provider.py` (`WikipediaSearchProvider`)
- **Official API:** `https://en.wikipedia.org/w/api.php`
- **Purpose:** General encyclopedic knowledge, crop descriptions, botanical history, definitions.
- **Authentication:** None required (Public access).
- **Result Type:** `result_type="encyclopedic"`
- **Capabilities:** Action API queries, HTML snippet stripping, canonical article URL formatting, multilingual language subdomain routing (e.g. `hi.wikipedia.org`).

#### 2. Wikidata — SPARQL Query Service
- **Module:** `modules/knowledge_base/web_search/providers/wikidata_provider.py` (`WikidataSearchProvider`)
- **Official API:** `https://query.wikidata.org/sparql`
- **Purpose:** Structured facts, entity linking, botanical classification, scientific names (`wdt:P225`), identifiers.
- **Authentication:** None required (Public query access; User-Agent header required).
- **Result Type:** `result_type="structured_fact"`
- **Capabilities:** SPARQL queries using `wikibase:mwapi` EntitySearch and label services, structured metadata (`qid`, `label`, `description`, `taxon_name`), direct entity URLs (`https://www.wikidata.org/wiki/{qid}`). Exempt from URL-based deduplication collapse.

#### 3. Crossref — REST API
- **Module:** `modules/knowledge_base/web_search/providers/scholarly_provider.py` (`CrossrefSearchProvider`)
- **Official API:** `https://api.crossref.org/works`
- **Purpose:** Scholarly publication metadata, DOI discovery, author attribution, peer-reviewed journal articles.
- **Authentication:** None required for public access.
- **Polite Pool:** Supports configurable `EARTHMIND_CROSSREF_MAILTO` in request headers.
- **Result Type:** `result_type="scholarly"`
- **Capabilities:** DOI metadata, author list parsing, journal container titles, abstracts, publication dates.

#### 4. OpenAlex — API
- **Module:** `modules/knowledge_base/web_search/providers/scholarly_provider.py` (`OpenAlexSearchProvider`)
- **Official API:** `https://api.openalex.org/works`
- **Documentation:** `https://docs.openalex.org/`
- **Purpose:** Academic research papers, authors, institutions, open-access scholarly discovery.
- **Authentication:** Basic public access without key; optional API key supported via `EARTHMIND_OPENALEX_API_KEY` for higher throughput.
- **Result Type:** `result_type="scholarly"`
- **Capabilities:** Abstract reconstruction from inverted index, open-access landing page discovery, citation metrics (`cited_by_count`).

#### 5. NASA POWER — API
- **Module:** `modules/knowledge_base/web_search/providers/nasa_power_provider.py` (`NasaPowerSearchProvider`)
- **Official Portal & API:** `https://power.larc.nasa.gov/api/temporal/daily/point`
- **Purpose:** Numerical environmental and agroclimatological data (temperature T2M, precipitation PRECTOTCORR, solar radiation ALLSKY_SFC_SW_DWN).
- **Authentication:** None required for public access.
- **Result Type:** `result_type="agroclimatology"`
- **Capabilities:** Coordinate resolution from request filters/metadata/query text, time-window calculation, summary metrics (mean, min, max, total precipitation), raw daily time-series preservation in `metadata`. Data is strictly separated from ordinary web search HTML results and exempt from URL deduplication.

---

### B. Managed Search Providers (Prepared, Awaiting Credentials)

#### 6. Tavily — Primary Managed Web Search Provider
- **Module:** `modules/knowledge_base/web_search/providers/tavily_provider.py` (`TavilySearchProvider`)
- **Official Website:** `https://www.tavily.com/`
- **Role:** Primary managed search provider.
- **Configuration Variable:** `EARTHMIND_WEB_SEARCH_TAVILY_API_KEY`
- **State:** **IMPLEMENTED — LIVE CREDENTIALS PENDING**
- **Safety Guard:** `is_available()` returns `False` when `tavily_api_key` is not configured. Calls without credentials raise `WebSearchAuthenticationError` without crashing the search engine.
- **Output Handling:** Parses AI-optimized search snippets, answers, scores, and organic links into `WebSearchResult` (`result_type="web"`).

#### 7. Gemini Grounding with Google Search — Secondary Managed Search Provider
- **Module:** `modules/knowledge_base/web_search/providers/gemini_grounding_provider.py` (`GeminiGroundingSearchProvider`)
- **Official Documentation:** `https://ai.google.dev/gemini-api/docs/google-search`
- **Role:** Secondary managed search and grounded research provider.
- **Configuration Variable:** `EARTHMIND_WEB_SEARCH_GEMINI_API_KEY`
- **State:** **IMPLEMENTED — LIVE CREDENTIALS PENDING**
- **Safety Guard:** `is_available()` returns `False` when `gemini_api_key` is not configured. Calls without credentials raise `WebSearchAuthenticationError` without crashing the search engine.
- **Output Handling:** Specifically handles Gemini Grounding response structures: extracting grounded text, generated search queries (`web_search_queries`), grounding chunks (source URIs and titles), and grounding support citation segments into `WebSearchResult` (`result_type="grounded_search"`).

---

### C. Safe Public Web Page Content Retriever (`SafeContentFetcher`)
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
# Primary search provider: 'brave', 'tavily', 'gemini_grounding', 'api', or 'fake'
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

# Managed: Tavily Search API (Prepared, pending credentials)
# EARTHMIND_WEB_SEARCH_TAVILY_API_KEY=your_tavily_api_key_here
# EARTHMIND_TAVILY_ENDPOINT=https://api.tavily.com/search

# Managed: Gemini Grounding with Google Search (Prepared, pending credentials)
# EARTHMIND_WEB_SEARCH_GEMINI_API_KEY=your_gemini_api_key_here
# EARTHMIND_GEMINI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent

# Supplementary: Wikipedia
EARTHMIND_WIKIPEDIA_ENABLED=true
EARTHMIND_WIKIPEDIA_ENDPOINT=https://en.wikipedia.org/w/api.php
EARTHMIND_WIKIPEDIA_MAX_RESULTS=3

# Supplementary: Wikidata SPARQL
EARTHMIND_WIKIDATA_ENABLED=true
EARTHMIND_WIKIDATA_ENDPOINT=https://query.wikidata.org/sparql
EARTHMIND_WIKIDATA_MAX_RESULTS=3

# Supplementary: Scientific Literature (Crossref & OpenAlex)
EARTHMIND_CROSSREF_ENABLED=true
EARTHMIND_CROSSREF_ENDPOINT=https://api.crossref.org/works
EARTHMIND_CROSSREF_MAILTO=research@earthmind.org
EARTHMIND_CROSSREF_MAX_RESULTS=3

EARTHMIND_OPENALEX_ENABLED=true
EARTHMIND_OPENALEX_ENDPOINT=https://api.openalex.org/works
EARTHMIND_OPENALEX_EMAIL=research@earthmind.org
# EARTHMIND_OPENALEX_API_KEY=your_optional_openalex_api_key_placeholder
EARTHMIND_OPENALEX_MAX_RESULTS=3

# Supplementary: NASA POWER Agroclimatology
EARTHMIND_NASA_POWER_ENABLED=true
EARTHMIND_NASA_POWER_ENDPOINT=https://power.larc.nasa.gov/api/temporal/daily/point
EARTHMIND_NASA_POWER_COMMUNITY=AG

# Safe Page Text Fetching
EARTHMIND_WEB_FETCH_CONTENT=false
EARTHMIND_WEB_FETCH_TIMEOUT=5.0
EARTHMIND_WEB_FETCH_MAX_BYTES=1048576

# Trusted Agricultural Domain Score Boost
EARTHMIND_TRUSTED_DOMAIN_BOOST=0.2
```

---

## 6. Manual Setup & Activation Instructions for Manan

### A. Free Public APIs
All five free public providers (**Wikipedia**, **Wikidata**, **Crossref**, **OpenAlex**, **NASA POWER**) are active and require **NO** manual key acquisition. They function out of the box.

Optional OpenAlex boost:
```bash
# Optional: if higher throughput is required
EARTHMIND_OPENALEX_API_KEY=<your_openalex_api_key>
```

### B. Managed Search Provider Activation (Pending Credentials)

When ready, Manan can obtain and securely configure credentials for our two managed providers:

#### 1. Tavily — Primary Managed Web Search Provider
1. **Obtain API Key:**
   - Navigate to [Tavily Search](https://www.tavily.com/).
   - Sign up and copy your API key from the developer dashboard.
2. **Configure Environment:**
   - In your `.env` or secure production secrets manager, set:
     ```bash
     EARTHMIND_WEB_SEARCH_PROVIDER=tavily
     EARTHMIND_WEB_SEARCH_TAVILY_API_KEY=<your_tavily_api_key_here>
     ```
   - Restart the EarthMind service. `WebSearchEngine` will automatically route primary search requests through Tavily.

#### 2. Gemini Grounding with Google Search — Secondary Managed Search Provider
1. **Obtain API Key:**
   - Navigate to [Google AI Studio](https://aistudio.google.com/) or Google Cloud Vertex AI.
   - Create an API key with access to Gemini 1.5 models and search grounding.
2. **Configure Environment:**
   - In your `.env` or secure production secrets manager, set:
     ```bash
     EARTHMIND_WEB_SEARCH_PROVIDER=gemini_grounding
     EARTHMIND_WEB_SEARCH_GEMINI_API_KEY=<your_gemini_api_key_here>
     ```
   - Restart the EarthMind service. `WebSearchEngine` will automatically execute search grounding via Gemini.

> **SECURITY WARNING:**
> Never paste API keys into chat, PRs, issue trackers, or Git commits. Always keep `.env` in `.gitignore`.
