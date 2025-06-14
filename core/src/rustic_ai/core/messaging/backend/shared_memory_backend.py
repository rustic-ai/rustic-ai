from collections import defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import queue as queue_module
import re
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import uuid

from rustic_ai.core.messaging.core import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import GemstoneID


@dataclass
class StoredMessage:
    """Message with metadata for storage."""

    message: dict
    timestamp: float
    ttl_expires: Optional[float] = None


@dataclass
class Subscription:
    """Subscription with pattern matching support."""

    subscriber_id: str
    pattern: str
    is_pattern: bool = False
    queue: queue_module.Queue = field(default_factory=lambda: queue_module.Queue(maxsize=1000))


class SharedMemoryRequestHandler(BaseHTTPRequestHandler):
    """Request handler for the shared memory server."""

    def __init__(self, server_instance, *args, **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_POST(self):
        routes = {
            "/store_message": self._handle_store_message,
            "/subscribe": self._handle_subscribe,
            "/unsubscribe": self._handle_unsubscribe,
            "/psubscribe": self._handle_pattern_subscribe,
            "/punsubscribe": self._handle_pattern_unsubscribe,
            "/publish": self._handle_publish,
            # Redis-like operations
            "/set": self._handle_set,
            "/hset": self._handle_hset,
            "/sadd": self._handle_sadd,
        }

        handler = routes.get(self.path)
        if handler:
            handler()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path.startswith("/messages/"):
            self._handle_get_messages()
        elif self.path.startswith("/messages_since/"):
            self._handle_get_messages_since()
        elif self.path.startswith("/messages_by_id"):
            self._handle_get_messages_by_id()
        elif self.path.startswith("/poll"):
            self._handle_poll()
        elif self.path == "/health":
            self._handle_health()
        elif self.path == "/stats":
            self._handle_stats()
        # Redis-like operations
        elif self.path.startswith("/get/"):
            self._handle_get()
        elif self.path.startswith("/hget/"):
            self._handle_hget()
        elif self.path.startswith("/smembers/"):
            self._handle_smembers()
        else:
            self.send_error(404)

    def _read_json_body(self) -> dict:
        """Helper to read and parse JSON body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        post_data = self.rfile.read(content_length)
        return json.loads(post_data.decode("utf-8"))

    def _send_json_response(self, data: Union[Dict[str, Any], List[Any]], status: int = 200):
        """Helper to send JSON response."""
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _handle_store_message(self):
        try:
            data = self._read_json_body()

            namespace = data["namespace"]
            topic = data["topic"]
            message_dict = data["message"]
            ttl = data.get("ttl")  # Optional TTL in seconds

            with self.server_instance.lock:
                # Create stored message
                stored_msg = StoredMessage(
                    message=message_dict,
                    timestamp=message_dict["timestamp"],
                    ttl_expires=time.time() + ttl if ttl else None,
                )

                # Store in messages index
                key = f"{namespace}:{message_dict['id']}"
                self.server_instance.messages[key] = stored_msg

                # Store in topic
                self.server_instance.topics[topic].append(stored_msg)
                # Keep sorted by timestamp
                self.server_instance.topics[topic].sort(key=lambda m: m.timestamp)

                # Notify subscribers
                self.server_instance._notify_subscribers(topic, message_dict)

            self._send_json_response({"status": "success"})

        except Exception as e:
            logging.error(f"Error storing message: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_poll(self):
        """Long polling endpoint for real-time updates."""
        try:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            subscriber_id = query_params.get("subscriber_id", [""])[0]
            timeout = float(query_params.get("timeout", ["30"])[0])

            if not subscriber_id:
                self._send_json_response({"error": "subscriber_id required"}, 400)
                return

            # Find subscriber's queue
            sub_queue = self._find_subscriber_queue(subscriber_id)

            if not sub_queue:
                self._send_json_response({"messages": []})
                return

            # Wait for messages with timeout
            messages = self._wait_for_messages(sub_queue, timeout)
            self._send_json_response({"messages": messages})

        except Exception as e:
            logging.error(f"Error in poll: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _find_subscriber_queue(self, subscriber_id: str):
        """Helper to find subscriber queue."""
        sub_queue = None
        with self.server_instance.lock:
            # Check all subscriptions for this subscriber
            for subs in self.server_instance.subscriptions.values():
                for sub in subs:
                    if sub.subscriber_id == subscriber_id:
                        sub_queue = sub.queue
                        break
                if sub_queue:
                    break

            # Check pattern subscriptions
            if not sub_queue:
                for sub in self.server_instance.pattern_subscriptions:
                    if sub.subscriber_id == subscriber_id:
                        sub_queue = sub.queue
                        break
        return sub_queue

    def _wait_for_messages(self, sub_queue, timeout: float) -> list:
        """Helper to wait for messages with timeout."""
        messages = []
        deadline = time.time() + timeout

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            try:
                # Use much shorter timeout for more responsive polling
                msg = sub_queue.get(timeout=min(remaining, 0.1))  # Max 100ms wait
                messages.append(msg)

                # Drain queue up to a limit
                for _ in range(99):  # Max 100 messages per poll
                    try:
                        msg = sub_queue.get_nowait()
                        messages.append(msg)
                    except queue_module.Empty:
                        break

                break  # Got messages, return them

            except queue_module.Empty:
                continue  # Keep waiting with shorter intervals

        return messages

    def _handle_subscribe(self):
        try:
            data = self._read_json_body()

            topic = data["topic"]
            subscriber_id = data["subscriber_id"]

            with self.server_instance.lock:
                # Check if already subscribed to this specific topic
                existing = None
                for sub in self.server_instance.subscriptions[topic]:
                    if sub.subscriber_id == subscriber_id:
                        existing = sub
                        break

                if not existing:
                    # Look for an existing queue from any other subscription by the same subscriber
                    existing_queue = None
                    for other_subs in self.server_instance.subscriptions.values():
                        for other_sub in other_subs:
                            if other_sub.subscriber_id == subscriber_id:
                                existing_queue = other_sub.queue
                                break
                        if existing_queue:
                            break

                    # If no existing queue found, also check pattern subscriptions
                    if not existing_queue:
                        for other_sub in self.server_instance.pattern_subscriptions:
                            if other_sub.subscriber_id == subscriber_id:
                                existing_queue = other_sub.queue
                                break

                    # Create new subscription, reusing existing queue if available
                    if existing_queue:
                        sub = Subscription(
                            subscriber_id=subscriber_id, pattern=topic, is_pattern=False, queue=existing_queue
                        )
                    else:
                        sub = Subscription(subscriber_id=subscriber_id, pattern=topic, is_pattern=False)

                    self.server_instance.subscriptions[topic].append(sub)

            self._send_json_response({"status": "subscribed"})

        except Exception as e:
            logging.error(f"Error subscribing: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_unsubscribe(self):
        try:
            data = self._read_json_body()

            topic = data["topic"]
            subscriber_id = data["subscriber_id"]

            with self.server_instance.lock:
                subs = self.server_instance.subscriptions.get(topic, [])
                self.server_instance.subscriptions[topic] = [sub for sub in subs if sub.subscriber_id != subscriber_id]
                if not self.server_instance.subscriptions[topic]:
                    del self.server_instance.subscriptions[topic]

            self._send_json_response({"status": "unsubscribed"})

        except Exception as e:
            logging.error(f"Error unsubscribing: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_pattern_subscribe(self):
        """Handle pattern-based subscriptions (Redis PSUBSCRIBE)."""
        try:
            data = self._read_json_body()

            pattern = data["pattern"]
            subscriber_id = data["subscriber_id"]

            with self.server_instance.lock:
                # Check if already subscribed to this specific pattern
                existing = None
                for sub in self.server_instance.pattern_subscriptions:
                    if sub.subscriber_id == subscriber_id and sub.pattern == pattern:
                        existing = sub
                        break

                if not existing:
                    # Look for an existing queue from any other subscription by the same subscriber
                    existing_queue = None
                    # Check regular topic subscriptions first
                    for other_subs in self.server_instance.subscriptions.values():
                        for other_sub in other_subs:
                            if other_sub.subscriber_id == subscriber_id:
                                existing_queue = other_sub.queue
                                break
                        if existing_queue:
                            break

                    # If no existing queue found, check other pattern subscriptions
                    if not existing_queue:
                        for other_sub in self.server_instance.pattern_subscriptions:
                            if other_sub.subscriber_id == subscriber_id:
                                existing_queue = other_sub.queue
                                break

                    # Create new pattern subscription, reusing existing queue if available
                    if existing_queue:
                        sub = Subscription(
                            subscriber_id=subscriber_id, pattern=pattern, is_pattern=True, queue=existing_queue
                        )
                    else:
                        sub = Subscription(subscriber_id=subscriber_id, pattern=pattern, is_pattern=True)

                    self.server_instance.pattern_subscriptions.append(sub)

            self._send_json_response({"status": "psubscribed"})

        except Exception as e:
            logging.error(f"Error in pattern subscribe: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_pattern_unsubscribe(self):
        try:
            data = self._read_json_body()

            pattern = data["pattern"]
            subscriber_id = data["subscriber_id"]

            with self.server_instance.lock:
                self.server_instance.pattern_subscriptions = [
                    sub
                    for sub in self.server_instance.pattern_subscriptions
                    if not (sub.subscriber_id == subscriber_id and sub.pattern == pattern)
                ]

            self._send_json_response({"status": "punsubscribed"})

        except Exception as e:
            logging.error(f"Error in pattern unsubscribe: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_publish(self):
        """Redis-style PUBLISH command."""
        try:
            data = self._read_json_body()

            channel = data["channel"]
            message = data["message"]

            with self.server_instance.lock:
                # Create a simple message structure
                msg_data = {"channel": channel, "data": message, "timestamp": time.time()}

                # Notify subscribers
                count = self._notify_publish_subscribers(channel, msg_data)

            self._send_json_response({"subscribers": count})

        except Exception as e:
            logging.error(f"Error in publish: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _notify_publish_subscribers(self, channel: str, msg_data: dict) -> int:
        """Helper to notify subscribers of published messages."""
        count = 0

        # Direct subscribers
        for sub in self.server_instance.subscriptions.get(channel, []):
            try:
                sub.queue.put_nowait({"type": "message", "channel": channel, "data": msg_data})
                count += 1
            except queue_module.Full:
                pass

        # Pattern subscribers
        for sub in self.server_instance.pattern_subscriptions:
            if self.server_instance._match_pattern(sub.pattern, channel):
                try:
                    sub.queue.put_nowait(
                        {"type": "pmessage", "pattern": sub.pattern, "channel": channel, "data": msg_data}
                    )
                    count += 1
                except queue_module.Full:
                    pass

        return count

    def _handle_get_messages(self):
        try:
            topic = self.path.split("/")[-1]
            with self.server_instance.lock:
                messages = self.server_instance.topics.get(topic, [])
                # Just return messages without sorting - let client handle sorting
                message_dicts = [msg.message for msg in messages]

            self._send_json_response(message_dicts)

        except Exception as e:
            logging.error(f"Error getting messages: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_get_messages_since(self):
        try:
            path_parts = self.path.split("/")
            topic = path_parts[-2]
            timestamp_since = float(path_parts[-1])

            with self.server_instance.lock:
                all_messages = self.server_instance.topics.get(topic, [])
                filtered_messages = [msg.message for msg in all_messages if msg.timestamp > timestamp_since]
                sorted_messages = sorted(filtered_messages, key=lambda m: m["id"])

            self._send_json_response(sorted_messages)

        except Exception as e:
            logging.error(f"Error getting messages since: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_get_messages_by_id(self):
        try:
            # Parse query string for namespace and message IDs
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            namespace = query_params.get("namespace", [""])[0]
            msg_ids = [int(id_str) for id_str in query_params.get("ids", [])]

            with self.server_instance.lock:
                result_messages = []
                for msg_id in msg_ids:
                    key = f"{namespace}:{msg_id}"
                    if key in self.server_instance.messages:
                        result_messages.append(self.server_instance.messages[key].message)

            self._send_json_response(result_messages)

        except Exception as e:
            logging.error(f"Error getting messages by ID: {e}")
            self._send_json_response({"error": str(e)}, 500)

    # Redis-like data structure handlers
    def _handle_set(self):
        """Redis SET command."""
        try:
            data = self._read_json_body()

            key = data["key"]
            value = data["value"]
            ex = data.get("ex")  # Expire in seconds

            with self.server_instance.lock:
                expires = time.time() + ex if ex else None
                self.server_instance.strings[key] = (value, expires)

            self._send_json_response({"status": "OK"})

        except Exception as e:
            logging.error(f"Error in SET: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_get(self):
        """Redis GET command."""
        try:
            key = self.path.split("/")[-1]

            with self.server_instance.lock:
                if key in self.server_instance.strings:
                    value, expires = self.server_instance.strings[key]
                    if expires and expires <= time.time():
                        del self.server_instance.strings[key]
                        result = None
                    else:
                        result = value
                else:
                    result = None

            self._send_json_response({"value": result})

        except Exception as e:
            logging.error(f"Error in GET: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_hset(self):
        """Redis HSET command."""
        try:
            data = self._read_json_body()

            key = data["key"]
            field = data["field"]
            value = data["value"]

            with self.server_instance.lock:
                self.server_instance.hashes[key][field] = value

            self._send_json_response({"status": "OK"})

        except Exception as e:
            logging.error(f"Error in HSET: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_hget(self):
        """Redis HGET command."""
        try:
            path_parts = self.path.split("/")
            key = path_parts[-2]
            field = path_parts[-1]

            with self.server_instance.lock:
                result = self.server_instance.hashes.get(key, {}).get(field)

            self._send_json_response({"value": result})

        except Exception as e:
            logging.error(f"Error in HGET: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_sadd(self):
        """Redis SADD command."""
        try:
            data = self._read_json_body()

            key = data["key"]
            members = data["members"] if isinstance(data["members"], list) else [data["members"]]

            with self.server_instance.lock:
                added = 0
                for member in members:
                    if member not in self.server_instance.sets[key]:
                        self.server_instance.sets[key].add(member)
                        added += 1

            self._send_json_response({"added": added})

        except Exception as e:
            logging.error(f"Error in SADD: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_smembers(self):
        """Redis SMEMBERS command."""
        try:
            key = self.path.split("/")[-1]

            with self.server_instance.lock:
                members = list(self.server_instance.sets.get(key, set()))

            self._send_json_response({"members": members})

        except Exception as e:
            logging.error(f"Error in SMEMBERS: {e}")
            self._send_json_response({"error": str(e)}, 500)

    def _handle_health(self):
        self._send_json_response({"status": "healthy"})

    def _handle_stats(self):
        with self.server_instance.lock:
            total_messages = sum(len(messages) for messages in self.server_instance.topics.values())
            stats = {
                "status": "healthy",
                "uptime": time.time() - getattr(self.server_instance, "start_time", time.time()),
                "topics": len(self.server_instance.topics),
                "total_messages": total_messages,
                "subscriptions": sum(len(subs) for subs in self.server_instance.subscriptions.values()),
                "pattern_subscriptions": len(self.server_instance.pattern_subscriptions),
            }

        self._send_json_response(stats)


class SharedMemoryServer:
    """
    Enhanced HTTP server for shared message storage with Redis-like features.
    Designed for testing distributed agents across processes/containers.
    """

    def __init__(self, host: str = "localhost", port: int = 0):
        self.host = host
        self.port = port
        self.actual_port = port
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.start_time = time.time()

        # Enhanced storage
        self.topics: Dict[str, List[StoredMessage]] = defaultdict(list)
        self.messages: Dict[str, StoredMessage] = {}  # namespace:id -> message
        self.subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self.pattern_subscriptions: List[Subscription] = []

        # Redis-like data structures
        self.strings: Dict[str, Tuple[str, Optional[float]]] = {}  # key -> (value, expires)
        self.hashes: Dict[str, Dict[str, str]] = defaultdict(dict)
        self.sets: Dict[str, Set[str]] = defaultdict(set)
        self.sorted_sets: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.lists: Dict[str, List[str]] = defaultdict(list)

        # Cleanup thread for TTL
        self.cleanup_thread: Optional[threading.Thread] = None
        self.running = False

        self.lock = threading.RLock()

    def _find_free_port(self) -> int:
        """Find a free port if port=0 was specified."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            return s.getsockname()[1]

    def _cleanup_expired(self):
        """Background thread to clean up expired items."""
        while self.running:
            try:
                now = time.time()
                with self.lock:
                    # Clean up expired messages
                    for topic, messages in list(self.topics.items()):
                        self.topics[topic] = [
                            msg for msg in messages if msg.ttl_expires is None or msg.ttl_expires > now
                        ]
                        if not self.topics[topic]:
                            del self.topics[topic]

                    # Clean up expired strings
                    expired_keys = [key for key, (_, expires) in self.strings.items() if expires and expires <= now]
                    for key in expired_keys:
                        del self.strings[key]

                time.sleep(1)  # Check every second
            except Exception as e:
                logging.error(f"Cleanup thread error: {e}")

    def _match_pattern(self, pattern: str, topic: str) -> bool:
        """Check if topic matches subscription pattern (Redis-style)."""
        # Convert Redis-style pattern to regex
        # * matches any number of characters
        # ? matches single character
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        return bool(re.match(f"^{regex_pattern}$", topic))

    def _notify_subscribers(self, topic: str, message_dict: dict):
        """Notify all subscribers of a new message."""
        # Direct topic subscribers
        for sub in self.subscriptions.get(topic, []):
            try:
                sub.queue.put_nowait({"type": "message", "topic": topic, "data": message_dict})
            except queue_module.Full:
                logging.warning(f"Queue full for subscriber {sub.subscriber_id}")

        # Pattern subscribers
        for sub in self.pattern_subscriptions:
            if self._match_pattern(sub.pattern, topic):
                try:
                    sub.queue.put_nowait(
                        {"type": "pmessage", "pattern": sub.pattern, "topic": topic, "data": message_dict}
                    )
                except queue_module.Full:
                    logging.warning(f"Queue full for pattern subscriber {sub.subscriber_id}")

    def start(self) -> str:
        """Start the server and return the base URL."""
        if self.server_thread is not None:
            return f"http://{self.host}:{self.actual_port}"

        if self.port == 0:
            self.actual_port = self._find_free_port()
        else:
            self.actual_port = self.port

        self.running = True
        self.start_time = time.time()

        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self.cleanup_thread.start()

        def handler_factory(*args, **kwargs):
            return SharedMemoryRequestHandler(self, *args, **kwargs)

        def run_server():
            try:
                self.server = HTTPServer((self.host, self.actual_port), handler_factory)
                self.server.serve_forever()
            except Exception as e:
                logging.error(f"Server error: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        return f"http://{self.host}:{self.actual_port}"

    def stop(self):
        """Stop the server."""
        self.running = False

        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=1)

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=1)

        self.server = None
        self.server_thread = None

    def cleanup(self):
        """Clear all stored data."""
        with self.lock:
            self.topics.clear()
            self.messages.clear()
            self.subscriptions.clear()
            self.pattern_subscriptions.clear()
            self.strings.clear()
            self.hashes.clear()
            self.sets.clear()
            self.sorted_sets.clear()
            self.lists.clear()


