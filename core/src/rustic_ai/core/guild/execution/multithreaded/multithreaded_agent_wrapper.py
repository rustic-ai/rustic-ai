import threading

from ..agent_wrapper import AgentWrapper


class MultiThreadedAgentWrapper(AgentWrapper):
    """
    An implementation of AgentWrapper that runs the agent in a separate thread.
    """

    def run(self) -> None:
        """
        Initializes the agent with Messaging and its client, then runs the agent in a separate thread.
        """
        # Start the agent's message processing loop in a new thread
        self.agent_thread = threading.Thread(target=self.initialize_agent)
        self.agent_thread.start()
