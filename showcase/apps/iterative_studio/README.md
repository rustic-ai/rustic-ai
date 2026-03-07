# Iterative Studio

A multi-mode AI platform with 5 operational modes for code refinement, strategic reasoning, research, and content generation. Based on the [Iterative Contextual Refinements](https://github.com/ryoiki-tokuiten/Iterative-Contextual-Refinements) system.

## Overview

Iterative Studio is a Rustic AI guild that automatically routes user requests to the most appropriate processing pipeline based on intent classification. It supports:

- **Refine** - Code refinement with parallel feature suggestions and bug fixing
- **Deepthink** - Multi-agent strategic reasoning with critique loops
- **Adaptive** - Self-guided strategic reasoning with tool-based exploration
- **Agentic** - Tool-based operations with file manipulation and research
- **Contextual** - Iterative content generation with memory compression

## Architecture

```
User Request
     │
     ▼
┌─────────────────┐
│ Mode Controller │  ← Classifies intent into one of 5 modes
└────────┬────────┘
         │
    ┌────┴────┬────────┬──────────┬───────────┐
    ▼         ▼        ▼          ▼           ▼
 Refine  Deepthink  Adaptive  Agentic  Contextual
   │         │        │          │           │
   ▼         ▼        ▼          ▼           ▼
User Broadcast (final response)
```

The guild uses **routing slips** with JSONata transformers to orchestrate message flow between agents. Each mode has its own set of specialized agents that process requests through defined workflows.

## Modes

### 1. Refine Mode

Code refinement with parallel feature suggestions and bug fixing.

**Trigger keywords:** Code review, bug fixes, feature suggestions

**Test Questions:**
- "Review this code and suggest improvements"
- "Fix the bugs in this Python function"
- "What features should I add to this API?"

**Flow:**

```
User Input → Mode Controller (outputs "refine")
    │
    ├─→ Feature Suggester (Novelty) → REFINE_AGGREGATE
    └─→ Feature Suggester (Quality) → REFINE_AGGREGATE
              │
    Refine Aggregator (waits for 2 responses, combines them)
              │
    Bug Fixer (reviews and fixes issues)
              │
    User Broadcast (final response)
```

**Agents:**
| Agent | Description |
|-------|-------------|
| Feature Suggester (Novelty) | Suggests 2-3 creative, innovative features focusing on user experience and differentiation |
| Feature Suggester (Quality) | Suggests 2-3 quality improvements focusing on reliability, performance, and security |
| Refine Aggregator | Aggregates responses from both feature suggesters (count-based aggregation) |
| Bug Fixer | Reviews aggregated suggestions and identifies/fixes bugs in provided code |

---

### 2. Deepthink Mode

Multi-agent strategic reasoning with critique loops for complex problems.

**Trigger keywords:** Complex problems, multiple perspectives, strategic analysis

**Test Questions:**
- "Help me solve this complex technical problem"
- "Design an architecture for a distributed system"
- "What's the best approach for scaling this microservice?"

**Flow:**

```
User Input → Mode Controller (outputs "deepthink")
    │
Strategy Generator → generates 3-5 strategies
    │
Solution Agent → develops detailed solutions
    │
Critique Agent → evaluates (APPROVE/NEEDS_REVISION/REJECT)
    │ (if NEEDS_REVISION, max 2 iterations)
Refinement Agent → applies improvements → back to Critique
    │ (when approved or max iterations)
Red Team Agent → adversarial analysis (vulnerabilities, attacks)
    │
Final Judge → selects best solution
    │
User Broadcast
```

**Agents:**
| Agent | Description |
|-------|-------------|
| Strategy Generator | Generates 3-5 diverse high-level strategies with assumptions, strengths, and weaknesses |
| Solution Agent | Develops detailed solutions based on strategies with implementation details |
| Critique Agent | Evaluates solutions and outputs APPROVE/NEEDS_REVISION/REJECT verdict |
| Refinement Agent | Applies improvements based on critique feedback |
| Red Team Agent | Performs adversarial analysis identifying vulnerabilities and attack vectors |
| Final Judge | Reviews all analysis and selects the best solution with justification |

---

### 3. Adaptive Mode

Self-guided strategic reasoning with tool-based exploration.

**Trigger keywords:** Technical problems needing flexible exploration

**Test Questions:**
- "Explore different approaches to implement caching"
- "Analyze the trade-offs between Redis and Memcached"
- "Help me debug this performance issue step by step"

**Flow:**

```
User Input → Mode Controller (outputs "adaptive")
    │
Adaptive Deepthink Agent (ReAct with tools)
    - Tools: GenerateStrategies, GenerateHypotheses, CritiqueSolution,
             RedTeam, SelectBestSolution, RecordReasoning
    - Self-guided iteration up to 20 turns
    │
User Broadcast
```

**Tools (DeepthinkToolset):**
| Tool | Description |
|------|-------------|
| GenerateStrategies | Generate 1-5 high-level strategies for approaching a problem |
| GenerateHypotheses | Generate testable hypotheses for a given strategy |
| CritiqueSolution | Evaluate a solution against criteria (correctness, completeness, efficiency, etc.) |
| RedTeam | Perform adversarial analysis identifying failure modes and vulnerabilities |
| SelectBestSolution | Compare multiple solutions and select the best one with justification |
| RecordReasoning | Record reasoning steps for context tracking and self-reflection |

---

### 4. Agentic Mode

Tool-based operations with file manipulation and academic research.

**Trigger keywords:** File operations, web search, code execution, research papers

**Test Questions:**
- "Search for papers on transformer architectures"
- "Read the config.yaml file and summarize it"
- "Create a new Python file with a data processing pipeline"
- "Look up the latest research on attention mechanisms"

**Flow:**

```
User Input → Mode Controller (outputs "agentic")
    │
Agentic Agent (ReAct with tools)
    - Tools: ReadFile, WriteFile, ApplyDiff, ListDirectory, SearchArxiv
    - Up to 15 iterations
    - Working dir: /tmp/iterative_studio
    │
User Broadcast
```

**Tools (AgenticToolset + ArxivToolset):**
| Tool | Description |
|------|-------------|
| ReadFile | Read file contents with optional line range (start_line, end_line) |
| WriteFile | Write content to a file, optionally creating parent directories |
| ApplyDiff | Apply exact string replacement to modify files |
| ListDirectory | List files in a directory with optional recursion and glob patterns |
| SearchArxiv | Search academic papers on ArXiv by topic, author, or keywords |

---

### 5. Contextual Mode

Iterative content generation with review loops and memory compression.

**Trigger keywords:** Content generation, writing, documents

**Test Questions:**
- "Write a technical blog post about microservices"
- "Draft a project proposal for a new feature"
- "Create documentation for this API"

**Flow:**

```
User Input → Mode Controller (outputs "contextual")
    │
Main Generator → generates content
    │
Iterative Agent → reviews (APPROVE or NEEDS_REVISION)
    │ (if NEEDS_REVISION, loops back, max 4 iterations)
Main Generator → revises → Iterative Agent
    │ (when APPROVE or max iterations)
Memory Agent → compresses conversation history
    │
User Broadcast
```

**Agents:**
| Agent | Description |
|-------|-------------|
| Main Generator | Generates high-quality, well-structured content based on user requests |
| Iterative Agent | Reviews content and decides APPROVE or NEEDS_REVISION with specific feedback |
| Memory Agent | Compresses conversation history to preserve essential context |

---

## Summary Table

| Mode | Question Type | Key Agents | Max Iterations |
|------|---------------|------------|----------------|
| Refine | Code review, bugs, features | Novelty + Quality → Aggregator → Bug Fixer | 1 pass (parallel) |
| Deepthink | Complex strategic problems | Strategy → Solution → Critique → Refinement → Red Team → Judge | 2 critique loops |
| Adaptive | Flexible technical exploration | ReAct agent with reasoning tools | 20 turns |
| Agentic | File ops, research, execution | ReAct agent with file/arxiv tools | 15 turns |
| Contextual | Writing, content generation | Main → Iterative → Memory | 4 revision loops |

## Configuration

### Dependencies

The guild requires the following dependencies:

```json
{
  "llm": {
    "class_name": "rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
    "properties": {
      "model": "vertex_ai/gemini-2.5-pro"
    }
  },
  "filesystem": {
    "class_name": "rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
    "properties": {
      "path_base": "/tmp/iterative_studio",
      "protocol": "file"
    },
    "scope": "guild"
  },
  "kb_backend": {
    "class_name": "rustic_ai.core.knowledgebase.kbindex_backend_memory.InMemoryKBIndexBackendResolver",
    "scope": "guild"
  }
}
```

### Environment Variables

- `GOOGLE_APPLICATION_CREDENTIALS` - For Vertex AI authentication (Gemini models)

### Model

All agents use `vertex_ai/gemini-2.5-pro` by default via LiteLLM.

## Topics

The guild uses the following internal topics for message routing:

| Topic | Purpose |
|-------|---------|
| `MODE_CONTROL` | Mode Controller receives user requests |
| `REFINE_NOVELTY` | Feature Suggester (Novelty) |
| `REFINE_QUALITY` | Feature Suggester (Quality) |
| `REFINE_AGGREGATE` | Refine Aggregator collects suggestions |
| `REFINE_BUGFIX` | Bug Fixer reviews suggestions |
| `DT_STRATEGY` | Strategy Generator (Deepthink) |
| `DT_SOLUTION` | Solution Agent (Deepthink) |
| `DT_CRITIQUE` | Critique Agent (Deepthink) |
| `DT_REFINEMENT` | Refinement Agent (Deepthink) |
| `DT_REDTEAM` | Red Team Agent (Deepthink) |
| `DT_JUDGE` | Final Judge (Deepthink) |
| `ADAPTIVE_DT` | Adaptive Deepthink Agent |
| `AGENTIC` | Agentic Agent |
| `CTX_MAIN` | Main Generator (Contextual) |
| `CTX_ITERATE` | Iterative Agent (Contextual) |
| `CTX_MEMORY` | Memory Agent (Contextual) |
| `user_message_broadcast` | Final responses to user |

## Usage

### Running the Guild

```python
from rustic_ai.core.guild import Guild
import json

# Load guild spec
with open("showcase/apps/iterative_studio/guild.json") as f:
    guild_config = json.load(f)

# Create and start the guild
guild = Guild.from_spec(guild_config["spec"])
guild.start()

# Send a message
guild.send_user_message({
    "messages": [
        {"role": "user", "content": "Review this code and suggest improvements"}
    ]
})
```

### Starter Prompts

- "Review this code and suggest improvements"
- "Help me solve this complex technical problem"
- "Search for papers on transformer architectures"
- "Write a technical blog post about microservices"

## Implementation Details

### Mode Classification

The Mode Controller uses a simple classification prompt to route requests:

```
Classification rules:
- refine: Code review, bug fixes, feature suggestions
- deepthink: Complex problems requiring multiple perspectives and structured critique
- adaptive: Technical problems needing flexible, iterative exploration
- agentic: Tasks requiring file operations, web search, or code execution
- contextual: Content generation, writing tasks, iterative document development
```

### Routing

Routes use JSONata transformers for content-based routing. For example, the Critique Agent uses this logic:

```jsonata
$needs_revision and $iteration < 2
  ? route to DT_REFINEMENT (with incremented iteration)
  : route to DT_REDTEAM
```

### Aggregation

The Refine mode uses count-based aggregation to wait for exactly 2 responses (from Novelty and Quality suggesters) before proceeding to the Bug Fixer.

## Related Files

- `guild.json` - Guild specification
- `toolsets/deepthink_toolset.py` - Strategic reasoning tools
- `toolsets/agentic_toolset.py` - File operation tools
- `toolsets/arxiv_toolset.py` - ArXiv search tool
