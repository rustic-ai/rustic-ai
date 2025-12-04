import shortuuid

from rustic_ai.core import Agent
from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse
from rustic_ai.core.ui_protocol.types import TextFormat


class MarkdownAgent(Agent):

    @agent.processor(MediaLink, depends_on=["filesystem:guild_fs:True"])
    def extract_text(self, ctx: agent.ProcessContext[MediaLink], guild_fs: FileSystem) -> None:
        request = ctx.payload

        try:
            with guild_fs.open(request.url, "rb") as f:
                content = f.read().decode("utf-8")

            ctx.send(TextFormat(text=content))
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ExtractTextError",
                    error_message=str(ex),
                )
            )

    @agent.processor(ChatCompletionResponse, depends_on=["filesystem:guild_fs:True"])
    def generate_markdown(self, ctx: agent.ProcessContext[ChatCompletionResponse], guild_fs: FileSystem) -> None:
        request = ctx.payload

        try:
            file_name = f"report-{shortuuid.uuid()}.md"
            content: str = ""
            if request.choices[0].message and request.choices[0].message.content:
                content = request.choices[0].message.content

            with guild_fs.open(file_name, "w") as f:
                f.write(content)

            response = MediaLink(
                name=file_name,
                url=f"{file_name}",
                on_filesystem=True,
                mimetype="text/markdown",
            )
            ctx.send(response)
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="GenerateMarkdownError",
                    error_message=str(ex),
                )
            )
