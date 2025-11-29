# Routes to work with the Catalog models

from copy import deepcopy
from typing import Annotated, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.params import Query
from jsonschema import exceptions as jsonschema_exceptions
from jsonschema import validate
from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine
from starlette import status

from rustic_ai.api_server.guilds.schema import IdInfo
from rustic_ai.api_server.guilds.service import GuildService
from rustic_ai.core.guild.builders import GuildBuilder, KeyConstants
from rustic_ai.core.guild.metaprog.agent_registry import AgentEntry
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.guild.metastore.models import GuildStatus

from .catalog_store import CatalogStore
from .models import (
    AgentNameWithIcon,
    BasicGuildInfo,
    BlueprintAgentsIconReqRes,
    BlueprintCategoryCreate,
    BlueprintCategoryResponse,
    BlueprintCreate,
    BlueprintDetailsResponse,
    BlueprintInfoResponse,
    BlueprintResponseWithAccessReason,
    BlueprintReviewCreate,
    BlueprintReviewResponse,
    BlueprintReviewsResponse,
    LaunchGuildFromBlueprintRequest,
)

catalog_router = APIRouter()
guild_service = GuildService()


def validate_guild_configuration(schema: dict, data: dict):
    try:
        validate(instance=data, schema=schema)
    except jsonschema_exceptions.ValidationError as e:
        raise HTTPException(status_code=400, detail=f"configuration and/or schema invalid. {e.message}")
    return data


@catalog_router.post(
    "/blueprints/",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBlueprint",
    tags=["blueprints"],
)
async def create_blueprint(blueprint: BlueprintCreate, engine: Engine = Depends(Metastore.get_engine)):
    try:
        if KeyConstants.CONFIGURATION_SCHEMA in blueprint.spec and KeyConstants.CONFIGURATION in blueprint.spec:
            validate_guild_configuration(
                blueprint.spec[KeyConstants.CONFIGURATION_SCHEMA], blueprint.spec[KeyConstants.CONFIGURATION]
            )
        elif KeyConstants.CONFIGURATION in blueprint.spec:
            raise HTTPException(status_code=400, detail=f"{KeyConstants.CONFIGURATION_SCHEMA} is required")
        elif KeyConstants.CONFIGURATION_SCHEMA in blueprint.spec:
            raise HTTPException(status_code=400, detail=f"{KeyConstants.CONFIGURATION} is required")

        # Validate GuildSpec can be built
        blueprint.spec.pop(KeyConstants.ID, None)
        spec_copy = deepcopy(blueprint.spec)  # deepcopy to prevent modification of the original spec
        valid_guild_spec = GuildBuilder._from_spec_dict(spec_copy).build_spec()

        for agent in valid_guild_spec.agents:
            class_name = agent.class_name
            try:
                CatalogStore(engine).get_agent_by_class_name(class_name)
            except Exception:
                raise HTTPException(status_code=400, detail=f"Agent not found for class_name: {class_name}")
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid GuildSpec: {e}")
    blueprint_id = CatalogStore(engine).create_blueprint(blueprint)
    return IdInfo(id=blueprint_id)


@catalog_router.get(
    "/blueprints/{blueprint_id}",
    response_model=BlueprintDetailsResponse,
    operation_id="getBlueprintById",
    tags=["blueprints"],
)
async def get_blueprint(blueprint_id: str, engine: Engine = Depends(Metastore.get_engine)):
    blueprint = CatalogStore(engine).get_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return blueprint


