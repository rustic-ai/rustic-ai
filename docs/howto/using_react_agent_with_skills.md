# Using ReActAgent with Skills

This guide demonstrates how to create a powerful AI agent by combining the **ReActAgent** with the **Skills** module.

## Overview

The ReActAgent provides reasoning and tool-use capabilities, while Skills provide pre-built, reusable tools that agents can invoke. Together, they enable rapid development of capable AI agents.

## Quick Start

### 1. Install a Skill

```python
from rustic_ai.skills import SkillMarketplace

# Initialize marketplace
marketplace = SkillMarketplace()

# Install a skill (e.g., PDF processing)
marketplace.install("pdf")
```

### 2. Create ReActAgent with Skill

```python
from pathlib import Path
from rustic_ai.skills import SkillToolset
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec

# Load skill as toolset
toolset = SkillToolset.from_path(Path("/tmp/rustic-skills/pdf"))

# Build agent spec
agent_spec = (
    AgentBuilder(ReActAgent)
    .set_id("pdf_assistant")
    .set_name("PDF Assistant")
    .set_description("Helps with PDF document processing")
    .set_properties(
        ReActAgentConfig(
            model="gpt-4o-mini",
            max_iterations=10,
            toolset=toolset,
            system_prompt=toolset.get_system_prompt_addition(),
        )
    )
    .build_spec()
)

# Build guild
guild_spec = (
    GuildBuilder("pdf_guild", "PDF Processing Guild", "PDF document processing")
    .add_agent_spec(agent_spec)
    .set_dependency_map({
        "llm": DependencySpec(
            class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
            properties={"model": "gpt-4o-mini"}
        )
    })
    .build()
)
```

### 3. Use the Agent

```python
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UserMessage,
)
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

# For testing
agent, results = wrap_agent_for_testing(
    agent_spec,
    dependency_map=guild_spec.dependency_map
)

# Create and send a request
generator = GemstoneGenerator(1)
request = ChatCompletionRequest(
    messages=[
        UserMessage(content="Extract the text from report.pdf")
    ]
)
message = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(name="test", id="test-1"),
    topics=GuildTopics.DEFAULT_TOPICS,
    payload=request.model_dump(),
    format=get_qualified_class_name(ChatCompletionRequest),
)
agent._on_message(message)

# Get response
assert len(results) == 1
response = ChatCompletionResponse.model_validate(results[0].payload)
print(response.choices[0].message.content)
```

## Using Multiple Skills

### Combine Skills for Rich Functionality

```python
from rustic_ai.skills import SkillToolset

# Load multiple skills
toolset = SkillToolset.from_paths([
    Path("/tmp/rustic-skills/pdf"),
    Path("/tmp/rustic-skills/csv"),
    Path("/tmp/rustic-skills/web-search"),
])

# Create agent with all skills
config = ReActAgentConfig(
    model="gpt-4",
    max_iterations=15,
    toolset=toolset,
    system_prompt=toolset.get_combined_system_prompt(),
)

agent_spec = (
    AgentBuilder(ReActAgent)
    .set_id("multi_skill_agent")
    .set_name("Multi-Skill Agent")
    .set_description("Agent with PDF, CSV, and search capabilities")
    .set_properties(config)
    .build_spec()
)
```

### Example Queries

With multiple skills, your agent can handle complex workflows:

```python
# PDF + CSV workflow
"Extract the data table from report.pdf and save it as data.csv"

# Search + PDF workflow
"Search for 'climate change reports 2023', download the top result, and summarize it"

# CSV + Search workflow
"Analyze sales.csv and search for best practices based on the trends"
```

## YAML Configuration

### Agent Spec with Skills

```yaml
id: pdf_assistant
name: PDF Assistant
description: Processes PDF documents
class_name: rustic_ai.llm_agent.react.ReActAgent
properties:
  model: gpt-4o-mini
  max_iterations: 10
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths:
      - /tmp/rustic-skills/pdf
  system_prompt: |
    You are a PDF processing assistant.
    Use the PDF tools to extract and analyze document content.
```

### Multiple Skills in YAML

```yaml
properties:
  model: gpt-4
  max_iterations: 15
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths:
      - /tmp/rustic-skills/pdf
      - /tmp/rustic-skills/csv
      - /tmp/rustic-skills/web-search
```

### Marketplace Integration

Auto-install skills on agent initialization:

```yaml
properties:
  model: gpt-4
  toolset:
    kind: rustic_ai.skills.toolset.MarketplaceSkillToolset
    source: anthropic
    skill_names:
      - pdf
      - csv
```

## Advanced Patterns

### Pattern 1: Custom System Prompt with Skills

```python
# Get skill instructions
skill_instructions = toolset.get_system_prompt_addition()

# Combine with custom prompt
custom_prompt = f"""You are a research assistant specializing in document analysis.

{skill_instructions}

When analyzing documents:
1. Always extract full context before summarizing
2. Cross-reference claims with web search when uncertain
3. Provide citations for external information
4. Format results in markdown

Be thorough and accurate in your analysis."""

config = ReActAgentConfig(
    model="gpt-4",
    toolset=toolset,
    system_prompt=custom_prompt,
)
```

