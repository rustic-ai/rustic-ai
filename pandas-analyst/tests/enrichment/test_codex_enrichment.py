"""
Unit tests for the Codex Enrichment System.

Tests cover:
- DatasetLoadedEmitter: ToolCallWrapper that emits events
- EnrichmentContextPreprocessor: RequestPreprocessor that injects context
- DatasetEnrichmentMetadata: Pydantic model serialization
"""

from unittest.mock import Mock

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    SystemMessage,
    UserMessage,
)
from rustic_ai.llm_agent.plugins.tool_call_wrapper import ToolCallResult
from rustic_ai.pandas_analyst.enrichment import (
    DatasetEnrichmentMetadata,
    DatasetLoadedEmitter,
    DatasetLoadedEvent,
    EnrichmentContextPreprocessor,
)


class TestDatasetLoadedEmitter:
    """Tests for the ToolCallWrapper that emits events."""

    def test_emits_event_on_successful_load(self):
        """Verify event is emitted after successful load_file."""
        emitter = DatasetLoadedEmitter(sample_rows=3)

        # Mock agent with toolset and analyzer
        mock_agent = Mock()
        mock_analyzer = Mock()
        mock_analyzer.get_dataset_summary.return_value = Mock(
            num_rows=100, num_columns=5, column_names=["a", "b", "c", "d", "e"]
        )
        mock_analyzer.get_schema.return_value = Mock(
            dataschema={"a": "int64", "b": "object", "c": "float64", "d": "bool", "e": "datetime64"}
        )
        mock_analyzer.preview_dataset.return_value = Mock(
            columns=["a", "b"],
            data=[[1, "x"], [2, "y"], [3, "z"]]
        )
        mock_agent.config = Mock()
        mock_agent.config.toolset = Mock()
        mock_agent.config.toolset._analyzer = mock_analyzer

        mock_ctx = Mock()
        mock_input = Mock(filename="test.csv", dataset_name=None)

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=mock_ctx,
            tool_name="load_file",
            tool_input=mock_input,
            tool_output='{"name": "test", "rows": 100}',
        )

        assert isinstance(result, ToolCallResult)
        assert result.messages is not None
        assert len(result.messages) == 1
        assert isinstance(result.messages[0], DatasetLoadedEvent)
        assert result.messages[0].dataset_name == "test"
        assert result.messages[0].row_count == 100
        assert result.messages[0].column_count == 5

    def test_extracts_name_from_input_dataset_name(self):
        """Verify dataset name is extracted from input when provided."""
        emitter = DatasetLoadedEmitter()

        mock_agent = Mock()
        mock_analyzer = Mock()
        mock_analyzer.get_dataset_summary.return_value = Mock(num_rows=50, num_columns=3, column_names=["x", "y", "z"])
        mock_analyzer.get_schema.return_value = Mock(dataschema={"x": "int64"})
        mock_analyzer.preview_dataset.return_value = Mock(columns=["x"], data=[[1]])
        mock_agent.config.toolset._analyzer = mock_analyzer

        mock_input = Mock(filename="data.csv", dataset_name="my_dataset")

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=Mock(),
            tool_name="load_file",
            tool_input=mock_input,
            tool_output='{"status": "loaded"}',
        )

        assert result.messages[0].dataset_name == "my_dataset"

    def test_no_event_on_failed_load(self):
        """Verify no event is emitted when load fails."""
        emitter = DatasetLoadedEmitter()
        mock_agent = Mock()
        mock_ctx = Mock()
        mock_input = Mock(filename="test.csv")

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=mock_ctx,
            tool_name="load_file",
            tool_input=mock_input,
            tool_output="Error: File not found",
        )

        assert result.messages is None
        assert result.output == "Error: File not found"

    def test_ignores_other_tools(self):
        """Verify wrapper ignores non-load_file tools."""
        emitter = DatasetLoadedEmitter()
        mock_agent = Mock()
        mock_ctx = Mock()
        mock_input = Mock()

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=mock_ctx,
            tool_name="query_dataset",
            tool_input=mock_input,
            tool_output="query result",
        )

        assert result.messages is None
        assert result.output == "query result"

    def test_preprocess_passes_through(self):
        """Verify preprocess returns input unchanged."""
        emitter = DatasetLoadedEmitter()
        mock_input = Mock()

        result = emitter.preprocess(
            agent=Mock(),
            ctx=Mock(),
            tool_name="load_file",
            tool_input=mock_input,
        )

        assert result is mock_input

    def test_handles_missing_toolset(self):
        """Verify graceful handling when toolset is missing."""
        emitter = DatasetLoadedEmitter()
        mock_agent = Mock()
        mock_agent.config = Mock(spec=[])  # No toolset attribute

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=Mock(),
            tool_name="load_file",
            tool_input=Mock(filename="test.csv"),
            tool_output='{"status": "loaded"}',
        )

        assert result.messages is None
        assert result.output == '{"status": "loaded"}'

    def test_handles_missing_analyzer(self):
        """Verify graceful handling when analyzer is missing."""
        emitter = DatasetLoadedEmitter()
        mock_agent = Mock()
        mock_agent.config.toolset._analyzer = None

        result = emitter.postprocess(
            agent=mock_agent,
            ctx=Mock(),
            tool_name="load_file",
            tool_input=Mock(filename="test.csv"),
            tool_output='{"status": "loaded"}',
        )

        assert result.messages is None


