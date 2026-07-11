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
                    ┌──────────┴──────────┐
                    │  Content Router     │
                    │  Decision Logic:    │
                    │  1. Already answered│
                    │  2. Good recall?    │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
      Already            Good Recall         Poor Recall
      Answered?          (score > 0.3)       (score ≤ 0.3)
            │                  │                  │
            ▼                  ▼                  ▼
         STOP            AnswerRequest      Query Generation
                              │                  │
                              ▼                  ▼
                    ┌──────────────────┐  ┌────────────────┐
                    │ Memory Agent     │  │ Query Agent    │
                    │ (answer)         │  │ (LLM)          │
                    │                  │  │                │
                    │ • Uses LLM       │  │ Generates 5-7  │
                    │ • Returns answer │  │ optimized      │
                    │ • With citations │  │ sub-queries    │
                    └────────┬─────────┘  └────────┬───────┘
                             │                     │
                             ▼                     ▼
                       AnswerResponse    ChatCompletionResponse
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Splitter Agent │
                             │            │                │
                             │            │ Splits queries │
                             │            │ by "####"      │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │            Multiple SERPQuery
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Search Agent   │
                             │            │ (SerpAPI)      │
                             │            │                │
                             │            │ OR             │
                             │            │                │
                             │            │ Google Research│
                             │            │ Agent (Vertex) │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │                SERPResults
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Transform to   │
                             │            │ WebScrapingReq │
                             │            │ Filter social  │
                             │            │ media links    │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Playwright     │
                             │            │ Agent          │
                             │            │                │
                             │            │ Scrapes pages  │
                             │            │ Returns        │
                             │            │ markdown       │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │                MediaLink
                             │                     │
                             │                     ▼
                             │            IngestDocumentRequest
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Memory Agent   │
                             │            │ (ingest)       │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │               IngestOutcome
                             │                     │
                             │                     ▼
                             │            ObserveTurnRequest
                             │                     │
                             │                     ▼
                             │               ObserveResult
                             │                     │
                             │                     ▼
                             │               RecallRequest
                             │                     │
                             │                     ▼
                             │              RecallResponse
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Transform to   │
                             │            │ Synthesis Req  │
                             │            │ with context   │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Synthesis      │
                             │            │ Agent (LLM)    │
                             │            │                │
                             │            │ Analyzes all   │
                             │            │ sources        │
                             │            └────────┬───────┘
                             │                     │
                             │                     ▼
                             │        ChatCompletionResponse
                             │                     │
                             │                     ▼
                             │            ObserveTurnRequest
                             │                     │
                             │                     ▼
                             │            ┌────────────────┐
                             │            │ Memory Agent   │
                             │            │ (observe)      │
                             │            │ Stores synth   │
                             │            └────────┬───────┘
                             │                     │
                             └─────────────────────┘
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
                                              USER OUTPUT
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

### 2. RecallResponse → Decision Logic
```javascript
// Checks if already answered
$is_answered = $.context.current_id in $.guild_state.answered

// Checks recall quality
$has_good_recall = $count($.payload.items[score > 0.3]) > 0

// Routes to:
// - AnswerRequest (good recall)
// - Query Agent (poor recall)
// - null (already answered)
```

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

**State Updates:**
- User input → Increments `current_id`, appends to `user_queries`
- Good recall → Adds to `answered` array
- Prevents duplicate answers for same query ID

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

- **Loop Prevention**: Guild state tracks `answered` IDs to prevent infinite loops
- **Parallel Processing**: Multiple SERP queries execute in parallel
- **Social Media Filtering**: LinkedIn, Facebook, Instagram, Twitter links excluded from scraping
- **Persistent Memory**: All ingested content stored in Uniko for future recall
- **Adaptive Routing**: Content-based routers make intelligent decisions based on message content and guild state
