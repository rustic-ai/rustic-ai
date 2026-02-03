"""
Tests for the AggregatingAgent, specifically for the _processed_correlations race condition fix.

The fix (commit 67e646a) adds tracking of processed correlation IDs to prevent duplicate
outputs when multiple state updates arrive before cleanup is complete.
"""

from unittest.mock import MagicMock

from rustic_ai.core.agents.eip.aggregating_agent import (
    AggregatedMessages,
    AggregatingAgent,
    AggregatorConf,
    CountingAggregator,
    DictCollector,
    FormatCountAggregator,
    FormatWithCount,
    JsonataAggregator,
    ListCollector,
    PayloadWithFormat,
    TypeCollector,
)
from rustic_ai.core.utils.json_utils import JsonDict


class TestAggregatingAgentRaceCondition:
    """Tests specifically for the _processed_correlations race condition prevention.

    The race condition occurs when:
    1. Agent receives state update, correlation is complete
    2. Agent sends aggregated message
    3. Before state cleanup completes, another state update arrives
    4. Without _processed_correlations, agent would send duplicate message

    The fix tracks processed correlation IDs to skip duplicates.
    """

    def _create_mock_agent(self, aggregator_conf: AggregatorConf) -> AggregatingAgent:
        """Helper to create a mock agent with proper config setup."""
        agent = object.__new__(AggregatingAgent)
        # Set up the config attribute that __init__ expects
        agent.config = aggregator_conf
        agent.handled_formats = []
        agent.update_state = MagicMock()
        return agent

    def test_processed_correlations_initialized(self):
        """Test that _processed_correlations is initialized as an empty set."""
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=3),
        )
        agent = self._create_mock_agent(aggregator_conf)

        # Call __init__ manually
        agent.__init__()

        # Verify _processed_correlations is initialized
        assert hasattr(agent, "_processed_correlations")
        assert isinstance(agent._processed_correlations, set)
        assert len(agent._processed_correlations) == 0

    def test_skip_already_processed_correlation(self):
        """Test that on_state_updated skips correlation IDs that are already processed."""
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=2),
        )
        agent = self._create_mock_agent(aggregator_conf)
        agent.__init__()

        # Pre-populate with a processed correlation ID
        agent._processed_correlations.add("correlation_123")

        # Create mock context
        mock_ctx = MagicMock()
        mock_ctx.message = MagicMock()
        mock_ctx.message.message_history = []
        mock_ctx.send = MagicMock()
        mock_ctx.get_context = MagicMock(return_value={})

        # Create state with the already-processed correlation
        state: JsonDict = {
            "aggregations": {
                "correlation_123": [
                    {"type": "test", "data": {"value": 1}},
                    {"type": "test", "data": {"value": 2}},
                ]
            }
        }

        # Call on_state_updated
        agent.on_state_updated(state, mock_ctx)

        # Verify send was NOT called (correlation was skipped)
        mock_ctx.send.assert_not_called()

    def test_new_correlation_is_processed_and_tracked(self):
        """Test that a new correlation ID is processed and added to _processed_correlations."""
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=2),
            correlation_location=None,
        )
        agent = self._create_mock_agent(aggregator_conf)
        agent.__init__()

        # Ensure the correlation is not yet processed
        assert "new_correlation" not in agent._processed_correlations

        # Create mock context
        mock_ctx = MagicMock()
        mock_ctx.message = MagicMock()
        mock_ctx.message.message_history = []
        mock_ctx.send = MagicMock()
        mock_ctx.get_context = MagicMock(return_value={})
        mock_ctx.update_context = MagicMock()

        # Create state with a new correlation that meets the aggregation criteria
        state: JsonDict = {
            "aggregations": {
                "new_correlation": [
                    {"type": "test", "data": {"value": 1}},
                    {"type": "test", "data": {"value": 2}},
                ]
            }
        }

        # Call on_state_updated
        agent.on_state_updated(state, mock_ctx)

        # Verify send WAS called
        mock_ctx.send.assert_called_once()

        # Verify the correlation is now tracked
        assert "new_correlation" in agent._processed_correlations

    def test_second_state_update_does_not_resend(self):
        """Test that a second state update for the same correlation doesn't cause duplicate send.

        This is the core race condition test - simulating what happens when a second
        state update arrives before the cleanup from the first update completes.
        """
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=2),
            correlation_location=None,
        )
        agent = self._create_mock_agent(aggregator_conf)
        agent.__init__()

        mock_ctx = MagicMock()
        mock_ctx.message = MagicMock()
        mock_ctx.message.message_history = []
        mock_ctx.send = MagicMock()
        mock_ctx.get_context = MagicMock(return_value={})
        mock_ctx.update_context = MagicMock()

        state: JsonDict = {
            "aggregations": {
                "race_test": [
                    {"type": "test", "data": {"value": 1}},
                    {"type": "test", "data": {"value": 2}},
                ]
            }
        }

        # First call should process and send
        agent.on_state_updated(state, mock_ctx)
        assert mock_ctx.send.call_count == 1
        assert "race_test" in agent._processed_correlations

        # Second call (simulating race condition) should skip
        agent.on_state_updated(state, mock_ctx)
        assert mock_ctx.send.call_count == 1  # Still 1, not 2

    def test_different_correlations_are_independent(self):
        """Test that processing one correlation doesn't affect others."""
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=2),
            correlation_location=None,
        )
        agent = self._create_mock_agent(aggregator_conf)
        agent.__init__()

        mock_ctx = MagicMock()
        mock_ctx.message = MagicMock()
        mock_ctx.message.message_history = []
        mock_ctx.send = MagicMock()
        mock_ctx.get_context = MagicMock(return_value={})
        mock_ctx.update_context = MagicMock()

        # State with two correlations
        state: JsonDict = {
            "aggregations": {
                "corr_a": [
                    {"type": "test", "data": {"value": "a1"}},
                    {"type": "test", "data": {"value": "a2"}},
                ],
                "corr_b": [
                    {"type": "test", "data": {"value": "b1"}},
                    {"type": "test", "data": {"value": "b2"}},
                ],
            }
        }

        # Process first time - both should be sent
        agent.on_state_updated(state, mock_ctx)
        assert mock_ctx.send.call_count == 2
        assert "corr_a" in agent._processed_correlations
        assert "corr_b" in agent._processed_correlations

        # Process again - neither should be resent
        agent.on_state_updated(state, mock_ctx)
        assert mock_ctx.send.call_count == 2  # Still 2

    def test_incomplete_aggregation_not_tracked(self):
        """Test that correlations that don't meet criteria are not tracked."""
        aggregator_conf = AggregatorConf(
            collector=ListCollector(),
            aggregator=CountingAggregator(count=3),  # Needs 3 messages
            correlation_location=None,
        )
        agent = self._create_mock_agent(aggregator_conf)
        agent.__init__()

        mock_ctx = MagicMock()
        mock_ctx.message = MagicMock()
        mock_ctx.message.message_history = []
        mock_ctx.send = MagicMock()
        mock_ctx.get_context = MagicMock(return_value={})

        # State with only 2 messages (needs 3)
        state: JsonDict = {
            "aggregations": {
                "incomplete": [
                    {"type": "test", "data": {"value": 1}},
                    {"type": "test", "data": {"value": 2}},
                ]
            }
        }

        agent.on_state_updated(state, mock_ctx)

        # Verify send was NOT called (criteria not met)
        mock_ctx.send.assert_not_called()

        # Verify the correlation is NOT tracked (incomplete)
        assert "incomplete" not in agent._processed_correlations


