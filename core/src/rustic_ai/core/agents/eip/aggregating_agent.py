from abc import abstractmethod
from enum import Enum
import logging
from typing import Dict, Literal, Optional, Union

from jsonata import Jsonata
from pydantic import BaseModel, Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.messaging.core.message import MessageConstants
from rustic_ai.core.state import StateUpdateFormat
from rustic_ai.core.state.models import StateUpdateResponse
from rustic_ai.core.utils.json_utils import JsonDict, JsonUtils


class CorrelationLocation(str, Enum):
    SESSION = "session"
    PAYLOAD = "payload"


class PayloadWithFormat(BaseModel):
    """Model for the payload with type information."""

    type: str
    """The type of the payload."""

    data: JsonDict
    """The actual payload data."""


# Collector Classes
class BaseCollector(BaseModel):
    """Base class for different message collection strategies."""

    collector_type: str  # Discriminator field

    @abstractmethod
    def get_state_operations(self, correlation_id: str, payload_with_format: PayloadWithFormat) -> list[JsonDict]:
        """
        Generate JSON Patch operations to collect a new message into the state.

        Args:
            correlation_id: The correlation identifier
            new_message: New message to collect

        Returns:
            List of JSON Patch operations to update the state
        """
        pass

    @abstractmethod
    def get_messages(self, state: JsonDict) -> list[JsonDict]:
        """Extract messages from state for aggregation evaluation."""
        pass


class ListCollector(BaseCollector):
    """Collects messages as a simple list (current behavior)."""

    collector_type: Literal["list"] = "list"  # Discriminator value

    def get_state_operations(self, correlation_id: str, payload_with_format: PayloadWithFormat) -> list[JsonDict]:
        # JSON Patch add with /- automatically handles initialization and appending
        return [{"op": "add", "path": "/-", "value": payload_with_format.model_dump()}]

    def get_messages(self, state: JsonDict) -> list[JsonDict]:
        # For ListCollector, state is directly the list of messages
        return state if isinstance(state, list) else []


class DictCollector(BaseCollector):
    """Collects messages in a dictionary using a field as key (prevents duplicates)."""

    collector_type: Literal["dict"] = "dict"  # Discriminator value
    key_field: str = "id"  # Field to use as dictionary key

    def get_state_operations(self, correlation_id: str, payload_with_format: PayloadWithFormat) -> list[JsonDict]:
        try:
            key = JsonUtils.read_from_path(payload_with_format.data, self.key_field)
        except Exception as e:
            logging.warning(f"Failed to extract key from field '{self.key_field}': {e}. Using message hash.")
            key = str(hash(str(payload_with_format.data)))

        key = str(key)

        # JSON Patch add automatically handles initialization and key assignment
        return [{"op": "add", "path": f"/{key}", "value": payload_with_format.model_dump()}]

    def get_messages(self, state: JsonDict) -> list[JsonDict]:
        # For DictCollector, state is directly the dictionary of messages
        if isinstance(state, dict):
            return list(state.values())  # type: ignore
        return []


class TypeCollector(BaseCollector):
    """Collects messages grouped by type/format."""

    collector_type: Literal["type"] = "type"  # Discriminator value

    def get_state_operations(self, correlation_id: str, payload_with_format: PayloadWithFormat) -> list[JsonDict]:
        msg_type = payload_with_format.type

        # JSON Patch add with /- automatically handles initialization and appending
        return [
            {
                "op": "add",
                "path": f"/{msg_type}/-",
                "value": payload_with_format.model_dump(),
            }
        ]

    def get_messages(self, state: JsonDict) -> list[JsonDict]:
        # For TypeCollector, state is a dict of {type: [messages]}
        # Flatten all types into single list for aggregation
        if isinstance(state, dict):
            messages = []
            for type_messages in state.values():
                if isinstance(type_messages, list):
                    messages.extend(type_messages)
            return messages
        return []


# Aggregator Classes


class BaseAggregator(BaseModel):
    """Aggregator base that evaluates the currently gathered messages and aggregates them."""

    aggregation_check: str

    @abstractmethod
    def evaluate(self, correlation_id: str, messages: list[JsonDict]) -> bool:
        """Evaluate if aggregation is complete for the given messages."""
        pass


class CountingAggregator(BaseAggregator):
    """Aggregator that determines completion based on message count."""

    aggregation_check: Literal["count"] = "count"

    count: int

    def evaluate(self, correlation_id: str, messages: list[JsonDict]) -> bool:
        return len(messages) >= self.count


class JsonataAggregator(BaseAggregator):
    """Aggregator that determines completion based on JSONata expression.

    The expression has access to:
    - messages: List of collected messages
    - correlation_id: The correlation identifier
    - count: Number of messages collected
    - message_types: List of message types/formats

    Example expressions:
    - "count >= 3" - Wait for at least 3 messages
    - "$all(messages, $exists($.status) and $.status = 'complete')" - All messages have status 'complete'
    - "messages[type='error'] | $count($) = 0" - No error messages present
    - "$count(message_types[$distinct($)]) = 3" - Messages from exactly 3 different types
    """

    aggregation_check: Literal["jsonata"] = "jsonata"

    expression: str

    def evaluate(self, correlation_id: str, messages: list[JsonDict]) -> bool:
        """Evaluate the messages against the JSONata expression."""
        try:
            jsonata = Jsonata(self.expression)
            context = {
                "messages": messages,
                "correlation_id": correlation_id,
                "count": len(messages),
                "message_types": [msg.get("type") for msg in messages if "type" in msg],
            }
            result = jsonata.evaluate(context)
            if result is None:
                return False
            if isinstance(result, bool):
                return result
            if isinstance(result, (int, float)):
                return bool(result)
            if isinstance(result, str):
                return bool(result.strip())

            return False
        except Exception as e:
            logging.error(f"Error evaluating JSONata expression: {e}")
            return False


