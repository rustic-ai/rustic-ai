# Uniko Research Guild - Message Flow Diagram

## Overview
The Uniko Research Guild implements an intelligent research system with persistent memory, combining knowledge recall, web research, and synthesis capabilities.

---

## Complete Message Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INPUT                                      │
│                   (ChatCompletionRequest)                                    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   UserProxyAgent      │
                    │   Content Analyzer    │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴───────────────┐
                    │  Content-Based Router     │
                    │  Detects: Files/URLs/Text │
                    └───────┬───────────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌──────────────┐  ┌──────────┐  ┌────────────────┐
    │ Has Files?   │  │ Has URLs?│  │ Plain Text?    │
    │ (image_url,  │  │          │  │                │
    │  file_url)   │  │          │  │                │
    └──────┬───────┘  └────┬─────┘  └────┬───────────┘
           │               │               │
           ▼               ▼               ▼
    IngestDocument   WebScraping      RecallRequest
    Request          Request           
           │               │               │
           ▼               ▼               │
    ┌────────────┐  ┌──────────────┐     │
    │ Memory     │  │ Playwright   │     │
    │ Agent      │  │ Agent        │     │
    │ (ingest)   │  │ (scrape)     │     │
    └─────┬──────┘  └──────┬───────┘     │
          │                │              │
          ▼                ▼              │
    IngestOutcome     MediaLink          │
          │                │              │
          │                └──────┐       │
          │                       ▼       │
          │              IngestDocument   │
          │              Request          │
          │                       │       │
          │                       ▼       │
          │              ┌────────────┐   │
          │              │ Memory     │   │
          │              │ Agent      │   │
          │              │ (ingest)   │   │
          │              └─────┬──────┘   │
          │                    │          │
          └────────────────────┼──────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Transform to         │
                    │ ObserveTurnRequest   │
                    │ "Ingested X chunks"  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Memory Agent         │
                    │ (observe_turn)       │
                    └──────────┬───────────┘
                               │
                               ▼
                         ObserveResult
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Transform to         │
                    │ RecallRequest        │
                    └──────────┬───────────┘
                               │
