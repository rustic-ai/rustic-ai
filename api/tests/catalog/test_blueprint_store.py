import os
import re

import pytest

from rustic_ai.api_server.catalog.catalog_store import BlueprintCreate, CatalogStore
from rustic_ai.api_server.catalog.models import (
    BlueprintCategoryCreate,
    BlueprintExposure,
    BlueprintReviewCreate,
)
from rustic_ai.core.agents.testutils.echo_agent import EchoAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metaprog.agent_registry import (
    AgentEntry,
    HandlerEntry,
    SendMessageCall,
)
from rustic_ai.core.guild.metastore.database import Metastore


class TestCatalogStore:
    @pytest.fixture
    def catalog_engine(self, request):
        # Generate unique database filename based on test name and worker
        test_name = request.node.name
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
        
        # Sanitize test name for filename
        sanitized_test_name = re.sub(r"[^\w\-_.]", "_", test_name)
        db_filename = f"catalog_store_test_{sanitized_test_name}_{worker_id}.db"
        db_url = f"sqlite:///{db_filename}"
        
        Metastore.drop_db(unsafe=True)
        Metastore.initialize_engine(db_url)
        yield Metastore.get_engine()
        Metastore.drop_db(unsafe=True)
        
        # Clean up database file
        try:
            os.remove(db_filename)
        except FileNotFoundError:
            pass

    @pytest.fixture
    def catalog_store(self, catalog_engine):
        return CatalogStore(catalog_engine)

    def test_blueprint_actions(self, catalog_store: CatalogStore):
        echo_agent = AgentEntry(
            agent_name="EchoAgent",
            qualified_class_name="rustic_ai.core.agents.testutils.echo_agent.EchoAgent",
            agent_doc="An Agent that echoes the received message back to the sender.",
            agent_props_schema={
                "description": "Empty class for Agent properties.",
                "properties": {},
                "title": "BaseAgentProps",
                "type": "object",
            },
            message_handlers={
                "echo_message": HandlerEntry(
                    handler_name="echo_message",
                    message_format="generic_json",
                    message_format_schema={"type": "object"},
                    handler_doc=None,
                    send_message_calls=[
                        SendMessageCall(
                            calling_class="EchoAgent",
                            calling_function="echo_message",
                            call_type="send_dict",
                            message_type="ctx.format",
                        )
                    ],
                )
            },
            agent_dependencies=[],
        )

        catalog_store.register_agent(echo_agent)
        guild = (
            GuildBuilder(
                guild_id="cataloged_guild", guild_name="Cataloged Guild", guild_description="A cataloged guild"
            )
            .add_agent_spec(
                AgentBuilder(EchoAgent)
                .set_id("echo_agent")
                .set_name("Echo Agent")
                .set_description("An echo agent")
                .build_spec()
            )
            .build_spec()
        )

        user_id = "75989303-52c6-42f3-b0fc-db74aa02521b"
        org_id = "eb5e409a-284d-47e8-87a6-d85d91204c61"

        category_create = BlueprintCategoryCreate(name="finance", description="Finance related blueprints")
        category_id = catalog_store.create_category(category_create)

        blueprint_create = BlueprintCreate(
            name="Test Blueprint",
            description="A test blueprint",
            exposure=BlueprintExposure.PRIVATE,
            author_id=user_id,
            organization_id=org_id,
            version="1.0.0",
            spec=guild.model_dump(),
            category_id=category_id,
            icon="icon.png",
        )
        blueprint_id = catalog_store.create_blueprint(blueprint_create)

        get_blueprint_response = catalog_store.get_blueprint(blueprint_id)

        assert get_blueprint_response is not None
        assert get_blueprint_response.name == blueprint_create.name
        assert get_blueprint_response.description == blueprint_create.description
        assert get_blueprint_response.exposure == blueprint_create.exposure
        assert get_blueprint_response.author_id == blueprint_create.author_id
        assert get_blueprint_response.organization_id == blueprint_create.organization_id
        assert get_blueprint_response.version == blueprint_create.version
        assert get_blueprint_response.spec == blueprint_create.spec.model_dump(
            exclude={"id": True, "agents": {"__all__": {"id"}}}  # type: ignore
        )
        assert get_blueprint_response.category_id == blueprint_create.category_id
        assert get_blueprint_response.tags == []

        catalog_store.add_tag_to_blueprint(blueprint_id, "test_tag")
        blueprints_by_tag = catalog_store.get_blueprints_by_tag("test_tag")
        assert len(blueprints_by_tag) > 0
        blueprint = blueprints_by_tag[0]
        assert blueprint.id == blueprint_id

        catalog_store.add_tag_to_blueprint(blueprint_id, "test_tag_2")
        blueprints_by_tag = catalog_store.get_blueprints_by_tag("test_tag_2")
        assert len(blueprints_by_tag) > 0
        blueprint = blueprints_by_tag[0]
        assert blueprint.id == blueprint_id

        catalog_store.remove_tag_from_blueprint(blueprint_id, "test_tag")
        updated_blueprint = catalog_store.get_blueprint(blueprint_id)
        assert updated_blueprint is not None
        assert updated_blueprint.tags == ["test_tag_2"]

        category_blueprints = catalog_store.get_blueprints_by_category("finance")
        assert len(category_blueprints) == 1
        assert category_blueprints[0].id == blueprint_id

        org2_id = "42dfd68b-cde7-405d-a7f9-d0f749865db6"
        catalog_store.share_blueprint(blueprint_id, org2_id)
        shared_blueprints = catalog_store.get_blueprints_shared_with_organization(org2_id)
        assert len(shared_blueprints) == 1
        assert shared_blueprints[0].id == blueprint_id

        catalog_store.unshare_blueprint(blueprint_id, org2_id)
        shared_blueprints = catalog_store.get_blueprints_shared_with_organization(org2_id)
        assert len(shared_blueprints) == 0

        review_create1 = BlueprintReviewCreate(
            blueprint_id=blueprint_id,
            rating=5,
            review="Great blueprint",
            user_id=user_id,
        )

        review_create2 = BlueprintReviewCreate(
            rating=3,
            review="Good blueprint",
            user_id=user_id,
        )

        catalog_store.create_blueprint_review(blueprint_id, review_create1)
        catalog_store.create_blueprint_review(blueprint_id, review_create2)

        reviews = catalog_store.get_blueprint_reviews(blueprint_id)

        assert reviews.total_reviews == 2
        assert reviews.average_rating == (5 + 3) / 2
        assert reviews.reviews[0].rating == 5
        assert reviews.reviews[0].review == "Great blueprint"
        assert reviews.reviews[1].rating == 3
        assert reviews.reviews[1].review == "Good blueprint"