### Pattern 2: Skills with Tool Wrappers

Add caching, logging, or validation:

```python
from pydantic import BaseModel
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallWrapper,
    ToolCallResult,
)

class SkillLogger(ToolCallWrapper):
    """Log all skill invocations."""
    
    def preprocess(self, agent, ctx, tool_name: str, tool_input: BaseModel):
        logger.info(f"Executing skill tool: {tool_name}")
        logger.debug(f"Arguments: {tool_input.model_dump_json()}")
        return tool_input  # Pass through unchanged
    
    def postprocess(
        self, agent, ctx, tool_name: str, tool_input: BaseModel, tool_output: str
    ) -> ToolCallResult:
        logger.info(f"Skill tool completed: {tool_name}")
        logger.debug(f"Result length: {len(tool_output)} chars")
        return ToolCallResult(output=tool_output)

config = ReActAgentConfig(
    model="gpt-4",
    toolset=toolset,
    tool_wrappers=[SkillLogger()],
)
```

### Pattern 3: Dynamic Skill Loading

Load skills based on user needs:

```python
def create_agent_for_task(task_type: str) -> AgentSpec:
    """Create agent with skills appropriate for task type."""
    
    skill_map = {
        "documents": [
            Path("/tmp/rustic-skills/pdf"),
            Path("/tmp/rustic-skills/docx"),
        ],
        "data": [
            Path("/tmp/rustic-skills/csv"),
            Path("/tmp/rustic-skills/json"),
            Path("/tmp/rustic-skills/sql"),
        ],
        "web": [
            Path("/tmp/rustic-skills/web-search"),
            Path("/tmp/rustic-skills/web-scrape"),
        ],
    }
    
    skills = skill_map.get(task_type, [])
    toolset = SkillToolset.from_paths(skills)
    
    return (
        AgentBuilder(ReActAgent)
        .set_id(f"{task_type}_agent")
        .set_name(f"{task_type.title()} Agent")
        .set_properties(
            ReActAgentConfig(
                model="gpt-4",
                toolset=toolset,
                system_prompt=toolset.get_combined_system_prompt(),
            )
        )
        .build_spec()
    )

# Usage
doc_agent_spec = create_agent_for_task("documents")
data_agent_spec = create_agent_for_task("data")
```

## Complete Example

### Research Assistant with PDF and Search

```python
from pathlib import Path
from rustic_ai.skills import SkillMarketplace, SkillToolset
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec

# Setup: Install skills
marketplace = SkillMarketplace()
marketplace.install("pdf")
marketplace.install("web-search")

# Create toolset
toolset = SkillToolset.from_paths([
    Path("/tmp/rustic-skills/pdf"),
    Path("/tmp/rustic-skills/web-search"),
])

# Define agent
agent_spec = (
    AgentBuilder(ReActAgent)
    .set_id("research_assistant")
    .set_name("Research Assistant")
    .set_description("Analyzes documents and performs web research")
    .set_properties(
        ReActAgentConfig(
            model="gpt-4",
            max_iterations=20,
            toolset=toolset,
            system_prompt=f"""You are an academic research assistant.

{toolset.get_combined_system_prompt()}

Research Process:
1. For document analysis, extract full content first
2. For claims requiring verification, use web search
3. Cite all sources in your analysis
4. Provide comprehensive, well-structured responses

Be thorough and academically rigorous.""",
        )
    )
    .build_spec()
)

# Create guild
guild_spec = (
    GuildBuilder("research_guild", "Research Guild", "Academic research and analysis")
    .add_agent_spec(agent_spec)
    .set_dependency_map({
        "llm": DependencySpec(
            class_name="rustic_ai.litellm.agent_ext.llm.LiteLLMResolver",
            properties={"model": "gpt-4"}
        )
    })
    .build()
)

# Test the agent
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UserMessage,
)
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

agent, results = wrap_agent_for_testing(
    agent_spec,
    dependency_map=guild_spec.dependency_map
)

# Example research query
generator = GemstoneGenerator(1)
request = ChatCompletionRequest(
    messages=[
        UserMessage(content="""
Analyze the research paper in paper.pdf and:
1. Extract the main hypothesis
2. Summarize the methodology
3. Search for recent related work published after this paper
4. Compare the findings with current research
        """)
    ]
)
message = Message(
    id_obj=generator.get_id(),
    sender=AgentTag(name="test", id="test-1"),
    topics=GuildTopics.DEFAULT_TOPICS,
    payload=request.model_dump(),
    format=get_qualified_class_name(ChatCompletionRequest),
)

agent._on_message(message)
response = ChatCompletionResponse.model_validate(results[0].payload)

print("Research Analysis:")
print(response.choices[0].message.content)

# View the reasoning trace
trace = response.choices[0].provider_specific_fields["react_trace"]
print(f"\nCompleted in {len(trace)} reasoning steps")
```

