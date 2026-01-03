import asyncio
from datetime import UTC, datetime
import json
from typing import List, Literal, Optional
import uuid

from fsspec import filesystem
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field, PrivateAttr

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    FunctionMessage,
    LLMMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.knowledgebase.agent_config import KnowledgeAgentConfig
from rustic_ai.core.knowledgebase.kbindex_backend import KBIndexBackend
from rustic_ai.core.knowledgebase.kbindex_backend_memory import InMemoryKBIndexBackend
from rustic_ai.core.knowledgebase.knowledge_base import KnowledgeBase
from rustic_ai.core.knowledgebase.pipeline_executor import SimplePipelineExecutor
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class KnowledgeBasedMemoriesStore(MemoriesStore):
    """
    Memory store that uses KnowledgeBase for semantic memory storage and retrieval.

    This memory store indexes conversation messages into a vector database using the
    KnowledgeBase infrastructure, enabling semantic search across conversation history.

    The store creates its own instances of FileSystem and KBIndexBackend, so agents
    do not need to have these dependencies configured.

    Configuration:
    - context_window_size: Number of recent messages to use for building search queries
    - recall_limit: Maximum number of memories to retrieve during recall
    - path_base: Base path for storing knowledge base data (defaults to "/tmp/kb_memories")
    - protocol: Filesystem protocol (defaults to "file")
    - storage_options: Additional storage options (defaults to {"auto_mkdir": True})
    - asynchronous: Whether to use async filesystem (defaults to True)
    """

    memory_type: Literal["knowledge_based"] = "knowledge_based"
    context_window_size: int = 5
    recall_limit: int = 10
    path_base: str = "/tmp/kb_memories"
    protocol: str = "file"
    storage_options: dict = Field(default_factory=lambda: {"auto_mkdir": True})
    asynchronous: bool = True

    _kb: Optional[KnowledgeBase] = PrivateAttr(default=None)
    _message_counter: int = PrivateAttr(default=0)
    _filesystem: Optional[FileSystem] = PrivateAttr(default=None)
    _kb_backend: Optional[KBIndexBackend] = PrivateAttr(default=None)

    async def _get_kb(self, agent: Agent, ctx: ProcessContext) -> KnowledgeBase:
        """
        Lazily initialize and return the KnowledgeBase instance.

        Creates new instances of FileSystem and KBIndexBackend instead of using
        guild-scoped dependencies.
        """
        if self._kb is not None:
            return self._kb

        # Create filesystem instance
        if self._filesystem is None:
            basefs = filesystem(
                self.protocol,
                asynchronous=self.asynchronous,
                **self.storage_options,
            )

            if self.asynchronous and not basefs.__class__.async_impl:
                basefs = AsyncFileSystemWrapper(basefs)

            self._filesystem = FileSystem(
                path=f"{self.path_base}/{agent.guild_id}",
                fs=basefs,
                asynchronous=self.asynchronous,
                storage_options=self.storage_options,
            )

        # Create kb_backend instance
        if self._kb_backend is None:
            self._kb_backend = InMemoryKBIndexBackend()

        # Create KnowledgeBase with default text configuration
        cfg = KnowledgeAgentConfig.default_text(id=f"kb_memory_{agent.guild_id}")
        kb = KnowledgeBase(
            config=cfg.to_kb_config(),
            filesystem=self._filesystem,
            library_path=cfg.library_path,
            executor=SimplePipelineExecutor(),
            index_backend=self._kb_backend,
        )
        await kb.ensure_ready()

        self._kb = kb
        return kb

    def _serialize_message(self, message: LLMMessage) -> tuple[str, dict]:
        """
        Convert an LLMMessage to text content and metadata.

        Returns:
            tuple: (content_str, metadata_dict) where content is the message text
                   and metadata contains role, timestamp, and other message fields.
        """
        timestamp = datetime.now(UTC).isoformat()
        self._message_counter += 1

        # Build metadata dictionary with all message fields
        metadata = {
            "role": message.role,
            "timestamp": timestamp,
        }

        # Include optional fields if present
        if hasattr(message, "name") and message.name:
            metadata["name"] = message.name
        if hasattr(message, "tool_calls") and message.tool_calls:
            # Serialize tool calls to JSON
            metadata["tool_calls"] = json.dumps(
                [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in message.tool_calls]
            )
        if hasattr(message, "tool_call_id") and message.tool_call_id:
            metadata["tool_call_id"] = message.tool_call_id

        # Extract content as plain text
        content_str = ""
        if isinstance(message.content, str):
            content_str = message.content
        elif isinstance(message.content, list):
            # For multimodal content, extract text parts
            text_items = [item.get("text", "") for item in message.content if isinstance(item, dict) and "text" in item]
            content_str = " ".join(text_items)
        else:
            content_str = str(message.content)

        return content_str, metadata

    def _deserialize_message(self, content: str, metadata: dict) -> Optional[LLMMessage]:
        """
        Reconstruct an LLMMessage from content and metadata.

        Args:
            content: The message text content
            metadata: Dictionary containing role, timestamp, and other fields

        Returns:
            LLMMessage object or None if deserialization fails
        """
        try:
            # Extract fields from metadata
            role = metadata.get("role")
            if not role:
                return None

            name = metadata.get("name")
            tool_call_id = metadata.get("tool_call_id")

            # Deserialize tool_calls if present
            tool_calls = None
            if "tool_calls" in metadata:
                try:
                    tool_calls = json.loads(metadata["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    tool_calls = metadata["tool_calls"]

            # Create the appropriate message type based on role
            if role == "user":
                msg = UserMessage(content=content, name=name)
            elif role == "assistant":
                msg = AssistantMessage(content=content, name=name, tool_calls=tool_calls)
            elif role == "system":
                msg = SystemMessage(content=content, name=name)
            elif role == "tool":
                msg = ToolMessage(content=content, tool_call_id=tool_call_id or "")
            elif role == "function":
                msg = FunctionMessage(content=content, name=name or "")
            else:
                # Fallback to user message
                msg = UserMessage(content=content)

            return msg
        except (KeyError, ValueError, TypeError) as e:
            # Log warning but don't fail
            print(f"Warning: Failed to deserialize message: {e}")
            return None

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        """
        Store a memory message by indexing it in the KnowledgeBase.

        The message content is stored as text and metadata is attached to the MediaLink.
        """
        # Serialize the message to content and metadata
        content_str, metadata = self._serialize_message(message)

        # Create a unique message ID
        msg_id = f"memory_{self._message_counter}_{uuid.uuid4().hex[:8]}"

        async def _index_message():
            kb = await self._get_kb(agent, ctx)

            # Create a temporary file content
            content_bytes = content_str.encode("utf-8")

            # Write to filesystem
            # Note: filesystem is already rooted at {path_base}/{agent.guild_id}
            file_path = "guild/memories/" + f"{msg_id}.txt"

            # Ensure directory exists and write files
            dir_path = "guild/memories"
            if self._filesystem:
                # Get the underlying filesystem for operations
                fs = getattr(self._filesystem, 'fs', self._filesystem)

                # Build full paths (DirFileSystem prepends its path automatically)
                full_file_path = file_path
                full_meta_path = file_path + ".metadata"

                # Create directory if needed (sync operation on local fs)
                if not self._filesystem.exists(dir_path):
                    self._filesystem.makedirs(dir_path, exist_ok=True)

                # Write content file
                with self._filesystem.open(full_file_path, "wb") as f:
                    f.write(content_bytes)

                # Write sidecar metadata file using KB naming convention
                # Format: guild/memories/.memory_1_abc.txt.meta (not .metadata!)
                dir_part, file_part = file_path.rsplit("/", 1)
                full_meta_path = f"{dir_part}/.{file_part}.meta"

                meta_json = json.dumps(metadata, indent=2).encode("utf-8")
                with self._filesystem.open(full_meta_path, "wb") as f:
                    f.write(meta_json)

            # Create MediaLink (metadata is now in sidecar file)
            media = MediaLink(
                id=msg_id,
                url=f"file:///{file_path}",
                name=f"{msg_id}.txt",
                mimetype="text/plain",
            )

            # Index via KB pipeline
            try:
                await kb.ingest_media([media])
            except Exception as e:
                print(f"Warning: Failed to index memory: {e}")

        # Run the async indexing and wait for completion
        try:
            loop = asyncio.get_running_loop()
            # Event loop is running - we need to run in a thread to avoid blocking
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _index_message())
                future.result()  # Wait for completion
        except RuntimeError:
            # No event loop running, create one
            asyncio.run(_index_message())

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        """
        Retrieve relevant memory messages based on the context.

        Uses the recent context window to build a search query, then performs semantic
        search in the KnowledgeBase to find relevant past memories.
        """

        async def _search_memories():
            kb = await self._get_kb(agent, ctx)

            # Extract recent messages from context window
            recent_messages = context[-self.context_window_size :] if context else []

            if not recent_messages:
                # If no context, return empty list
                return []

            # Build search query from recent messages
            query_parts = []
            for msg in recent_messages:
                if isinstance(msg.content, str):
                    query_parts.append(msg.content)
                elif isinstance(msg.content, list):
                    # Extract text from multimodal content
                    for item in msg.content:
                        if isinstance(item, dict) and "text" in item:
                            query_parts.append(item["text"])

            query = " ".join(query_parts)

            if not query.strip():
                return []

            # Perform semantic search
            try:
                results = await kb.search_text(text=query, limit=self.recall_limit)
            except Exception as e:
                print(f"Warning: Failed to search memories: {e}")
                return []

            # Parse results back into LLMMessage objects
            recalled_messages = []
            for result in results.results:
                # Extract text content and metadata from payload
                text_content = result.payload.get("text", "")

                # KB stores metadata from MediaLink in the "metadata" JSON column
                # Try to get it from there first, otherwise use individual fields
                metadata = result.payload.get("metadata", {})
                if not metadata or not isinstance(metadata, dict):
                    # Fallback: try to extract from denormalized fields
                    metadata = {
                        k: v
                        for k, v in result.payload.items()
                        if k not in ["text", "chunk_id", "_debug", "metadata"]
                    }

                if text_content and metadata:
                    msg = self._deserialize_message(text_content, metadata)
                    if msg:
                        recalled_messages.append(msg)

            return recalled_messages

        # Run the async search
        try:
            loop = asyncio.get_running_loop()
            # Event loop is running - we need to run in a thread to avoid blocking
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _search_memories())
                return future.result()  # Wait for completion and return result
        except RuntimeError:
            # No event loop running, use asyncio.run
            return asyncio.run(_search_memories())
