"""
Request preprocessor to extract file URLs from FileContentParts and inject
information about currently loaded datasets.

When users upload files via the UI, the file URLs come as FileContentParts
in the UserMessage. This preprocessor extracts those URLs and adds a
system message informing the agent about the available files.

Additionally, this preprocessor injects information about datasets that are
already loaded in the analyzer from previous requests, ensuring the LLM has
context about available data across conversation turns.
"""

import logging
import os
from typing import List, Optional

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    FileContentPart,
    SystemMessage,
    UserMessage,
)
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor

logger = logging.getLogger(__name__)


class FileUrlExtractorPreprocessor(RequestPreprocessor):
    """
    Extracts file URLs from FileContentParts in UserMessages and adds
    a system message with the file information.

    Also injects information about currently loaded datasets from the analyzer,
    ensuring the LLM has context across conversation turns.

    This allows the ReActAgent to be aware of:
    1. Newly uploaded files in the current request
    2. Previously loaded datasets from earlier requests
    """

    def _get_loaded_datasets(self, agent: Agent) -> Optional[List[str]]:
        """
        Try to get the list of currently loaded datasets from the agent's toolset.

        Returns:
            List of dataset names if available, None if not accessible.
        """
        try:
            # Access the toolset from the agent's config
            if hasattr(agent, "config") and hasattr(agent.config, "toolset"):
                toolset = agent.config.toolset
                # Check if this is a DataAnalystReActToolset with an analyzer
                if hasattr(toolset, "_analyzer") and toolset._analyzer is not None:
                    result = toolset._analyzer.list_datasets()
                    return result.datasets if result.datasets else None
        except Exception as e:
            logger.debug(f"Could not get loaded datasets: {e}")
        return None

    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        """
        Extract file URLs from the request and inject dataset context.

        This method:
        1. Extracts filenames from FileContentParts in the current request
        2. Gets the list of already-loaded datasets from the analyzer
        3. Adds a system message with this context for the LLM

        Note: We look at ctx.payload (the original incoming request) rather than
        the preprocessed request, because ReActAgent extracts only text from
        UserMessages when building its internal request, stripping FileContentParts.
        """
        file_names: List[str] = []

        # Extract file URLs from the ORIGINAL request (ctx.payload) which contains
        # FileContentParts. The 'request' parameter may have already had these stripped.
        original_request = ctx.payload
        for msg in original_request.messages:
            if isinstance(msg, UserMessage):
                if not isinstance(msg.content, str):
                    # ArrayOfContentParts - look for FileContentParts
                    for part in msg.content.root:
                        if isinstance(part, FileContentPart):
                            # Extract just the filename, not the full path
                            # The toolset's filesystem is already configured with the base path
                            full_url = part.file_url.url
                            filename = os.path.basename(full_url)
                            file_names.append(filename)

        # Get currently loaded datasets from the analyzer
        loaded_datasets = self._get_loaded_datasets(agent)

        # If no new files and no loaded datasets, return unchanged
        if not file_names and not loaded_datasets:
            return request

        # Build the system message content
        system_parts: List[str] = []

        # Add information about newly uploaded files
        if file_names:
            file_info = "\n".join(f"- {name}" for name in file_names)
            system_parts.append(
                f"The user has uploaded the following file(s):\n{file_info}\n\n"
                "Use the load_file tool with these filenames to load the data for analysis."
            )

        # Add information about already loaded datasets
        if loaded_datasets:
            dataset_info = "\n".join(f"- {name}" for name in loaded_datasets)
            system_parts.append(
                f"The following datasets are already loaded and available for analysis:\n{dataset_info}\n\n"
                "You can use these datasets directly with query_dataset, get_schema, describe_dataset, "
                "and other analysis tools without needing to load them again."
            )

        system_content = "\n\n".join(system_parts)

        # Insert the context system message after existing system messages
        new_messages = list(request.messages)

        # Find position after last SystemMessage
        insert_pos = 0
        for i, msg in enumerate(new_messages):
            if isinstance(msg, SystemMessage):
                insert_pos = i + 1

        new_messages.insert(insert_pos, SystemMessage(content=system_content))

        return ChatCompletionRequest(
            messages=new_messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tool_choice=request.tool_choice,
        )
