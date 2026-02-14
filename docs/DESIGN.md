# News App — Design Document

> Context-aware news retrieval system with LLM-powered query parsing.  
> This document outlines architecture, assumptions, trade-offs

---

## 1. Architecture Overview

### System Components

```
API Layer (FastAPI)
  /news (unified)
        ↓
Intent & Services
  - NewsService: parse → fetch → rank → paginate
  - TrendingService: aggregate → decay → cache
        ↓
Data Layer
  - MongoDB (articles, user_events)
  - Valkey/Redis (caching)
  - LLM (intent parsing, summarization)
        
Ingestion Pipeline
  load → normalize → upsert → async summarize
```

### Query Flow (Unified Endpoint)

1. User query → LLM parses intent (category, search, nearby, source).
2. Optional geocode resolution if intent is nearby.
3. MongoDB fetch (filters + $text / $geoNear), capped at 100 candidates.
4. Service-layer ranking (distance, weighted text score + relevance_score, or publication date depending on intent).
5. In-memory pagination.

---

## 2. Key Design Decisions

### 2.1 Technology Choices

| Choice | Why | Trade-off |
|--------|-----|-----------|
| **Python (FastAPI)** | Strong LLM ecosystem, async-friendly, rapid iteration | Not optimal for CPU-heavy scaling. |
| **MongoDB** | Flexible schema, built-in text + geo search, fast to prototype | Limited advanced ranking vs Elasticsearch/Atlas Search. |
| **Valkey/Redis** | Cache trending and repeated queries, reduce aggregation load | Cache invalidation complexity. |

### 2.2 Ranking Strategy (Hybrid Approach)

The system uses a **hybrid ranking approach**, combining database-level sorting with service-level ranking.

**Phase 1 — Database Filtering & Pre-Sorting**
- Apply geo, text, category/source filters
- Use MongoDB sorting (`$geoNear`, `$textScore`, `$sort`)
- Limit to 100 candidates

**Phase 2 — Service Ranking**
Apply intent-specific final ranking in Python:
- **Search** → weighted (text score + `relevance_score`)
- **Nearby** → distance-based (fallback if needed)
- **Score** → `relevance_score` descending
- **Category/Source** → publication date descending

Trade-off:  
- Slight in-memory sorting overhead after candidate retrieval.


### 2.3 Summary Generation

- Generated once at ingestion, stored in DB, non-personalized.
- Avoids per-request LLM latency and cost.
- Trade-off: Requires batch regeneration if model changes.

### 2.4 Intent Priority

When the LLM returns multiple intents for a single query:
The system supports multi-intent composition, meaning filters and ranking logic can be combined.

Intents are ordered by priority to determine how the pipeline executes ranking and geo resolution:

| Priority | Intent   | Rationale                      |
|----------|----------|--------------------------------|
| 1        | nearby   | Geo-constrained                |
| 2        | search   | Text relevance                 |
| 3        | category | Broad filter                   |
| 4        | source   | Publisher filter               |
| 5        | score    | Relevance threshold            |

### Multi-Intent Behavior

- **Filters are cumulative.**  
  - Example: `"Technology news near Mumbai"` → applies both `category` and `nearby`.

- **Ranking behavior follows priority order.**
  - If `nearby` is present, results are distance-ranked.
  - If `search` is present, weighted ranking is applied.
  - If neither applies, fallback ranking is publication date or relevance score.

The system does **not** enforce a single dominant intent.  
Instead, it allows composable query behavior while preserving deterministic ranking precedence.




### 2.5 Location Services

| Component | Choice | Why | Trade-off |
|-----------|--------|-----|-----------|
| **Geocoding** | Nominatim (OpenStreetMap) | Free, no API key; place-name → lat/lon | 1 req/sec rate limit; external dependency |
| **Radius** | Scope-based (`country` / `state` / `city`) | Fixed km per scope: city 50, state 300, country 1000 | Fixed values; no user override when LLM extracts place |
| **Geo search** | MongoDB `$geoNear` / `$geoWithin`, Haversine fallback | Native 2dsphere indexing; Haversine when combining text+geo | No geo-clustering; limited at scale |

**Radius planning when undefined**: If the user (or LLM) does not specify a radius, it is derived from Nominatim's `address_type`:

| Scope   | Radius (km) |
|---------|-------------|
| city    | 50          |
| state   | 300         |
| country | 1000        |
| other   | 10 (fallback, `default_radius_km`) |

**LLM and coordinates**: LLMs are unreliable for extracting lat/long directly. The pipeline uses `location_name` (place names) from the LLM and geocodes via Nominatim—not raw coordinates. Explicit lat/lon is only used when the API receives them directly (e.g. `/nearby?lat=...&lon=...`).

### 2.6 Performance Considerations

#### Candidate Cap (Limit 100)

MongoDB results are capped at **100 candidates** before service-layer ranking.

Rationale:
- The product returns only Top-N results (default 5).
- MongoDB pre-sorting (`$geoNear`, `$textScore`, `$sort`) already surfaces the most relevant items.
- Limiting candidates reduces memory usage, network transfer, and in-memory sorting cost.
- Ensures predictable latency as dataset size grows.

If the product evolves to support long scroll or deeper ranking evaluation, this cap can be increased or replaced with cursor-based pagination.

---

## 3. Core Assumptions

| Area | Assumption |
|------|------------|
| **Product** | Top-N results only. Multiple intents may be combined; ranking priority determines execution order, Generic summary (not personalized). |
| **Data** | Moderate dataset (thousands to tens of thousands). Batch ingestion. User events stored for trending (deduped by article_id + user_id). |
| **Technical** | Plain MongoDB. No stream processing. Geo via $geoNear or Haversine. Offset-based pagination. |

---

## 4. Trade-offs

| Decision | Pros | Cons |
|----------|------|------|
| **Top-N model** | Fast response, simple ranking | Not suitable for infinite scroll UX |
| **App-layer ranking** | Flexible scoring, easy experimentation | Slight extra latency |
| **Plain MongoDB search** | Simple deployment, Docker-friendly | Limited relevance, no typo tolerance or semantic search |
| **Query-time trending** | No additional infra, easy to implement | Requires caching for performance |

---

## 5. Scale-Out Roadmap

1. Replace Mongo text index with a **full-fledged search engine** (Atlas Search / Elasticsearch) to enable BM25 scoring, typo tolerance, faceting, and compound queries.

2. Move to **single-phase ranking inside the search layer**, combining text relevance, geo decay, recency, and engagement signals.

3. Introduce **vector semantic search** (hybrid lexical + embeddings) for semantic relevance and related-article discovery.

4. **Precompute and materialize top feeds** (home, category, region) in Redis for low-latency responses.

5. Shift trending to a **stream-based event pipeline** (Kafka/queue) with rolling windows (1h, 24h, 7d).

6. Add **personalized ranking and summaries** using user profiles and behavioral signals.

---