class TestEnrichmentContextPreprocessor:
    """Tests for the preprocessor that injects context."""

    def test_injects_context_when_enrichments_exist(self):
        """Verify enrichment context is added to prompts."""
        preprocessor = EnrichmentContextPreprocessor()

        mock_agent = Mock()
        mock_agent.get_guild_state.return_value = {
            "codex_enrichment": {
                "datasets": {
                    "test_data": {
                        "dataset_name": "test_data",
                        "table_purpose": "Test data for analysis",
                        "table_description": "Contains test records",
                        "grain_description": "One row per test",
                        "primary_key_candidates": ["id"],
                        "columns": [
                            {
                                "name": "id",
                                "description": "Unique identifier",
                                "semantic_type": "identifier",
                                "uniqueness": "unique",
                                "is_primary_key_candidate": True,
                            }
                        ],
                        "row_count": 100,
                        "column_count": 5,
                        "enrichment_timestamp": "2024-01-01T00:00:00",
                    }
                }
            }
        }

        request = ChatCompletionRequest(messages=[UserMessage(content="Analyze the data")])

        result = preprocessor.preprocess(
            agent=mock_agent,
            ctx=Mock(),
            request=request,
            llm=Mock(),
        )

        # Should have added a system message
        assert len(result.messages) == 2
        assert isinstance(result.messages[0], SystemMessage)
        assert "test_data" in result.messages[0].content
        assert "Test data for analysis" in result.messages[0].content
        assert "One row per test" in result.messages[0].content

    def test_passthrough_when_no_enrichments(self):
        """Verify request passes through when guild state is empty."""
        preprocessor = EnrichmentContextPreprocessor()

        mock_agent = Mock()
        mock_agent.get_guild_state.return_value = {}

        request = ChatCompletionRequest(messages=[UserMessage(content="Analyze the data")])

        result = preprocessor.preprocess(
            agent=mock_agent,
            ctx=Mock(),
            request=request,
            llm=Mock(),
        )

        # Should be unchanged
        assert len(result.messages) == 1
        assert isinstance(result.messages[0], UserMessage)

    def test_passthrough_when_no_guild_state(self):
        """Verify request passes through when get_guild_state returns None."""
        preprocessor = EnrichmentContextPreprocessor()

        mock_agent = Mock()
        mock_agent.get_guild_state.return_value = None

        request = ChatCompletionRequest(messages=[UserMessage(content="Analyze the data")])

        result = preprocessor.preprocess(
            agent=mock_agent,
            ctx=Mock(),
            request=request,
            llm=Mock(),
        )

        assert len(result.messages) == 1

    def test_inserts_after_existing_system_messages(self):
        """Verify enrichment context is inserted after existing system messages."""
        preprocessor = EnrichmentContextPreprocessor()

        mock_agent = Mock()
        mock_agent.get_guild_state.return_value = {
            "codex_enrichment": {
                "datasets": {
                    "sales": {
                        "dataset_name": "sales",
                        "table_purpose": "Sales records",
                        "table_description": "Sales transactions",
                        "grain_description": "One row per sale",
                        "row_count": 1000,
                        "column_count": 10,
                    }
                }
            }
        }

        request = ChatCompletionRequest(
            messages=[
                SystemMessage(content="You are a helpful assistant."),
                UserMessage(content="What is the total?"),
            ]
        )

        result = preprocessor.preprocess(
            agent=mock_agent,
            ctx=Mock(),
            request=request,
            llm=Mock(),
        )

        assert len(result.messages) == 3
        # Original system message first
        assert result.messages[0].content == "You are a helpful assistant."
        # Enrichment context second
        assert "sales" in result.messages[1].content
        # User message last
        assert result.messages[2].content == "What is the total?"

    def test_handles_invalid_enrichment_data(self):
        """Verify invalid enrichment entries are skipped gracefully."""
        preprocessor = EnrichmentContextPreprocessor()

        mock_agent = Mock()
        mock_agent.get_guild_state.return_value = {
            "codex_enrichment": {
                "datasets": {
                    "valid_data": {
                        "dataset_name": "valid_data",
                        "table_purpose": "Valid dataset",
                        "table_description": "Description",
                        "grain_description": "One row per item",
                        "row_count": 50,
                        "column_count": 3,
                    },
                    "invalid_data": {
                        # Missing required fields
                        "some_field": "value"
                    },
                }
            }
        }

        request = ChatCompletionRequest(messages=[UserMessage(content="Query")])

        result = preprocessor.preprocess(
            agent=mock_agent,
            ctx=Mock(),
            request=request,
            llm=Mock(),
        )

        # Should have added context for valid_data only
        assert len(result.messages) == 2
        assert "valid_data" in result.messages[0].content
        assert "invalid_data" not in result.messages[0].content