class TestCollectorStrategies:
    """Tests for different collector strategies in aggregation."""

    def test_list_collector_get_messages(self):
        """Test ListCollector.get_messages returns list directly."""
        collector = ListCollector()
        state = [{"type": "a", "data": {}}, {"type": "b", "data": {}}]
        messages = collector.get_messages(state)
        assert len(messages) == 2

    def test_list_collector_get_state_operations(self):
        """Test ListCollector generates correct JSON Patch operations."""
        collector = ListCollector()
        payload = PayloadWithFormat(type="test", data={"value": 1})
        operations = collector.get_state_operations("corr_123", payload)
        assert len(operations) == 1
        assert operations[0]["op"] == "add"
        assert operations[0]["path"] == "/-"

    def test_dict_collector_get_messages(self):
        """Test DictCollector.get_messages extracts values from dict."""
        collector = DictCollector(key_field="id")
        state = {"key1": {"type": "a", "data": {}}, "key2": {"type": "b", "data": {}}}
        messages = collector.get_messages(state)
        assert len(messages) == 2

    def test_dict_collector_get_state_operations(self):
        """Test DictCollector generates correct JSON Patch operations with key extraction."""
        collector = DictCollector(key_field="id")
        payload = PayloadWithFormat(type="test", data={"id": "item_123", "value": 1})
        operations = collector.get_state_operations("corr_123", payload)
        assert len(operations) == 1
        assert operations[0]["op"] == "add"
        assert operations[0]["path"] == "/item_123"

    def test_type_collector_get_messages(self):
        """Test TypeCollector.get_messages flattens type-grouped messages."""
        collector = TypeCollector()
        state = {
            "type_a": [{"type": "a", "data": {"v": 1}}, {"type": "a", "data": {"v": 2}}],
            "type_b": [{"type": "b", "data": {"v": 3}}],
        }
        messages = collector.get_messages(state)
        assert len(messages) == 3

    def test_type_collector_get_state_operations(self):
        """Test TypeCollector generates correct JSON Patch operations grouped by type."""
        collector = TypeCollector()
        payload = PayloadWithFormat(type="my_type", data={"value": 1})
        operations = collector.get_state_operations("corr_123", payload)
        assert len(operations) == 1
        assert operations[0]["op"] == "add"
        assert operations[0]["path"] == "/my_type/-"


