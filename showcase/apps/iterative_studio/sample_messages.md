  1. Refine Mode (Code refinement)                                                                                                                                                          
                                                                                                                                                                                            
  Trigger keywords: Code review, bug fixes, feature suggestions                                                                                                                             
                  
  Test Questions:

  "Review this code and suggest improvements"
  "Fix the bugs in this Python function"
  "What features should I add to this API?"

  Flow:

  User Input → Mode Controller (outputs "refine")
      ↓
      ├─→ Feature Suggester (Novelty) → REFINE_AGGREGATE
      └─→ Feature Suggester (Quality) → REFINE_AGGREGATE
                ↓
      Refine Aggregator (waits for 2 responses, combines them)
                ↓
      Bug Fixer (reviews and fixes issues)
                ↓
      User Broadcast (final response)

  ---
  2. Deepthink Mode (Multi-agent strategic reasoning)

  Trigger keywords: Complex problems, multiple perspectives, strategic analysis

  Test Questions:

  "Help me solve this complex technical problem"
  "Design an architecture for a distributed system"
  "What's the best approach for scaling this microservice?"

  Flow:

  User Input → Mode Controller (outputs "deepthink")
      ↓
  Strategy Generator → generates 3-5 strategies
      ↓
  Solution Agent → develops detailed solutions
      ↓
  Critique Agent → evaluates (APPROVE/NEEDS_REVISION/REJECT)
      ↓ (if NEEDS_REVISION, max 2 iterations)
  Refinement Agent → applies improvements → back to Critique
      ↓ (when approved or max iterations)
  Red Team Agent → adversarial analysis (vulnerabilities, attacks)
      ↓
  Final Judge → selects best solution
      ↓
  User Broadcast

  ---
  3. Adaptive Mode (Self-guided strategic reasoning with tools)

  Trigger keywords: Technical problems needing flexible exploration

  Test Questions:

  "Explore different approaches to implement caching"
  "Analyze the trade-offs between Redis and Memcached"
  "Help me debug this performance issue step by step"

  Flow:

  User Input → Mode Controller (outputs "adaptive")
      ↓
  Adaptive Deepthink Agent (ReAct with tools)
      - Tools: GenerateStrategies, GenerateHypotheses, CritiqueSolution,
               RedTeam, SelectBestSolution, RecordReasoning
      - Self-guided iteration up to 20 turns
      ↓
  User Broadcast

  ---
  4. Agentic Mode (Tool-based with file ops and research)

  Trigger keywords: File operations, web search, code execution, research papers

  Test Questions:

  "Search for papers on transformer architectures"
  "Read the config.yaml file and summarize it"
  "Create a new Python file with a data processing pipeline"
  "Look up the latest research on attention mechanisms"

  Flow:

  User Input → Mode Controller (outputs "agentic")
      ↓
  Agentic Agent (ReAct with tools)
      - Tools: ReadFile, WriteFile, ApplyDiff, ListDirectory, SearchArxiv
      - Up to 15 iterations
      - Working dir: /tmp/iterative_studio
      ↓
  User Broadcast

  ---
  5. Contextual Mode (Iterative content generation)

  Trigger keywords: Content generation, writing, documents

  Test Questions:

  "Write a technical blog post about microservices"
  "Draft a project proposal for a new feature"
  "Create documentation for this API"

  Flow:

  User Input → Mode Controller (outputs "contextual")
      ↓
  Main Generator → generates content
      ↓
  Iterative Agent → reviews (APPROVE or NEEDS_REVISION)
      ↓ (if NEEDS_REVISION, loops back, max 4 iterations)
  Main Generator → revises → Iterative Agent
      ↓ (when APPROVE or max iterations)
  Memory Agent → compresses conversation history
      ↓
  User Broadcast

  ---
  Summary Table

  ┌────────────┬────────────────────────────────┬────────────────────────────────────────────────────────────────┬───────────────────┐
  │    Mode    │         Question Type          │                           Key Agents                           │  Max Iterations   │
  ├────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────┤
  │ Refine     │ Code review, bugs, features    │ Novelty + Quality → Aggregator → Bug Fixer                     │ 1 pass (parallel) │
  ├────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────┤
  │ Deepthink  │ Complex strategic problems     │ Strategy → Solution → Critique → Refinement → Red Team → Judge │ 2 critique loops  │
  ├────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────┤
  │ Adaptive   │ Flexible technical exploration │ ReAct agent with reasoning tools                               │ 20 turns          │
  ├────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────┤
  │ Agentic    │ File ops, research, execution  │ ReAct agent with file/arxiv tools                              │ 15 turns          │
  ├────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────┤
  │ Contextual │ Writing, content generation    │ Main → Iterative → Memory                                      │ 4 revision loops  │
  └────────────┴────────────────────────────────┴────────────────────────────────────────────────────────────────┴───────────────────┘

