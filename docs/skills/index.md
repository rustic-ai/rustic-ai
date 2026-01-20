# Skills Module

## Overview

The **Skills** module provides a complete framework for discovering, installing, parsing, and executing **Agent Skills** - standardized, reusable capabilities that AI agents can invoke. Skills follow the [agentskills.io](https://agentskills.io) specification, enabling interoperability across platforms.

## Key Features

- **Skill Discovery** - Find skills from GitHub, Git repositories, or local directories
- **Skill Installation** - Sparse checkout for efficient installation from large repos
- **SKILL.md Parsing** - Parse standardized skill definitions with metadata, scripts, and references
- **Script Execution** - Securely execute Python, Shell, JavaScript, TypeScript, and Ruby scripts
- **ReActAgent Integration** - Seamlessly integrate skills as tools via `SkillToolset`
- **Marketplace Support** - Pre-configured access to official skill sources (e.g., Anthropic)

## Architecture

```mermaid
flowchart LR
    A[SkillMarketplace] --> B[Discover Skills]
    B --> C[Install Skills]
    C --> D[SkillParser]
    D --> E[SkillDefinition]
    E --> F[SkillToolset]
    F --> G[ReActAgent]
    G --> H[ScriptExecutor]
    H --> I[Tool Results]
```

### Components

| Component | Purpose |
|-----------|---------|
| **SkillMarketplace** | Discover and install skills from various sources |
| **SkillParser** | Parse SKILL.md files and skill resources |
| **SkillDefinition** | Structured representation of a skill |
| **SkillToolset** | Convert skills to ReActToolset for agent use |
| **ScriptExecutor** | Execute skill scripts with sandboxing and timeouts |

## Installation

```bash
cd skills
poetry install --with dev
```

## Quick Start

### 1. Discover and Install Skills

```python
from rustic_ai.skills import SkillMarketplace

# Initialize marketplace
marketplace = SkillMarketplace()

# Add skill sources
marketplace.add_source(
    name="my-skills",
    source_type="github",
    location="myorg/agent-skills",
)

# Discover available skills
skills = marketplace.discover()
for skill in skills:
    print(f"{skill.name}: {skill.description}")

# Install a specific skill
marketplace.install("pdf")

# List installed skills
installed = marketplace.list_installed()
print(f"Installed {len(installed)} skills")
```

### 2. Use Skills with ReActAgent

```python
from pathlib import Path
from rustic_ai.skills import SkillToolset
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig
from rustic_ai.core.guild.builders import AgentBuilder

# Create toolset from installed skill
toolset = SkillToolset.from_path(Path("/tmp/rustic-skills/pdf"))

# Configure ReActAgent
agent_spec = (
    AgentBuilder(ReActAgent)
    .set_id("pdf_agent")
    .set_name("PDF Assistant")
    .set_description("Processes PDF documents")
    .set_properties(
        ReActAgentConfig(
            model="gpt-4",
            toolset=toolset,
            system_prompt=toolset.get_system_prompt_addition(),
        )
    )
    .build_spec()
)
```

### 3. Use Multiple Skills

```python
# Load multiple skills at once
toolset = SkillToolset.from_paths([
    Path("/tmp/rustic-skills/pdf"),
    Path("/tmp/rustic-skills/csv"),
    Path("/tmp/rustic-skills/web-search"),
])

# Configure agent with all skills
config = ReActAgentConfig(
    model="gpt-4",
    toolset=toolset,
    system_prompt=toolset.get_combined_system_prompt(),
)
```

## Skill Format

### Directory Structure

```
my-skill/
├── SKILL.md           # Required: Skill definition
├── scripts/           # Optional: Executable scripts
│   ├── process.py
│   └── setup.sh
├── references/        # Optional: Reference documents
│   └── api-docs.md
└── assets/            # Optional: Templates, configs
    └── template.json
```

### SKILL.md Format

```markdown
---
name: pdf-processor
description: Extract text and metadata from PDF documents
allowed-tools: Read, Write
model: gpt-4
version: 1.0.0
author: YourName
---

# PDF Processor Skill

This skill enables extraction and analysis of PDF documents.

## Capabilities

- Extract text from single or multi-page PDFs
- Parse PDF metadata (title, author, creation date)
- Handle password-protected PDFs
- Export to plain text or JSON format

## Usage

When the user asks to process a PDF:

1. Use `extract_text` to get PDF content
2. Use `extract_metadata` for document information
3. Combine results for comprehensive analysis

## Scripts

- `extract_text.py` - Extract all text from a PDF
- `extract_metadata.py` - Get PDF metadata
- `unlock_pdf.sh` - Unlock password-protected PDFs

## Examples

**User**: "What is the title of document.pdf?"
**Agent**: Use `extract_metadata` with file="document.pdf"
```

### Script Example

```python
#!/usr/bin/env python3
"""Extract text from PDF files."""

import sys
import json
from pathlib import Path

def extract_text(file_path: str) -> str:
    """Extract text from PDF."""
    # Implementation here
    pass

if __name__ == "__main__":
    # Read arguments from stdin (JSON)
    args = json.loads(sys.stdin.read())
    
    # Execute
    result = extract_text(args["file_path"])
    
    # Output result
    print(result)
```

## SkillMarketplace

### Adding Sources

```python
marketplace = SkillMarketplace()

# Add GitHub repository
marketplace.add_source(
    name="anthropic",
    source_type="github",
    location="anthropics/skills",
    branch="main",
    skills_path="skills"  # Subfolder containing skills
)

# Add local directory
marketplace.add_source(
    name="local",
    source_type="local",
    location="/path/to/skills"
)

# Add custom Git repository
marketplace.add_source(
    name="private-skills",
    source_type="git",
    location="https://git.company.com/skills.git",
    branch="production"
)
```

### Discovery and Installation

```python
# Discover all available skills
skills = marketplace.discover()

# Filter skills
pdf_skills = [s for s in skills if "pdf" in s.name.lower()]

# Install a skill
marketplace.install("pdf")

# Install with custom location
marketplace.install("pdf", install_path=Path("/custom/path"))

# List installed skills
installed = marketplace.list_installed()
for skill in installed:
    print(f"{skill.name} v{skill.metadata.version}")
```

### Pre-configured Sources

The marketplace includes well-known skill sources that are automatically configured:

```python
# Anthropic's official skills are pre-configured
# Just discover and install directly:
marketplace = SkillMarketplace()
skills = marketplace.discover("anthropic")  # Discovers from anthropics/skills repo
marketplace.install("pdf")  # Installs the pdf skill

# To add a custom source with the same configuration:
marketplace.add_source(
    name="my-anthropic",
    source_type="github",
    location="anthropics/skills",
    branch="main",
    skills_path="skills"
)
```

## SkillParser

### Parse Complete Skills

```python
from rustic_ai.skills import parse_skill

# Parse a skill folder
skill = parse_skill(Path("./my-skill"))

# Access components
print(f"Name: {skill.name}")
print(f"Description: {skill.description}")
print(f"Instructions:\n{skill.instructions}")

# Enumerate scripts
for script in skill.scripts:
    print(f"Script: {script.name} ({script.language})")
    print(f"  Path: {script.path}")
    print(f"  Executable: {script.executable}")

# Enumerate references
for ref in skill.references:
    print(f"Reference: {ref.name}")
    print(f"  Content: {ref.content[:100]}...")

# Get specific script
process_script = skill.get_script("process_data")
```

### Parse Metadata Only

For efficient discovery without loading full content:

```python
from rustic_ai.skills import SkillParser

# Parse only frontmatter (fast)
metadata = SkillParser.parse_metadata_only(Path("./my-skill"))

print(f"Name: {metadata.name}")
print(f"Description: {metadata.description}")
print(f"Version: {metadata.version}")
print(f"Author: {metadata.author}")
```

### Skill Models

```python
from rustic_ai.skills.models import (
    SkillDefinition,
    SkillMetadata,
    SkillScript,
    SkillReference,
    SkillAsset,
)

# SkillMetadata - Frontmatter fields
metadata = SkillMetadata(
    name="my-skill",
    description="Does something useful",
    allowed_tools=["Read", "Write"],
    model="gpt-4",
    version="1.0.0",
    author="YourName"
)

# SkillScript - Executable script
script = SkillScript(
    name="process",
    path=Path("scripts/process.py"),
    language="python",
    executable=True
)

# SkillDefinition - Complete skill
skill = SkillDefinition(
    metadata=metadata,
    instructions="Skill instructions...",
    path=Path("./my-skill"),
    scripts=[script],
    references=[],
    assets=[]
)
```

## SkillToolset

### Basic Usage

```python
from rustic_ai.skills import SkillToolset

# Single skill
toolset = SkillToolset.from_path(Path("/tmp/rustic-skills/pdf"))

# Multiple skills
toolset = SkillToolset.from_paths([
    Path("/tmp/rustic-skills/pdf"),
    Path("/tmp/rustic-skills/csv"),
])

# Get system prompt addition
prompt = toolset.get_system_prompt_addition()
print(prompt)  # Includes skill instructions

# Get combined prompt for multiple skills
combined = toolset.get_combined_system_prompt()
```

### YAML Configuration

```yaml
# Single skill
properties:
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths:
      - /tmp/rustic-skills/pdf

# Multiple skills
properties:
  toolset:
    kind: rustic_ai.skills.toolset.SkillToolset
    skill_paths:
      - /tmp/rustic-skills/pdf
      - /tmp/rustic-skills/csv
      - /tmp/rustic-skills/web-search
```

### Marketplace Integration

```python
from rustic_ai.skills import MarketplaceSkillToolset

# Auto-install and load skills
toolset = MarketplaceSkillToolset(
    source="anthropic",
    skill_names=["pdf", "csv"],
)

# Use with ReActAgent
config = ReActAgentConfig(
    model="gpt-4",
    toolset=toolset,
)
```

### Custom Execution Config

```python
from rustic_ai.skills import SkillToolset, ExecutionConfig

toolset = SkillToolset.from_path(
    path=Path("/tmp/rustic-skills/pdf"),
    execution_config=ExecutionConfig(
        timeout_seconds=60,
        max_output_bytes=10 * 1024 * 1024,  # 10MB
        env_vars={
            "API_KEY": "secret",
            "DEBUG": "true"
        }
    )
)
```

## ScriptExecutor

### Direct Execution

```python
from rustic_ai.skills import ScriptExecutor, ExecutionConfig

# Configure executor
executor = ScriptExecutor(
    config=ExecutionConfig(
        timeout_seconds=30,
        env_vars={"API_KEY": "secret"},
    )
)

# Execute inline code
result = executor.execute_inline(
    code='print("Hello from skill")',
    language="python",
    args={"input": "test"},
)

if result.success:
    print(f"Output: {result.output}")
    print(f"Duration: {result.duration_ms}ms")
else:
    print(f"Error: {result.error}")
    print(f"Exit code: {result.exit_code}")
```

### Execute Skill Scripts

```python
from rustic_ai.skills import parse_skill

skill = parse_skill(Path("./my-skill"))
script = skill.get_script("process_data")

executor = ScriptExecutor()
result = executor.execute(
    script=script,
    args={"input_file": "data.csv", "format": "json"},
)
```

### Supported Languages

| Language | Extension | Interpreter |
|----------|-----------|-------------|
| Python | `.py` | `python3 -u` |
| Shell | `.sh`, `.bash` | `bash` |
| JavaScript | `.js` | `node` |
| TypeScript | `.ts` | `npx ts-node` |
| Ruby | `.rb` | `ruby` |

### Execution Results

```python
result = executor.execute(script, args)

# Check success
if result.success:
    output = result.output
    duration = result.duration_ms
else:
    error = result.error
    exit_code = result.exit_code
    stderr = result.error if result.capture_stderr else None
```

## Advanced Usage

### Custom Skill Development

```python
from rustic_ai.skills.models import (
    SkillDefinition,
    SkillMetadata,
    SkillScript,
)
from pathlib import Path

# Programmatically create a skill
metadata = SkillMetadata(
    name="custom-skill",
    description="My custom skill",
    allowed_tools=["Read", "Write"],
    model="gpt-4"
)

script = SkillScript(
    name="my_script",
    path=Path("scripts/my_script.py"),
    language="python",
    executable=True
)

skill = SkillDefinition(
    metadata=metadata,
    instructions="Use this skill when...",
    path=Path("./custom-skill"),
    scripts=[script],
    references=[],
    assets=[]
)
```

### Tool Prefix for Skill Names

Prevent name collisions across skills:

```python
toolset = SkillToolset.from_paths(
    paths=[
        Path("/tmp/rustic-skills/pdf"),
        Path("/tmp/rustic-skills/csv"),
    ],
    tool_prefix="skill_"  # Tools become: skill_extract_text, skill_parse_csv
)
```

### Error Handling in Scripts

```python
#!/usr/bin/env python3
import sys
import json

try:
    args = json.loads(sys.stdin.read())
    result = process_data(args)
    print(json.dumps({"success": True, "result": result}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
    sys.exit(1)
```

### Async Execution

For long-running scripts, use background execution:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ScriptExecutor()

async def execute_skill_async(script, args):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            executor.execute,
            script,
            args
        )
    return result

