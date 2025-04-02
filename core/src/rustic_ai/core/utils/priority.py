from enum import IntEnum


class Priority(IntEnum):
    """
    Priority levels for messages.
    """

    LOWEST = 7
    VERY_LOW = 6
    LOW = 5
    NORMAL = 4
    ABOVE_NORMAL = 3
    HIGH = 2
    IMPORTANT = 1
    URGENT = 0
