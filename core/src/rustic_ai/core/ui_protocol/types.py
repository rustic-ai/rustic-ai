"""
Message format types for UI components.

These types correspond to the message formats used in the Rustic UI component library.
For more examples and detailed explanations, check out the Storybook documentation:
https://rustic-ai.github.io/rustic-ui-components
"""

from enum import Enum
from typing import Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from rustic_ai.core import AgentTag


class DataFormat(BaseModel):
    """Base class for all message data formats."""

    title: Optional[str] = None
    description: Optional[str] = None
    tagged_users: list[AgentTag] = []


class VisualizationFormat(DataFormat):
    """Base class for visual components that need accessibility support."""

    alt: Optional[str] = None


class TextFormat(DataFormat):
    """Format for displaying plain text or markdown messages.

    Examples:
        Plain text:
        ```python
        text_msg = TextFormat(
            text="Hello, this is a plain text message!",
            title="Greeting"
        )
        ```

        Markdown text:
        ```python
        markdown_msg = TextFormat(
            text="# Welcome to the Project\n\nHere's a **bold** statement and some `code`.\n\n- Item 1\n- Item 2\n- Item 3",
            title="Project Overview"
        )
        ```
    """

    text: str


class FileData(BaseModel):
    """Represents file information with name and URL.

    Example:
        ```python
        file_data = FileData(
            name="report.pdf",
            url="https://example.com/files/report.pdf"
        )
        ```
    """

    name: str
    url: str


class FilesWithTextFormat(DataFormat):
    """Format for messages containing files with optional text. Used in the Multipart component.

    Example:
        ```python
        files = FilesWithTextFormat(
            files=[
                FileData(name="document.pdf", url="https://example.com/doc.pdf"),
                FileData(name="image.jpg", url="https://example.com/img.jpg")
            ],
            text="Please review these attached files",
        )
        ```
    """

    files: list[FileData]
    text: Optional[str]


class QuestionFormat(DataFormat):
    """Format for the question component.

    Examples:
        String options:
        ```python
        question = QuestionFormat(
            options=["Option A", "Option B", "Option C"],
            title="Survey Question",
            description="Please select your preferred option"
        )
        ```

        Number options:
        ```python
        rating = QuestionFormat(
            options=[1, 2, 3, 4, 5],
            title="Rate this service",
            description="How would you rate your experience?"
        )
        ```
    """

    options: list[Union[str, int]]


class QuestionResponse(BaseModel):
    """Response data for a question format.

    Examples:
        String response:
        ```python
        response = QuestionResponse(data="Option A")
        ```

        Number response:
        ```python
        rating_response = QuestionResponse(data=4)
        ```
    """

    data: Union[str, int]


class FormSchema(BaseModel):
    """JSON schema definition for dynamic forms.

    Example:
        ```python
        schema = FormSchema(
            title="Provide a delivery address",
            type="object",
            properties={
                "city": {"type": "string"},
                "state": {"type": "string"},
                "street": {"type": "string"},
                "zip": {"type": "string", "pattern": "^[0-9]{5}(?:-[0-9]{4})?$"}
            },
            required=["city","zip",'street']
        )
        ```
    """

    type: str = "object"
    properties: Dict[str, JsonValue]
    required: list[str] = []


class FormFormat(DataFormat):
    """Format for dynamic form components based on JSON schema.

    Example:
        ```python
        form = FormFormat(
            schema_=FormSchema(
                properties={
                    "username": {"type": "string", "title": "Username"},
                    "password": {"type": "string", "format": "password"}
                },
                required=["username", "password"]
            ),
            title="Login Form"
        )
        ```
    """

    schema_: FormSchema = Field(alias="schema")
    model_config = ConfigDict(serialize_by_alias=True)


