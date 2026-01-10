# Rustic AI Skills

Agent Skills support for the Rustic AI framework. This module provides tools for discovering, installing, parsing, and executing Agent Skills from various sources including GitHub repositories and local directories.

## Overview

Agent Skills are a standardized format for packaging reusable capabilities that AI agents can invoke. This module implements:

- **SKILL.md Parser**: Parse skill definitions in the [Agent Skills](https://agentskills.io) format
- **Skill Marketplace**: Discover and install skills from GitHub repositories, Git URLs, or local directories
- **Script Executor**: Securely execute skill scripts (Python, Shell, JavaScript, etc.)
- **SkillToolset**: Integrate skills with the ReActAgent as executable tools

## Installation

```bash
cd skills
poetry install --with dev
```

## Quick Start

### Discover and Install Skills

```python
from rustic_ai.skills import SkillMarketplace

# Initialize marketplace
marketplace = SkillMarketplace()

# Add Anthropic's official skills (pre-configured)
# marketplace.add_source("anthropic", "github", "anthropics/skills")

# Add a custom source
marketplace.add_source(
    name="my-skills",
    source_type="github",
    location="myorg/agent-skills",
)

# Discover available skills
skills = marketplace.discover()
for skill in skills:
    print(f"{skill.name}: {skill.description}")

# Install a skill
marketplace.install("pdf")

# List installed skills
installed = marketplace.list_installed()
```

### Use Skills with ReActAgent

```python
from pathlib import Path
from rustic_ai.skills import SkillToolset
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig

# Create toolset from installed skill
toolset = SkillToolset.from_path(Path("/tmp/rustic-skills/pdf"))

# Configure ReActAgent with the skill
config = ReActAgentConfig(
    model="gpt-4",
    toolset=toolset,
    system_prompt=toolset.get_system_prompt_addition(),
)
```

### Use Multiple Skills

```python
from rustic_ai.skills import SkillToolset

# Load multiple skills at once
toolset = SkillToolset.from_paths([
    Path("/tmp/rustic-skills/pdf"),
    Path("/tmp/rustic-skills/csv"),
    Path("/tmp/rustic-skills/web-search"),
])

# Get combined system prompt
system_prompt = toolset.get_combined_system_prompt()
```

### Parse Skills Directly

```python
from pathlib import Path
from rustic_ai.skills import SkillParser, parse_skill

# Parse a skill folder
skill = parse_skill(Path("./my-skill"))

print(f"Name: {skill.name}")
print(f"Description: {skill.description}")
print(f"Scripts: {[s.name for s in skill.scripts]}")
print(f"Instructions:\n{skill.instructions}")

# Lazy load metadata only (for efficient discovery)
metadata = SkillParser.parse_metadata_only(Path("./my-skill"))
```

### Execute Scripts Directly

```python
from rustic_ai.skills import ScriptExecutor, ExecutionConfig

# Configure executor
config = ExecutionConfig(
    timeout_seconds=60,
    env_vars={"API_KEY": "secret"},
)

executor = ScriptExecutor(config)

# Execute inline code
result = executor.execute_inline(
    code='print("Hello from skill")',
    language="python",
    args={"input": "test"},
)

if result.success:
    print(result.output)
else:
    print(f"Error: {result.error}")
```

## Skill Format

Skills follow the [Agent Skills specification](https://agentskills.io):

```
my-skill/
├── SKILL.md           # Required: Skill definition
├── scripts/           # Optional: Executable scripts
│   ├── process.py
│   └── setup.sh
├── references/        # Optional: Reference documents
│   └── api-docs.md
└── assets/            # Optional: Template files, configs
    └── template.json
```

### SKILL.md Format

```markdown
---
name: my-skill
description: What this skill does and when to use it
allowed-tools: Read, Write, Bash
model: gpt-4
---

# My Skill

Instructions for how to use this skill...

## Usage

1. Step one
2. Step two
```

## Components

### Models

- `SkillMetadata`: Lightweight metadata from SKILL.md frontmatter
- `SkillDefinition`: Full skill definition with scripts, references, assets
- `SkillScript`: Executable script with interpreter info
- `SkillReference`: Reference document with lazy loading
- `SkillSource`: Configuration for a skill source (GitHub, local, Git)
- `SkillRegistry`: Registry of discovered skills

### Parser

- `SkillParser`: Parse SKILL.md files and discover resources
- `parse_skill()`: Convenience function for full parsing
- `parse_skill_metadata()`: Convenience function for metadata-only parsing

### Marketplace

- `SkillMarketplace`: Discover and install skills from various sources
- Supports GitHub repositories (via GitPython)
- Supports local directories
- Supports arbitrary Git URLs

### Executor

- `ScriptExecutor`: Execute scripts with timeout and sandboxing
- `ExecutionConfig`: Configuration for script execution
- `ExecutionResult`: Result of script execution
- Supports Python, Shell, JavaScript, TypeScript, Ruby

### Toolset

- `SkillToolset`: Convert skills to ReActToolset for use with ReActAgent (supports single or multiple skills)
- `MarketplaceSkillToolset`: Auto-install skills from marketplace
- `ScriptToolParams`: Parameters for script-based tools

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=rustic_ai.skills

# Run specific test file
poetry run pytest tests/test_parser.py
```

## Development

```bash
# Format code
poetry run tox -e format

# Lint code
poetry run tox -e lint

# Run all checks
poetry run tox
```

## License

Apache-2.0
