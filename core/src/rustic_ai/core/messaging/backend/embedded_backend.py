import asyncio
import base64
from collections import defaultdict
import json
import logging
import multiprocessing
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from rustic_ai.core.messaging.core import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import GemstoneID

# Fixed port for the embedded server
EMBEDDED_SERVER_PORT = 31134

# Global lock for server startup coordination
_server_lock = multiprocessing.Lock()


class SocketMessage:
    """Represents a message in the socket protocol."""

    def __init__(self, command: str, *args: str):
        self.command = command.upper()
        self.args = args

    def encode(self) -> bytes:
        """Encode message to wire format."""
        # For JSON arguments, encode them in base64 to avoid quoting issues
        encoded_args = []
        for arg in self.args:
            if arg.startswith("{") or arg.startswith("["):  # Likely JSON
                # Base64 encode JSON to avoid parsing issues
                encoded_arg = "JSON:" + base64.b64encode(arg.encode("utf-8")).decode("ascii")
                encoded_args.append(encoded_arg)
            else:
                encoded_args.append(arg)

        parts = [self.command] + encoded_args
        line = " ".join(f'"{part}"' if " " in part else part for part in parts)
        return f"{line}\r\n".encode("utf-8")

    @classmethod
    def decode(cls, line: bytes) -> "SocketMessage":
        """Decode message from wire format."""
        text = line.decode("utf-8").strip()
        if not text:
            raise ValueError("Empty message")

        # Simple parsing - split on spaces, handle quoted strings
        parts = []
        current = ""
        in_quotes = False

        for char in text:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
            elif char == " " and not in_quotes:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char

        if current:
            parts.append(current)

        if not parts:
            raise ValueError("No command found")

        # Decode any base64-encoded JSON arguments
        decoded_args = []
        for arg in parts[1:]:
            if arg.startswith("JSON:"):
                # Decode base64 JSON
                json_data = base64.b64decode(arg[5:]).decode("utf-8")
                decoded_args.append(json_data)
            else:
                decoded_args.append(arg)

        return cls(parts[0], *decoded_args)