class FormResponse(BaseModel):
    """Response data for form submissions with flexible field structure.

    Example:
        ```python
        response = FormResponse(username="john_doe", password="secret123")
        ```
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class CodeFormat(DataFormat):
    """Format for displaying syntax-highlighted code snippets.

    Example:
        ```python
        code_snippet = CodeFormat(
            code='def hello_world():\n    print("Hello, World!")',
            language="Python",
            title="Python Function",
            description="A simple hello world function"
        )
        ```
    """

    code: str
    language: str


class CalendarEvent(BaseModel):
    """Represents a single calendar event with date, time, and details.

    Example:
        ```python
        event = CalendarEvent(
            start="2024-03-15T09:00:00Z",
            end="2024-03-15T10:30:00Z",
            title="Team Meeting",
            description="Weekly team sync meeting",
            location="Conference Room A",
            is_all_day=False
        )
        ```
    """

    start: str
    end: str
    location: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    is_all_day: Optional[bool] = Field(default=None, alias="isAllDay")
    model_config = ConfigDict(populate_by_name=True)


class CalendarFormat(DataFormat):
    """Format for displaying calendar events and schedules.

    Example:
        ```python
        calendar = CalendarFormat(
            events=[
                CalendarEvent(
                    start="2024-03-15T09:00:00Z",
                    end="2024-03-15T10:00:00Z",
                    title="Morning Standup"
                ),
                CalendarEvent(
                    start="2024-03-15T14:00:00Z",
                    end="2024-03-15T15:00:00Z",
                    title="Client Call"
                )
            ],
            title="Weekly Schedule"
        )
        ```
    """

    events: list[CalendarEvent]


class LocationFormat(VisualizationFormat):
    """Format for displaying geographic locations on maps.

    Example:
        ```python
        location = LocationFormat(
            longitude=-122.4194,
            latitude=37.7749,
            title="San Francisco Office",
            description="Our main headquarters location",
            alt="Map showing San Francisco office location"
        )
        ```
    """

    longitude: float
    latitude: float


class ImageFormat(VisualizationFormat):
    """Format for displaying images with optional sizing.

    Example:
        ```python
        image = ImageFormat(
            src="https://example.com/image.jpg",
            alt="Product screenshot showing the main dashboard",
            title="Dashboard Screenshot"
        )
        ```
    """

    src: str
    width: Optional[int] = None
    height: Optional[int] = None


class MermaidFormat(VisualizationFormat):
    """Format for displaying Mermaid diagrams.

    Examples:
        Class diagram:
        ```python
        class_diagram = MermaidFormat(
            diagram="classDiagram\\n   Animal <|-- Duck\\n   Animal <|-- Fish\\n   Animal <|-- Zebra\\n   "
                    "Animal : +int age\\n   Animal : +String gender\\n   Animal: +isMammal()\\n   Animal: +mate()\\n   "
                    "class Duck{\\n     +String beakColor\\n     +swim()\\n     +quack()\\n   }\\n   "
                    "class Fish{\\n     -int sizeInFeet\\n     -canEat()\\n   }\\n   "
                    "class Zebra{\\n     +bool is_wild\\n     +run()\\n   }",
            title="Animal Class Hierarchy",
            alt="Class diagram showing animal inheritance structure"
        )
        ```

        Flowchart diagram:
        ```python
        flowchart = MermaidFormat(
            diagram="flowchart TD\\n   A[Christmas] -->|Get money| B(Go shopping)\\n   B --> C{Let me think}\\n   "
                    "C -->|One| D[Laptop]\\n   C -->|Two| E[iPhone]\\n   C -->|Three| F[fa:fa-car Car]",
            title="Christmas Shopping Decision",
            alt="Flowchart showing Christmas shopping decision process"
        )
        ```
    """

    diagram: str
    config: Optional[Dict[str, JsonValue]] = None


class PlotlyGraphFormat(VisualizationFormat):
    """Format for displaying Plotly interactive graphs and charts.

    Example:
        Grouped bar chart:
        ```python
        sales_report = PlotlyGraphFormat(
            plot_params={
                "data": [
                    {
                        "marker": {
                            "color": "rgb(49,130,189)",
                            "opacity": 0.7
                        },
                        "name": "Primary Product",
                        "type": "bar",
                        "x": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                        "y": [20, 14, 25, 16, 18, 22, 19, 15, 12, 16, 14, 17]
                    },
                    {
                        "marker": {
                            "color": "rgb(204,204,204)",
                            "opacity": 0.5
                        },
                        "name": "Secondary Product",
                        "type": "bar",
                        "x": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                        "y": [19, 14, 22, 14, 16, 19, 15, 14, 10, 12, 12, 16]
                    }
                ],
                "layout": {
                    "barmode": "group",
                    "title": "2013 Sales Report",
                    "xaxis": {
                        "autorange": True,
                        "range": [-0.5, 11.5],
                        "tickangle": -45,
                        "type": "category"
                    },
                    "yaxis": {
                        "autorange": True,
                        "range": [0, 26.31578947368421],
                        "type": "linear"
                    }
                }
            },
            title="Annual Sales Comparison",
            alt="Grouped bar chart comparing primary and secondary product sales across 12 months"
        )
        ```
    """

    plot_params: Dict[str, JsonValue] = Field(alias="plotParams")
    model_config = ConfigDict(populate_by_name=True)


class VegaLiteFormat(VisualizationFormat):
    """Format for displaying Vega-Lite visualizations.

    Example:
        Bar chart:
        ```python
        bar_chart = VegaLiteFormat(
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
                "encoding": {
                    "x": {
                        "axis": {
                            "labelAngle": 0
                        },
                        "field": "a",
                        "type": "nominal"
                    },
                    "y": {
                        "field": "b",
                        "type": "quantitative"
                    }
                },
                "height": "container",
                "mark": "bar",
                "width": "container"
            },
            theme={
                "light": "quartz",
                "dark": "dark"
            },
            title="Data Visualization",
            alt="Bar chart showing categorical data with values from A to E"
        )
        ```
    """

    spec: Dict[str, JsonValue]
    theme: Dict[str, Optional[str]]
    options: Optional[Dict[str, JsonValue]] = None


class TableHeader(BaseModel):
    """Configuration for table column headers.

    Example:
        ```python
        header = TableHeader(
            data_key="user_name",
            label="User Name"
        )
        ```
    """

    data_key: str = Field(alias="dataKey")
    label: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True)


class TableSortOption(str, Enum):
    """Enumeration of available table sorting options."""

    ASC = "asc"
    DESC = "desc"
    COL_ASC = "col asc"
    COL_DESC = "col desc"


class TableAggregateOption(str, Enum):
    """Enumeration of available table aggregation functions."""

    ABS_SUM = "abs sum"
    AND = "and"
    ANY = "any"
    AVG = "avg"
    COUNT = "count"
    DISTINCT_COUNT = "distinct count"
    DISTINCT_LEAF = "distinct leaf"
    DOMINANT = "dominant"
    FIRST = "first"
    HIGH = "high"
    LAST = "last"
    LOW = "low"
    OR = "or"
    MEDIAN = "median"
    PCT_SUM_PARENT = "pct sum parent"
    PCT_SUM_GRAND_TOTAL = "pct sum grand total"
    STDDEV = "stddev"
    SUM = "sum"
    SUM_ABS = "sum abs"
    SUM_NOT_NULL = "sum not null"
    UNIQUE = "unique"
    VAR = "var"


class FilterOperation(str, Enum):
    """Enumeration of available table filter operations."""

    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    EQ = "=="
    NEQ = "!="
    IS_NULL = "is null"
    IS_NOT_NULL = "is not null"
    IN = "in"
    NOT_IN = "not in"
    BEGINS_WITH = "begins with"
    CONTAINS = "contains"


class TableSort(BaseModel):
    """Configuration for table column sorting.

    Example:
        ```python
        sort_config = TableSort(
            field="created_date",
            option=TableSortOption.DESC
        )
        ```
    """

    field: str
    option: TableSortOption


class TableFilter(BaseModel):
    """Configuration for table data filtering.

    Example:
        ```python
        filter_config = TableFilter(
            field="status",
            operation=FilterOperation.IN,
            value=["active", "pending"]
        )
        ```
    """

    field: str
    operation: FilterOperation
    value: Union[str, int, float, bool, list[Union[str, int, float, bool]]]


class TableConfig(BaseModel):
    """Advanced configuration for table display and data processing.

    Example:
        ```python
        config = TableConfig(
            columns=["name", "email", "status"],
            group_by=["department"],
            sort=[TableSort(field="name", option=TableSortOption.ASC)],
            filter=[TableFilter(field="status", operation=FilterOperation.EQ, value="active")]
        )
        ```
    """

    columns: Optional[list[str]] = None
    group_by: Optional[list[str]] = Field(default=None, alias="groupBy")
    split_by: Optional[list[str]] = Field(default=None, alias="splitBy")
    aggregates: Optional[Dict[str, TableAggregateOption]] = None
    sort: Optional[list[TableSort]] = None
    filter: Optional[list[TableFilter]] = None
    expansion_depth: Optional[int] = Field(default=None, alias="expansionDepth")
    model_config = ConfigDict(populate_by_name=True)


class TableFormat(VisualizationFormat):
    """Format for displaying tabular data with advanced features like sorting and filtering.
    Note: Headers are used in the basic table to set the order of columns and assign labels and can also be used to limit which columns are shown.

    Examples:
        Basic table with headers:
        ```python
        table = TableFormat(
            data=[
                {"name": "John Doe", "age": 30, "department": "Engineering"},
                {"name": "Jane Smith", "age": 25, "department": "Design"},
                {"name": "Bob Johnson", "age": 35, "department": "Engineering"}
            ],
            headers=[
                TableHeader(data_key="name", label="Full Name"),
                TableHeader(data_key="age", label="Age"),
                TableHeader(data_key="department", label="Department")
            ],
            title="Employee Directory"
        )
        ```

        Perspective table with pivot configuration:
        ```python
        perspective_table = TableFormat(
            data=[
                {"region": "North", "state": "CA", "category": "Tech", "subCategory": "Laptops", "sales": 1000, "profit": 200},
                {"region": "North", "state": "CA", "category": "Tech", "subCategory": "Phones", "sales": 800, "profit": 150},
                {"region": "South", "state": "TX", "category": "Office", "subCategory": "Chairs", "sales": 600, "profit": 120},
                {"region": "South", "state": "FL", "category": "Office", "subCategory": "Desks", "sales": 900, "profit": 180}
            ],
            config=TableConfig(
                aggregates={"profit": TableAggregateOption.ANY, "sales": TableAggregateOption.ANY},
                columns=["sales", "profit"],
                group_by=["region", "state"],
                split_by=["category", "subCategory"]
            ),
            title="Sales Analysis Pivot"
        )
        ```
    """

    data: list[Dict[str, Union[str, int, float]]]
    headers: Optional[list[TableHeader]] = None
    config: Optional[TableConfig] = None


class MediaFormat(DataFormat):
    """Base format for media content (audio/video) with optional captions and transcripts.

    Example:
        ```python
        media = MediaFormat(
            src="https://example.com/video.mp4",
            captions="https://example.com/captions.vtt",
            transcript="Full transcript of the video content...",
            title="Product Demo Video"
        )
        ```
    """

    src: str
    captions: Optional[str] = None
    transcript: Optional[str] = None


class AudioFormat(MediaFormat):
    """Format for audio content playback.

    Example:
        ```python
        audio = AudioFormat(
            src="https://example.com/podcast.mp3",
            transcript="Welcome to our weekly podcast...",
            title="Weekly Tech Podcast"
        )
        ```
    """

    pass


class VideoFormat(MediaFormat):
    """Format for video content with optional poster image.

    Example:
        ```python
        video = VideoFormat(
            src="https://example.com/training.mp4",
            poster="https://example.com/poster.jpg",
            captions="https://example.com/captions.vtt",
            title="Training Video"
        )
        ```
    """

    poster: Optional[str] = None


class Weather(BaseModel):
    """Represents weather data for a specific timestamp.

    Example:
        ```python
        weather_data = Weather(
            timestamp=1640995200,  # Unix timestamp
            temp={"low": 15, "high": 25, "current": 22},
            weather_icon={"icon": "sunny", "description": "Clear sky"}
        )
        ```
    """

    timestamp: int
    temp: Dict[str, Union[int, float]]
    weather_icon: Dict[str, str] = Field(alias="weatherIcon")
    model_config = ConfigDict(populate_by_name=True)


class WeatherFormat(DataFormat):
    """Format for displaying weather information and forecasts.

    Example:
        ```python
        weather_forecast = WeatherFormat(
            weather=[
                Weather(
                    timestamp=1640995200,
                    temp={"low": 15, "high": 25, "current": 22},
                    weather_icon={"icon": "sunny", "description": "Clear sky"}
                ),
                Weather(
                    timestamp=1641081600,
                    temp={"low": 12, "high": 20},
                    weather_icon={"icon": "cloudy", "description": "Partly cloudy"}
                )
            ],
            location="San Francisco, CA",
            units="metric",
            title="5-Day Weather Forecast"
        )
        ```
    """

    weather: list[Weather]
    location: str
    units: Literal["metric", "imperial"]


class PromptsFormat(BaseModel):
    """Format for displaying interactive prompt suggestions to users.

    Example:
        ```python
        prompts = PromptsFormat(
            prompts=[
                "What's the weather like today?",
                "Help me write a Python function",
                "Explain machine learning basics"
            ],
            position="inConversation"
        )
        ```
    """

    prompts: list[str]
    position: Optional[Literal["inConversation", "hoverOverInput"]] = None
