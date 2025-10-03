from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse
from rustic_ai.core.messaging import MessageConstants
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.ui_protocol.types import (
    AudioFormat,
    CalendarEvent,
    CalendarFormat,
    CanvasFormat,
    CodeFormat,
    FileData,
    FilesWithTextFormat,
    FormFormat,
    FormSchema,
    ImageFormat,
    LocationFormat,
    MermaidFormat,
    PlotlyGraphFormat,
    QuestionFormat,
    TableFormat,
    TableHeader,
    TextFormat,
    UpdateType,
    VegaLiteFormat,
    VideoFormat,
    Weather,
    WeatherFormat,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class UiComponentAgent(Agent):
    """An Agent that sends messages in formats compatible with UI components."""

    def __init__(self) -> None:
        self.handled_formats = [MessageConstants.RAW_JSON_FORMAT]

    @agent.processor(JsonDict)
    def send_ui_components(self, ctx: ProcessContext[JsonDict]) -> None:
        """
        Processes the received message and sends responses in all available UI component formats.
        Demonstrates all DataFormat, VisualizationFormat, and MediaFormat components using sample data.

        Args:
            ctx (ProcessContext[JsonDict]): The context of the message being processed.
        """

        # DataFormat types

        # TextFormat
        text_msg = TextFormat(text="This is a text message example", title="Text format example")
        ctx.send(payload=text_msg)

        # MarkdownFormat
        markdown_msg = TextFormat(
            text="# Welcome to the Project\n\nHere's a **bold** statement and some `code`.\n\n- Item 1\n- Item 2\n- Item 3",
            title="Project Overview",
        )
        ctx.send_dict(
            markdown_msg.model_dump(),
            format="MarkdownFormat",
        )

        # CanvasFormat - Markdown
        canvas_msg = CanvasFormat(
            component="MarkdownFormat",
            title="Canvas Markdown Example",
            description="Canvas component with markdown content",
            text="# Canvas Component\n\nThis is a **canvas** with *markdown* content.\n\n- Flexible structure\n- Dynamic fields\n- Component-based rendering",
        )
        ctx.send(payload=canvas_msg)

        # CanvasFormat - Image
        canvas_image_msg = CanvasFormat(
            component=get_qualified_class_name(ImageFormat),
            title="Canvas Image Example",
            description="Canvas component with image content",
            mediaLink=MediaLink(
                url="http://localhost:3000/640e5f0fb14b6075ead8.png",
            ),
            alt="Dragonscale logo in canvas",
        )
        ctx.send(payload=canvas_image_msg)

        files_msg = FilesWithTextFormat(
            files=[
                FileData(
                    mediaLink=MediaLink(
                        name="logo.png",
                        url="http://localhost:3000/640e5f0fb14b6075ead8.png",
                    )
                )
            ],
            text="Please review this document.",
            title="File Attachments",
        )
        ctx.send(payload=files_msg)

        # QuestionFormat
        question_msg = QuestionFormat(
            options=["Option A", "Option B", "Option C"],
            title="Survey Question",
            description="Please select your preferred option",
        )
        ctx.send(payload=question_msg)

        # FormFormat
        form_schema = FormSchema(
            properties={
                "username": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password"},
            },
            required=["username", "password"],
        )
        form_msg = FormFormat(schema=form_schema, title="Login Form")
        ctx.send(payload=form_msg)

        # CodeFormat
        code_msg = CodeFormat(
            code='def hello_world():\n    print("Hello, World!")',
            language="Python",
            title="Python Function",
            description="A simple hello world function",
        )
        ctx.send(payload=code_msg)

        # CalendarFormat
        calendar_msg = CalendarFormat(
            events=[
                CalendarEvent(start="2024-03-15T09:00:00Z", end="2024-03-15T10:00:00Z", title="Morning Standup"),
                CalendarEvent(start="2024-03-15T14:00:00Z", end="2024-03-15T15:00:00Z", title="Client Call"),
            ],
            title="Weekly Schedule",
        )
        ctx.send(payload=calendar_msg)

        # WeatherFormat
        weather_msg = WeatherFormat(
            weather=[
                Weather(
                    timestamp=1640995200,
                    temp={"low": -5, "high": -2, "current": -3},
                    weatherIcon={"icon": "https://openweathermap.org/img/wn/13d.png", "description": "Snowy"},
                ),
                Weather(
                    timestamp=1641081600,
                    temp={"low": 0, "high": 7},
                    weatherIcon={"icon": "https://openweathermap.org/img/wn/04d.png", "description": "Partly cloudy"},
                ),
                Weather(
                    timestamp=1641168000,
                    temp={"low": 2, "high": 8},
                    weatherIcon={"icon": "https://openweathermap.org/img/wn/10d.png", "description": "Light rain"},
                ),
                Weather(
                    timestamp=1641254400,
                    temp={"low": -3, "high": 5},
                    weatherIcon={"icon": "https://openweathermap.org/img/wn/13d.png", "description": "Snowy"},
                ),
                Weather(
                    timestamp=1641340800,
                    temp={"low": 4, "high": 12},
                    weatherIcon={"icon": "https://openweathermap.org/img/wn/04d.png", "description": "Partly cloudy"},
                ),
            ],
            location="San Francisco, CA",
            units="metric",
            title="5-Day Weather Forecast",
        )
        ctx.send(payload=weather_msg)

        # VisualizationFormat types

        # LocationFormat
        location_msg = LocationFormat(
            longitude=-122.4194,
            latitude=37.7749,
            title="San Francisco Office",
            description="Our main headquarters location",
            alt="Map showing San Francisco office location",
        )
        ctx.send(payload=location_msg)

        # ImageFormat
        image_msg = ImageFormat(
            src="http://localhost:3000/640e5f0fb14b6075ead8.png", alt="Dragonscale logo", title="Dragonscale logo"
        )
        ctx.send(payload=image_msg)

        # MermaidFormat
        mermaid_msg = MermaidFormat(
            diagram="""flowchart TD
   A[Christmas] -->|Get money| B(Go shopping)
   B --> C{Let me think}
   C -->|One| D[Laptop]
   C -->|Two| E[iPhone]
   C -->|Three| F[fa:fa-car Car]""",
            title="Christmas Shopping Decision",
            alt="Flowchart showing Christmas shopping decision process",
        )
        ctx.send(payload=mermaid_msg)

        # PlotlyGraphFormat
        plotly_msg = PlotlyGraphFormat(
            plotParams={
                "data": [
                    {"labels": ["Residential", "Non-Residential", "Utility"], "type": "pie", "values": [19, 26, 55]}
                ],
                "layout": {"title": "Pie chart"},
            },
            title="Energy Distribution",
            alt="Pie chart showing energy distribution across sectors",
        )
        ctx.send(payload=plotly_msg)

        # VegaLiteFormat
        vega_msg = VegaLiteFormat(
            spec={
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "data": {
                    "values": [
                        {"a": "A", "b": 28},
                        {"a": "B", "b": 55},
                        {"a": "C", "b": 43},
                        {"a": "D", "b": 91},
                        {"a": "E", "b": 81},
                    ]
                },
                "encoding": {"x": {"field": "a", "type": "nominal"}, "y": {"field": "b", "type": "quantitative"}},
                "mark": "bar",
                "width": "container",
            },
            title="Data Visualization",
            alt="Bar chart showing categorical data with values from A to E",
        )
        ctx.send_dict(vega_msg.model_dump(exclude_none=True), format=get_qualified_class_name(VegaLiteFormat))

        # TableFormat
        table_msg = TableFormat(
            data=[
                {"food": "chocolate milk", "calories": 219, "carbs": 27.31, "fat": 8.95, "protein": 8.37},
                {"food": "whole milk", "calories": 165, "carbs": 11.99, "fat": 9.44, "protein": 8.46},
                {"food": "2% skimmed milk", "calories": 129, "carbs": 12.38, "fat": 5.1, "protein": 8.51},
                {"food": "1% skimmed milk", "calories": 108, "carbs": 12.87, "fat": 2.5, "protein": 8.69},
                {"food": "skim milk", "calories": 88, "carbs": 12.84, "fat": 0.21, "protein": 8.72},
            ],
            title="Milk Nutrition Facts",
        )
        ctx.send(payload=table_msg)

        perspective_msg = TableFormat(
            data=[
                {
                    "category": "Furniture",
                    "orderDate": "2022/2/14",
                    "profit": 2508,
                    "region": "South",
                    "sales": 16790,
                    "state": "Texas",
                    "subCategory": "Desks",
                },
                {
                    "category": "Office Supplies",
                    "orderDate": "2022/10/26",
                    "profit": -2134,
                    "region": "Midwest",
                    "sales": 11259,
                    "state": "Illinois",
                    "subCategory": "Pens",
                },
                {
                    "category": "Apparel",
                    "orderDate": "2023/4/20",
                    "profit": -4386,
                    "region": "West",
                    "sales": 15244,
                    "state": "Washington",
                    "subCategory": "Shirts",
                },
                {
                    "category": "Office Supplies",
                    "orderDate": "2022/8/11",
                    "profit": -6694,
                    "region": "East",
                    "sales": 19316,
                    "state": "Pennsylvania",
                    "subCategory": "Paper",
                },
                {
                    "category": "Furniture",
                    "orderDate": "2022/7/22",
                    "profit": -4926,
                    "region": "Midwest",
                    "sales": 19108,
                    "state": "Illinois",
                    "subCategory": "Chairs",
                },
                {
                    "category": "Technology",
                    "orderDate": "2023/4/1",
                    "profit": -3550,
                    "region": "South",
                    "sales": 9856,
                    "state": "Florida",
                    "subCategory": "Phones",
                },
                {
                    "category": "Food and Beverage",
                    "orderDate": "2023/4/13",
                    "profit": 1621,
                    "region": "West",
                    "sales": 16756,
                    "state": "California",
                    "subCategory": "Snacks",
                },
                {
                    "category": "Apparel",
                    "orderDate": "2023/2/17",
                    "profit": 1632,
                    "region": "Midwest",
                    "sales": 6872,
                    "state": "Illinois",
                    "subCategory": "Pants",
                },
                {
                    "category": "Office Supplies",
                    "orderDate": "2021/12/8",
                    "profit": -855,
                    "region": "South",
                    "sales": 6669,
                    "state": "Texas",
                    "subCategory": "Paper",
                },
                {
                    "category": "Furniture",
                    "orderDate": "2022/12/28",
                    "profit": -83,
                    "region": "Midwest",
                    "sales": 5551,
                    "state": "Illinois",
                    "subCategory": "Chairs",
                },
            ],
            headers=[
                TableHeader(dataKey="region", label="Region"),
                TableHeader(dataKey="state", label="State"),
                TableHeader(dataKey="category", label="Category"),
                TableHeader(dataKey="subCategory", label="Sub-Category"),
                TableHeader(dataKey="sales", label="Sales"),
                TableHeader(dataKey="profit", label="Profit"),
                TableHeader(dataKey="orderDate", label="Order Date"),
            ],
            title="Superstore Table",
        )

        ctx.send_dict(
            perspective_msg.model_dump(by_alias=True),
            format="PerspectiveFormat",
        )

        # MediaFormat types

        # AudioFormat
        audio_msg = AudioFormat(
            src="https://rustic-ai.github.io/rustic-ui-components/audioExamples/audioStorybook.mp3",
            transcript="audio test transcript...",
            title="Weekly Tech Podcast",
        )
        ctx.send(payload=audio_msg)

        # VideoFormat
        video_msg = VideoFormat(
            src="https://rustic-ai.github.io/rustic-ui-components/videoExamples/videoCaptions.mp4",
            captions="https://rustic-ai.github.io/rustic-ui-components/audioExamples/captions.vtt",
            title="Training Video",
        )
        ctx.send(payload=video_msg)

        # LLM Models - ChatCompletionResponse
        chat_response = ChatCompletionResponse(
            id="chatcmpl-123",
            object="chat.completion",
            created=1677652288,
            model="gpt-4o-mini",
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "This is a **chat completion response message** in markdown format",
                    },
                    "finish_reason": "stop",
                }
            ],
        )
        ctx.send(payload=chat_response)

        # Update messages
        text_msg_1 = TextFormat(
            updateId="test_update_text", text="This is a text message example", title="update text format example"
        )
        ctx.send_dict(payload=text_msg_1.model_dump(), format="updateTextFormat")

        text_msg_2 = TextFormat(
            updateId="test_update_text",
            text="This text should be appended to previous text in UI",
            title="update text format example",
            updateType=UpdateType.APPEND,
        )

        ctx.send_dict(payload=text_msg_2.model_dump(), format="updateTextFormat")