class ClientConnection:
    """Represents a client connection to the socket server."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, client_id: str):
        self.reader = reader
        self.writer = writer
        self.client_id = client_id
        self.subscriptions: Set[str] = set()
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.active = True

    async def send_message(self, message: SocketMessage) -> bool:
        """Send a message to the client. Returns False if connection is broken."""
        try:
            if not self.active:
                return False

            self.writer.write(message.encode())
            await self.writer.drain()
            return True
        except Exception as e:
            logging.warning(f"Failed to send message to client {self.client_id}: {e}")
            self.active = False
            return False

    async def queue_message(self, topic: str, message_data: str) -> bool:
        """Queue a message for delivery. Returns False if connection is broken."""
        try:
            if not self.active:
                return False

            msg = SocketMessage("MESSAGE", topic, message_data)
            await self.message_queue.put(msg)
            return True
        except Exception as e:
            logging.warning(f"Failed to queue message for client {self.client_id}: {e}")
            return False

    def close(self):
        """Close the connection."""
        self.active = False
        try:
            self.writer.close()
        except Exception:
            pass


class EmbeddedServer:
    """Pure asyncio TCP server for embedded messaging."""

    def __init__(self, host: str = "localhost", port: int = EMBEDDED_SERVER_PORT):
        self.host = host
        self.port = port
        # Validate port is not 0 (no random ports)
        if self.port == 0:
            raise ValueError("Random ports not supported. Use fixed port 31134 or specify a port.")

        self.server: Optional[asyncio.Server] = None
        self.running = False

        # In-memory storage
        self.topics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.messages: Dict[str, Dict[str, Any]] = {}  # namespace:msg_id -> message
        self.subscribers: Dict[str, Set[str]] = defaultdict(set)  # topic -> client_ids

        # Client connections
        self.connections: Dict[str, ClientConnection] = {}

        # Background tasks
        self.tasks: List[asyncio.Task] = []

        # Synchronization for shared data structures
        self._data_lock: asyncio.Lock  # Will be initialized in start()

    async def start(self) -> str:
        """Start the asyncio server."""
        if self.running:
            return f"http://{self.host}:{self.port}"

        # Initialize the data lock in the event loop context
        self._data_lock = asyncio.Lock()

        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self.running = True

        # Start background cleanup task
        cleanup_task = asyncio.create_task(self._cleanup_expired_messages())
        self.tasks.append(cleanup_task)

        logging.info(f"Socket server started on {self.host}:{self.port}")
        return f"http://{self.host}:{self.port}"

    async def stop(self):
        """Stop the server and cleanup."""
        if not self.running:
            return

        self.running = False

        # Close all client connections
        for connection in list(self.connections.values()):
            connection.close()
        self.connections.clear()

        # Cancel background tasks
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks.clear()

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        logging.info("Socket server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection."""
        client_id = str(uuid.uuid4())
        connection = ClientConnection(reader, writer, client_id)
        self.connections[client_id] = connection

        # Start message delivery task for this client
        delivery_task = asyncio.create_task(self._handle_client_delivery(connection))

        try:
            logging.debug(f"Client {client_id} connected")

            while connection.active and self.running:
                try:
                    # Read one line
                    line = await reader.readline()
                    if not line:
                        break

                    # Parse and handle command
                    try:
                        message = SocketMessage.decode(line)
                        await self._handle_command(connection, message)
                    except Exception as e:
                        error_msg = SocketMessage("ERROR", f"Invalid command: {e}")
                        await connection.send_message(error_msg)

                except asyncio.IncompleteReadError:
                    break
                except Exception as e:
                    logging.warning(f"Error handling client {client_id}: {e}")
                    break

        finally:
            # Cleanup
            delivery_task.cancel()
            try:
                await delivery_task
            except asyncio.CancelledError:
                pass

            connection.close()

            # Protect shared data during cleanup
            async with self._data_lock:
                self.connections.pop(client_id, None)

                # Remove from all subscriptions
                for topic_subs in self.subscribers.values():
                    topic_subs.discard(client_id)

            logging.debug(f"Client {client_id} disconnected")

    async def _handle_client_delivery(self, connection: ClientConnection):
        """Handle message delivery for a client connection."""
        try:
            while connection.active and self.running:
                try:
                    # Wait for message to deliver
                    message = await asyncio.wait_for(connection.message_queue.get(), timeout=1.0)

                    # Send the message
                    success = await connection.send_message(message)
                    if not success:
                        break

                except asyncio.TimeoutError:
                    # No message to deliver, continue
                    continue
                except Exception as e:
                    logging.warning(f"Error in delivery for {connection.client_id}: {e}")
                    break

        except asyncio.CancelledError:
            pass

    async def _handle_command(self, connection: ClientConnection, message: SocketMessage):
        """Handle a command from a client."""
        command = message.command
        args = message.args

        if command == "PUBLISH":
            await self._handle_publish(connection, args)
        elif command == "SUBSCRIBE":
            await self._handle_subscribe(connection, args)
        elif command == "UNSUBSCRIBE":
            await self._handle_unsubscribe(connection, args)
        elif command == "STORE_MESSAGE":
            await self._handle_store_message(connection, args)
        elif command == "GET_MESSAGES":
            await self._handle_get_messages(connection, args)
        elif command == "GET_MESSAGES_SINCE":
            await self._handle_get_messages_since(connection, args)
        elif command == "GET_MESSAGES_BY_ID":
            await self._handle_get_messages_by_id(connection, args)
        elif command == "PING":
            await connection.send_message(SocketMessage("PONG"))
        else:
            await connection.send_message(SocketMessage("ERROR", f"Unknown command: {command}"))

    async def _handle_publish(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle PUBLISH command."""
        if len(args) < 2:
            await connection.send_message(SocketMessage("ERROR", "PUBLISH requires topic and message"))
            return

        topic = args[0]
        message_data = args[1]

        # Notify all subscribers
        count = 0
        for client_id in self.subscribers.get(topic, set()):
            if client_id in self.connections:
                success = await self.connections[client_id].queue_message(topic, message_data)
                if success:
                    count += 1

        await connection.send_message(SocketMessage("OK", str(count)))

    async def _handle_subscribe(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle SUBSCRIBE command."""
        if len(args) < 1:
            await connection.send_message(SocketMessage("ERROR", "SUBSCRIBE requires topic"))
            return

        topic = args[0]

        async with self._data_lock:
            self.subscribers[topic].add(connection.client_id)
            connection.subscriptions.add(topic)

        await connection.send_message(SocketMessage("OK", "SUBSCRIBED", topic))

    async def _handle_unsubscribe(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle UNSUBSCRIBE command."""
        if len(args) < 1:
            await connection.send_message(SocketMessage("ERROR", "UNSUBSCRIBE requires topic"))
            return

        topic = args[0]

        async with self._data_lock:
            self.subscribers[topic].discard(connection.client_id)
            connection.subscriptions.discard(topic)

            # Clean up empty subscriber sets
            if not self.subscribers[topic]:
                del self.subscribers[topic]

        await connection.send_message(SocketMessage("OK", "UNSUBSCRIBED", topic))

    async def _handle_store_message(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle STORE_MESSAGE command."""
        if len(args) < 3:
            await connection.send_message(SocketMessage("ERROR", "STORE_MESSAGE requires namespace, topic, message"))
            return

        namespace = args[0]
        topic = args[1]
        message_json = args[2]

        try:
            message_data = json.loads(message_json)
            msg_id = message_data.get("id")
            timestamp = message_data.get("timestamp", time.time())

            # Store in messages index
            key = f"{namespace}:{msg_id}"
            stored_msg = {"data": message_data, "timestamp": timestamp, "ttl_expires": None}

            if "ttl" in message_data and message_data["ttl"]:
                stored_msg["ttl_expires"] = time.time() + message_data["ttl"]

            # Protect shared data structures
            async with self._data_lock:
                self.messages[key] = stored_msg
                # Store in topic
                self.topics[topic].append(stored_msg)
                # Get current subscribers (copy to avoid holding lock during I/O)
                topic_subscribers = set(self.subscribers.get(topic, set()))

            # Notify subscribers (outside the lock to avoid blocking other operations)
            count = 0
            for client_id in topic_subscribers:
                if client_id in self.connections:
                    success = await self.connections[client_id].queue_message(topic, message_json)
                    if success:
                        count += 1

            await connection.send_message(SocketMessage("OK", "STORED"))

        except Exception as e:
            await connection.send_message(SocketMessage("ERROR", f"Failed to store message: {e}"))

    async def _handle_get_messages(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle GET_MESSAGES command."""
        if len(args) < 1:
            await connection.send_message(SocketMessage("ERROR", "GET_MESSAGES requires topic"))
            return

        topic = args[0]
        messages = []

        # Protect reading from shared data
        async with self._data_lock:
            for stored_msg in self.topics.get(topic, []):
                if not self._is_message_expired(stored_msg):
                    messages.append(stored_msg["data"])

        # Sort by priority first (lower values = higher priority), then by message ID
        messages.sort(key=lambda m: (m.get("priority", 4), m.get("id", 0)))

        response = json.dumps(messages)
        await connection.send_message(SocketMessage("MESSAGES", response))

    async def _handle_get_messages_since(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle GET_MESSAGES_SINCE command."""
        if len(args) < 2:
            await connection.send_message(SocketMessage("ERROR", "GET_MESSAGES_SINCE requires topic and msg_id"))
            return

        topic = args[0]
        try:
            msg_id_since = int(args[1])
            timestamp_since = self._get_timestamp_for_id(msg_id_since)
        except ValueError:
            await connection.send_message(SocketMessage("ERROR", "Invalid message ID"))
            return

        messages = []
        # Protect reading from shared data
        async with self._data_lock:
            for stored_msg in self.topics.get(topic, []):
                if not self._is_message_expired(stored_msg):
                    # Compare timestamps like InMemoryBackend does
                    stored_timestamp = stored_msg["data"].get("timestamp", 0)
                    if stored_timestamp > timestamp_since:
                        messages.append(stored_msg["data"])

        # Sort by priority first (lower values = higher priority), then by message ID
        messages.sort(key=lambda m: (m.get("priority", 4), m.get("id", 0)))

        response = json.dumps(messages)
        await connection.send_message(SocketMessage("MESSAGES", response))

    async def _handle_get_messages_by_id(self, connection: ClientConnection, args: Tuple[str, ...]):
        """Handle GET_MESSAGES_BY_ID command."""
        if len(args) < 2:
            await connection.send_message(SocketMessage("ERROR", "GET_MESSAGES_BY_ID requires namespace and msg_ids"))
            return

        namespace = args[0]
        try:
            msg_ids = json.loads(args[1])
        except (ValueError, json.JSONDecodeError):
            await connection.send_message(SocketMessage("ERROR", "Invalid message IDs JSON"))
            return

        messages = []
        for msg_id in msg_ids:
            key = f"{namespace}:{msg_id}"
            if key in self.messages:
                stored_msg = self.messages[key]
                if not self._is_message_expired(stored_msg):
                    messages.append(stored_msg["data"])

        response = json.dumps(messages)
        await connection.send_message(SocketMessage("MESSAGES", response))

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """Get timestamp for a message ID."""
        if msg_id == 0 or msg_id is None:
            return 0.0
        try:
            id_instance = GemstoneID.from_int(msg_id)
            return id_instance.timestamp
        except Exception:
            return 0.0

    def _is_message_expired(self, stored_msg: Dict[str, Any]) -> bool:
        """Check if a message has expired."""
        ttl_expires = stored_msg.get("ttl_expires")
        if ttl_expires is None:
            return False
        return time.time() > ttl_expires

    async def _cleanup_expired_messages(self):
        """Background task to clean up expired messages."""
        try:
            while self.running:
                await asyncio.sleep(30)  # Clean up every 30 seconds

                # Protect shared data during cleanup
                async with self._data_lock:
                    # Clean up messages
                    expired_keys = []
                    for key, stored_msg in self.messages.items():
                        if self._is_message_expired(stored_msg):
                            expired_keys.append(key)

                    for key in expired_keys:
                        del self.messages[key]

                    # Clean up topic messages
                    for topic, messages in self.topics.items():
                        self.topics[topic] = [msg for msg in messages if not self._is_message_expired(msg)]

                if expired_keys:
                    logging.debug(f"Cleaned up {len(expired_keys)} expired messages")

        except asyncio.CancelledError:
            pass


class EmbeddedMessagingBackend(MessagingBackend):
    """Embedded messaging backend with true bidirectional async communication."""

    def __init__(self, host: str = "localhost", port: int = EMBEDDED_SERVER_PORT, auto_start_server: bool = True):
        self.host = host
        self.port = port
        # Validate port is not 0 (no random ports)
        if self.port == 0:
            raise ValueError("Random ports not supported. Use fixed port 31134 or specify a port.")

        self.auto_start_server = auto_start_server

        # Async connection objects
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False

        # Subscription handling
        self.subscription_handlers: Dict[str, Callable[[Message], None]] = {}

        # For owned server
        self.owned_server: Optional[EmbeddedServer] = None
        self.server_process: Optional[multiprocessing.Process] = None

        # Async event loop management
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client_thread: Optional[threading.Thread] = None
        self._stop_event = multiprocessing.Event()
        self._server_ready = multiprocessing.Event()
        self._client_ready = multiprocessing.Event()

        # Command/response handling
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._response_counter = 0
        self._response_lock: Optional[asyncio.Lock] = None  # Created in event loop context

        # Track subscription handler tasks for proper cleanup
        self._subscription_tasks: Set[asyncio.Task] = set()

        if auto_start_server:
            self._ensure_server_running()

        self._start_async_client()

    def _test_server_connection(self) -> bool:
        """Test if server is reachable with a quick connection attempt."""
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)  # Quick timeout
                result = sock.connect_ex((self.host, self.port))
                return result == 0  # 0 means connection successful
        except Exception:
            return False

    def _ensure_server_running(self):
        """Ensure the socket server is running by attempting to connect."""
        # Try to connect to see if server is already running
        if self._test_server_connection():
            logging.debug(f"Server already running on {self.host}:{self.port}")
            return

        # Server not reachable, start a new one
        logging.debug(f"Starting new server on {self.host}:{self.port}")
        with _server_lock:
            # Double-check after acquiring lock (another process might have started it)
            if self._test_server_connection():
                return

            self.owned_server = EmbeddedServer(self.host, self.port)

            # Start the server in a separate process with its own event loop
            self.server_process = multiprocessing.Process(target=self._run_server_process, daemon=True)
            self.server_process.start()

            # Wait for server to be ready
            if not self._server_ready.wait(timeout=5.0):
                # If server failed to start, clean up the process
                if self.server_process and self.server_process.is_alive():
                    self.server_process.terminate()
                    self.server_process.join(timeout=2.0)
                    if self.server_process.is_alive():
                        self.server_process.kill()
                raise RuntimeError("Server failed to start within timeout")

    def _run_server_process(self):
        """Run the server in its own process with asyncio event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Start the server
            if self.owned_server is not None:
                loop.run_until_complete(self.owned_server.start())

            # Signal that server is ready
            self._server_ready.set()

            # Run until stop is requested - check more frequently
            while not self._stop_event.is_set():
                loop.run_until_complete(asyncio.sleep(0.05))  # More responsive to stop events

        except Exception as e:
            logging.error(f"Server process error: {e}")
            self._server_ready.set()  # Set even on error to avoid hanging
        finally:
            try:
                if self.owned_server and self.owned_server.running:
                    loop.run_until_complete(self.owned_server.stop())
            except Exception as e:
                logging.debug(f"Error stopping server in process cleanup: {e}")
            finally:
                loop.close()

    def _start_async_client(self):
        """Start the async client in its own thread."""
        self.client_thread = threading.Thread(target=self._run_client_thread, daemon=True)
        self.client_thread.start()

        # Wait for client to be ready
        if not self._client_ready.wait(timeout=5.0):
            raise RuntimeError("Client failed to start within timeout")

    def _run_client_thread(self):
        """Run the async client in its own thread with asyncio event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create response lock in the correct event loop context
        self._response_lock = asyncio.Lock()

        try:
            # Connect to server and start message listener
            self.loop.run_until_complete(self._async_connect())

            # Signal that client is ready
            self._client_ready.set()

            # Run the event loop until stop is requested
            self.loop.run_until_complete(self._run_until_stopped())

        except Exception as e:
            logging.error(f"Client thread error: {e}")
            self._client_ready.set()  # Set even on error to avoid hanging
        finally:
            if self.connected:
                self.loop.run_until_complete(self._async_disconnect())
            self.loop.close()

    async def _async_connect(self):
        """Establish async connection to the server."""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            logging.debug(f"Connected to socket server at {self.host}:{self.port}")

            # Start the message listener task
            asyncio.create_task(self._message_listener())

        except Exception as e:
            logging.error(f"Failed to connect to socket server: {e}")
            raise

    async def _async_disconnect(self):
        """Close the async connection."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False

    async def _run_until_stopped(self):
        """Run the event loop until stop is requested."""
        while not self._stop_event.is_set():
            await asyncio.sleep(0.05)  # More responsive to stop events

    async def _message_listener(self):
        """Async message listener - no polling, pure event-driven."""
        if self.reader is None:
            return

        buffer = b""

        try:
            while self.connected and not self._stop_event.is_set():
                # Wait for data to arrive (blocks until data comes, no polling!)
                data = await self.reader.read(4096)

                if not data:
                    # Connection closed
                    break

                buffer += data

                # Process complete messages
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    if line.strip():
                        await self._handle_incoming_message(line + b"\r\n")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Message listener error: {e}")
        finally:
            self.connected = False

    async def _handle_incoming_message(self, raw_message: bytes):
        """Handle an incoming message from the server."""
        try:
            msg = SocketMessage.decode(raw_message)

            if msg.command == "MESSAGE" and len(msg.args) >= 2:
                # This is a subscription message - handle immediately!
                topic = msg.args[0]
                message_json = msg.args[1]

                if topic in self.subscription_handlers:
                    try:
                        message = Message.from_json(message_json)
                        # Execute handler in a separate task to avoid blocking
                        task = asyncio.create_task(self._execute_subscription_handler(topic, message))
                        # Track the task for proper cleanup
                        self._subscription_tasks.add(task)
                        # Clean up completed tasks automatically
                        task.add_done_callback(self._subscription_tasks.discard)
                    except Exception as e:
                        logging.error(f"Error processing subscription message: {e}")

            else:
                # This is a command response (OK, ERROR, MESSAGES, etc.)
                # Route to the first pending response
                if self._pending_responses:
                    # Get the oldest pending response (FIFO)
                    response_id = next(iter(self._pending_responses))
                    future = self._pending_responses.pop(response_id)
                    if not future.done():
                        future.set_result(msg)

        except Exception as e:
            logging.error(f"Error handling incoming message: {e}")

    async def _execute_subscription_handler(self, topic: str, message: Message):
        """Execute subscription handler in async context."""
        try:
            handler = self.subscription_handlers.get(topic)
            if handler:
                # Run the handler (which is sync) in a thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler, message)
        except Exception as e:
            logging.error(f"Error executing subscription handler for topic {topic}: {e}")

    def _run_async_command(self, coro):
        """Run an async command from sync context."""
        if not self.loop or not self.connected:
            raise RuntimeError("Client not connected")

        # Submit coroutine to the client event loop and wait for result
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=10.0)

    async def _send_command_async(self, command: str, *args: str) -> SocketMessage:
        """Send a command asynchronously and get response."""
        if not self.connected:
            raise RuntimeError("Not connected to server")

        if self._response_lock is None or self.writer is None:
            raise RuntimeError("Client not properly initialized")

        try:
            # Create unique response ID
            async with self._response_lock:
                self._response_counter += 1
                response_id = str(self._response_counter)

            message = SocketMessage(command, *args)

            # Create future for response
            response_future: asyncio.Future[SocketMessage] = asyncio.Future()
            self._pending_responses[response_id] = response_future

            # Send command
            self.writer.write(message.encode())
            await self.writer.drain()

            # Wait for response (no polling, just async wait!)
            try:
                response_msg = await asyncio.wait_for(response_future, timeout=10.0)

                if response_msg.command == "ERROR":
                    raise RuntimeError(f"Server error: {' '.join(response_msg.args)}")

                return response_msg

            except asyncio.TimeoutError:
                # Clean up pending response
                self._pending_responses.pop(response_id, None)
                raise RuntimeError("Timeout waiting for response")

        except Exception as e:
            self.connected = False
            raise RuntimeError(f"Communication error: {e}")

    def _send_command(self, command: str, *args: str) -> SocketMessage:
        """Send a command and get response (sync interface)."""
        return self._run_async_command(self._send_command_async(command, *args))

    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """Store a message."""
        message_json = message.to_json()
        self._send_command("STORE_MESSAGE", namespace, topic, message_json)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """Get all messages for a topic."""
        response = self._send_command("GET_MESSAGES", topic)
        if response.command == "MESSAGES" and response.args:
            messages_data = json.loads(response.args[0])
            return [Message.from_json(json.dumps(msg_data)) for msg_data in messages_data]
        return []

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """Get messages for topic since a message ID."""
        response = self._send_command("GET_MESSAGES_SINCE", topic, str(msg_id_since))
        if response.command == "MESSAGES" and response.args:
            messages_data = json.loads(response.args[0])
            return [Message.from_json(json.dumps(msg_data)) for msg_data in messages_data]
        return []

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """Get the next message for a topic since a message ID."""
        messages = self.get_messages_for_topic_since(topic, last_message_id)
        return messages[0] if messages else None

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """Get messages by their IDs."""
        if not msg_ids:
            return []

        msg_ids_json = json.dumps(msg_ids)
        response = self._send_command("GET_MESSAGES_BY_ID", namespace, msg_ids_json)

        if response.command == "MESSAGES" and response.args:
            messages_data = json.loads(response.args[0])
            return [Message.from_json(json.dumps(msg_data)) for msg_data in messages_data]
        return []

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """Load subscribers (returns empty dict for socket backend)."""
        return {}

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to a topic with real-time event-driven delivery."""
        self.subscription_handlers[topic] = handler
        self._send_command("SUBSCRIBE", topic)
        # No polling setup needed - messages arrive via _message_listener automatically!

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        self.subscription_handlers.pop(topic, None)
        self._send_command("UNSUBSCRIBE", topic)

    async def _cancel_subscription_tasks(self):
        """Cancel all pending subscription handler tasks."""
        if self._subscription_tasks:
            logging.debug(f"Cancelling {len(self._subscription_tasks)} subscription tasks")
            # Cancel all tasks
            for task in self._subscription_tasks:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to be cancelled with a timeout
            if self._subscription_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._subscription_tasks, return_exceptions=True), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    logging.warning("Some subscription tasks did not cancel within timeout")
                except Exception as e:
                    logging.debug(f"Exception during task cancellation (expected): {e}")

            self._subscription_tasks.clear()

    def cleanup(self) -> None:
        """Clean up the backend."""
        self.subscription_handlers.clear()

        # Cancel any pending subscription tasks in the client loop
        if self.loop and not self.loop.is_closed():
            try:
                # Submit task cancellation to the client event loop
                future = asyncio.run_coroutine_threadsafe(self._cancel_subscription_tasks(), self.loop)
                future.result(timeout=3.0)
            except Exception as e:
                logging.debug(f"Error cancelling subscription tasks: {e}")

        # Signal stop to all threads
        self._stop_event.set()

        # Wait for client thread to finish
        if self.client_thread and self.client_thread.is_alive():
            self.client_thread.join(timeout=2.0)

        # Clean up server process if we own it
        if self.server_process and self.server_process.is_alive():
            logging.debug("Terminating server process...")
            # First set the stop event
            self._stop_event.set()
            # Give it a brief moment to respond to the stop event
            self.server_process.join(timeout=0.5)

            # If still alive, terminate it
            if self.server_process.is_alive():
                self.server_process.terminate()
                self.server_process.join(timeout=1.0)

            # If still alive, force kill
            if self.server_process.is_alive():
                self.server_process.kill()
                self.server_process.join(timeout=0.5)

        # Reset process reference
        self.server_process = None

    def __del__(self):
        """Destructor to ensure cleanup happens even if not called explicitly."""
        try:
            if hasattr(self, "server_process") and self.server_process and self.server_process.is_alive():
                logging.warning("EmbeddedMessagingBackend destructor cleaning up server process")
                self.cleanup()
        except Exception as e:
            logging.debug(f"Error in destructor cleanup: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.cleanup()

    def supports_subscription(self) -> bool:
        """Return True since we support real-time subscriptions."""
        return True


def create_embedded_messaging_config(host: str = "localhost", port: int = EMBEDDED_SERVER_PORT) -> Dict[str, Any]:
    """Create a messaging config for the embedded backend."""
    return {
        "backend_module": "rustic_ai.core.messaging.backend.embedded_backend",
        "backend_class": "EmbeddedMessagingBackend",
        "backend_config": {"host": host, "port": port, "auto_start_server": True},
    }
