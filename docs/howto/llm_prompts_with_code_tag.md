# Using `!code` Tag for LLM Agent Prompts

The modular guild support in Rustic AI includes a powerful `!code` tag that allows you to load file contents directly into your YAML configurations. This is particularly useful for managing LLM agent prompts in external files.

## Why Use `!code` for Prompts?

1. **Separation of Concerns**: Keep your prompt engineering separate from configuration
2. **Version Control**: Track prompt changes independently with clear diffs
3. **Reusability**: Share prompts across multiple agents or guilds
4. **Maintainability**: Edit prompts in dedicated markdown/text editors with syntax highlighting
5. **Team Collaboration**: Different team members can work on prompts without touching YAML

## Basic Example

### Directory Structure
```
my_guild/
├── guild.yaml
├── agents/
│   └── research_agent.yaml
└── prompts/
    └── research_assistant.md
```

### Agent Configuration (`agents/research_agent.yaml`)
```yaml
id: research_assistant_agent
name: Research Assistant
description: An LLM agent that helps with research tasks
class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
properties:
  model: gpt-4o
  temperature: 0.7
  max_tokens: 2000
  default_system_prompt: !code ../prompts/research_assistant.md
```

### Prompt File (`prompts/research_assistant.md`)
```markdown
# Research Assistant System Prompt

You are an expert research assistant with deep knowledge across multiple domains.

## Your Capabilities
1. Information synthesis from multiple sources
2. Critical analysis and evaluation
3. Structured output and clear communication

## Guidelines
- Always verify information before presenting conclusions
- Use markdown formatting for clarity
- Provide sources and context when applicable
```

### Guild Configuration (`guild.yaml`)
```yaml
id: research_guild
name: Research Guild
description: A guild with research capabilities
agents:
  - !include agents/research_agent.yaml
```

## Advanced Examples

### Multiple Prompts for Different Agent Configurations

```yaml
agents:
  - id: friendly_assistant
    class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
    properties:
      model: gpt-4o-mini
      default_system_prompt: !code prompts/friendly_tone.md
      
  - id: technical_assistant
    class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
    properties:
      model: gpt-4o
      default_system_prompt: !code prompts/technical_expert.md
      
  - id: creative_assistant
    class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
    properties:
      model: claude-3-5-sonnet-latest
      default_system_prompt: !code prompts/creative_writer.md
```

### Combining with Request Preprocessors

```yaml
id: enhanced_llm_agent
class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
properties:
  model: gpt-4o
  default_system_prompt: !code prompts/base_prompt.md
  request_preprocessors:
    - kind: rustic_ai.llm_agent.plugins.request_preprocessor.SystemPromptInjector
      additional_prompt: !code prompts/additional_instructions.txt
```

### Using with ReAct Agent

```yaml
id: react_research_agent
class_name: rustic_ai.llm_agent.react.ReActAgent
properties:
  model: gpt-4o
  max_iterations: 10
  system_prompt: !code prompts/react_system_prompt.md
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths:
      - /path/to/skills/research
      - /path/to/skills/analysis
```

## File Format Recommendations

### Markdown (.md)
Best for rich prompts with formatting, structure, and documentation:
- Headers for sections
- Lists for capabilities or guidelines
- Code blocks for examples
- Bold/italic for emphasis

### Plain Text (.txt)
Good for simple, unformatted prompts:
- Single-purpose instructions
- Quick additions to base prompts
- Environment-specific variations

### JSON (.json)
Useful when prompts need to be programmatically generated or include structured data

## Path Resolution

The `!code` tag resolves paths **relative to the YAML file** that contains the tag:

```yaml
# In guild.yaml at /project/config/guild.yaml
agents:
  - !include agents/my_agent.yaml  # Resolves to /project/config/agents/my_agent.yaml

# In agents/my_agent.yaml at /project/config/agents/my_agent.yaml
properties:
  default_system_prompt: !code ../prompts/prompt.md  # Resolves to /project/config/prompts/prompt.md
```

## Best Practices

### 1. Organize by Purpose
```
prompts/
├── system/              # Base system prompts
│   ├── research.md
│   ├── creative.md
│   └── technical.md
├── instructions/        # Additional instructions
│   ├── tone.txt
│   └── format.txt
└── examples/           # Few-shot examples
    ├── qa_examples.md
    └── analysis_examples.md
```

### 2. Use Descriptive Names
- `research_assistant_system.md` ✓
- `prompt.txt` ✗
- `code_review_instructions.md` ✓
- `p1.txt` ✗

### 3. Version Control
Commit prompt files alongside your configuration:
```bash
git add prompts/research_assistant.md
git commit -m "feat: enhance research assistant with citation guidelines"
```

### 4. Documentation in Prompts
Include metadata and changelog in your prompt files:
```markdown
<!--
Prompt: Research Assistant System Prompt
Version: 2.1.0
Last Updated: 2026-01-09
Changelog:
- 2.1.0: Added citation format guidelines
- 2.0.0: Restructured for clarity
- 1.0.0: Initial version
-->

# Research Assistant System Prompt
...
```

### 5. Test Prompts Independently
Create test cases that verify prompt behavior:
```python
def test_research_prompt_loaded():
    """Verify research assistant prompt is loaded correctly."""
    guild = GuildBuilder.from_yaml_file("config/guild.yaml")
    spec = guild.build_spec()
    
    agent = spec.agents[0]
    prompt = agent.properties.default_system_prompt
    
    assert "Research Assistant" in prompt
    assert "capabilities" in prompt.lower()
```

## Integration with Other Tags

The `!code` tag works seamlessly with `!include`:

```yaml
# guild.yaml
id: my_guild
name: My Guild
agents:
  - !include agents/agent1.yaml  # Load agent config
  - !include agents/agent2.yaml

# agents/agent1.yaml
id: agent1
properties:
  default_system_prompt: !code ../prompts/agent1_prompt.md  # Load prompt
```

## Troubleshooting

### File Not Found
```
FileNotFoundError: [Errno 2] No such file or directory: '/path/to/prompt.md'
```
**Solution**: Check that the path is relative to the YAML file containing the `!code` tag, not the current working directory.

### Empty Prompt
If the prompt appears empty, verify:
1. File has actual content
2. File encoding is UTF-8
3. No permission issues reading the file

### Quotes in YAML
When using `!code`, you don't need quotes:
```yaml
# Correct
default_system_prompt: !code prompts/my_prompt.md

# Incorrect (creates a string literal)
default_system_prompt: "!code prompts/my_prompt.md"
```

## See Also

- [Modular Guild Loading](modular_guild_loading.md)
- [LLMAgent Configuration](../agents/llm_agent.md)
- [YAML Include Tag](yaml_include_tag.md)
- [Guild Builder API](../core/guild_builder.md)
