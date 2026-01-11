from datetime import datetime, timezone
from enum import StrEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, JsonValue, computed_field
import shortuuid
from sqlalchemy.ext.mutable import MutableDict
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from rustic_ai.core.guild.metaprog.agent_registry import AgentEntry


class BlueprintExposure(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    ORGANIZATION = "organization"
    SHARED = "shared"
    ORGANIZATION_AND_CHILDREN = "organization_and_children"  # NOTE: Not used, for future possible use


class BlueprintSharedWithOrganization(SQLModel, table=True):
    organization_id: str = Field(primary_key=True)
    blueprint_id: str = Field(primary_key=True, foreign_key="blueprint.id")


class BlueprintCommandBase(SQLModel):
    blueprint_id: str = Field(foreign_key="blueprint.id")
    command: str


class BlueprintCommandCreate(BlueprintCommandBase):
    pass


class BlueprintCommand(BlueprintCommandBase, table=True):
    __tablename__ = "blueprint_command"
    id: str = Field(default_factory=shortuuid.uuid, primary_key=True)

    blueprint: "Blueprint" = Relationship(back_populates="commands")


class BlueprintCommandResponse(BlueprintCommandBase):
    id: str = Field(primary_key=True)
    pass


class BlueprintStarterPromptBase(SQLModel):
    blueprint_id: str = Field(foreign_key="blueprint.id")
    prompt: str


class BlueprintStarterPromptCreate(BlueprintStarterPromptBase):
    pass


class BlueprintStarterPrompt(BlueprintStarterPromptBase, table=True):
    __tablename__ = "blueprint_starter_prompt"
    id: str = Field(default_factory=shortuuid.uuid, primary_key=True)

    blueprint: "Blueprint" = Relationship(back_populates="starter_prompts")


class BlueprintStarterPromptResponse(BlueprintStarterPromptBase):
    id: str = Field(primary_key=True)
    pass


class TagBase(SQLModel):
    tag: str


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: int


class BlueprintTag(SQLModel, table=True):
    __tablename__ = "blueprint_tag"
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)
    blueprint_id: str = Field(foreign_key="blueprint.id", primary_key=True)


class Tag(TagBase, table=True):
    __tablename__ = "tag"
    id: int = Field(default=None, primary_key=True)
    tag: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    blueprints: List["Blueprint"] = Relationship(back_populates="tags", link_model=BlueprintTag)


class BlueprintBase(SQLModel):
    name: str = Field(index=True)
    description: str = Field(index=True)
    version: str
    icon: Optional[str] = Field(default=None)
    intro_msg: Optional[str] = Field(default=None)

    exposure: BlueprintExposure = Field(default=BlueprintExposure.PRIVATE)

    author_id: str
    organization_id: Optional[str]
    category_id: Optional[str] = Field(foreign_key="blueprint_category.id")


class BlueprintCreate(BlueprintBase):
    spec: dict
    tags: Optional[List[str]] = None
    commands: Optional[List[str]] = None
    starter_prompts: Optional[List[str]] = None
    agent_icons: Optional[dict] = None


class BlueprintAgentLink(SQLModel, table=True):
    __tablename__ = "blueprint_agent_link"

    blueprint_id: str = Field(default=None, foreign_key="blueprint.id", primary_key=True)
    qualified_class_name: str = Field(default=None, foreign_key="agent_entry.qualified_class_name", primary_key=True)


