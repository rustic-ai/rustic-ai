# Quick Reference: !code Tag for Prompts

## Basic Syntax

```yaml
properties:
  default_system_prompt: !code path/to/prompt.md
```

## Common Use Cases

### LLMAgent
```yaml
id: my_llm_agent
class_name: rustic_ai.llm_agent.llm_agent.LLMAgent
properties:
  model: gpt-4o
  default_system_prompt: !code prompts/system.md
```

### ReActAgent
```yaml
id: react_agent
class_name: rustic_ai.llm_agent.react.ReActAgent
properties:
  model: gpt-4o
  system_prompt: !code prompts/react_instructions.md
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths: [/path/to/skills]
```

### With Request Preprocessor
```yaml
properties:
  request_preprocessors:
    - kind: rustic_ai.llm_agent.plugins.request_preprocessor.SystemPromptInjector
      additional_prompt: !code prompts/extra_instructions.txt
```

## Path Examples

```yaml
# Relative to current YAML file
default_system_prompt: !code prompts/system.md
default_system_prompt: !code ../prompts/system.md
default_system_prompt: !code ../../shared/prompts/system.md

# From project root (not recommended, less portable)
default_system_prompt: !code /absolute/path/to/prompts/system.md
```

## File Types

- `.md` - Markdown with metadata (recommended)
- `.md` - Standard markdown
- `.txt` - Plain text
- `.json` - JSON content (loaded as string)
- Any text file

## Tips

✓ Use relative paths for portability
✓ Organize prompts in a dedicated directory
✓ Use descriptive filenames
✓ Version control prompt files
✓ Add comments/metadata in prompt files

✗ Don't use absolute paths
✗ Don't quote the tag: `"!code ..."`
✗ Don't forget the space: `!code` not `!codeprompts/file.md`