class TestAggregatorStrategies:
    """Tests for different aggregator strategies."""

    def test_counting_aggregator_met(self):
        """Test CountingAggregator returns True when count is met."""
        aggregator = CountingAggregator(count=3)
        messages = [{"type": "t", "data": {}}, {"type": "t", "data": {}}, {"type": "t", "data": {}}]
        assert aggregator.evaluate("corr", messages) is True

    def test_counting_aggregator_not_met(self):
        """Test CountingAggregator returns False when count is not met."""
        aggregator = CountingAggregator(count=3)
        messages = [{"type": "t", "data": {}}, {"type": "t", "data": {}}]
        assert aggregator.evaluate("corr", messages) is False

    def test_counting_aggregator_exceeded(self):
        """Test CountingAggregator returns True when count is exceeded."""
        aggregator = CountingAggregator(count=2)
        messages = [{"type": "t", "data": {}}, {"type": "t", "data": {}}, {"type": "t", "data": {}}]
        assert aggregator.evaluate("corr", messages) is True

    def test_jsonata_aggregator_simple_count(self):
        """Test JsonataAggregator with simple count expression."""
        aggregator = JsonataAggregator(expression="count >= 2")
        messages = [{"type": "t", "data": {}}, {"type": "t", "data": {}}]
        assert aggregator.evaluate("corr", messages) is True

    def test_jsonata_aggregator_not_met(self):
        """Test JsonataAggregator returns False when expression not satisfied."""
        aggregator = JsonataAggregator(expression="count >= 5")
        messages = [{"type": "t", "data": {}}, {"type": "t", "data": {}}]
        assert aggregator.evaluate("corr", messages) is False

    def test_format_count_aggregator_met(self):
        """Test FormatCountAggregator returns True when all format counts are met."""
        aggregator = FormatCountAggregator(
            formats=[
                FormatWithCount(format="type_a", count=2),
                FormatWithCount(format="type_b", count=1),
            ]
        )
        messages = [
            {"format": "type_a", "data": {}},
            {"format": "type_a", "data": {}},
            {"format": "type_b", "data": {}},
        ]
        assert aggregator.evaluate("corr", messages) is True

    def test_format_count_aggregator_not_met(self):
        """Test FormatCountAggregator returns False when format counts not met."""
        aggregator = FormatCountAggregator(
            formats=[
                FormatWithCount(format="type_a", count=2),
                FormatWithCount(format="type_b", count=1),
            ]
        )
        messages = [
            {"format": "type_a", "data": {}},  # Only 1 of type_a, needs 2
            {"format": "type_b", "data": {}},
        ]
        assert aggregator.evaluate("corr", messages) is False


class TestAggregatedMessagesModel:
    """Tests for the AggregatedMessages Pydantic model."""

    def test_aggregated_messages_creation(self):
        """Test creating an AggregatedMessages instance."""
        payloads = [
            PayloadWithFormat(type="type_a", data={"value": 1}),
            PayloadWithFormat(type="type_b", data={"value": 2}),
        ]
        aggregated = AggregatedMessages(correlation_id="corr_123", messages=payloads)

        assert aggregated.correlation_id == "corr_123"
        assert len(aggregated.messages) == 2
        assert aggregated.messages[0].type == "type_a"
        assert aggregated.messages[1].data == {"value": 2}

    def test_payload_with_format_model(self):
        """Test PayloadWithFormat model."""
        payload = PayloadWithFormat(type="my_type", data={"key": "value", "num": 42})
        assert payload.type == "my_type"
        assert payload.data["key"] == "value"
        assert payload.data["num"] == 42
