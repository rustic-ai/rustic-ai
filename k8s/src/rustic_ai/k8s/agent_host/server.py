"""Agent host server entry point.

This is the main entry point for the agent host pod. It:
- Parses environment configuration
- Creates Redis client
- Initializes AgentHostServicer
- Starts gRPC server
- Starts heartbeat worker
- Handles graceful shutdown
"""

import logging
import os
import signal
import sys
import time
from typing import Optional

import grpc
import redis

from rustic_ai.k8s.agent_host.grpc_service import AgentHostServicer, create_grpc_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class AgentHostServer:
    """
    Agent host server that manages the gRPC server and servicer lifecycle.
    
    This server:
    - Reads configuration from environment variables
    - Creates Redis client with connection pooling
    - Initializes and runs AgentHostServicer
    - Handles graceful shutdown on SIGTERM/SIGINT
    """

    def __init__(self):
        """Initialize the agent host server from environment variables."""
        # Redis configuration
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        # gRPC configuration
        self.grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        
        # Process management configuration
        self.max_processes = int(os.getenv("MAX_PROCESSES", "100"))
        
        # Heartbeat configuration
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "20"))
        
        # Server state
        self.redis_client: Optional[redis.Redis] = None
        self.servicer: Optional[AgentHostServicer] = None
        self.grpc_server: Optional[grpc.Server] = None
        self.shutdown_requested = False
        
        logger.info(
            f"Agent host server configuration: "
            f"redis_url={self.redis_url}, "
            f"grpc_port={self.grpc_port}, "
            f"max_processes={self.max_processes}, "
            f"heartbeat_interval={self.heartbeat_interval}s"
        )

    def _create_redis_client(self) -> redis.Redis:
        """
        Create Redis client with connection pooling.
        
        Returns:
            Configured Redis client
            
        Raises:
            redis.ConnectionError: If cannot connect to Redis
        """
        try:
            # Parse Redis URL and create client
            client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            
            # Test connection
            client.ping()
            
            logger.info(f"Successfully connected to Redis at {self.redis_url}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"Received signal {signal_name}, initiating graceful shutdown")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Signal handlers registered (SIGTERM, SIGINT)")

    def start(self):
        """
        Start the agent host server.
        
        This method:
        1. Creates Redis client
        2. Initializes AgentHostServicer
        3. Creates gRPC server
        4. Starts heartbeat worker
        5. Starts gRPC server
        6. Blocks until shutdown signal
        """
        try:
            logger.info("Starting agent host server")
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Create Redis client
            logger.info("Creating Redis client")
            self.redis_client = self._create_redis_client()
            
            # Create servicer
            logger.info("Initializing AgentHostServicer")
            self.servicer = AgentHostServicer(
                redis_client=self.redis_client,
                max_processes=self.max_processes,
                heartbeat_interval=self.heartbeat_interval,
            )
            
            # Create gRPC server
            logger.info(f"Creating gRPC server on port {self.grpc_port}")
            self.grpc_server = create_grpc_server(self.servicer, port=self.grpc_port)
            
            # Start heartbeat worker
            logger.info("Starting heartbeat worker")
            self.servicer.start_heartbeat_worker()
            
            # Start gRPC server
            logger.info(f"Starting gRPC server on port {self.grpc_port}")
            self.grpc_server.start()
            
            logger.info(
                f"Agent host server started successfully on port {self.grpc_port}"
            )
            
            # Block until shutdown signal
            self._wait_for_shutdown()
            
        except Exception as e:
            logger.error(f"Failed to start agent host server: {e}", exc_info=True)
            raise
        finally:
            self.stop()

    def _wait_for_shutdown(self):
        """Wait for shutdown signal."""
        logger.info("Agent host server running, waiting for shutdown signal")
        
        try:
            while not self.shutdown_requested:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.shutdown_requested = True

    def stop(self):
        """
        Stop the agent host server gracefully.
        
        This method:
        1. Stops accepting new gRPC requests
        2. Shuts down AgentHostServicer (stops agents, heartbeat worker)
        3. Closes Redis connection
        """
        logger.info("Stopping agent host server")
        
        # Stop gRPC server (give 30s for in-flight requests)
        if self.grpc_server:
            logger.info("Stopping gRPC server (30s grace period)")
            self.grpc_server.stop(grace=30)
            logger.info("gRPC server stopped")
        
        # Shutdown servicer (stops all agents and heartbeat worker)
        if self.servicer:
            logger.info("Shutting down AgentHostServicer")
            self.servicer.shutdown()
            logger.info("AgentHostServicer shutdown complete")
        
        # Close Redis connection
        if self.redis_client:
            logger.info("Closing Redis connection")
            try:
                self.redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
        
        logger.info("Agent host server stopped successfully")


def serve():
    """
    Main entry point for the agent host server.
    
    This function is called by the Docker container entry point
    or the Poetry script command.
    """
    server = AgentHostServer()
    
    try:
        server.start()
    except Exception as e:
        logger.error(f"Agent host server failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    serve()