class SharedMemoryMessagingBackend(MessagingBackend):
    """
    Enhanced messaging backend with Redis-like features for testing.
    Works with any execution engine and requires only standard library dependencies.
    """

    def __init__(self, server_url: Optional[str] = None, auto_start_server: bool = True):
        self.server_url = server_url
        self.auto_start_server = auto_start_server
        self.owned_server = None
        self.subscriber_id = f"backend_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"
        self.poll_thread = None
        self.running = False
        self.local_handlers: Dict[str, Callable[[Message], None]] = {}

        if not self.server_url and self.auto_start_server:
            self.owned_server = SharedMemoryServer()
            self.server_url = self.owned_server.start()
            logging.info(f"Started enhanced shared memory server at {self.server_url}")
        elif not self.server_url:
            raise ValueError("server_url must be provided if auto_start_server=False")

        # Test connection
        self._test_connection()

        # Start polling thread for subscriptions
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _test_connection(self):
        """Test connection to the server."""
        try:
            response = urlopen(f"{self.server_url}/health", timeout=5)
            if response.getcode() != 200:
                raise ConnectionError(f"Server health check failed: {response.getcode()}")
        except URLError as e:
            raise ConnectionError(f"Cannot connect to shared memory server at {self.server_url}: {e}")

    def _make_request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        """Make HTTP request to the server."""
        url = f"{self.server_url}{path}"

        if method == "GET":
            response = urlopen(url, timeout=10)
        elif method == "POST":
            req_data = json.dumps(data).encode("utf-8") if data else b""
            req = Request(url, data=req_data, method="POST")
            req.add_header("Content-Type", "application/json")
            response = urlopen(req, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response_data = response.read().decode("utf-8")
        return json.loads(response_data) if response_data else {}

    def _poll_loop(self):
        """Background thread for long polling."""
        while self.running:
            try:
                if self.local_handlers:
                    # Use shorter polling timeout for faster real-time notifications
                    response = self._make_request("GET", f"/poll?subscriber_id={self.subscriber_id}&timeout=1")

                    messages = response.get("messages", [])
                    for msg in messages:
                        if msg["type"] in ["message", "pmessage"] and "data" in msg:
                            topic = msg["topic"]
                            if topic in self.local_handlers:
                                try:
                                    # Convert dict back to Message
                                    message = Message.model_validate(msg["data"])
                                    self.local_handlers[topic](message)
                                except Exception as e:
                                    logging.error(f"Error handling message: {e}")
                else:
                    time.sleep(0.01)  # Very short sleep when no handlers

            except Exception as e:
                if self.running:
                    logging.error(f"Poll loop error: {e}")
                    time.sleep(0.1)  # Shorter back off on error

    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """Store a message with optional TTL."""
        data = {
            "namespace": namespace,
            "topic": topic,
            "message": message.model_dump(),
            "ttl": message.ttl,  # Use message TTL if set
        }
        self._make_request("POST", "/store_message", data)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """Retrieve all messages for a topic, sorted by ID (which includes priority)."""
        response = self._make_request("GET", f"/messages/{topic}")
        messages = [Message.model_validate(msg_dict) for msg_dict in response]
        # Sort by ID only - GemstoneID already encodes priority in the ID
        messages.sort(key=lambda m: m.id)
        return messages

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """Retrieve messages for a topic since a specific message ID."""
        # Get all messages for the topic first
        all_messages = self.get_messages_for_topic(topic)

        # Find the timestamp of the "since" message
        since_timestamp = None
        for msg in all_messages:
            if msg.id == msg_id_since:
                since_timestamp = msg.timestamp
                break

        if since_timestamp is None:
            # If we can't find the since message, use ID-based comparison
            filtered_messages = [msg for msg in all_messages if msg.id > msg_id_since]
        else:
            # Use timestamp-based filtering, but for same timestamp use ID comparison
            filtered_messages = []
            for msg in all_messages:
                if msg.timestamp > since_timestamp:
                    filtered_messages.append(msg)
                elif msg.timestamp == since_timestamp and msg.id > msg_id_since:
                    filtered_messages.append(msg)

        # Sort by ID only - GemstoneID already encodes priority in the ID
        filtered_messages.sort(key=lambda m: m.id)

        return filtered_messages

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """Get timestamp for a message ID by extracting it from the GemstoneID."""
        try:
            # Extract timestamp from the GemstoneID like other backends do
            gemstone_id = GemstoneID.from_int(msg_id)
            return float(gemstone_id.timestamp)
        except Exception:
            # Fallback to using ID as timestamp if extraction fails
            return float(msg_id)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """Get the next message for a topic since a specific ID."""
        messages = self.get_messages_for_topic_since(topic, last_message_id)
        return messages[0] if messages else None

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """Retrieve messages by their IDs."""
        if not msg_ids:
            return []

        # Build query string
        ids_param = "&".join(f"ids={msg_id}" for msg_id in msg_ids)
        path = f"/messages_by_id/?namespace={namespace}&{ids_param}"

        response = self._make_request("GET", path)
        return [Message.model_validate(msg_dict) for msg_dict in response]

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """Load subscribers (simplified for this implementation)."""
        return {}

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to a topic with real-time notifications via polling."""
        # Register local handler
        self.local_handlers[topic] = handler

        # Register with server
        data = {"topic": topic, "subscriber_id": self.subscriber_id}
        self._make_request("POST", "/subscribe", data)

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        # Remove local handler
        self.local_handlers.pop(topic, None)

        # Unregister from server
        data = {"topic": topic, "subscriber_id": self.subscriber_id}
        self._make_request("POST", "/unsubscribe", data)

    def supports_subscription(self) -> bool:
        """This implementation now supports real-time subscriptions via polling."""
        return True

    def cleanup(self) -> None:
        """Clean up resources."""
        self.running = False

        if self.poll_thread:
            self.poll_thread.join(timeout=1)

        if self.owned_server:
            self.owned_server.cleanup()
            self.owned_server.stop()
            self.owned_server = None

    # Additional Redis-like methods for testing
    def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        """Redis-like SET command."""
        data: Dict[str, Any] = {"key": key, "value": value}
        if ex:
            data["ex"] = ex
        self._make_request("POST", "/set", data)

    def get(self, key: str) -> Optional[str]:
        """Redis-like GET command."""
        response = self._make_request("GET", f"/get/{key}")
        return response.get("value")

    def publish(self, channel: str, message: str) -> int:
        """Redis-like PUBLISH command."""
        data = {"channel": channel, "message": message}
        response = self._make_request("POST", "/publish", data)
        return response.get("subscribers", 0)

    def psubscribe(self, pattern: str, handler: Callable[[Message], None]) -> None:
        """Redis-like PSUBSCRIBE command."""
        # Register local handler for pattern
        self.local_handlers[pattern] = handler

        # Register with server
        data = {"pattern": pattern, "subscriber_id": self.subscriber_id}
        self._make_request("POST", "/psubscribe", data)

    def punsubscribe(self, pattern: str) -> None:
        """Redis-like PUNSUBSCRIBE command."""
        # Remove local handler
        self.local_handlers.pop(pattern, None)

        # Unregister from server
        data = {"pattern": pattern, "subscriber_id": self.subscriber_id}
        self._make_request("POST", "/punsubscribe", data)

    def hset(self, key: str, field: str, value: str) -> None:
        """Redis-like HSET command."""
        data = {"key": key, "field": field, "value": value}
        self._make_request("POST", "/hset", data)

    def hget(self, key: str, field: str) -> Optional[str]:
        """Redis-like HGET command."""
        response = self._make_request("GET", f"/hget/{key}/{field}")
        return response.get("value")

    def sadd(self, key: str, *members: str) -> int:
        """Redis-like SADD command."""
        data = {"key": key, "members": list(members)}
        response = self._make_request("POST", "/sadd", data)
        return response.get("added", 0)

    def smembers(self, key: str) -> Set[str]:
        """Redis-like SMEMBERS command."""
        response = self._make_request("GET", f"/smembers/{key}")
        return set(response.get("members", []))


# Utility functions for testing
def start_shared_memory_server(host: str = "localhost", port: int = 0) -> tuple[SharedMemoryServer, str]:
    """
    Start a shared memory server for testing.

    Returns:
        Tuple of (server_instance, server_url)
    """
    server = SharedMemoryServer(host, port)
    url = server.start()
    return server, url


def create_shared_messaging_config(server_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a MessagingConfig for shared memory backend.

    Args:
        server_url: URL of existing server, or None to auto-start one

    Returns:
        Configuration dictionary for MessagingConfig
    """
    config: Dict[str, Any] = {
        "backend_module": "rustic_ai.core.messaging.backend.shared_memory_backend",
        "backend_class": "SharedMemoryMessagingBackend",
        "backend_config": {},
    }

    if server_url:
        config["backend_config"]["server_url"] = server_url
        config["backend_config"]["auto_start_server"] = False

    return config
