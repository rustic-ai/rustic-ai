"""
Auto-generated Pydantic models for huggingface's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://huggingface.co/mcp"
   },
   "tools": [
     {
       "name": "hf_whoami",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HfWhoamiInput",
       "description": "Hugging Face tools are being used by authenticated user 'shiti'"
     },
     {
       "name": "space_search",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.SpaceSearchInput",
       "description": "Find Hugging Face Spaces using semantic search. IMPORTANT Only MCP Servers can be used with the dynamic_space toolInclude links to the Space when presenting the results."
     },
     {
       "name": "hub_repo_search",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HubRepoSearchInput",
       "description": "Search Hugging Face repositories with a shared query interface. You can target models, datasets, spaces, or aggregate across multiple repo types in one call. Use space_search for semantic-first discovery of Spaces. Include links to repositories in your response."
     },
     {
       "name": "paper_search",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.PaperSearchInput",
       "description": "Find Machine Learning research papers on the Hugging Face hub. Include 'Link to paper' When presenting the results. Consider whether tabulating results matches user intent."
     },
     {
       "name": "hub_repo_details",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HubRepoDetailsInput",
       "description": "Get details for one or more Hugging Face repos (model, dataset, or space). Auto-detects type unless specified. For datasets, use operations: overview, dataset_structure, dataset_preview. Use dataset_structure first to discover configs, splits, sizes, and schema. Use dataset_preview only when config and split are known, unless the dataset has a single config/split."
     },
     {
       "name": "hf_doc_search",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HfDocSearchInput",
       "description": "Search and Discover Hugging Face Product and Library documentation. Send an empty query to discover structure and navigation instructions. Knowledge up-to-date as at 19 June 2026. Combine with the Product filter to focus results."
     },
     {
       "name": "hf_doc_fetch",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HfDocFetchInput",
       "description": "Fetch a document from the Hugging Face or Gradio documentation library. For large documents, use offset to get subsequent chunks."
     },
     {
       "name": "dynamic_space",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.DynamicSpaceInput",
       "description": "Perform Tasks with Hugging Face Spaces. Use \"discover\" to view available Tasks. Examples are Image Generation/Editing, Background Removal, Text to Speech, OCR and many more. Call with no arguments for full usage instructions."
     },
     {
       "name": "hf_hub_query",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.HfHubQueryInput",
       "description": "Read-only Hugging Face Hub navigator for discovery, lookup, filtering, ranking, counts, field-constrained extraction, and relationship questions across users, orgs, models, datasets, spaces, collections, discussions, daily papers, recent activity, followers/following, likes, and likers. Good for structured raw outputs and compact results. Generated helper calls can explicitly bound limit, scan_limit, max_pages, and ranking_window for brevity or broader coverage, and the tool can also be asked about its supported helpers, canonical fields, defaults, and coverage behavior."
     },
     {
       "name": "gr1_z_image_turbo_generate",
       "input_class_name": "rustic_ai.mcp.connectors.huggingface.Gr1ZImageTurboGenerateInput",
       "description": "Generate an image using the Z-Image model based on the provided prompt and settings. This function is triggered when the user clicks the \"Generate\" button. It processes the input prompt (optionally enhancing it), configures generation parameters, and produces an image using the Z-Image diffusion transformer pipeline. Returns: tuple: (gallery_images, seed_str, seed_int), - seed_str: String representation of the seed used for generation, - seed_int: Integer representation of the seed used for generation (from mcp-tools/Z-Image-Turbo)"
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel


class HfWhoamiInput(BaseModel):
    pass


class SpaceSearchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Semantic Search Query", max_length=100, min_length=1)]
    limit: Annotated[Optional[float], Field(description="Number of results to return")] = 10
    mcp: Annotated[Optional[bool], Field(description="Only return MCP Server enabled Spaces")] = False


class RepoType(Enum):
    MODEL = "model"
    DATASET = "dataset"
    SPACE = "space"


class Sort(Enum):
    """
    Sort order (descending): trendingScore, downloads, likes, createdAt, lastModified
    """

    TRENDING_SCORE = "trendingScore"
    DOWNLOADS = "downloads"
    LIKES = "likes"
    CREATED_AT = "createdAt"
    LAST_MODIFIED = "lastModified"


class HubRepoSearchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[
        Optional[str],
        Field(
            description="Search term. Leave blank and specify sort + limit to browse trending or recent repositories."
        ),
    ] = None
    repo_types: Annotated[
        Optional[list[RepoType]],
        Field(
            description=(
                'Repository types to search. Defaults to ["model", "dataset"]. space uses keyword search via'
                " /api/spaces."
            ),
            max_length=3,
            min_length=1,
        ),
    ] = [RepoType.MODEL, RepoType.DATASET]
    author: Annotated[
        Optional[str],
        Field(description="Organization or user namespace to filter by (e.g. 'google', 'meta-llama', 'huggingface')."),
    ] = None
    filters: Annotated[
        Optional[list[str]],
        Field(
            description=(
                'Optional hub filter tags. Applied to each selected repo type (e.g. ["text-generation"],'
                ' ["language:en"], ["mcp-server"]).'
            )
        ),
    ] = None
    sort: Annotated[
        Optional[Sort],
        Field(description="Sort order (descending): trendingScore, downloads, likes, createdAt, lastModified"),
    ] = None
    limit: Annotated[
        Optional[float],
        Field(description="Maximum number of results to return per selected repo type", ge=1.0, le=100.0),
    ] = 20


class PaperSearchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Semantic Search query", max_length=200, min_length=3)]
    results_limit: Annotated[Optional[float], Field(description="Number of results to return")] = 12
    concise_only: Annotated[
        Optional[bool],
        Field(
            description=(
                "Return a 2 sentence summary of the abstract. Use for broad search terms which may return a lot of"
                " results. Check with User if unsure."
            )
        ),
    ] = False


class RepoId(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class RepoType1(Enum):
    """
    Specify lookup type; otherwise auto-detects
    """

    MODEL = "model"
    DATASET = "dataset"
    SPACE = "space"


class Operation(Enum):
    OVERVIEW = "overview"
    DATASET_STRUCTURE = "dataset_structure"
    DATASET_PREVIEW = "dataset_preview"


class HubRepoDetailsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    repo_ids: Annotated[
        list[RepoId],
        Field(
            description=(
                "Repo IDs for (models|dataset/space) - usually in author/name format (e.g. openai/gpt-oss-120b)"
            ),
            max_length=10,
            min_length=1,
        ),
    ]
    repo_type: Annotated[Optional[RepoType1], Field(description="Specify lookup type; otherwise auto-detects")] = None
    operations: Annotated[
        Optional[list[Operation]],
        Field(
            description=(
                'Details to return. Defaults to ["overview"]. For datasets, prefer ["overview", "dataset_structure"]'
                ' first; then call ["dataset_preview"] with config and split.'
            )
        ),
    ] = None
    config: Annotated[
        Optional[str],
        Field(
            description=(
                "Dataset Viewer config. Required for dataset_preview when the dataset has multiple config/split"
                " options. Discover via dataset_structure."
            )
        ),
    ] = None
    split: Annotated[
        Optional[str],
        Field(
            description=(
                "Dataset Viewer split. Required for dataset_preview when the dataset has multiple config/split options."
                " Discover via dataset_structure."
            )
        ),
    ] = None
    offset: Annotated[Optional[int], Field(description="Row offset for dataset_preview. Defaults to 0.", ge=0)] = None
    limit: Annotated[
        Optional[int], Field(description="Row count for dataset_preview. Defaults to 5 and is clamped to 1-100.")
    ] = None


class HfDocSearchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[
        str,
        Field(
            description=(
                "Start with an empty query for structure, endpoint discovery and navigation tips. Use semantic queries"
                " for targetted searches."
            ),
            max_length=200,
        ),
    ]
    product: Annotated[Optional[str], Field(description="Filter by Product. Supply when known for focused results")] = (
        None
    )


class HfDocFetchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    doc_url: Annotated[str, Field(description="Documentation URL (Hugging Face or Gradio)", max_length=200)]
    offset: Annotated[
        Optional[float],
        Field(description="Token offset for large documents (use the offset from truncation message)", ge=0.0),
    ] = None


class Operation1(Enum):
    """
    Operation to perform.
    """

    DISCOVER = "discover"
    VIEW_PARAMETERS = "view_parameters"
    INVOKE = "invoke"


class DynamicSpaceInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation: Annotated[Optional[Operation1], Field(description="Operation to perform.")] = None
    space_name: Annotated[
        Optional[str],
        Field(
            description=(
                'Space ID (format: "username/space-name"). Required for "view_parameters" and "invoke" operations.'
            )
        ),
    ] = None
    parameters: Annotated[
        Optional[str], Field(description='JSON object string of parameters. Only used for "invoke" operation.')
    ] = None


class HfHubQueryInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    message: str


class Resolution(Enum):
    """
    Output resolution in format "WIDTHxHEIGHT ( RATIO )" (e.g., "1024x1024 ( 1:1 )")
    """

    FIELD_1024X1024___1_1__ = "1024x1024 ( 1:1 )"
    FIELD_1152X896___9_7__ = "1152x896 ( 9:7 )"
    FIELD_896X1152___7_9__ = "896x1152 ( 7:9 )"
    FIELD_1152X864___4_3__ = "1152x864 ( 4:3 )"
    FIELD_864X1152___3_4__ = "864x1152 ( 3:4 )"
    FIELD_1248X832___3_2__ = "1248x832 ( 3:2 )"
    FIELD_832X1248___2_3__ = "832x1248 ( 2:3 )"
    FIELD_1280X720___16_9__ = "1280x720 ( 16:9 )"
    FIELD_720X1280___9_16__ = "720x1280 ( 9:16 )"
    FIELD_1344X576___21_9__ = "1344x576 ( 21:9 )"
    FIELD_576X1344___9_21__ = "576x1344 ( 9:21 )"
    FIELD_1280X1280___1_1__ = "1280x1280 ( 1:1 )"
    FIELD_1440X1120___9_7__ = "1440x1120 ( 9:7 )"
    FIELD_1120X1440___7_9__ = "1120x1440 ( 7:9 )"
    FIELD_1472X1104___4_3__ = "1472x1104 ( 4:3 )"
    FIELD_1104X1472___3_4__ = "1104x1472 ( 3:4 )"
    FIELD_1536X1024___3_2__ = "1536x1024 ( 3:2 )"
    FIELD_1024X1536___2_3__ = "1024x1536 ( 2:3 )"
    FIELD_1536X864___16_9__ = "1536x864 ( 16:9 )"
    FIELD_864X1536___9_16__ = "864x1536 ( 9:16 )"
    FIELD_1680X720___21_9__ = "1680x720 ( 21:9 )"
    FIELD_720X1680___9_21__ = "720x1680 ( 9:21 )"
    FIELD_1536X1536___1_1__ = "1536x1536 ( 1:1 )"
    FIELD_1728X1344___9_7__ = "1728x1344 ( 9:7 )"
    FIELD_1344X1728___7_9__ = "1344x1728 ( 7:9 )"
    FIELD_1728X1296___4_3__ = "1728x1296 ( 4:3 )"
    FIELD_1296X1728___3_4__ = "1296x1728 ( 3:4 )"
    FIELD_1872X1248___3_2__ = "1872x1248 ( 3:2 )"
    FIELD_1248X1872___2_3__ = "1248x1872 ( 2:3 )"
    FIELD_2048X1152___16_9__ = "2048x1152 ( 16:9 )"
    FIELD_1152X2048___9_16__ = "1152x2048 ( 9:16 )"
    FIELD_2016X864___21_9__ = "2016x864 ( 21:9 )"
    FIELD_864X2016___9_21__ = "864x2016 ( 9:21 )"


class Gr1ZImageTurboGenerateInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prompt: Annotated[Optional[str], Field(description="Text prompt describing the desired image content")] = None
    resolution: Annotated[
        Optional[Resolution],
        Field(description='Output resolution in format "WIDTHxHEIGHT ( RATIO )" (e.g., "1024x1024 ( 1:1 )")'),
    ] = Resolution.FIELD_1024X1024___1_1__
    seed: Annotated[Optional[int], Field(description="Seed for reproducible generation")] = 42
    steps: Annotated[Optional[float], Field(description="Number of inference steps for the diffusion process")] = 8
    shift: Annotated[Optional[float], Field(description="Time shift parameter for the flow matching scheduler")] = 3
    random_seed: Annotated[
        Optional[bool], Field(description="Whether to generate a new random seed, if True will ignore the seed input")
    ] = True