┌──────────────────────────────┘
│
│  MEMORY RECALL FLOW
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Memory Agent (recall)                         │
│                                                                      │
│  • Performs 3-phase cascade recall                                  │
│  • Returns ranked items with sources                                │
│  • Calculates coverage score                                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
                         RecallResponse
                               │
                    ┌──────────┴──────────────────────┐
                    │  Content Router — PRE-RESEARCH   │
                    │  gate. No-ops (null) whenever:   │
                    │   - current_id already answered  │
                    │   - context.research_phase ==    │
                    │     "post_research" (that case   │
                    │     is handled by the            │
                    │     POST-RESEARCH gate below)    │
                    └──────────────┬───────────────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
              Good Recall                  Poor Recall
              (score > 0.05)               (score <= 0.05)
                     │                           │
                     ▼                           ▼
                AnswerRequest             Query Generation
                     │                           │
                     ▼                           ▼
           ┌──────────────────┐        ┌────────────────┐
           │ Memory Agent     │        │ Query Agent    │
           │ (answer)         │        │ (LLM)          │
           │                  │        │                │
           │ - Uses LLM       │        │ Generates 5-7  │
           │ - Returns answer │        │ optimized      │
           │ - With citations │        │ sub-queries    │
           └────────┬─────────┘        └────────┬───────┘
                    │                            │
                    ▼                            ▼
              AnswerResponse           ChatCompletionResponse
                    │                            │
                    ▼                            ▼
      ┌────────────────────────────┐    ┌────────────────┐
      │ ChatCompletionResponse     │    │ Splitter Agent │
      │ to user_message_broadcast  │    │ Splits queries │
      │ PROCESS: completed         │    │ by "####"      │
      └──────────────┬─────────────┘    └────────┬───────┘
                     │                           │
                     ▼                           ▼
          USER OUTPUT (Fast Path)        Multiple SERPQuery
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Search Agent   │
                                          │ (SerpAPI)      │
                                          │                │
                                          │ OR             │
                                          │                │
                                          │ Google Research│
                                          │ Agent (Vertex) │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                              SERPResults
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Transform to   │
                                          │ WebScrapingReq │
                                          │ Filter social  │
                                          │ media links    │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Playwright     │
                                          │ Agent          │
                                          │                │
                                          │ Scrapes pages  │
                                          │ Returns        │
                                          │ markdown       │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                              MediaLink
                                                   │
                                                   ▼
                                          IngestDocumentRequest
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Memory Agent   │
                                          │ (ingest)       │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                             IngestOutcome
                                                   │
                                                   ▼
                                          ObserveTurnRequest
                                                   │
                                                   ▼
                                             ObserveResult
                                                   │
                                                   ▼
                                  ┌────────────────────────┐
                                  │ Basic Wiring Agent tags│
                                  │ context.research_phase│
                                  │ = "post_research"     │
                                  └──────────┬─────────────┘
                                             │
                                             ▼
                                        RecallRequest
                                             │
                                             ▼
                                       RecallResponse
                                             │
                                             ▼
                                  ┌─────────────────────────┐
                                  │ POST-RESEARCH gate      │
                                  │ (only fires when        │
                                  │ research_phase ==       │
                                  │ "post_research")        │
                                  │ - items > 0 -> Synthesis│
                                  │ - items = 0 -> fallback │
                                  │   "no memories" reply  │
                                  │ - marks answered either│
                                  │   way (stops the loop) │
                                  └──────────┬─────────────┘
                                             │
                                             ▼
                                          ┌────────────────┐
                                          │ Transform to   │
                                          │ Synthesis Req  │
                                          │ with context   │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Synthesis      │
                                          │ Agent (LLM)    │
                                          │                │
                                          │ Analyzes all   │
                                          │ sources        │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                      ChatCompletionResponse
                                                   │
                                                   ▼
                                          ObserveTurnRequest
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ Memory Agent   │
                                          │ (observe)      │
                                          │ Stores synth   │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                             ObserveResult
                                                   │
                                                   ▼
                                        ┌──────────────────┐
                                        │ Transform to     │
                                        │ User Response    │
                                        └──────────┬───────┘
                                                   │
                                                   ▼
                                    ┌──────────────────────────┐
                                    │ ChatCompletionResponse   │
                                    │ to user_message_broadcast│
                                    │                          │
                                    │ PROCESS: completed       │
                                    └──────────────────────────┘
                                                   │
                                                   ▼
                                   USER OUTPUT (Research Path)
```

---

## Gateway Agent Flow (G2G Communication)

```
┌────────────────────────────────────────────────────────┐
│                  External Guild                         │
│             (sends ResearchRequest)                     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ Gateway Agent    │
              │ (receives)       │
              └─────────┬────────┘
                        │
                        ▼
                  RecallRequest
                        │
                        ▼
        [Same flow as above from RecallRequest]
                        │
                        ▼
                  ResearchResults
                        │
                        ▼
              ┌──────────────────┐
              │ Gateway Agent    │
              │ (returns)        │
              └─────────┬────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ External Guild   │
              │ receives results │
              └──────────────────┘
```

---

## Key Message Transformations

### 1. User Input → Initial Route Decision
```javascript
// Checks content type
$hasFiles = $count($content[type in ["image_url", "file_url"]]) > 0
$hasUrls = $count($urls) > 0

// Routes to:
// - IngestDocumentRequest (if files)
// - WebScrapingRequest (if URLs)
// - RecallRequest (if plain text)
```

### 2. RecallResponse → Decision Logic (Pre-Research)
```javascript
// Checks if already answered
$is_answered = $.context.current_id in $.guild_state.answered

// Checks if this recall is the post-research follow-up (handled by rule 2a below instead)
$is_post_research = $.context.research_phase = "post_research"

// Checks recall quality
$has_good_recall = $count($.payload.items[score > 0.05]) > 0