# Usage
result = await execute_skill_async(script, args)
```

## Testing

### Unit Tests

```python
from rustic_ai.skills import parse_skill

def test_skill_parsing():
    skill = parse_skill(Path("./test-skill"))
    
    assert skill.name == "test-skill"
    assert len(skill.scripts) > 0
    assert skill.get_script("test_script") is not None

def test_script_execution():
    executor = ScriptExecutor()
    result = executor.execute_inline(
        code="print('test')",
        language="python",
        args={}
    )
    
    assert result.success
    assert "test" in result.output
```

### Integration Tests

```python
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    FinishReason,
    UserMessage,
)
from rustic_ai.testing.helpers import wrap_agent_for_testing

def test_skill_with_react_agent():
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
    
    # Test skill invocation (see Testing section for message construction)
    agent._on_message(test_message)
    
    assert len(results) == 1
    response = ChatCompletionResponse.model_validate(results[0].payload)
    assert response.choices[0].finish_reason == FinishReason.stop
```

## Best Practices

### 1. Skill Naming

- Use lowercase with hyphens: `pdf-processor`, `web-search`
- Be descriptive but concise
- Avoid version numbers in names (use metadata)

### 2. Script Design

- **Accept JSON from stdin** for arguments
- **Print results to stdout** (JSON or plain text)
- **Exit with non-zero code** on errors
- **Use stderr** for logging/debugging
- **Keep scripts focused** on single tasks

### 3. Documentation

- Provide clear usage instructions in SKILL.md
- Include examples for common use cases
- Document script parameters and return types
- Specify required environment variables

### 4. Security

- **Validate all inputs** in scripts
- **Avoid shell injection** vulnerabilities
- **Use timeouts** to prevent runaway processes
- **Limit output size** to prevent memory issues
- **Sanitize file paths** before file operations

### 5. Error Handling

- Return **descriptive error messages**
- Distinguish between **user errors** and **system errors**
- Provide **recovery suggestions** when possible
- Log errors for debugging

## Common Patterns

### Pattern 1: Multi-Step Skill

```python
# extract_and_analyze.py
import sys
import json

