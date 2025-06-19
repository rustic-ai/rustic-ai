import threading

from ..agent_wrapper import AgentWrapper


class MultiThreadedAgentWrapper(AgentWrapper):
    """
    An implementation of AgentWrapper that runs the agent in a separate thread.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialization_complete = threading.Event()
        self.agent_thread = None

    def run(self) -> None:
        """
        Initializes the agent with Messaging and its client, then runs the agent in a separate thread.
        """
        # Start the agent's message processing loop in a new thread
        self.agent_thread = threading.Thread(target=self._initialize_and_run)
        self.agent_thread.start()

    def _initialize_and_run(self) -> None:
        """
        Internal method that initializes the agent and signals completion.
        """
        self.initialize_agent()
        self.initialization_complete.set()

    def shutdown(self) -> None:
        """
        Shuts down the agent and its connection to the Messaging.
        """
        # Wait for initialization to complete before shutting down
        if hasattr(self, "initialization_complete"):
            self.initialization_complete.wait(timeout=5.0)  # Wait up to 5 seconds

        super().shutdown()

        # Wait for the agent thread to finish
        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=5.0)
