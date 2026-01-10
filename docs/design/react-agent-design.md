# ReAct Agent Design: Loop-based vs Message-based

This document compares two architectural approaches for implementing the ReAct (Reasoning and Acting) pattern in AI agent frameworks.

## Background

### What is ReAct?

ReAct is a prompting paradigm that interleaves **reasoning traces** with **actions**, enabling LLMs to solve complex tasks by:

1. **Thinking** - Reasoning about the current state and what to do next
2. **Acting** - Invoking tools to gather information or perform actions
3. **Observing** - Processing tool results to inform the next thought

```
Question: What is the capital of the country where the Eiffel Tower is located?

Thought: I need to find where the Eiffel Tower is located.
Action: Search["Eiffel Tower location"]
Observation: The Eiffel Tower is located in Paris, France.

Thought: Now I need to find the capital of France.
Action: Search["capital of France"]
Observation: Paris is the capital of France.

Thought: I now know the final answer.
Final Answer: Paris
```

Reference: [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

---

## Approach 1: Loop-based ReAct Agent

### Architecture

The ReAct loop is implemented **inside a single agent** as an iterative process:

```
┌─────────────────────────────────────────────────────┐
│                    ReActAgent                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  messages = [system_prompt, user_query]             │
│                                                     │
│  while iterations < max_iterations:                 │
│      │                                              │
│      ▼                                              │
│    response = LLM(messages)                         │
│      │                                              │
│      ▼                                              │
│    tool_calls = extract_tool_calls(response)        │
│      │                                              │
│    if not tool_calls:                               │
│        return response  ◄── Final Answer            │
│      │                                              │
│    for tool_call in tool_calls:                     │
│        result = execute_tool(tool_call)  ◄── Local  │
│        messages.append(ToolMessage(result))         │
│      │                                              │
│    iterations += 1                                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Implementation Pattern

```python
class ReActAgent(Agent):
    def __init__(self, tools: List[Tool], max_iterations: int = 10):
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations

    @processor(ChatCompletionRequest, depends_on=["llm"])
    def react_loop(self, ctx: ProcessContext, llm: LLM):
        messages = list(ctx.payload.messages)

        for _ in range(self.max_iterations):
            # LLM call
            response = llm.completion(ChatCompletionRequest(messages=messages))

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                ctx.send(response)  # Final answer
                return

            # Execute tools locally
            messages.append(response.choices[0].message)
            for tc in tool_calls:
                result = self.tools[tc.name].execute(tc.args)
                messages.append(ToolMessage(content=result, tool_call_id=tc.id))

        ctx.send(MaxIterationsReached())
```

### Characteristics

| Aspect | Description |
|--------|-------------|
| Execution model | Synchronous loop within single agent |
| Tool execution | Direct function calls |
| State management | Local variable (`messages` list) |
| Visibility | Internal to agent |
| Latency | Minimal (no message passing overhead) |
| Complexity | Self-contained, easy to understand |

---

## Approach 2: Message-based ReAct (Rustic AI)

### Architecture

The ReAct pattern emerges from **message routing between agents**:

```
┌─────────────┐                           ┌─────────────┐
│             │  ToolCallParams message   │             │
│  LLMAgent   │ ────────────────────────► │  ToolAgent  │
│             │                           │             │
│             │ ◄──────────────────────── │             │
│             │  ToolResult message       │             │
└─────────────┘  (routed with history)    └─────────────┘
       │                                        │
       │         ┌─────────────────┐            │
       │         │  RoutingSlip    │            │
       └────────►│  + History      │◄───────────┘
                 │  (session_state)│
                 └─────────────────┘
```

### Message Flow

```
1. User sends ChatCompletionRequest to LLMAgent

2. LLMAgent:
   - Processes request through plugins
   - Calls LLM
   - Extracts tool calls
   - Publishes ToolCallParams message

3. RoutingSlip routes ToolCallParams to appropriate ToolAgent

4. ToolAgent:
   - Executes the tool
   - Publishes ToolResult message

5. RoutingSlip routes ToolResult back to LLMAgent (with history)

6. LLMAgent:
   - Receives ToolResult
   - Reconstructs conversation with observation
   - Calls LLM again
   - If more tool calls → goto step 3
   - If final answer → publish response

7. Loop terminates naturally when LLMAgent produces no tool calls
```

### Implementation Pattern

```python
# No special ReActAgent needed - just configuration

# LLMAgent with ToolsManagerPlugin (already exists)
llm_agent_spec = (
    AgentBuilder(LLMAgent)
    .set_properties(LLMAgentConfig(
        model="gpt-4",
        llm_request_wrappers=[
            ToolsManagerPlugin(toolset=my_tools)
        ]
    ))
    .build_spec()
)

# ToolAgent that executes tools
tool_agent_spec = (
    AgentBuilder(ToolExecutorAgent)
    .set_properties(ToolExecutorConfig(tools=my_tools))
    .build_spec()
)

# Guild with routing that creates the ReAct loop
guild_spec = (
    GuildBuilder()
    .add_agent(llm_agent_spec)
    .add_agent(tool_agent_spec)
    .set_routing_slip(RoutingSlip(
        rules=[
            # Tool calls go to tool agent
            RoutingRule(
                match=MessageMatch(format="ToolCallParams"),
                destination="tool_agent"
            ),
            # Tool results go back to LLM agent with history
            RoutingRule(
                match=MessageMatch(format="ToolResult"),
                destination="llm_agent",
                include_history=True
            ),
        ]
    ))
    .build()
)
```

### Characteristics

| Aspect | Description |
|--------|-------------|
| Execution model | Asynchronous message passing between agents |
| Tool execution | Delegated to specialized ToolAgents |
| State management | Carried via session_state/routing_slip |
| Visibility | Every step is an observable message |
| Latency | Higher (serialization, routing, message passing) |
| Complexity | Distributed, requires routing configuration |

---

## Detailed Comparison

### Performance

| Metric | Loop-based | Message-based |
|--------|------------|---------------|
| Tool call latency | ~microseconds | ~milliseconds |
| 5-tool ReAct chain | ~5 LLM calls | ~5 LLM calls + 10 message hops |
| Memory | Single agent memory | Distributed across agents |
| Serialization | None | Per message hop |

**Verdict**: Loop-based wins for latency-sensitive applications.

### Flexibility

| Capability | Loop-based | Message-based |
|------------|------------|---------------|
| Simple function tools | Easy | Requires ToolAgent wrapper |
| Stateful tools | Possible but complex | Natural (agents have state) |
| Long-running tools | Blocks the loop | Async, no blocking |
| Human-in-the-loop | Difficult | Natural (human is just an agent) |
| Tool is another LLM | Nested complexity | Same pattern |
| Cross-service tools | Requires HTTP calls | G2G messaging |

**Verdict**: Message-based wins for complex, heterogeneous tool ecosystems.

### Observability

| Aspect | Loop-based | Message-based |
|--------|------------|---------------|
| Logging | Must add explicitly | Every message logged |
| Debugging | Breakpoints in loop | Message trace analysis |
| Replay | Must implement | Built-in (replay messages) |
| Auditing | Custom implementation | Message history |
| Monitoring | Agent-level metrics | Per-hop metrics |

**Verdict**: Message-based wins for production observability requirements.

### Development Experience

| Aspect | Loop-based | Message-based |
|--------|------------|---------------|
| Learning curve | Low (just a while loop) | Higher (routing, messages) |
| Testing | Unit test the agent | Integration test message flows |
| Local development | Simple | Requires message infrastructure |
| Error handling | try/catch in one place | Distributed error handling |
| Debugging | Step through code | Trace through messages |

**Verdict**: Loop-based wins for simplicity and developer experience.

### Scalability

| Aspect | Loop-based | Message-based |
|--------|------------|---------------|
| Horizontal scaling | Scale the agent | Scale agents independently |
| Tool isolation | Same process | Separate processes/containers |
| Resource management | Shared | Independent per agent |
| Failure isolation | Agent fails = all fails | Tool agent fails = just that tool |

**Verdict**: Message-based wins for large-scale production deployments.

---

## When to Use Each Approach

### Use Loop-based When:

- Building prototypes or demos
- Tools are simple, pure functions
- Latency is critical (interactive chat)
- Single-process deployment
- Team is new to agent frameworks
- Tools are tightly coupled to the reasoning

### Use Message-based When:

- Building production systems
- Tools are complex (stateful, long-running, external)
- Observability and auditing are required
- Tools need independent scaling
- Human approval steps are needed
- Tools span multiple services or organizations
- Want to reuse existing agent infrastructure

---

## Hybrid Approach

A practical architecture might combine both:

```
┌─────────────────────────────────────────────────────────────┐
│                      ReActAgent                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  for each iteration:                                        │
│      response = LLM(messages)                               │
│      tool_calls = extract(response)                         │
│                                                             │
│      for tool_call in tool_calls:                           │
│          if tool_call.is_simple:                            │
│              result = local_execute(tool_call)  ◄── Fast    │
│          else:                                              │
│              ctx.send(ToolCallRequest(tool_call))           │
│              result = await ctx.receive(ToolResult) ◄── Msg │
│                                                             │
│          messages.append(result)                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

This allows:
- Simple tools (calculator, string manipulation) to execute inline
- Complex tools (web search, database, human approval) to use messaging

---

## Rustic AI Recommendation

Given Rustic AI's philosophy of **"agents as tools, tools as agents"**, the message-based approach is the natural fit:

1. **Consistency**: Everything is an agent, everything communicates via messages
2. **Composability**: Tools are first-class agents that can be composed
3. **Scalability**: Ready for production from day one
4. **Flexibility**: Same LLMAgent handles simple queries and complex ReAct chains

The "ReAct pattern" in Rustic AI is not a special agent type - it's an **emergent behavior** from routing configuration:

```
ReAct = LLMAgent + ToolAgents + RoutingSlip
```

### Required Infrastructure

To fully support the message-based ReAct pattern, ensure:

1. **ToolsManagerPlugin**: Extracts tool calls and publishes them as messages
2. **ToolExecutorAgent**: Base agent for executing tools and publishing results
3. **History preservation**: Routing carries conversation history via session_state
4. **Termination detection**: Natural (no tool calls = no routing = done)

---

## Conclusion

| Criteria | Loop-based | Message-based |
|----------|------------|---------------|
| Simplicity | Excellent | Good |
| Performance | Excellent | Good |
| Flexibility | Good | Excellent |
| Scalability | Good | Excellent |
| Observability | Good | Excellent |
| Rustic AI alignment | Partial | Full |

**For Rustic AI**: Embrace the message-based approach as the primary pattern, leveraging the existing agent and messaging infrastructure. The ReAct "loop" becomes a natural consequence of how agents communicate, not special code to maintain.

**For simple use cases**: Consider a lightweight inline executor for trivial tools to avoid message passing overhead, while still supporting message-based tools for complex operations.
