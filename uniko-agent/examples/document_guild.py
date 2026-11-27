"""Local persistent document guild: python uniko-agent/examples/document_guild.py --storage /tmp/documents."""

import argparse
import json
from pathlib import Path
import time

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.messaging.core.message import ProcessStatus
from rustic_ai.uniko_agent import (
    DocumentCoordinatorAgent,
    DocumentCoordinatorConfig,
    DocumentWorkflowError,
    DocumentWorkflowRequest,
    DocumentWorkflowResult,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgent,
    MemoryAgentConfig,
    MemoryAgentError,
    MemorySource,
    RecallRequest,
    RecallResponse,
)


def build_document_guild(storage_root: str) -> GuildBuilder:
    coordinator = (
        AgentBuilder(DocumentCoordinatorAgent)
        .set_id("documents")
        .set_name("Documents")
        .set_description("Ingestion barriers and bounded evidence")
        .set_properties(DocumentCoordinatorConfig(corpus_session_id="corpus:references", memory_agent_id="memory"))
        .listen_to_default_topic(False)
        .add_additional_topic("documents.requests")
        .add_additional_topic("memory.results")
        .build_spec()
    )
    memory = (
        AgentBuilder(MemoryAgent)
        .set_id("memory")
        .set_name("Corpus Memory")
        .set_description("Private native document store")
        .set_properties(
            MemoryAgentConfig(
                allowed_record_producers={"external_evidence": ["documents"]}, scope_producers=["documents"]
            )
        )
        .listen_to_default_topic(False)
        .add_additional_topic("memory.commands")
        .build_spec()
    )
    caller = (
        AgentBuilder(ProbeAgent)
        .set_id("caller")
        .set_name("Caller")
        .set_description("Typed workflow caller")
        .listen_to_default_topic(False)
        .add_additional_topic("documents.results")
        .build_spec()
    )
    builder = GuildBuilder("document-foundation", "Document Foundation", "Local persistent ingestion and recall")
    builder.set_dependency_map(
        {
            "filesystem": DependencySpec(
                class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
                properties={
                    "protocol": "file",
                    "path_base": str(Path(storage_root).resolve()),
                    "storage_options": {"auto_mkdir": True},
                },
            ),
            "uniko": DependencySpec(
                class_name="rustic_ai.uniko_agent.UnikoResolver",
                properties={"storage_path": "corpus.db", "streaming": False},
            ),
        }
    )
    for spec in (coordinator, memory, caller):
        builder.add_agent_spec(spec)
    for producer, formats, topic, status in (
        (coordinator, (IngestDocumentRequest, RecallRequest), "memory.commands", ProcessStatus.RUNNING),
        (memory, (IngestOutcome, RecallResponse, MemoryAgentError), "memory.results", ProcessStatus.RUNNING),
        (coordinator, (DocumentWorkflowResult,), "documents.results", ProcessStatus.COMPLETED),
        (coordinator, (DocumentWorkflowError,), "documents.results", ProcessStatus.ERROR),
    ):
        for model in formats:
            builder.add_route(
                RouteBuilder(producer)
                .on_message_format(model)
                .set_destination_topics(topic)
                .set_process_status(status)
                .set_route_times(-1)
                .build()
            )
    return builder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", required=True)
    args = parser.parse_args()
    guild = build_document_guild(args.storage).launch("documents-org")
    try:
        caller = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "caller").agent
        caller.publish_with_guild_route(
            "documents.requests",
            DocumentWorkflowRequest(
                request_id="harbor-example",
                sources=[
                    MemorySource(
                        text="Harbor pilot budget is CAD 42000. Mina Patel coordinates the pilot.",
                        source_id="harbor-plan",
                        path_hint="harbor.txt",
                    )
                ],
                query="What is the Harbor pilot budget and who coordinates it?",
            ),
        )
        deadline = time.monotonic() + 130
        while time.monotonic() < deadline:
            messages = caller.get_messages()
            if messages:
                print(json.dumps(messages[0].payload, indent=2))
                if messages[0].is_error_message:
                    raise SystemExit(1)
                return
            time.sleep(0.02)
        raise TimeoutError("No terminal document response")
    finally:
        guild.shutdown()


if __name__ == "__main__":
    main()