class Blueprint(BlueprintBase, table=True):
    __tablename__ = "blueprint"

    id: str = Field(default_factory=shortuuid.uuid, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    spec: Dict = Field(default_factory=dict, sa_column=Column(JSON))

    author_id: str
    organization_id: Optional[str]
    category: Optional["BlueprintCategory"] = Relationship(back_populates="blueprints")

    commands: List[BlueprintCommand] = Relationship(back_populates="blueprint")
    starter_prompts: List[BlueprintStarterPrompt] = Relationship(back_populates="blueprint")
    tags: List[Tag] = Relationship(back_populates="blueprints", link_model=BlueprintTag)

    reviews: List["BlueprintReview"] = Relationship(back_populates="blueprint")
    agents: List["CatalogAgentEntry"] = Relationship(back_populates="blueprints", link_model=BlueprintAgentLink)


class BlueprintInfoResponse(BaseModel):
    id: str
    name: str
    description: str
    version: str
    exposure: BlueprintExposure
    author_id: str
    created_at: datetime
    updated_at: datetime
    icon: Optional[str]
    organization_id: Optional[str]
    category_id: Optional[str]
    category_name: Optional[str]

    @classmethod
    def from_table(cls, blueprint: Blueprint) -> "BlueprintInfoResponse":
        return cls(
            id=blueprint.id,
            name=blueprint.name,
            description=blueprint.description,
            version=blueprint.version,
            exposure=blueprint.exposure,
            author_id=blueprint.author_id,
            created_at=blueprint.created_at,
            updated_at=blueprint.updated_at,
            icon=blueprint.icon,
            organization_id=blueprint.organization_id,
            category_id=blueprint.category.id if blueprint.category else None,
            category_name=blueprint.category.name if blueprint.category else None,
        )


class BlueprintDetailsResponse(BlueprintInfoResponse):
    spec: Dict
    tags: List[str]
    commands: List[str]
    starter_prompts: List[str]
    intro_msg: Optional[str]

    @classmethod
    def from_table(cls, blueprint: Blueprint) -> "BlueprintDetailsResponse":
        blueprint_info = BlueprintInfoResponse.from_table(blueprint)
        return cls(
            **blueprint_info.model_dump(),
            intro_msg=blueprint.intro_msg,
            spec=blueprint.spec,
            tags=[tag.tag for tag in blueprint.tags],
            starter_prompts=[sp.prompt for sp in blueprint.starter_prompts],
            commands=[c.command for c in blueprint.commands],
        )


class BlueprintResponseWithAccessReason(BlueprintInfoResponse):
    access_organization_id: Optional[str] = Field(default=None)


class BlueprintCategoryBase(SQLModel):
    name: str
    description: str


class BlueprintCategoryCreate(BlueprintCategoryBase):
    pass


class BlueprintCategory(BlueprintCategoryBase, table=True):
    __tablename__ = "blueprint_category"
    id: str = Field(default_factory=shortuuid.uuid, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    blueprints: List[Blueprint] = Relationship(back_populates="category")


class BlueprintCategoryResponse(BlueprintCategoryBase):
    id: str = Field(primary_key=True)
    pass


class BlueprintReviewBase(SQLModel):
    user_id: str
    rating: int
    review: str = Field(default=None)


class BlueprintReviewCreate(BlueprintReviewBase):
    pass


class BlueprintReview(BlueprintReviewBase, table=True):
    __tablename__ = "blueprint_reviews"
    blueprint_id: str = Field(foreign_key="blueprint.id")
    id: str = Field(default_factory=shortuuid.uuid, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user_id: str
    blueprint: Blueprint = Relationship(back_populates="reviews")


class BlueprintReviewResponse(BlueprintReviewBase):
    blueprint_id: str = Field(foreign_key="blueprint.id")
    pass


class BlueprintReviewsResponse(SQLModel):
    reviews: List[BlueprintReviewResponse]

    @computed_field
    def average_rating(self) -> float:
        if not self.reviews:
            return 0
        rating = sum(review.rating for review in self.reviews) / len(self.reviews)
        return rating

    @computed_field
    def total_reviews(self) -> int:
        return len(self.reviews)


class DatabaseConflictError(Exception):
    pass


class BlueprintGuild(SQLModel, table=True):
    __tablename__ = "blueprint_guild"
    guild_id: str = Field(foreign_key="guilds.id", primary_key=True, index=True)
    blueprint_id: str = Field(foreign_key="blueprint.id", index=True)


class UserGuild(SQLModel, table=True):
    __tablename__ = "user_guild"
    guild_id: str = Field(foreign_key="guilds.id", primary_key=True, index=True)
    user_id: str = Field(primary_key=True, index=True)


class BasicGuildInfo(SQLModel):
    id: str
    name: str
    blueprint_id: Optional[str] = Field(default=None)
    icon: Optional[str] = Field(default=None)
    status: str


class AgentIcon(SQLModel, table=True):
    __tablename__ = "agent_icon"
    agent_class: str = Field(primary_key=True, index=True)
    icon: str


class AgentNameWithIcon(SQLModel):
    agent_name: str
    icon: str


class BlueprintAgentIcon(AgentNameWithIcon, table=True):
    __tablename__ = "blueprint_agent_icon"
    blueprint_id: str = Field(foreign_key="blueprint.id", primary_key=True, index=True)
    agent_name: str = Field(primary_key=True, index=True)
    icon: str


class BlueprintAgentsIconReqRes(BaseModel):
    agent_icons: list[AgentNameWithIcon]


class CatalogAgentEntry(SQLModel, table=True):
    __tablename__ = "agent_entry"
    agent_name: str = Field(..., description="The name of the agent.")
    qualified_class_name: str = Field(..., primary_key=True, index=True)
    agent_doc: Optional[str] = Field(default="")
    agent_props_schema: Dict[str, JsonValue] = Field(sa_column=Column(JSON))
    message_handlers: Dict[str, JsonValue] = Field(sa_column=Column(JSON))
    agent_dependencies: dict = Field(
        sa_column=Column(MutableDict.as_mutable(JSON(none_as_null=True)), default={}),
        description="A dictionary containing agent dependencies.",
    )
    blueprints: List["Blueprint"] = Relationship(back_populates="agents", link_model=BlueprintAgentLink)

    @classmethod
    def from_base(cls, base: AgentEntry) -> "CatalogAgentEntry":
        return cls(
            agent_name=base.agent_name,
            qualified_class_name=base.qualified_class_name,
            agent_doc=base.agent_doc,
            message_handlers={key: value.model_dump() for key, value in base.message_handlers.items()},
            agent_props_schema=base.agent_props_schema,
            agent_dependencies={dep.dependency_key: dep.model_dump() for dep in base.agent_dependencies},
        )


class LaunchGuildFromBlueprintRequest(BaseModel):
    """
    Request to launch a guild from a blueprint.
    """

    guild_name: str
    user_id: str
    org_id: str
    description: Optional[str] = None
    configuration: dict = {}
    guild_id: Optional[str] = None