// Routes to:
// - null (already answered, OR this is the post-research recall)
// - AnswerRequest (good recall on the first pass)
// - Query Agent (poor recall on the first pass — kicks off research)
```

### 2a. RecallResponse → Decision Logic (Post-Research)
```javascript
// Only acts on the recall that was tagged by the Basic Wiring Agent
// after the ingest → observe → recall follow-up loop
$is_post_research = $.context.research_phase = "post_research"
$is_answered = $.context.current_id in $.guild_state.answered

// Routes to:
// - null (already answered, OR this is NOT the post-research recall —
//   left for rule 2 above to decide)
// - Synthesis Request (post-research recall found items)
// - Fallback "no relevant memories" reply (post-research recall found nothing)
//
// Either branch marks current_id as answered, so this recall can never
// re-trigger Query Agent or re-fire Synthesis again.
```

**Why two separate rules exist:** Rustic AI's routing slip fires *every* rule whose
`(agent, message_format)` matches — not just the first match — so rule 2 and rule 2a
both evaluate on every `RecallResponse` from the Memory Agent. The `research_phase`
context flag is what keeps them mutually exclusive: rule 2 only acts when the flag is
absent (first pass), rule 2a only acts when it's `"post_research"` (follow-up pass).
Without this flag, a low recall score (which rarely crosses even a well-calibrated
threshold once the corpus fills up with tangential scraped pages) would cause rule 2
to keep re-dispatching Query Agent forever — this was the root cause of the
ingestion/search loop that used to never converge.

**Why the score threshold is `0.05`, not `0.3`:** `item.score` is **not** a 0–1 cosine
similarity — it's a raw Reciprocal Rank Fusion value from the Uniko memory engine
(`uniko-memory/src/recall/mod.rs`): `contribution = 1 / (rrf_k + rank)` with
`rrf_k = 60`, summed across every retrieval channel that surfaces the item (fulltext /
vector × Message / Observation / Episode, plus query-reformulation variants), then
multiplied by a tier weight of `0.4`–`1.0`. In practice:

| Scenario | Approx. score |
|---|---|
| Single channel, weak rank, low-tier hit (noise) | 0.005 – 0.02 |
| One channel, rank 0, high-tier Fact hit | ~0.017 |
| 3 channels agreeing at rank 0, mid-to-high tier | 0.025 – 0.05 |
| 5 channels agreeing at rank 0, high tier (near-perfect match) | ~0.08 |

A score of `0.3` would require an item to rank **#1 across nearly every channel and
every query reformulation simultaneously** — a bar only a near-exact duplicate could
clear. Real recall traffic tops out around 0.01–0.06, so `0.3` made "good recall" not
just rare but *unreachable*, forcing every recall down the "poor recall → research"
path forever regardless of how relevant the memory actually was. `0.05` requires
genuine multi-channel agreement (not a single low-rank hit) while staying inside the
range real matches actually produce.

### 3. IngestOutcome → ObserveTurnRequest
```javascript
{
  "sender_id": "memory_agent",
  "content": "Ingested document: " + chunk_count + " chunks, " + 
             entity_count + " entities extracted",
  "metadata": {
    "chunk_count": ...,
    "page_count": ...,
    "artifact_node_id": ...
  }
}
```

### 4. SERPResults → WebScrapingRequest
```javascript
{
  "links": $.results[!url.includes("linkedin|facebook|instagram|twitter")],
  "depth": "0",
  "output_format": "text/markdown"
}
```

### 5. RecallResponse → Synthesis Request
```javascript
{
  "messages": [{
    "role": "user",
    "content": "Context from research:\n" + 
               join(items.content, "\n\n") + 
               "\n\nOriginal Question: " + query +
               "\n\nProvide comprehensive answer..."
  }]
}
```

---

## Agent Roles Summary

| Agent | Purpose | Input Formats | Output Formats |
|-------|---------|---------------|----------------|
| **Memory Agent** | 5-tier cognitive memory system | ObserveTurnRequest, RecallRequest, AnswerRequest, IngestDocumentRequest | ObserveResult, RecallResponse, AnswerResponse, IngestOutcome |
| **Google Research Agent** | Google Search with grounding | ChatCompletionRequest | ChatCompletionResponse |
| **Search Agent (SERP)** | Search engine results | SERPQuery | SERPResults |
| **Playwright Agent** | Web scraping | WebScrapingRequest | MediaLink |
| **Query Agent** | Query generation & optimization | ChatCompletionRequest | ChatCompletionResponse (with queries) |
| **Synthesis Agent** | Multi-source synthesis | ChatCompletionRequest | ChatCompletionResponse |
| **Splitter Agent** | Query splitting | ChatCompletionResponse | Multiple SERPQuery |
| **Basic Wiring Agent** | Message routing/transformation | Various | Various |
| **Gateway Agent** | G2G communication | ResearchRequest | ResearchResults |

---

## State Management

The guild maintains state across message flows:

```javascript
guild_state = {
  "user_queries": [],        // All user queries
  "current_id": 0,          // Current query ID
  "answered": []            // IDs of answered queries
}
```

Additionally, each message thread carries **per-message context** (not persisted in
`guild_state`, but propagated hop-to-hop automatically unless a transformer overwrites it):

```javascript
context = {
  "original_query": "...",   // The user's original question, threaded through every hop
  "current_id": 0,           // Matches guild_state.current_id for this query
  "research_phase": null     // Set to "post_research" only on the recall that follows
                              // the query-generation → search → scrape → ingest loop
}
```

**State Updates:**
- User input → Increments `current_id`, appends to `user_queries`
- Good recall (first pass) or post-research recall → Adds `current_id` to `answered` array
- `answered` prevents duplicate answers/synthesis for the same query ID
- `context.research_phase` distinguishes the *first* recall (which may trigger research)
  from the *post-research* recall (which must never re-trigger research) — see
  [RecallResponse → Decision Logic](#2-recallresponse--decision-logic-pre-research) above

---

## Completion Points

Routes marked with `process_status: "completed"`:

1. **Direct Memory Answer** → User (when recall is sufficient)
2. **Synthesized Answer** → User (after web research)
3. **Gateway Response** → External guild (for G2G requests)

All completion points send to `user_message_broadcast` topic.

---

## Flow Patterns

### Pattern 1: Fast Path (Memory Hit)
```
User → Recall → Good Score → Answer → User
(~2 agent hops, <1s)
```

### Pattern 2: Research Path (Memory Miss)
```
User → Recall → Poor Score → Query Gen → Search → 
Scrape → Ingest → Recall → Synthesis → User
(~9 agent hops, 5-15s)
```

### Pattern 3: Direct URL
```
User → URL Detect → Scrape → Ingest → Observe → 
Recall → Synthesis → User
(~6 agent hops, 3-8s)
```

### Pattern 4: File Upload
```
User → File Detect → Ingest → Observe → User
(~3 agent hops, 1-3s)
```

---

## Notes

- **Loop Prevention**: Two mechanisms work together to stop the research loop from
  re-triggering itself:
  1. `context.research_phase = "post_research"` tags the recall that follows the
     ingest → observe → recall loop, so the pre-research decision rule (2) never fires
     Query Agent again for it — only the post-research rule (2a) is allowed to act.
  2. `guild_state.answered` records `current_id` once a query has been answered
     (either via direct recall or via synthesis), blocking any further routing for
     that same query.
- **Why both are needed**: Rustic AI's routing slip evaluates *every* rule matching an
  `(agent, message_format)` pair on each message — it does not stop at the first match —
  so overlapping `RecallResponse` rules must be made mutually exclusive with an explicit
  context flag (`research_phase`) rather than relying on recall-score thresholds alone,
  since scores can legitimately stay low forever on a noisy corpus.
- **Parallel Processing**: Multiple SERP queries execute in parallel (2 subqueries ×
  Google + SerpAPI engines); each spawns its own scrape → ingest → recall chain sharing
  the same `current_id`, so `answered` may race across a handful of parallel branches
  before it's set — bounded duplication, not an infinite loop.
- **Social Media Filtering**: LinkedIn, Facebook, Instagram, Twitter links excluded from scraping
- **Persistent Memory**: All ingested content stored in Uniko for future recall
- **Adaptive Routing**: Content-based routers make intelligent decisions based on message content and guild state
