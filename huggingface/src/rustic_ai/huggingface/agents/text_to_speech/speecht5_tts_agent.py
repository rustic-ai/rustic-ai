import mimetypes
import uuid

from datasets import load_dataset
import soundfile as sf
import torch
from transformers import pipeline

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import (
    ErrorMessage,
    GenerationPromptRequest,
)
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, AgentMode, AgentType
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.dsl import AgentSpec


class SpeechT5TTSAgent(Agent):

    def __init__(
        self,
        agent_spec: AgentSpec,
    ) -> None:
        super().__init__(
            agent_spec,
            AgentType.BOT,
            AgentMode.LOCAL,
        )
        self._synthesiser = pipeline("text-to-speech", "microsoft/speecht5_tts")

        embeddings_dataset = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation")
        self._speaker_embedding = torch.tensor(embeddings_dataset[7306]["xvector"]).unsqueeze(0)

    @agent.processor(GenerationPromptRequest, depends_on=["filesystem:guild_fs:True"])
    def convert(self, ctx: agent.ProcessContext[GenerationPromptRequest], guild_fs: FileSystem) -> None:
        """
        Handles the received message.

        Args:
            message (Message): The received message.
        """
        data = ctx.payload
        try:
            speech = self._synthesiser(
                data.generation_prompt, forward_params={"speaker_embeddings": self._speaker_embedding}
            )
            filename = f"{uuid.uuid4()}.wav"
            try:
                with guild_fs.open(filename, "wb") as f:
                    sf.write(f, speech["audio"], samplerate=speech["sampling_rate"])
                    output = MediaLink(
                        url=filename,
                        name=filename,
                        metadata={"sampling_rate": speech["sampling_rate"]},
                        on_filesystem=True,
                        mimetype=mimetypes.guess_type(filename)[0],
                    )
                    ctx.send(output)
            except Exception as e:
                ctx.send(
                    ErrorMessage(
                        agent_type=self.get_qualified_class_name(), error_type="FileWriteError", error_message=str(e)
                    )
                )
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SpeechGenerationError",
                    error_message=str(ex),
                )
            )
