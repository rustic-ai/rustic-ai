import asyncio
from datetime import UTC, datetime
import json
from typing import List, Literal, Optional
import uuid

from pydantic import PrivateAttr

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import FileSystem
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
from rustic_ai.core.knowledgebase.knowledge_base import KnowledgeBase
from rustic_ai.core.knowledgebase.pipeline_executor import SimplePipelineExecutor
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class KnowledgeBasedMemoriesStore(MemoriesStore):
    """
    Memory store that uses KnowledgeBase for semantic memory storage and retrieval.

    This memory store indexes conversation messages into a vector database using the
    KnowledgeBase infrastructure, enabling semantic search across conversation history.

    Requires guild-scoped dependencies:
    - filesystem: FileSystem for storing knowledge base data
    - kb_backend: KBIndexBackend for vector storage

    Configuration:
    - context_window_size: Number of recent messages to use for building search queries
    - recall_limit: Maximum number of memories to retrieve during recall
    """

    memory_type: Literal["knowledge_based"] = "knowledge_based"
    context_window_size: int = 5
    recall_limit: int = 10

    _kb: Optional[KnowledgeBase] = PrivateAttr(default=None)
    _message_counter: int = PrivateAttr(default=0)
    _filesystem: Optional[FileSystem] = PrivateAttr(default=None)
    _kb_backend: Optional[KBIndexBackend] = PrivateAttr(default=None)

    async def _get_kb(self, agent: Agent, ctx: ProcessContext) -> KnowledgeBase:
        """
        Lazily initialize and return the KnowledgeBase instance.

        Uses guild-scoped dependencies for filesystem and kb_backend.
        """
        if self._kb is not None:
            return self._kb

        # Get guild-scoped dependencies
        if self._filesystem is None:
            fs_resolver = agent._dependency_resolvers.get("filesystem")
            if not fs_resolver:
                raise ValueError("KnowledgeBasedMemoriesStore requires 'filesystem' guild dependency")
            self._filesystem = fs_resolver.get_or_resolve(agent.guild_id)

        if self._kb_backend is None:
            kb_resolver = agent._dependency_resolvers.get("kb_backend")
            if not kb_resolver:
                raise ValueError("KnowledgeBasedMemoriesStore requires 'kb_backend' guild dependency")
            self._kb_backend = kb_resolver.get_or_resolve(agent.guild_id)

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

    def _serialize_message(self, message: LLMMessage) -> str:
        """
        Convert an LLMMessage to a structured text format for indexing.

        Preserves all message metadata including role, content, and additional fields.
        """
        timestamp = datetime.now(UTC).isoformat()
        self._message_counter += 1
        message_id = f"msg_{self._message_counter}_{uuid.uuid4().hex[:8]}"

        # Extract message data
        data = {
            "message_id": message_id,
            "timestamp": timestamp,
            "role": message.role,
            "content": message.content,
        }

        # Include optional fields if present
        if hasattr(message, "name") and message.name:
            data["name"] = message.name
        if hasattr(message, "tool_calls") and message.tool_calls:
            data["tool_calls"] = [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in message.tool_calls]
        if hasattr(message, "tool_call_id") and message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id

        # Serialize to JSON for storage (handle complex types)
        def default_serializer(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        json_data = json.dumps(data, indent=2, default=default_serializer)

        # Create human-readable format
        text_parts = [
            f"Role: {message.role}",
            f"Timestamp: {timestamp}",
            f"MessageID: {message_id}",
        ]

        if message.name:
            text_parts.append(f"Name: {message.name}")

        # Handle content (can be string or list)
        content_str = ""
        if isinstance(message.content, str):
            content_str = message.content
        elif isinstance(message.content, list):
            # For multimodal content, extract text parts
            text_items = [item.get("text", "") for item in message.content if isinstance(item, dict) and "text" in item]
            content_str = " ".join(text_items)
        else:
            content_str = str(message.content)

        text_parts.append(f"Content: {content_str}")

        # Add separator and JSON
        text_parts.append("---")
        text_parts.append(json_data)

        return "\n".join(text_parts)

    def _deserialize_message(self, text: str) -> Optional[LLMMessage]:
        """
        Parse a stored message back into an LLMMessage object.

        Extracts the JSON portion after the '---' separator.
        """
        try:
            # Find the JSON portion after the separator
            if "---" in text:
                json_part = text.split("---", 1)[1].strip()
            else:
                json_part = text

            data = json.loads(json_part)

            # Reconstruct message based on role
            role = data["role"]
            content = data["content"]
            name = data.get("name")
            tool_calls = data.get("tool_calls")
            tool_call_id = data.get("tool_call_id")

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
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Log warning but don't fail
            print(f"Warning: Failed to deserialize message: {e}")
            return None

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        """
        Store a memory message by indexing it in the KnowledgeBase.

        The message is converted to a structured text format and indexed via the KB pipeline.
        """
        # Serialize the message
        serialized = self._serialize_message(message)

        # Create a unique message ID
        msg_id = f"memory_{self._message_counter}_{uuid.uuid4().hex[:8]}"

        async def _index_message():
            kb = await self._get_kb(agent, ctx)

            # Create a temporary file content
            content_bytes = serialized.encode("utf-8")

            # Write to filesystem using fsspec directly
            file_path = f"{agent.guild_id}/guild/memories/{msg_id}.txt"

            # Ensure directory exists
            dir_path = f"{agent.guild_id}/guild/memories"
            if self._filesystem and not self._filesystem.exists(dir_path):
                self._filesystem.makedirs(dir_path, exist_ok=True)

            # Write file
            if self._filesystem:
                with self._filesystem.open(file_path, "wb") as f:
                    f.write(content_bytes)

            # Create MediaLink pointing to this content
            media = MediaLink(
                id=msg_id,
                url=f"file:///{file_path}",
                name=f"{msg_id}.txt",
                mimetype="text/plain",
                metadata={"type": "memory", "role": message.role},
            )

            # Index via KB pipeline
            try:
                await kb.ingest_media([media])
            except Exception as e:
                print(f"Warning: Failed to index memory: {e}")

        # Run the async indexing
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            # No event loop running, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_index_message())
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        else:
            # Event loop exists, run in it
            asyncio.create_task(_index_message())

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
                # Extract text content from payload
                text_content = result.payload.get("text", "")
                if text_content:
                    msg = self._deserialize_message(text_content)
                    if msg:
                        recalled_messages.append(msg)

            return recalled_messages

        # Run the async search
        try:
            return asyncio.get_event_loop().run_until_complete(_search_memories())
        except RuntimeError:
            # If no event loop exists, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_search_memories())
            finally:
                loop.close()