class TestDatasetEnrichmentMetadata:
    """Tests for the Pydantic models."""

    def test_model_serialization(self):
        """Verify model can be serialized to/from JSON."""
        metadata = DatasetEnrichmentMetadata(
            dataset_name="test",
            table_purpose="Test purpose",
            table_description="Test description",
            grain_description="One row per test",
            row_count=100,
            column_count=5,
        )

        json_str = metadata.model_dump_json()
        restored = DatasetEnrichmentMetadata.model_validate_json(json_str)

        assert restored.dataset_name == "test"
        assert restored.table_purpose == "Test purpose"
        assert restored.grain_description == "One row per test"
        assert restored.row_count == 100

    def test_default_values(self):
        """Verify default values are applied correctly."""
        metadata = DatasetEnrichmentMetadata(
            dataset_name="minimal",
            table_purpose="Purpose",
            table_description="Description",
            grain_description="Grain",
            row_count=10,
            column_count=2,
        )

        assert metadata.primary_key_candidates == []
        assert metadata.columns == []
        assert metadata.freshness_indicators == {}
        assert metadata.recommended_usage == []
        assert metadata.when_to_use == ""
        assert metadata.limitations == []

    def test_full_model_with_columns(self):
        """Verify model with all fields populated."""
        from rustic_ai.pandas_analyst.enrichment import ColumnSemantics

        metadata = DatasetEnrichmentMetadata(
            dataset_name="orders",
            table_purpose="Track customer orders",
            table_description="Complete order records",
            grain_description="One row per order",
            primary_key_candidates=["order_id"],
            columns=[
                ColumnSemantics(
                    name="order_id",
                    description="Unique order identifier",
                    semantic_type="identifier",
                    uniqueness="unique",
                    is_primary_key_candidate=True,
                ),
                ColumnSemantics(
                    name="amount",
                    description="Order total",
                    semantic_type="measure",
                ),
            ],
            row_count=5000,
            column_count=15,
            freshness_indicators={"date_range": "2023-01-01 to 2024-12-31"},
            recommended_usage=["Revenue analysis", "Customer segmentation"],
            when_to_use="For order-level analysis",
            limitations=["Does not include returns"],
        )

        assert len(metadata.columns) == 2
        assert metadata.columns[0].is_primary_key_candidate is True
        assert "order_id" in metadata.primary_key_candidates


class TestDatasetLoadedEvent:
    """Tests for the DatasetLoadedEvent model."""

    def test_event_creation(self):
        """Verify event can be created with required fields."""
        event = DatasetLoadedEvent(
            dataset_name="test_dataset",
            row_count=100,
            column_count=5,
            columns=["a", "b", "c", "d", "e"],
            column_schema={"a": "int64", "b": "object"},
            sample_data=[{"a": 1, "b": "x"}],
            load_summary="Loaded successfully",
        )

        assert event.dataset_name == "test_dataset"
        assert event.row_count == 100
        assert len(event.columns) == 5

    def test_event_serialization(self):
        """Verify event can be serialized to/from JSON."""
        event = DatasetLoadedEvent(
            dataset_name="sales",
            row_count=1000,
            column_count=10,
            columns=["id", "amount", "date"],
            column_schema={"id": "int64", "amount": "float64", "date": "datetime64"},
            sample_data=[{"id": 1, "amount": 99.99, "date": "2024-01-01"}],
            load_summary="Loaded 1000 rows",
        )

        json_str = event.model_dump_json()
        restored = DatasetLoadedEvent.model_validate_json(json_str)

        assert restored.dataset_name == "sales"
        assert restored.row_count == 1000
        assert len(restored.sample_data) == 1
