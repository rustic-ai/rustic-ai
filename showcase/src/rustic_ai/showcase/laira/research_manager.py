import textwrap
from typing import Dict

from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core import Agent, AgentTag
from rustic_ai.core.agents.indexing.vector_agent import VectorSearchQuery
from rustic_ai.core.guild import BaseAgentProps, agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    SystemMessage,
    TextContentPart,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.vectorstore import VectorSearchResults
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.playwright.agent import WebScrapingCompleted
from rustic_ai.serpapi.agent import SERPQuery


class UserQuery(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    query: str


class ResearchUpdates(BaseModel):
    id: str
    query: str
    update: str


class ResearchManagerConf(BaseAgentProps):
    serp_results: int = Field(default=5)
    vector_results: int = Field(default=5)
    max_serp_attempts: int = Field(default=2)
    context_max: int = Field(default=100000)


class ResearchManager(Agent[ResearchManagerConf]):
    """
    Agent that manages the research process.
    """

    def __init__(self):
        self.serp_results = self.config.serp_results
        self.vector_results = self.config.vector_results
        self.max_serp_attempts = self.config.max_serp_attempts
        self.context_max = self.config.context_max

        self.queries: Dict[str, str] = {}
        self.query_status: Dict[str, str] = {}
        self.query_users: Dict[str, AgentTag] = {}
        self.query_attempts: Dict[str, int] = {}

    def _process_query(self, query_id: str, query: str, ctx: ProcessContext):
        """
        Process the user query.
        """
        self.queries[query_id] = query

        if ctx.routing_origin.origin_sender:
            self.query_users[query_id] = ctx.routing_origin.origin_sender

        self.query_attempts[query_id] = 0
        ctx.send(VectorSearchQuery(query=query, id=query_id, k=self.vector_results))
        self.query_status[query_id] = "Searching vector index"
        ctx.send(ResearchUpdates(id=query_id, query=query, update=self.query_status[query_id]))

    @agent.processor(ChatCompletionRequest)
    def process_user_query(self, ctx: ProcessContext[ChatCompletionRequest]):
        """
        Run the user query against the vector index.
        """
        messages = ctx.payload.messages
        user_messages = [msg.content for msg in messages if isinstance(msg, UserMessage)]
        question = ""
        for u_msg in user_messages:
            if isinstance(u_msg, ArrayOfContentParts):
                for msg_part in u_msg:
                    content = msg_part[1]
                    text_msgs = [msg.text for msg in content if isinstance(msg, TextContentPart)]
                    question += "".join(text_msgs)
            elif isinstance(u_msg, str):
                question = u_msg
        if len(question) > 0:
            query: UserQuery = UserQuery(query=question)
            self._process_query(query.id, query.query, ctx)
        else:
            ctx.send(TextFormat(text="No results found"))

    @agent.processor(VectorSearchResults, depends_on=[AgentDependency(dependency_key="llm", guild_level=True)])
    def process_vector_results(self, ctx: ProcessContext[VectorSearchResults], llm: LLM):
        """
        Process the vector search results.
        """
        data: VectorSearchResults = ctx.payload
        query_id = data.query_id

        if data.documents:
            # If vector search had results are found, generate a response using the LLM model
            context = "\n".join([doc.content for doc in data.documents])

            if len(context) > self.context_max:
                context = context[: self.context_max]

            self.query_status[query_id] = "Generating response"
            ctx.send(ResearchUpdates(id=query_id, query=self.queries[query_id], update=self.query_status[query_id]))

            completion_request = ChatCompletionRequest(
                messages=[
                    SystemMessage(
                        content=textwrap.dedent(
                            """You are a helpful question-answering assistant.
                            User will ask you question and will provide you the context of the question.
                            Use the context to answer the question. You need to provide the answer to the question based on the context provided.
                            If the context doesn't contain the answer, just say that you don't know.
                            Use three sentences maximum and keep the answer concise."""
                        )
                    ),
                    UserMessage(
                        content=f"Question: {data.query}\nContext: {context}",
                        name=self.query_users[query_id].id,
                    ),
                ],
            )
            response = llm.completion(completion_request)
            self.query_status[query_id] = "Response generated"
            if response.choices and response.choices[0].message:
                ctx.send(TextFormat(text=response.choices[0].message.content))

        elif self.query_attempts[query_id] >= self.max_serp_attempts:
            # If the maximum number of serp attempts is reached, return no results
            self.query_status[query_id] = "No results found"
            ctx.send(ResearchUpdates(id=query_id, query=self.queries[query_id], update=self.query_status[query_id]))
            ctx.send(TextFormat(text="No results found"))

        else:
            # If no results are found, start serp search and scrape the responses
            self.query_attempts[query_id] += 1
            serp_query = SERPQuery(
                engine="google",
                query=self.queries[query_id],
                num=self.serp_results,
                id=query_id,
                start=self.query_attempts[query_id] * self.serp_results,
            )
            ctx.send(serp_query)
            self.query_status[query_id] = "Searching SERP API"
            ctx.send(ResearchUpdates(id=query_id, query=self.queries[query_id], update=self.query_status[query_id]))

    @agent.processor(WebScrapingCompleted)
    def process_scraping_completion(self, ctx: ProcessContext[WebScrapingCompleted]):
        """
        Process the scraping completion.
        """
        data: WebScrapingCompleted = ctx.payload
        query_id = data.id
        query = self.queries[query_id]

        self.query_status[query_id] = "Scraping completed"
        ctx.send(ResearchUpdates(id=data.id, query=query, update=self.query_status[data.id]))
        ctx.send(VectorSearchQuery(query=query, id=query_id, k=self.vector_results))
        self.query_status[data.id] = "Searching vector index again"
        ctx.send(ResearchUpdates(id=data.id, query=query, update=self.query_status[data.id]))