class FormatWithCount(BaseModel):
    format: str
    count: int = Field(default=1)


class FormatCountAggregator(BaseAggregator):
    """Aggregator that determines completion based on message format count."""

    aggregation_check: Literal["format_count"] = "format_count"

    formats: list[FormatWithCount]

    def evaluate(self, correlation_id: str, messages: list[JsonDict]) -> bool:
        """Evaluate the messages against the format count."""
        format_counts = {fmt.format: fmt.count for fmt in self.formats}
        actual_counts: Dict[str, int] = {}

        for message in messages:
            fmt = message.get("format")
            if fmt in format_counts:
                actual_counts[fmt] = actual_counts.get(fmt, 0) + 1

        return all(actual_counts.get(fmt, 0) >= count for fmt, count in format_counts.items())


class AggregatorConf(BaseAgentProps):
    """Configuration for the Aggregating Agent."""

    correlation_location: Optional[CorrelationLocation] = Field(default=CorrelationLocation.PAYLOAD)
    """The location of the correlation ID in the message."""

    correlation_id_path: Optional[str] = Field(default=None)
    """Path to the correlation ID in the message payload.
    If it is none, the thread_id from the message will be used."""

    collector: Union[ListCollector, DictCollector, TypeCollector] = Field(
        default_factory=lambda: ListCollector(), discriminator="collector_type"
    )
    """The collector strategy for gathering messages."""

    aggregator: Union[CountingAggregator, JsonataAggregator, FormatCountAggregator] = Field(
        default_factory=lambda: CountingAggregator(count=3), discriminator="aggregation_check"
    )
    """The aggregator to use for message aggregation."""


class AggregatedMessages(BaseModel):
    """Model for the aggregated messages."""

    correlation_id: str
    messages: list[PayloadWithFormat]


class AggregatingAgent(Agent[AggregatorConf]):
    """An agent that aggregates messages based on a correlation ID."""

    def __init__(self):
        self.handled_formats = [MessageConstants.RAW_JSON_FORMAT]

        self.correlation_location = self.config.correlation_location

        # Set the correlation ID path if provided
        self.path: Optional[str] = None
        if self.config.correlation_id_path:
            self.path = self.config.correlation_id_path

        self.collector = self.config.collector
        self.aggregator = self.config.aggregator
        self._route_to_default_topic = True  # Route messages to default topic if no specific routing is defined

    @agent.processor(JsonDict)
    def collect_message(self, ctx: ProcessContext[JsonDict]) -> None:
        """Collects a message using the configured collection strategy."""

        logging.debug("Collecting message ---")

        correlation_id = str(ctx.message.thread[-1])

        if self.path:
            try:
                if self.correlation_location == CorrelationLocation.PAYLOAD:
                    correlation_id = str(JsonUtils.read_from_path(ctx.message.payload, self.path))
                else:
                    correlation_id = str(JsonUtils.read_from_path(ctx.get_context(), self.path))
            except Exception as e:
                logging.warning(f"Failed to extract correlation ID from path '{self.path}': {e}. Using thread ID.")
                correlation_id = str(ctx.message.thread[-1])

        logging.debug(f"Correlation ID: {correlation_id}")
        logging.debug(f"Collecting message: {ctx.message.payload}")

        payload_with_format = PayloadWithFormat(type=ctx.message.format, data=ctx.message.payload)

        # Use collector to generate state operations
        operations = self.collector.get_state_operations(correlation_id, payload_with_format)

        self.update_state(  # type: ignore[no-untyped-call]
            ctx,
            update_format=StateUpdateFormat.JSON_PATCH,
            update={"operations": operations},
            update_path=f'aggregations["{correlation_id}"]',
        )

    def on_state_updated(self, state: JsonDict, ctx: ProcessContext[StateUpdateResponse]) -> None:
        """
        Handle state updates. Override from StateRefresherMixin.
        This method is called whenever the agent's state is updated.
        """

        logging.debug(f"Aggregation State updated: {state}")

        aggregations: Dict[str, JsonDict] = state.get("aggregations", {})  # type: ignore
        for correlation_id, correlation_state in aggregations.items():
            # Use collector to extract messages for evaluation (handles both list and dict states)
            messages = self.collector.get_messages(correlation_state)

            if messages and self.aggregator.evaluate(correlation_id, messages):
                # If the aggregator determines completion, we can process the aggregated messages
                logging.info(f"Aggregation complete for correlation_id={correlation_id}, message_count={len(messages)}")

                payloads = [PayloadWithFormat.model_validate(m) for m in messages]

                aggregated_messages = AggregatedMessages(correlation_id=correlation_id, messages=payloads)

                if self.correlation_location == CorrelationLocation.SESSION:
                    if not self.path:
                        self.path = "correlation_id"
                    context: JsonDict = {}
                    JsonUtils.update_at_path(context, self.path, correlation_id)
                    ctx.update_context(context)

                ctx.message.message_history = []

                ctx.send(
                    payload=aggregated_messages,
                )

                # Clean up completed aggregation
                self.update_state(  # type: ignore[no-untyped-call]
                    ctx,
                    update_format=StateUpdateFormat.JSON_PATCH,
                    update={"operations": [{"op": "remove", "path": "/"}]},
                    update_path=f'aggregations["{correlation_id}"]',
                )
