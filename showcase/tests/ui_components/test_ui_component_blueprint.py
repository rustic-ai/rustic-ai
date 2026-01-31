import time

from rustic_ai.core import GuildTopics
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.testutils.ui_component_agent import UiComponentAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.ui_protocol.types import (
    AudioFormat,
    CalendarFormat,
    CanvasFormat,
    CodeFormat,
    FilesWithTextFormat,
    FormFormat,
    ImageFormat,
    LocationFormat,
    MermaidFormat,
    PlotlyGraphFormat,
    QuestionFormat,
    TableFormat,
    TextFormat,
    UpdateType,
    VegaLiteFormat,
    VideoFormat,
    WeatherFormat,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class TestUiComponentBlueprint:

    def test_ui_component_agent_sends_formats(self, org_id):
        """Test that UiComponentAgent sends messages correctly."""

        # Build guild with UiComponentAgent using simple in-memory messaging
        builder = GuildBuilder(
            guild_name="UI Components Test Guild", guild_description="Test guild for UI component messages"
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add UI component agent
        ui_component_agent = (
            AgentBuilder(UiComponentAgent)
            .set_id("ui_component_agent_1")
            .set_name("UI Component Demo Agent")
            .set_description("UI Component Demo Agent")
            .build_spec()
        )

        builder.add_agent_spec(ui_component_agent)
        guild = builder.launch(org_id)

        # Add probe agent to capture messages
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.DEFAULT_TOPICS[0])
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send test message to trigger UI component responses
        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"test_message": "Hello UI Components!"})

        # Allow time for asynchronous message delivery
        time.sleep(1.0)

        messages = probe_agent.get_messages()

        # Expected: TextFormat, MarkdownFormat, CanvasFormat(x2), FilesWithTextFormat,
        # QuestionFormat, FormFormat, CodeFormat, CalendarFormat, WeatherFormat,
        # LocationFormat, ImageFormat, MermaidFormat, PlotlyGraphFormat,
        # VegaLiteFormat, TableFormat, PerspectiveFormat, AudioFormat, VideoFormat, ChatCompletionResponse
        # updateTextFormat(2)
        assert len(messages) == 22, f"Expected 22 messages, got {len(messages)}"

        # Helper function to get messages by format
        def get_messages_by_format(format_class):
            format_name = get_qualified_class_name(format_class)
            return [msg for msg in messages if msg.format == format_name]

        def get_messages_by_format_name(format_name):
            return [msg for msg in messages if msg.format == format_name]

        # Verify TextFormat message
        text_messages = get_messages_by_format(TextFormat)
        assert len(text_messages) == 1
        text_payload = text_messages[0].payload
        assert text_payload["text"] == "This is a text message example"
        assert text_payload["title"] == "Text format example"

        # Verify MarkdownFormat message (custom format)
        markdown_messages = get_messages_by_format_name("MarkdownFormat")
        assert len(markdown_messages) == 1
        markdown_payload = markdown_messages[0].payload
        assert "# Welcome to the Project" in markdown_payload["text"]
        assert markdown_payload["title"] == "Project Overview"

        # Verify CanvasFormat messages
        canvas_messages = get_messages_by_format(CanvasFormat)
        assert len(canvas_messages) == 2

        # Canvas Markdown
        canvas_md = next(msg for msg in canvas_messages if msg.payload["component"] == "MarkdownFormat")
        assert canvas_md.payload["title"] == "Canvas Markdown Example"
        assert "# Canvas Component" in canvas_md.payload["text"]

        # Canvas Image
        canvas_img = next(
            msg for msg in canvas_messages if msg.payload["component"] == get_qualified_class_name(ImageFormat)
        )
        assert canvas_img.payload["title"] == "Canvas Image Example"
        assert canvas_img.payload["mediaLink"]["url"] == "http://localhost:3000/640e5f0fb14b6075ead8.png"

        # Verify FilesWithTextFormat message
        files_messages = get_messages_by_format(FilesWithTextFormat)
        assert len(files_messages) == 1
        files_payload = files_messages[0].payload
        assert len(files_payload["files"]) == 1
        assert files_payload["files"][0]["mediaLink"]["name"] == "logo.png"
        assert files_payload["files"][0]["mediaLink"]["url"] == "http://localhost:3000/640e5f0fb14b6075ead8.png"

        # Verify QuestionFormat message
        question_messages = get_messages_by_format(QuestionFormat)
        assert len(question_messages) == 1
        question_payload = question_messages[0].payload
        assert question_payload["options"] == ["Option A", "Option B", "Option C"]
        assert question_payload["title"] == "Survey Question"

        # Verify FormFormat message
        form_messages = get_messages_by_format(FormFormat)
        assert len(form_messages) == 1
        form_payload = form_messages[0].payload
        assert "schema" in form_payload
        assert form_payload["title"] == "Login Form"

        # Verify CodeFormat message
        code_messages = get_messages_by_format(CodeFormat)
        assert len(code_messages) == 1
        code_payload = code_messages[0].payload
        assert "def hello_world():" in code_payload["code"]
        assert code_payload["language"] == "Python"

        # Verify CalendarFormat message
        calendar_messages = get_messages_by_format(CalendarFormat)
        assert len(calendar_messages) == 1
        calendar_payload = calendar_messages[0].payload
        assert len(calendar_payload["events"]) == 2
        assert calendar_payload["title"] == "Weekly Schedule"

        # Verify WeatherFormat message
        weather_messages = get_messages_by_format(WeatherFormat)
        assert len(weather_messages) == 1
        weather_payload = weather_messages[0].payload
        assert len(weather_payload["weather"]) == 5
        assert weather_payload["location"] == "San Francisco, CA"

        # Verify LocationFormat message
        location_messages = get_messages_by_format(LocationFormat)
        assert len(location_messages) == 1
        location_payload = location_messages[0].payload
        assert location_payload["longitude"] == -122.4194
        assert location_payload["latitude"] == 37.7749
        assert location_payload["title"] == "San Francisco Office"

        # Verify ImageFormat message
        image_messages = get_messages_by_format(ImageFormat)
        assert len(image_messages) == 1
        image_payload = image_messages[0].payload
        assert image_payload["src"] == "http://localhost:3000/640e5f0fb14b6075ead8.png"
        assert image_payload["alt"] == "Dragonscale logo"

        # Verify MermaidFormat message
        mermaid_messages = get_messages_by_format(MermaidFormat)
        assert len(mermaid_messages) == 1
        mermaid_payload = mermaid_messages[0].payload
        assert "flowchart TD" in mermaid_payload["diagram"]
        assert mermaid_payload["title"] == "Christmas Shopping Decision"

        # Verify PlotlyGraphFormat message
        plotly_messages = get_messages_by_format(PlotlyGraphFormat)
        assert len(plotly_messages) == 1
        plotly_payload = plotly_messages[0].payload
        assert "plotParams" in plotly_payload
        assert plotly_payload["title"] == "Energy Distribution"

        # Verify VegaLiteFormat message
        vega_messages = get_messages_by_format(VegaLiteFormat)
        assert len(vega_messages) == 1
        vega_payload = vega_messages[0].payload
        assert "spec" in vega_payload
        assert vega_payload["title"] == "Data Visualization"

        # Verify TableFormat messages
        table_messages = get_messages_by_format(TableFormat)
        assert len(table_messages) == 1
        table_payload = table_messages[0].payload
        assert len(table_payload["data"]) == 5
        assert table_payload["title"] == "Milk Nutrition Facts"

        # Verify PerspectiveFormat message (custom format)
        perspective_messages = get_messages_by_format_name("PerspectiveFormat")
        assert len(perspective_messages) == 1
        perspective_payload = perspective_messages[0].payload
        assert len(perspective_payload["data"]) == 10
        assert perspective_payload["title"] == "Superstore Table"

        # Verify AudioFormat message
        audio_messages = get_messages_by_format(AudioFormat)
        assert len(audio_messages) == 1
        audio_payload = audio_messages[0].payload
        assert "rustic-ai.github.io" in audio_payload["src"]
        assert audio_payload["title"] == "Weekly Tech Podcast"

        # Verify VideoFormat message
        video_messages = get_messages_by_format(VideoFormat)
        assert len(video_messages) == 1
        video_payload = video_messages[0].payload
        assert "rustic-ai.github.io" in video_payload["src"]
        assert video_payload["title"] == "Training Video"

        # Verify Update message
        update_messages = get_messages_by_format_name("updateTextFormat")
        assert len(update_messages) == 2
        update_msg_payload_1 = update_messages[0].payload
        update_msg_payload_2 = update_messages[1].payload
        assert update_msg_payload_1["updateId"] == update_msg_payload_2["updateId"]
        assert update_msg_payload_1["updateType"] is None
        assert update_msg_payload_2["updateType"] == UpdateType.APPEND

        guild.shutdown()