@catalog_router.get(
    "/organizations/{organization_id}/blueprints/owned/",
    response_model=List[BlueprintInfoResponse],
    operation_id="getOrganizationBlueprints",
    tags=["blueprints", "organizations"],
)
async def get_organization_blueprints(organization_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprints_by_organization(organization_id)


@catalog_router.get(
    "/users/{user_id}/blueprints/owned/",
    response_model=List[BlueprintInfoResponse],
    operation_id="getUserBlueprints",
    tags=["blueprints", "users"],
)
async def get_user_blueprints(user_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprints_by_author(user_id)


@catalog_router.get(
    "/users/{user_id}/blueprints/accessible/",
    response_model=List[BlueprintResponseWithAccessReason],
    operation_id="getAccessibleBlueprintsByUserId",
    tags=["blueprints", "users"],
)
async def get_user_accessible_blueprints(
    user_id: str, org_id: Annotated[str | None, Query()] = None, engine: Engine = Depends(Metastore.get_engine)
):
    return CatalogStore(engine).get_user_accessible_blueprints(user_id, org_id)


class ShareWithOrgRequest(BaseModel):
    organization_id: str


@catalog_router.post(
    "/blueprints/{blueprint_id}/share/",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="shareBlueprintWithOrganization",
    tags=["blueprints", "organizations"],
)
async def share_blueprint_with_organization(
    blueprint_id: str, sbr: ShareWithOrgRequest, engine: Engine = Depends(Metastore.get_engine)
):
    share_status = CatalogStore(engine).share_blueprint(blueprint_id, sbr.organization_id)
    if share_status:
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.delete(
    "/blueprints/{blueprint_id}/share/{organization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unshareBlueprintWithOrganization",
    tags=["blueprints", "organizations"],
)
async def unshare_blueprint_with_organization(
    blueprint_id: str, organization_id: str, engine: Engine = Depends(Metastore.get_engine)
):
    unshare_status = CatalogStore(engine).unshare_blueprint(blueprint_id, organization_id)
    if unshare_status:
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.get(
    "/organizations/{organization_id}/blueprints/shared/",
    response_model=List[BlueprintInfoResponse],
    operation_id="getSharedBlueprintsByOrganizationId",
    tags=["blueprints", "organizations"],
)
async def get_organization_shared_blueprints(organization_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprints_shared_with_organization(organization_id)


@catalog_router.get(
    "/blueprints/{blueprint_id}/organizations/shared/",
    response_model=List[str],
    operation_id="getSharedOrganizationsByBlueprintId",
    tags=["blueprints", "organizations"],
)
async def get_blueprint_shared_organizations(blueprint_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_organization_with_shared_blueprint(blueprint_id)


@catalog_router.get(
    "/categories/{category_id}", response_model=BlueprintCategoryResponse, operation_id="getCategoryById"
)
async def get_category(category_id: str, engine: Engine = Depends(Metastore.get_engine)):
    category = CatalogStore(engine).get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@catalog_router.post(
    "/categories/",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCategory",
)
async def create_category(category: BlueprintCategoryCreate, engine: Engine = Depends(Metastore.get_engine)):
    category_id = CatalogStore(engine).create_category(category)
    return IdInfo(id=category_id)


@catalog_router.get(
    "/categories/",
    response_model=List[BlueprintCategoryResponse],
    status_code=status.HTTP_200_OK,
    operation_id="listCategories",
)
async def list_categories(engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_categories()


@catalog_router.get(
    "/categories/{category_name}/blueprints/",
    response_model=List[BlueprintCategoryResponse],
    operation_id="getBlueprintsByCategoryName",
    tags=["blueprints"],
)
async def get_category_blueprints(category_name: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprints_by_category(category_name)


@catalog_router.get(
    "/tags/{tag}/blueprints/",
    response_model=List[BlueprintInfoResponse],
    operation_id="getBlueprintsByTag",
    tags=["blueprints"],
)
async def get_blueprints_by_tag(tag: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprints_by_tag(tag)


@catalog_router.post(
    "/blueprints/{blueprint_id}/reviews/",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBlueprintReview",
    tags=["blueprints"],
)
async def create_review(
    blueprint_id: str, review: BlueprintReviewCreate, engine: Engine = Depends(Metastore.get_engine)
):
    review_id = CatalogStore(engine).create_blueprint_review(blueprint_id, review)
    return IdInfo(id=review_id)


@catalog_router.get(
    "/blueprints/{blueprint_id}/reviews/",
    response_model=BlueprintReviewsResponse,
    operation_id="getReviewsByBlueprintId",
    tags=["blueprints"],
)
async def get_blueprint_reviews(blueprint_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprint_reviews(blueprint_id)


@catalog_router.get(
    "/blueprints/{blueprint_id}/reviews/{review_id}",
    response_model=BlueprintReviewResponse,
    operation_id="getBlueprintReview",
)
async def get_blueprint_review(blueprint_id: str, review_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprint_review(review_id)


@catalog_router.get("/tags/", response_model=List[str], operation_id="listTags", tags=["blueprints"])
async def list_tags(engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_tags()


@catalog_router.get(
    "/guilds/{guild_id}/blueprints/",
    response_model=BlueprintDetailsResponse,
    operation_id="getBlueprintForGuild",
    tags=["blueprints"],
)
async def get_blueprint_for_guild(guild_id: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_blueprint_for_guild(guild_id)


@catalog_router.post(
    "/guilds/{guild_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="addUserToGuild",
    tags=["users"],
)
async def add_user_to_guild(guild_id: str, user_id: str, engine: Engine = Depends(Metastore.get_engine)):
    CatalogStore(engine).add_user_to_guild(guild_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.get(
    "/users/{user_id}/guilds/",
    response_model=List[BasicGuildInfo],
    operation_id="getGuildsForUser",
    tags=["users"],
)
async def get_guilds_for_user(
    user_id: str,
    org_id: Annotated[str | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    engine: Engine = Depends(Metastore.get_engine),
):
    if statuses:
        valid_statuses = [s.value for s in GuildStatus]
        invalid_statuses = [s for s in statuses if s not in valid_statuses]
        if invalid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status values: {invalid_statuses}. Valid statuses are: {valid_statuses}",
            )

    return CatalogStore(engine).get_guilds_for_user(user_id, org_id, statuses)


@catalog_router.delete(
    "/guilds/{guild_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="removeUserFromGuild",
    tags=["users"],
)
async def remove_user_from_guild(guild_id: str, user_id: str, engine: Engine = Depends(Metastore.get_engine)):
    CatalogStore(engine).remove_user_from_guild(guild_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.get(
    "/organizations/{organization_id}/guilds/",
    response_model=List[BasicGuildInfo],
    operation_id="getGuildsForOrganization",
    tags=["organizations"],
)
async def get_guilds_for_organization(
    organization_id: str,
    statuses: Annotated[list[str] | None, Query()] = None,
    engine: Engine = Depends(Metastore.get_engine),
):
    if statuses:
        valid_statuses = [s.value for s in GuildStatus]
        invalid_statuses = [s for s in statuses if s not in valid_statuses]
        if invalid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status values: {invalid_statuses}. Valid statuses are: {valid_statuses}",
            )

    return CatalogStore(engine).get_guilds_for_org(organization_id, statuses)


@catalog_router.post(
    "/blueprints/{blueprint_id}/icons/",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="addBlueprintAgentIcons",
    tags=["blueprints"],
)
async def add_bp_agent_icons(
    blueprint_id: str, req_data: BlueprintAgentsIconReqRes, engine: Engine = Depends(Metastore.get_engine)
):
    if len(req_data.agent_icons) == 0:
        raise HTTPException(status_code=400, detail="No agent icons provided")
    CatalogStore(engine).add_agent_icons_to_blueprint(blueprint_id, req_data.agent_icons)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.get(
    "/blueprints/{blueprint_id}/icons/",
    response_model=BlueprintAgentsIconReqRes,
    operation_id="getBlueprintAgentIcons",
    tags=["blueprints"],
)
async def get_bp_agent_icons(blueprint_id: str, engine: Engine = Depends(Metastore.get_engine)):
    result = CatalogStore(engine).get_blueprint_agent_icons(blueprint_id)
    return BlueprintAgentsIconReqRes(agent_icons=result)


@catalog_router.post(
    "/blueprints/{blueprint_id}/icons/{agent_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="addBlueprintAgentIconByName",
    tags=["blueprints"],
)
async def add_bp_agent_icon_by_name(
    blueprint_id: str,
    agent_name: str,
    agent_icon: Annotated[str, Body(embed=True)],
    engine: Engine = Depends(Metastore.get_engine),
):
    if not agent_icon:
        raise HTTPException(status_code=400, detail="No agent icon provided")
    data = [AgentNameWithIcon(agent_name=agent_name, icon=agent_icon)]
    CatalogStore(engine).add_agent_icons_to_blueprint(blueprint_id, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@catalog_router.get(
    "/blueprints/{blueprint_id}/icons/{agent_name}",
    response_model=AgentNameWithIcon,
    operation_id="getBlueprintAgentIconByName",
    tags=["blueprints"],
)
async def get_bp_agent_icons_by_name(
    blueprint_id: str, agent_name: str, engine: Engine = Depends(Metastore.get_engine)
):
    return CatalogStore(engine).get_blueprint_agent_icon_by_name(blueprint_id, agent_name)


@catalog_router.post("/agents", status_code=status.HTTP_201_CREATED, operation_id="registerAgent", tags=["agents"])
def register_agent(
    agent_spec: AgentEntry,
    engine: Engine = Depends(Metastore.get_engine),
):
    try:
        agent = AgentEntry.model_validate(agent_spec)
        CatalogStore(engine).register_agent(agent)

        return Response(status_code=status.HTTP_201_CREATED)

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())


@catalog_router.get(
    "/agents",
    response_model=Dict[str, AgentEntry],
    operation_id="getAgents",
    tags=["agents"],
)
def get_agents(
    class_names: Annotated[list[str] | None, Query()] = None, engine: Engine = Depends(Metastore.get_engine)
):
    hidden_agents = [
        "rustic_ai.agents.system.guild_manager_agent.GuildManagerAgent",
        "rustic_ai.agents.utils.probe_agent.ProbeAgent",
        "rustic_ai.agents.utils.probe_agent.EssentialProbeAgent",
    ]
    return CatalogStore(engine).get_agents(class_names, hidden_agents)


@catalog_router.get(
    "/agents/{class_name}",
    response_model=AgentEntry,
    operation_id="getAgentByClassName",
    tags=["agents"],
)
def get_agent(class_name: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_agent_by_class_name(class_name)


@catalog_router.get(
    "/agents/message_schema/",
    response_model=dict,
    operation_id="getMessageSchemaByFormat",
    tags=["agents"],
)
def get_message_schema(message_format: str, engine: Engine = Depends(Metastore.get_engine)):
    return CatalogStore(engine).get_agent_by_message_format(message_format)


@catalog_router.post(
    "/blueprints/{blueprint_id}/guilds",
    response_model=IdInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="launchGuildFromBlueprint",
    tags=["blueprints", "guilds"],
)
async def launch_guild_from_blueprint(
    blueprint_id: str, launch_request: LaunchGuildFromBlueprintRequest, engine: Engine = Depends(Metastore.get_engine)
):
    blueprint = CatalogStore(engine).get_blueprint_with_exposure(
        blueprint_id, launch_request.user_id, launch_request.org_id
    )
    if not blueprint:
        raise HTTPException(status_code=403, detail="Insufficient permissions to launch")

    spec = deepcopy(blueprint.spec)  # deepcopy to prevent modification of the original spec
    try:
        if KeyConstants.CONFIGURATION_SCHEMA in spec:
            configuration = {**spec[KeyConstants.CONFIGURATION], **launch_request.configuration}
            validate_guild_configuration(spec[KeyConstants.CONFIGURATION_SCHEMA], configuration)
            spec[KeyConstants.CONFIGURATION] = configuration

        guild_spec = GuildBuilder._from_spec_dict(spec).build_spec()

        # Update the guild id if provided
        if launch_request.guild_id is not None:
            guild_spec.id = launch_request.guild_id

        # Update the guild name
        guild_spec.name = launch_request.guild_name

        # Update the description if provided
        if launch_request.description is not None:
            guild_spec.description = launch_request.description

        guild_id = guild_service.create_guild(Metastore.get_db_url(), guild_spec, launch_request.org_id)

        # Add the user to the guild
        CatalogStore(engine).add_user_to_guild(guild_id, launch_request.user_id)

        # Add the guild to the blueprint
        CatalogStore(engine).add_guild_to_blueprint(blueprint_id, guild_id)

        return IdInfo(id=guild_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())


@catalog_router.get(
    "/guilds/{guild_id}/users",
    response_model=List[str],
    status_code=status.HTTP_200_OK,
    operation_id="getUsersAddedToGuild",
    tags=["guilds"],
)
async def get_guild_users(guild_id: str, engine: Engine = Depends(Metastore.get_engine)):
    """Get the list of users added to a guild. This includes both active and inactive users."""
    result = CatalogStore(engine).get_users_for_guild(guild_id)
    return result
