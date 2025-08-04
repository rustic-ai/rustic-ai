import logging
from typing import Optional

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.execution import AgentWrapper


class SyncAgentWrapper(AgentWrapper):
    """
    A synchronous implementation of the AgentWrapper.
    """

    def run(self) -> Optional[Agent]:
        """
        Runs the agent synchronously in the same thread.
        """
        # Example synchronous execution, which might involve starting the agent's message processing loop
        logging.info(f"Running {self.agent_spec.name} synchronously")

        # Perform common initialization tasks
        return self.initialize_agent()
