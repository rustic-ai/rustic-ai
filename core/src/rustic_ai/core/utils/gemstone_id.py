import time
from datetime import datetime, timezone

from rustic_ai.core.utils.priority import Priority

# Define the date
date = datetime(2023, 1, 1, tzinfo=timezone.utc)
# Get the millisecond timestamp
EPOCH = int(date.timestamp() * 1000)

# Constants for magic numbers
MACHINE_ID_BITMASK = 0xFF  # Allows for 256 unique machine IDs using 8 bits
SEQUENCE_BITMASK = 0xFFF  # 12 bits, allows for 4096 unique sequence numbers
PRIORITY_BITMASK = 0x7  # 3 bits, allows for 8 unique priority levels
PRIORITY_SHIFT: int = 61
TIMESTAMP_SHIFT: int = 22
MACHINE_ID_SHIFT: int = 12


class ClockMovedBackwardsError(Exception):
    """Exception raised when the system clock moves backwards."""


class GemstoneID(object):
    """
    A unique identifier generator for distributed systems.

    The ID is composed of the following fields:
    - Priority (3 bits): The priority of the ID (between 0 and 7, inclusive)
    - Timestamp (41 bits): The number of milliseconds since the EPOCH (2023-01-01 00:00:00 UTC)
    - Machine ID (8 bits): A unique identifier for the machine generating the ID
    - Sequence Number (12 bits): A sequence number to ensure uniqueness within the same millisecond

    The ID is represented as a 64-bit integer.
    """

    def __init__(self, priority: Priority, timestamp: int, machine_id: int, sequence_number: int):
        """
        Initialize a new GemstoneID.

        :param priority: The priority of the ID (between 0 and 7, inclusive)
        :param timestamp: The number of milliseconds since the EPOCH (2023-01-01 00:00:00 UTC)
        :param machine_id: A unique identifier for the machine generating the ID
        :param sequence_number: A sequence number to ensure uniqueness within the same millisecond
        """
        # Validate the extracted values
        if priority > 7 or priority < 0:
            raise ValueError("Invalid priority value extracted from ID.")

        if machine_id > 255 or machine_id < 0:
            raise ValueError("Invalid machine_id value extracted from ID.")

        if sequence_number > 4095 or sequence_number < 0:
            raise ValueError("Invalid sequence_number value extracted from ID.")

        self.priority: int = priority.value
        self._timestamp = timestamp
        self.machine_id = machine_id
        self.sequence_number = sequence_number

    def to_int(self) -> int:
        """Convert the GemstoneID to a 64-bit integer."""
        p = (self.priority & PRIORITY_BITMASK) << PRIORITY_SHIFT
        t = (self._timestamp - EPOCH) << TIMESTAMP_SHIFT
        m = (self.machine_id & MACHINE_ID_BITMASK) << MACHINE_ID_SHIFT
        s = self.sequence_number & SEQUENCE_BITMASK

        return p | t | m | s

    @classmethod
    def from_int(cls, id: int) -> "GemstoneID":
        """Create a new GemstoneID from a 64-bit integer."""
        priority = (id >> PRIORITY_SHIFT) & PRIORITY_BITMASK
        timestamp = ((id >> TIMESTAMP_SHIFT) & ((1 << (PRIORITY_SHIFT - TIMESTAMP_SHIFT)) - 1)) + EPOCH
        machine_id = (id >> MACHINE_ID_SHIFT) & ((1 << (TIMESTAMP_SHIFT - MACHINE_ID_SHIFT)) - 1)
        sequence_number = id & SEQUENCE_BITMASK

        return cls(Priority(priority), timestamp, machine_id, sequence_number)

    @classmethod
    def from_string(cls, id: str) -> "GemstoneID":
        """Create a new GemstoneID from a string representation."""
        try:
            id_int = int(id)
        except ValueError:  # pragma: no cover
            raise ValueError("Invalid ID string format.")

        return cls.from_int(id_int)

    @property
    def encoded_priority(self) -> Priority:
        """Return the encoded priority of the ID."""
        return Priority(self.priority)

    @property
    def timestamp(self) -> int:
        return self._timestamp

    def __lt__(self, other):
        """Compare two GemstoneIDs."""
        if not isinstance(other, GemstoneID):
            raise TypeError(f"Cannot compare GemstoneID to {type(other)}")
        return (
            self.priority,
            self._timestamp,
            self.machine_id,
            self.sequence_number,
        ) < (
            other.priority,
            other._timestamp,
            other.machine_id,
            other.sequence_number,
        )

    def __eq__(self, other):
        """Compare two GemstoneIDs for equality."""
        if not isinstance(other, GemstoneID):
            raise TypeError(f"Cannot compare GemstoneID to {type(other)}")
        return (
            self.priority,
            self._timestamp,
            self.machine_id,
            self.sequence_number,
        ) == (
            other.priority,
            other._timestamp,
            other.machine_id,
            other.sequence_number,
        )

    def to_string(self) -> str:
        """Convert the GemstoneID to a string representation."""
        return self.__dict__.__str__()


class GemstoneGenerator:
    """
    A generator for GemstoneIDs.

    The generator uses a machine ID to ensure uniqueness across multiple machines.
    """

    def __init__(self, machine_id: int):
        """
        Initialize a new GemstoneGenerator.

        :param machine_id: A unique identifier for the machine generating the IDs
        """
        if machine_id > 255 or machine_id < 0:
            raise ValueError("Machine ID must be between 0 and 255, inclusive")

        self.machine_id = machine_id
        self.sequence_number = 0
        self.last_timestamp = -1

    def get_id(self, priority: Priority) -> GemstoneID:
        """Generate a new GemstoneID."""
        timestamp = time.time_ns() // 1000000
        if timestamp < self.last_timestamp:
            raise ClockMovedBackwardsError("Clock moved backwards!")

        if timestamp == self.last_timestamp:
            self.sequence_number = (self.sequence_number + 1) & SEQUENCE_BITMASK
            if self.sequence_number == 0:
                # We have already generated 4096 IDs in this millisecond, wait until the next one
                while timestamp <= self.last_timestamp:  # pragma: no cover
                    timestamp = time.time_ns() // 1000000
        else:
            self.sequence_number = 0

        self.last_timestamp = timestamp

        return GemstoneID(priority, timestamp, self.machine_id, self.sequence_number)

    def get_id_from_int(self, id: int) -> GemstoneID:
        """Create a new GemstoneID from a 64-bit integer."""
        return GemstoneID.from_int(id)

    def get_id_from_string(self, id: str) -> GemstoneID:
        """Create a new GemstoneID from a string representation."""
        return GemstoneID.from_string(id)
