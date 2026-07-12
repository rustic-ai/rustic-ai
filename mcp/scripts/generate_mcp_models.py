#!/usr/bin/env python3
"""
Script to generate Pydantic models from MCP provider schemas.

This script reads a YAML file containing MCP provider configurations,
fetches their tool schemas, and generates Pydantic models for each provider's
tool inputs and outputs using datamodel-code-generator.

From mcp folder,
   pip install datamodel-code-generator==0.60.0
   python scripts/generate_mcp_models.py scripts/remote-providers.yaml
   # Equivalent to:
   # python scripts/generate_mcp_models.py scripts/remote-providers.yaml \
   #     ./src/rustic_ai/mcp/connectors
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import httpx
import yaml
from datamodel_code_generator import InputFileType, generate, GenerateConfig, DataModelType, Formatter
from mcp import Tool
from pydantic import BaseModel, Field

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MCPProvider(BaseModel):
    """Configuration for an MCP provider."""
    name: str
    url: str
    token_env_var: Optional[str] = Field(None, description="Optional API token environment variable name")
    token_header: Optional[str] = Field("Authorization", description="Optional API token header name")


class MCPProviderConfig(BaseModel):
    """Root configuration containing MCP providers."""
    providers: List[MCPProvider]


def load_providers_config(yaml_path: Path) -> MCPProviderConfig:
    """
    Load MCP provider configuration from YAML file.

    Args:
        yaml_path: Path to the YAML configuration file

    Returns:
        MCPProviderConfig: Parsed provider configuration
    """
    logger.info(f"Loading provider configuration from {yaml_path}")

    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    with open(yaml_path, 'r') as f:
        config_data = yaml.safe_load(f)

    config = MCPProviderConfig(**config_data)
    logger.info(f"Loaded {len(config.providers)} provider(s)")

    return config


async def get_provider_tools(provider: MCPProvider) -> List[Tool]:
    """
    Fetch tools from MCP provider using HTTP+SSE client.

    This function connects to an HTTP-based MCP provider endpoint
    and fetches the available tools.

    Args:
        provider: MCP provider configuration

    Returns:
        List of tool definitions from the provider
    """
    logger.info(f"Fetching tools from provider: {provider.name} ({provider.url})")

    headers = {}
    if provider.token_env_var:
        token = os.environ.get(provider.token_env_var, None)
        if token:
            if provider.token_header == "Authorization":
                headers["Authorization"] = f"Bearer {token}"
            else:
                headers[provider.token_header] = token
        else:
            raise ValueError(f"Token environment variable '{provider.token_env_var}' not found")
    http_client = httpx.AsyncClient(headers=headers) if headers else None
    try:
        async with streamable_http_client(provider.url, http_client=http_client) as (read_stream, write_stream, _):
            # Create a session using the client streams
            async with ClientSession(read_stream, write_stream) as session:

                    # Initialize the connection
                    await session.initialize()
                    # List available tools
                    result = await session.list_tools()
                    logger.info(f"Fetched {len(result.tools)} tool(s) from {provider.name}")
                    return result.tools
    except Exception as e:
        for error in e.exceptions:
            logger.error(f"Error fetching tools from {provider.name}: {error}")
            raise

def _tool_to_dict(tool: Tool) -> Dict[str, Any]:
    """
    Convert Tool object to dictionary format.

    Args:
        tool: MCP Tool object

    Returns:
        Dictionary representation of the tool
    """
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
    }


def generate_pydantic_models(
        tools: List[Tool],
        provider: "MCPProvider",
        output_dir: Path
) -> None:
    """
    Generate Pydantic models for tool schemas using datamodel-code-generator.

    Args:
        tools: List of tool definitions
        provider: MCP provider configuration (name, url, optional token env var)
        output_dir: Output directory for generated models
    """
    if not tools:
        logger.warning(f"No tools found for provider: {provider.name}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{provider.name}.py"

    logger.info(f"Generating Pydantic models for {provider.name}")

    # Create combined schema with all tool models
    combined_models = _create_combined_schema(tools, provider, output_dir)

    try:

        # Generate using datamodel-code-generator
        config = GenerateConfig(
            input_file_type=InputFileType.JsonSchema,
            input_filename="example.json",
            output=output_file,
            output_model_type=DataModelType.PydanticV2BaseModel,
            field_constraints=True,
            use_schema_description=True,
            use_annotated=True,
            skip_root_model=True,
            custom_file_header="\"\"\" \n"
                               + combined_models["description"] + "\n\"\"\" # noqa",
            formatters=[Formatter.BLACK],
            wrap_string_literal=True,
            disable_future_imports=True,
            capitalise_enum_members=True,
            use_union_operator=False,
            set_default_enum_member=True,
        )
        generate(combined_models, config=config)

        logger.info(f"Generated models written to {output_file}")

    except Exception as e:
        logger.error(f"Failed to generate models: {e}")
        raise


def _snake_to_pascal_case(name: str) -> str:
    """Convert ``snake_case`` to ``PascalCase`` — mirrors the class naming
    convention applied by datamodel-code-generator on the ``<tool>_input`` keys."""
    return "".join(part.capitalize() for part in name.split("_"))


def _derive_connectors_module(output_dir: Path) -> str:
    """Derive the Python package path for the connector directory.

    Assumes the standard ``src/`` layout: finds the rightmost ``src`` segment
    in the resolved path and joins the remaining parts with ``.``.
    """
    parts = output_dir.resolve().parts
    if "src" in parts:
        idx = len(parts) - 1 - parts[::-1].index("src")
        return ".".join(parts[idx + 1:])
    return output_dir.name


def _build_bound_mcp_config_comment(
        tools: List[Tool],
        provider: "MCPProvider",
        connectors_module: str,
) -> str:
    """Build a commented JSON snippet of a ``BoundMCPAgentConfig`` referencing
    every generated input class. Drop it into ``set_properties(...)`` (or its
    serialized equivalent) to spin up a ``BoundMCPAgent`` for this provider."""
    server: Dict[str, Any] = {"type": "http", "url": str(provider.url)}
    tool_decls = [
        {
            "name": tool.name,
            "input_class_name": (
                f"{connectors_module}.{provider.name}."
                f"{_snake_to_pascal_case(tool.name)}Input"
            ),
            "description": tool.description
        }
        for tool in tools
    ]
    agent_config = {"server": server, "tools": tool_decls}
    if provider.token_env_var and provider.token_header and provider.token_header != "Authorization":
            agent_config["auth_header"] = provider.token_header
    config_json = json.dumps(agent_config, indent=2)
    commented = "\n".join(f" {line}" if line else "" for line in config_json.splitlines())
    return (
        "\n"
        "Example BoundMCPAgentConfig (JSON) for this provider:\n"
        f"{commented}\n"
    )


def _create_combined_schema(
        tools: List[Tool],
        provider: "MCPProvider",
        output_dir: Path,
) -> Dict[str, Any]:
    """
    Create a combined JSON schema containing all tool input schemas as separate definitions.

    Args:
        tools: List of tool dictionaries
        provider: MCP provider configuration
        output_dir: Directory the generated module will be written to (used to
            derive the qualified class names embedded in the config comment)

    Returns:
        Combined JSON schema
    """
    definitions = {}
    description = f"Auto-generated Pydantic models for {provider.name}'s MCP. Supported tools are: \n"

    for tool in tools:
        tool_name = tool.name

        # Add input schema - use the actual inputSchema from the tool
        input_schema = tool.inputSchema
        if input_schema:
            # Use tool name as definition key
            input_def_name = f"{tool_name}_input"
            # Copy the input schema and ensure it has a title for better generated class names
            input_schema_copy = input_schema.copy()
            if "title" not in input_schema_copy:
                input_schema_copy["title"] = tool_name
            definitions[input_def_name] = input_schema_copy
            logger.info(f"Added schema definition: {input_def_name}")

    description += _build_bound_mcp_config_comment(
        tools, provider, _derive_connectors_module(output_dir)
    )

    # Create root schema that references all definitions
    root_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "description": description,
        "definitions": definitions
    }

    return root_schema


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Pydantic models from MCP provider schemas"
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Path to YAML file containing MCP provider configurations"
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=Path("./src/rustic_ai/mcp/connectors"),
        help="Output directory for generated model files. Default: ./src/rustic_ai/mcp/connectors",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        load_dotenv()
        # Load configuration
        config = load_providers_config(args.yaml_file)

        # Process each provider
        for provider in config.providers:
            try:
                logger.info(f"Processing provider: {provider.name}")

                # Fetch tools
                tools = await get_provider_tools(provider)

                # Generate models
                generate_pydantic_models(
                    tools,
                    provider,
                    args.output_dir
                )

            except Exception as e:
                logger.error(f"Error processing provider {provider.name}: {e}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()

        logger.info("Model generation completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