def extract(file_path):
    # Extract data
    pass

def analyze(data):
    # Analyze extracted data
    pass

if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    
    # Step 1: Extract
    data = extract(args["file_path"])
    
    # Step 2: Analyze
    results = analyze(data)
    
    # Output combined results
    print(json.dumps({
        "extracted": data,
        "analysis": results
    }))
```

### Pattern 2: Streaming Results

```python
# stream_process.py
import sys
import json

args = json.loads(sys.stdin.read())

# Process in chunks, stream results
for chunk in process_in_chunks(args["input"]):
    print(json.dumps({"chunk": chunk}))
    sys.stdout.flush()
```

### Pattern 3: Skill Composition

```python
# Combine multiple skills in a composite toolset
from rustic_ai.llm_agent.react.toolset import CompositeToolset

composite = CompositeToolset(
    toolsets=[
        SkillToolset.from_path(Path("./skill1")),
        SkillToolset.from_path(Path("./skill2")),
        CustomToolset(),  # Mix with non-skill toolsets
    ]
)
```

## Troubleshooting

### Issue: Script Not Executing

**Check:**
1. Script has execute permissions
2. Correct interpreter is installed
3. Script path is correct in SKILL.md
4. Timeout is sufficient

### Issue: Skill Not Found

**Check:**
1. Skill path is correct
2. SKILL.md exists at skill root
3. Frontmatter is valid YAML
4. Skill name matches directory name

### Issue: Tool Not Available to Agent

**Check:**
1. Toolset includes the skill
2. Script is marked as a tool in SKILL.md
3. Tool name doesn't conflict with others
4. ReActAgent has correct toolset config

## Reference

### Module: `rustic_ai.skills`

**Main Classes:**
- `SkillMarketplace` - Discover and install skills
- `SkillParser` - Parse SKILL.md files
- `SkillDefinition` - Complete skill representation
- `SkillToolset` - ReActToolset implementation
- `MarketplaceSkillToolset` - Auto-install skills from marketplace
- `ScriptExecutor` - Execute skill scripts

**Models:**
- `SkillMetadata` - Frontmatter metadata
- `SkillScript` - Executable script
- `SkillReference` - Reference document
- `SkillAsset` - Asset file
- `SkillSource` - Skill source configuration

**Functions:**
- `parse_skill()` - Parse complete skill
- `parse_skill_metadata()` - Parse metadata only
- `create_skill_toolset()` - Create toolset from path

### Related Documentation

- [ReActAgent Documentation](../agents/react_agent.md)
- [Creating Custom Agents](../howto/creating_your_first_agent.md)
- [Testing Agents](../howto/testing_agents.md)
- [Agent Skills Specification](https://agentskills.io)
