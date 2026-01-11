from typing import Dict, List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import Engine, join
from sqlmodel import Session, col, select

from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.metaprog.agent_registry import AgentEntry
from rustic_ai.core.guild.metastore import GuildModel

from .models import (
    AgentIcon,
    AgentNameWithIcon,
    BasicGuildInfo,
    Blueprint,
    BlueprintAgentIcon,
    BlueprintCategory,
    BlueprintCategoryCreate,
    BlueprintCategoryResponse,
    BlueprintCommand,
    BlueprintCreate,
    BlueprintDetailsResponse,
    BlueprintExposure,
    BlueprintGuild,
    BlueprintInfoResponse,
    BlueprintResponseWithAccessReason,
    BlueprintReview,
    BlueprintReviewCreate,
    BlueprintReviewResponse,
    BlueprintReviewsResponse,
    BlueprintSharedWithOrganization,
    BlueprintStarterPrompt,
    BlueprintTag,
    CatalogAgentEntry,
    Tag,
    UserGuild,
)


class CatalogStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_or_get_tags(self, tag_names: List[str]) -> List[Tag]:
        query = select(Tag).where(Tag.tag.in_(tag_names))  # type:ignore
        with Session(self.engine) as session:
            existing_tags = session.exec(query).all()
            existing_tag_names = {tag.tag for tag in existing_tags}
            new_tag_names = set(tag_names) - existing_tag_names
            new_tags = [Tag(tag=name) for name in new_tag_names]
            session.add_all(new_tags)
            session.commit()
            tags = session.exec(query).all()
            return list(tags)

    def create_blueprint(self, blueprint_create: BlueprintCreate) -> str:
        with Session(self.engine) as session:
            try:
                blueprint_details = blueprint_create.model_dump(
                    exclude={
                        "spec": True,
                        "tags": True,
                        "commands": True,
                        "starter_prompts": True,
                        "agent_icons": True,
                    }
                )
                blueprint = Blueprint.model_validate(blueprint_details)
                blueprint.spec = blueprint_create.spec
                session.add(blueprint)
                session.commit()
                session.refresh(blueprint)

                agent_specs = blueprint.spec.get("agents", [])
                unique_class_names = set()
                for agent in agent_specs:
                    class_name = agent["class_name"]
                    if class_name not in unique_class_names:
                        agent_entry = session.get(CatalogAgentEntry, class_name)
                        if agent_entry:
                            blueprint.agents.append(agent_entry)
                            unique_class_names.add(class_name)

                if blueprint_create.tags and len(blueprint_create.tags) > 0:
                    tags = self.create_or_get_tags(blueprint_create.tags)
                    blueprint.tags.extend(tags)
                if blueprint_create.commands and len(blueprint_create.commands) > 0:
                    commands = [
                        BlueprintCommand(command=command, blueprint_id=blueprint.id)
                        for command in blueprint_create.commands
                    ]
                    blueprint.commands.extend(commands)
                if blueprint_create.starter_prompts and len(blueprint_create.starter_prompts) > 0:
                    starter_prompts = [
                        BlueprintStarterPrompt(prompt=prompt, blueprint_id=blueprint.id)
                        for prompt in blueprint_create.starter_prompts
                    ]
                    blueprint.starter_prompts.extend(starter_prompts)

                session.commit()

                return blueprint.id

            except HTTPException:
                raise

    def get_blueprint(self, blueprint_id: str) -> Optional[BlueprintDetailsResponse]:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                return None
            return BlueprintDetailsResponse.from_table(blueprint)

    def get_blueprint_with_exposure(self, blueprint_id: str, user_id: str, org_id: str) -> Optional[Blueprint]:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail="Blueprint not found")
            if blueprint.exposure == BlueprintExposure.PUBLIC:
                return blueprint
            if blueprint.exposure == BlueprintExposure.PRIVATE and blueprint.author_id == user_id:
                return blueprint
            if blueprint.exposure == BlueprintExposure.ORGANIZATION and blueprint.organization_id == org_id:
                return blueprint
            if blueprint.exposure == BlueprintExposure.SHARED and org_id:
                statement = (
                    select(BlueprintSharedWithOrganization)
                    .where(BlueprintSharedWithOrganization.organization_id == org_id)
                    .where(BlueprintSharedWithOrganization.blueprint_id == blueprint_id)
                )
                entry = session.exec(statement).first()
                if entry:
                    return blueprint
            return None

    def add_tag_to_blueprint(self, blueprint_id: str, tag: str):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail="Blueprint not found")

            stored_tag = self.create_or_get_tags([tag])[0]
            etag = session.exec(
                select(BlueprintTag)
                .where(BlueprintTag.tag_id == stored_tag.id)
                .where(BlueprintTag.blueprint_id == blueprint_id)
            ).first()

            if etag:
                raise HTTPException(status_code=409, detail=f"Blueprint {blueprint_id} already tagged with {tag}")
            btag = BlueprintTag(tag_id=stored_tag.id, blueprint_id=blueprint_id)
            session.add(btag)
            session.commit()

    def remove_tag_from_blueprint(self, blueprint_id: str, tag: str):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail="Blueprint not found")
            stored_tag = session.exec(select(Tag).where(Tag.tag == tag)).first()
            if not stored_tag:
                raise HTTPException(status_code=404, detail=f"Tag {tag} not found")
            etag = session.exec(
                select(BlueprintTag)
                .where(BlueprintTag.tag_id == stored_tag.id)
                .where(BlueprintTag.blueprint_id == blueprint_id)
            ).first()

            if not etag:
                raise HTTPException(status_code=404, detail=f"Tag {tag} not found on blueprint {blueprint_id}")

            session.delete(etag)
            session.commit()

    def get_blueprints_by_tag(self, tag: str) -> List[BlueprintInfoResponse]:
        with Session(self.engine) as session:
            stmt = select(Blueprint).join(BlueprintTag).join(Tag).where(Tag.tag == tag)
        blueprints = session.exec(stmt).all()
        return [BlueprintInfoResponse.from_table(b) for b in blueprints]

    def get_blueprints_by_category(self, category_name: str) -> List[BlueprintInfoResponse]:
        with Session(self.engine) as session:
            category = session.exec(select(BlueprintCategory).where(BlueprintCategory.name == category_name)).first()
            if not category:
                raise HTTPException(status_code=404, detail=f"Category {category_name} not found")

            return [BlueprintInfoResponse.from_table(b) for b in category.blueprints]

    def get_blueprints_by_author(self, author_id: str) -> List[BlueprintInfoResponse]:
        with Session(self.engine) as session:
            statement = select(Blueprint).where(Blueprint.author_id == author_id)
            blueprints = session.exec(statement).all()
            return [BlueprintInfoResponse.from_table(b) for b in blueprints]

    def get_blueprints_by_organization(self, organization_id: str) -> List[BlueprintInfoResponse]:
        with Session(self.engine) as session:
            statement = select(Blueprint).where(Blueprint.organization_id == organization_id)
            blueprints = session.exec(statement).all()
            return [BlueprintInfoResponse.from_table(b) for b in blueprints]

    def share_blueprint(self, blueprint_id: str, organization_id: str):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            # Ensure orginal organization has access when sharing bp with org exposure
            if blueprint.exposure == BlueprintExposure.ORGANIZATION:
                session.add(
                    BlueprintSharedWithOrganization(
                        organization_id=blueprint.organization_id, blueprint_id=blueprint_id
                    )
                )

            blueprint.sqlmodel_update({"exposure": BlueprintExposure.SHARED})
            shared_with_organizations = BlueprintSharedWithOrganization(
                organization_id=organization_id, blueprint_id=blueprint_id
            )

            session.add(blueprint)
            session.add(shared_with_organizations)
            session.commit()

    def unshare_blueprint(self, blueprint_id: str, organization_id: str):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            statement = (
                select(BlueprintSharedWithOrganization)
                .where(BlueprintSharedWithOrganization.organization_id == organization_id)
                .where(BlueprintSharedWithOrganization.blueprint_id == blueprint_id)
            )
            entry = session.exec(statement).first()
            session.delete(entry)
            session.commit()

    @staticmethod
    def _get_bps_shared_with_org(session: Session, organization_id: str):
        statement = (
            select(Blueprint)
            .join(BlueprintSharedWithOrganization)
            .where(BlueprintSharedWithOrganization.organization_id == organization_id)
        )
        shared_blueprints = session.exec(statement).all()
        return shared_blueprints

    def get_blueprints_shared_with_organization(self, organization_id: str) -> List[BlueprintInfoResponse]:
        with Session(self.engine) as session:
            shared_blueprints = self._get_bps_shared_with_org(session, organization_id)
            return [BlueprintInfoResponse.from_table(b) for b in shared_blueprints]

    def get_organization_with_shared_blueprint(self, blueprint_id: str) -> List[str]:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            statement = select(BlueprintSharedWithOrganization).where(
                BlueprintSharedWithOrganization.blueprint_id == blueprint_id
            )
            shared_organizations = session.exec(statement).all()
            return [bp_org.organization_id for bp_org in shared_organizations]

    def create_blueprint_review(self, blueprint_id: str, review_model: BlueprintReviewCreate) -> str:
        with Session(self.engine) as session:
            review = BlueprintReview.model_validate({"blueprint_id": blueprint_id, **review_model.model_dump()})

            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            session.add(review)
            session.commit()
            session.refresh(review)
            return review.id

    def get_blueprint_reviews(self, blueprint_id: str) -> BlueprintReviewsResponse:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            reviews = [BlueprintReviewResponse.model_validate(r) for r in blueprint.reviews]
            return BlueprintReviewsResponse(reviews=reviews)

    def get_blueprint_review(self, review_id: str) -> BlueprintReviewResponse:
        with Session(self.engine) as session:
            review = session.get(BlueprintReview, review_id)
            return BlueprintReviewResponse.model_validate(review)

    @staticmethod
    def _blueprint_with_org_access(
        blueprint: Blueprint, org_id: Optional[str] = None
    ) -> BlueprintResponseWithAccessReason:
        blueprint_info = BlueprintInfoResponse.from_table(blueprint).model_dump()
        return BlueprintResponseWithAccessReason(**blueprint_info, access_organization_id=org_id)

    def get_user_accessible_blueprints(
        self, user_id: str, org_id: Optional[str]
    ) -> List[BlueprintResponseWithAccessReason]:
        with Session(self.engine) as session:

            public_blueprints_list = session.exec(
                select(Blueprint).where(Blueprint.exposure == BlueprintExposure.PUBLIC)
            ).all()

            public_blueprints: Dict[str, BlueprintResponseWithAccessReason] = {
                b.id: self._blueprint_with_org_access(b) for b in public_blueprints_list
            }

            owned_blueprints_list = session.exec(select(Blueprint).where(Blueprint.author_id == user_id)).all()

            owned_blueprints: Dict[str, BlueprintResponseWithAccessReason] = {
                b.id: self._blueprint_with_org_access(b) for b in owned_blueprints_list
            }

            accessible_bps = {**public_blueprints, **owned_blueprints}

            if org_id and org_id.strip():
                org_blueprints_list = session.exec(
                    select(Blueprint)
                    .where(Blueprint.organization_id == org_id)
                    .where(Blueprint.exposure == BlueprintExposure.ORGANIZATION)
                ).all()
                org_owned_blueprints: Dict[str, BlueprintResponseWithAccessReason] = {
                    b.id: self._blueprint_with_org_access(b, org_id=org_id) for b in org_blueprints_list
                }

                shared_blueprints_list = self._get_bps_shared_with_org(session, org_id)
                shared_blueprints: Dict[str, BlueprintResponseWithAccessReason] = {
                    b.id: self._blueprint_with_org_access(b, org_id=org_id) for b in shared_blueprints_list
                }

                accessible_bps = {**public_blueprints, **owned_blueprints, **org_owned_blueprints, **shared_blueprints}

            return list(accessible_bps.values())

    def create_category(self, category_create: BlueprintCategoryCreate) -> str:
        with Session(self.engine) as session:
            category = BlueprintCategory.model_validate(category_create)
            session.add(category)
            session.commit()
            session.refresh(category)
            return category.id

    def get_category(self, category_id: str) -> BlueprintCategoryResponse:
        with Session(self.engine) as session:
            category = session.get(BlueprintCategory, category_id)
            return BlueprintCategoryResponse.model_validate(category)

    def get_categories(self) -> List[BlueprintCategory]:
        with Session(self.engine) as session:
            categories = session.exec(select(BlueprintCategory)).all()
            return list(categories)

    def get_tags(self) -> List[str]:
        with Session(self.engine) as session:
            tags = session.exec(select(Tag.tag).distinct()).all()
            return [t for t in tags]

    def add_guild_to_blueprint(self, blueprint_id: str, guild_id: str):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

            guild_model = session.get(GuildModel, guild_id)
            if not guild_model:
                raise HTTPException(status_code=404, detail=f"Guild {guild_id} not found")

            existing_mapping = session.get(BlueprintGuild, guild_id)

            if existing_mapping:
                raise HTTPException(status_code=409, detail=f"Guild {guild_id} is already associated with a blueprint")
            b_guild = BlueprintGuild(guild_id=guild_id, blueprint_id=blueprint_id)
            session.add(b_guild)
            session.commit()

    def get_blueprint_for_guild(self, guild_id: str) -> Optional[BlueprintDetailsResponse]:
        with Session(self.engine) as session:
            guild_model = session.get(GuildModel, guild_id)
            if not guild_model:
                raise HTTPException(status_code=404, detail=f"Guild {guild_id} not found")

            statement = select(Blueprint).join(BlueprintGuild).where(BlueprintGuild.guild_id == guild_id)
            blueprint = session.exec(statement).first()
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"No Blueprint associated with guild {guild_id}")
            return BlueprintDetailsResponse.from_table(blueprint)

    @staticmethod
    def get_user_guild(session, user_id: str, guild_id: str):
        guild = session.get(GuildModel, guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail=f"Guild {guild_id} not found")

        return session.get(UserGuild, {"guild_id": guild_id, "user_id": user_id})

    def get_guilds_for_org(self, org_id: str, statuses: Optional[List[str]] = None) -> List[BasicGuildInfo]:
        with Session(self.engine) as session:
            statement = (
                select(
                    GuildModel.id,
                    GuildModel.name,
                    Blueprint.id.label("blueprint_id"),  # type:ignore
                    Blueprint.icon,
                    GuildModel.status,
                )
                .select_from(GuildModel)
                .outerjoin(BlueprintGuild, GuildModel.id == BlueprintGuild.guild_id)  # type:ignore
                .outerjoin(Blueprint, Blueprint.id == BlueprintGuild.blueprint_id)  # type:ignore
                .where(GuildModel.organization_id == org_id)
            )

            if statuses:
                statement = statement.where(GuildModel.status.in_(statuses))

            guilds: Sequence[BasicGuildInfo] = session.exec(statement).all()  # type:ignore
            return list(guilds)

    def add_user_to_guild(self, guild_id: str, user_id: str):
        with Session(self.engine) as session:
            existing_mapping = self.get_user_guild(session, user_id, guild_id)
            if existing_mapping:
                raise HTTPException(status_code=409, detail=f"User {user_id} already associated with guild {guild_id}")

            session.add(UserGuild(guild_id=guild_id, user_id=user_id))
            session.commit()

    def remove_user_from_guild(self, guild_id: str, user_id: str):
        with Session(self.engine) as session:
            existing_mapping = self.get_user_guild(session, user_id, guild_id)
            if not existing_mapping:
                raise HTTPException(status_code=404, detail=f"User {user_id} is not associated with guild {guild_id}")

            session.delete(existing_mapping)
            session.commit()

    def get_guilds_for_user(
        self, user_id, org_id: Optional[str] = None, statuses: Optional[List[str]] = None
    ) -> List[BasicGuildInfo]:
        with Session(self.engine) as session:
            statement = (
                select(
                    GuildModel.id,
                    GuildModel.name,
                    Blueprint.id.label("blueprint_id"),  # type:ignore
                    Blueprint.icon,
                    GuildModel.status,
                )
                .select_from(
                    join(GuildModel, UserGuild, GuildModel.id == UserGuild.guild_id)  # type:ignore
                    .outerjoin(BlueprintGuild, GuildModel.id == BlueprintGuild.guild_id)  # type:ignore
                    .outerjoin(Blueprint, Blueprint.id == BlueprintGuild.blueprint_id)  # type:ignore
                )
                .where(UserGuild.user_id == user_id)
            )

            if org_id:
                statement = statement.where(GuildModel.organization_id == org_id)

            if statuses:
                statement = statement.where(GuildModel.status.in_(statuses))

            guilds: Sequence[BasicGuildInfo] = session.exec(statement).all()  # type:ignore
            return list(guilds)

    def get_users_for_guild(self, guild_id: str) -> List[str]:
        """Get all user IDs associated with a given guild."""
        with Session(self.engine) as session:
            guild = session.get(GuildModel, guild_id)
            if not guild:
                raise HTTPException(status_code=404, detail=f"Guild {guild_id} not found")

            statement = select(UserGuild.user_id).where(UserGuild.guild_id == guild_id)
            user_ids: Sequence[str] = session.exec(statement).all()  # type:ignore
            return list(user_ids)

    def add_agent_icon(self, agent_class: str, icon: str):
        with Session(self.engine) as session:
            existing_icon = session.get(AgentIcon, agent_class)
            if existing_icon:
                existing_icon.icon = icon
            else:
                session.add(AgentIcon(agent_class=agent_class, icon=icon))
            session.commit()

    def _get_default_agent_icons(self, guildspec: GuildSpec):
        with Session(self.engine) as session:
            agent_classes: set[str] = set([agent.class_name for agent in guildspec.agents])
            default_agent_icons: Sequence[AgentIcon] = session.exec(
                select(AgentIcon).where(col(AgentIcon.agent_class).in_(agent_classes))
            ).all()
            agent_icons_by_class = {agent_icon.agent_class: agent_icon.icon for agent_icon in default_agent_icons}
            return agent_icons_by_class

    def add_agent_icons_to_blueprint(self, blueprint_id: str, provided_icons: list[AgentNameWithIcon]):
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")
            guild_specs = GuildSpec.model_validate(blueprint.spec)
            agent_names = [x.name for x in guild_specs.agents]
            provided_agent_names = [a.agent_name for a in provided_icons] if provided_icons else []
            if provided_agent_names and not set(provided_agent_names).issubset(set(agent_names)):
                raise HTTPException(
                    status_code=400,
                    detail="Provided agent names are not a subset of the agent names in the blueprint",
                )
            existing_icons = session.exec(
                select(BlueprintAgentIcon).where(BlueprintAgentIcon.blueprint_id == blueprint_id)
            ).all()
            existing_icon_names = []
            for icon in existing_icons:
                if icon.agent_name in provided_agent_names:
                    agent_details: AgentNameWithIcon = provided_icons[provided_agent_names.index(icon.agent_name)]
                    icon.icon = agent_details.icon
                    existing_icon_names.append(icon.agent_name)
            new_icons = [
                BlueprintAgentIcon(blueprint_id=blueprint_id, agent_name=x.agent_name, icon=x.icon)
                for x in provided_icons
                if x.agent_name not in existing_icon_names
            ]
            if len(new_icons) > 0:
                session.add_all(new_icons)
            session.commit()

    def get_blueprint_agent_icons(self, blueprint_id: str) -> list[AgentNameWithIcon]:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")
            bp_agent_icons: Sequence[AgentNameWithIcon] = session.exec(
                select(BlueprintAgentIcon).where(BlueprintAgentIcon.blueprint_id == blueprint_id)
            ).all()
            guild_specs = GuildSpec.model_validate(blueprint.spec)
            result: list[AgentNameWithIcon] = list(bp_agent_icons)
            existing_icons = [agent_icon.agent_name for agent_icon in bp_agent_icons]
            default_icons = self._get_default_agent_icons(guild_specs)
            missing_icons = filter(
                lambda x: x.name not in existing_icons and x.class_name in default_icons, guild_specs.agents
            )
            for agent in missing_icons:
                icon_info = AgentNameWithIcon(agent_name=agent.name, icon=default_icons[agent.class_name])
                result.append(icon_info)
            return result

    def get_blueprint_agent_icon_by_name(self, blueprint_id: str, agent_name: str) -> AgentNameWithIcon:
        with Session(self.engine) as session:
            blueprint = session.get(Blueprint, blueprint_id)
            if not blueprint:
                raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")
            guild_specs = GuildSpec.model_validate(blueprint.spec)
            valid_agent_names = [x.name for x in guild_specs.agents]
            if agent_name and agent_name not in valid_agent_names:
                raise HTTPException(status_code=404, detail=f"Agent {agent_name} does not exist")
            agent_icon: Optional[AgentNameWithIcon] = session.exec(
                select(BlueprintAgentIcon)
                .where(BlueprintAgentIcon.blueprint_id == blueprint_id)
                .where(BlueprintAgentIcon.agent_name == agent_name)
            ).first()
            if agent_icon:
                return AgentNameWithIcon.model_validate(agent_icon)
            default_icons = self._get_default_agent_icons(guild_specs)
            if agent_name in default_icons.keys():
                return AgentNameWithIcon(agent_name=agent_name, icon=default_icons[agent_name])
            else:
                raise HTTPException(status_code=404, detail=f"Agent {agent_name} does not have an icon")

    def register_agent(self, agent_spec: AgentEntry):
        with Session(self.engine) as session:
            query = select(CatalogAgentEntry).where(
                CatalogAgentEntry.qualified_class_name == agent_spec.qualified_class_name
            )
            existing_agent = session.exec(query).first()
            if existing_agent:
                raise HTTPException(status_code=409, detail=f"'{agent_spec.qualified_class_name}' already exists")

            else:
                agent_entry = CatalogAgentEntry.from_base(agent_spec)
                session.add(agent_entry)
                session.commit()

    def get_agent_by_class_name(self, qualified_class_name: str) -> AgentEntry:
        with Session(self.engine) as session:
            agent_entry = session.exec(
                select(CatalogAgentEntry).where(CatalogAgentEntry.qualified_class_name == qualified_class_name)
            ).first()

            if not agent_entry:
                raise HTTPException(
                    status_code=404, detail=f"Agent with qualified class name {qualified_class_name} not found"
                )
            return AgentEntry.model_validate(
                {**agent_entry.model_dump(), "agent_dependencies": list(agent_entry.agent_dependencies.values())}
            )

    def get_agents(self, class_names: Optional[List[str]] = None, hidden_agents: Optional[List[str]] = None) -> dict:
        with Session(self.engine) as session:
            query = select(CatalogAgentEntry)

            if class_names:
                query = query.where(col(CatalogAgentEntry.qualified_class_name).in_(class_names))

            if hidden_agents:
                query = query.where(~col(CatalogAgentEntry.qualified_class_name).in_(hidden_agents))

            agents = session.exec(query).all()

            if not agents:
                return {}

            return {
                agent.qualified_class_name: AgentEntry.model_validate(
                    {**agent.model_dump(), "agent_dependencies": list(agent.agent_dependencies.values())}
                )
                for agent in agents
            }

    def get_agent_by_message_format(self, message_format: str):
        with Session(self.engine) as session:
            # Get all agent entries
            agent_entries = session.exec(select(CatalogAgentEntry)).all()
            # TODO: See if we need another table to store message format or message schema
            for agent_entry in agent_entries:
                handlers = agent_entry.message_handlers or {}
                for handler_data in handlers.values():
                    if isinstance(handler_data, dict) and handler_data.get("message_format") == message_format:
                        return handler_data.get("message_format_schema")

            raise HTTPException(status_code=404, detail=f"Agent with message format '{message_format}' not found")