## Testing

### Unit Test Skills Integration

```python
import pytest
from pathlib import Path
from rustic_ai.skills import SkillToolset, parse_skill
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    FinishReason,
    UserMessage,
)
from rustic_ai.testing.helpers import wrap_agent_for_testing

def test_skill_loading():
    """Test that skills load correctly."""
    skill = parse_skill(Path("./test-skill"))
    assert skill.name == "test-skill"
    assert len(skill.scripts) > 0

def test_toolset_creation():
    """Test SkillToolset creation."""
    toolset = SkillToolset.from_path(Path("./test-skill"))
    assert len(toolset.get_toolspecs()) > 0

def test_agent_with_skill(generator, build_message_from_payload, dependency_map):
    """Test ReActAgent with skill toolset.
    
    Note: generator and build_message_from_payload are pytest fixtures
    defined in conftest.py for test convenience.
    """
    toolset = SkillToolset.from_path(Path("./test-skill"))
    
    agent_spec = (
        AgentBuilder(ReActAgent)
        .set_id("test_agent")
        .set_name("Test Agent")
        .set_description("Test skill agent")
        .set_properties(
            ReActAgentConfig(
                model="gpt-4o-mini",
                toolset=toolset,
            )
        )
        .build_spec()
    )
    
    agent, results = wrap_agent_for_testing(agent_spec, dependency_map)
    
    request = ChatCompletionRequest(
        messages=[UserMessage(content="Test the skill")]
    )
    
    # Using pytest fixtures for message construction
    agent._on_message(build_message_from_payload(generator, request))
    
    assert len(results) == 1
    response = ChatCompletionResponse.model_validate(results[0].payload)
    assert response.choices[0].finish_reason == FinishReason.stop
```

## Best Practices

### 1. Match Skills to Use Cases

- **Document processing**: PDF, DOCX, TXT skills
- **Data analysis**: CSV, JSON, SQL skills
- **Research**: Web search, Wikipedia, academic database skills
- **Automation**: Email, calendar, file management skills

### 2. Optimize Max Iterations

```python
# Simple single-skill tasks
config = ReActAgentConfig(model="gpt-4", toolset=toolset, max_iterations=5)

# Multi-skill workflows
config = ReActAgentConfig(model="gpt-4", toolset=toolset, max_iterations=15)

# Complex research tasks
config = ReActAgentConfig(model="gpt-4", toolset=toolset, max_iterations=25)
```

### 3. Provide Clear Instructions

```python
system_prompt = f"""You are a data analyst assistant.

{toolset.get_combined_system_prompt()}

Data Analysis Workflow:
1. Load data using CSV tools
2. Perform requested analysis
3. Generate visualizations if needed
4. Provide insights and recommendations

Always verify data quality before analysis."""
```

### 4. Handle Skill Errors Gracefully

```python
from rustic_ai.llm_agent.plugins.tool_call_wrapper import ToolCallWrapper, ToolCallResult

class SkillErrorHandler(ToolCallWrapper):
    def preprocess(self, agent, ctx, tool_name: str, tool_input):
        return tool_input  # Pass through unchanged
    
    def postprocess(self, agent, ctx, tool_name: str, tool_input, tool_output: str):
        try:
            # Validate result
            if "error" in tool_output.lower():
                return ToolCallResult(
                    output=f"Tool error: {tool_output}. Please try a different approach."
                )
            return ToolCallResult(output=tool_output)
        except Exception as e:
            return ToolCallResult(
                output=f"Unexpected error: {str(e)}"
            )
```

## Troubleshooting

### Issue: Skill Not Found

**Solution**: Verify skill installation
```python
marketplace = SkillMarketplace()
installed = marketplace.list_installed()
print([s.name for s in installed])
```

### Issue: Agent Not Using Skills

**Check:**
1. Skill instructions in system prompt
2. Tool names are clear and descriptive
3. Max iterations is sufficient
4. Model supports tool calling

### Issue: Skill Execution Timeout

**Solution**: Increase timeout
```python
from rustic_ai.skills import ExecutionConfig

toolset = SkillToolset.from_path(
    path=Path("./skill"),
    execution_config=ExecutionConfig(timeout_seconds=120)
)
```

## Next Steps

- [ReActAgent Documentation](../agents/react_agent.md) - Complete ReActAgent reference
- [Skills Module](../skills/index.md) - Detailed Skills documentation
- [Creating Custom Skills](../skills/index.md#custom-skill-development) - Build your own skills
- [Testing Agents](testing_agents.md) - Agent testing strategies

## Related Examples

- [Data Analysis Agent](../showcase/index.md) - CSV + visualization skills
- [Research Agent](../showcase/index.md) - PDF + search + summarization
- [Automation Agent](../showcase/index.md) - File + email + calendar skills
