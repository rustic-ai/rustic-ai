import time

import pytest

from rustic_ai.core.utils import GemstoneGenerator, Priority
from rustic_ai.core.utils.gemstone_id import ClockMovedBackwardsError, GemstoneID


@pytest.fixture
def generator() -> GemstoneGenerator:
    """
    Fixture that returns a GemstoneGenerator instance with a seed of 1.
    """
    return GemstoneGenerator(1)


@pytest.fixture
def generator2() -> GemstoneGenerator:
    """
    Fixture that returns a GemstoneGenerator instance with a seed of 2.
    """
    return GemstoneGenerator(2)


def test_id_generator(generator):
    """
    Test that the get_id method of a GemstoneGenerator instance returns unique IDs.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator.get_id(Priority.NORMAL)
    assert id1 != id2


def test_id_generator_sorting(generator):
    """
    Test that the get_id method of a GemstoneGenerator instance returns IDs sorted by priority and time.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator.get_id(Priority.HIGH)
    id3 = generator.get_id(Priority.LOW)
    time.sleep(0.001)
    id4 = generator.get_id(Priority.URGENT)
    id5 = generator.get_id(Priority.NORMAL)
    sorted_ids = sorted([id1, id2, id3, id4, id5])
    assert sorted_ids == [id4, id2, id1, id5, id3]


def test_id_generator_across_generators(generator, generator2):
    """
    Test that the get_id method of two different GemstoneGenerator instances returns unique IDs.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator2.get_id(Priority.NORMAL)
    assert id1 != id2


def test_id_generator_sorting_across_generators(generator, generator2):
    """
    Test that the get_id method of two different GemstoneGenerator instances returns IDs sorted by priority and time.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator2.get_id(Priority.IMPORTANT)
    time.sleep(0.001)
    id3 = generator.get_id(Priority.IMPORTANT)
    id4 = generator.get_id(Priority.NORMAL)
    id5 = generator2.get_id(Priority.URGENT)
    sorted_ids = sorted([id1, id2, id3, id4, id5])
    assert sorted_ids == [id5, id2, id3, id1, id4]


def test_id_generator_by_priority_and_time(generator):
    """
    Test that the get_id method of a GemstoneGenerator instance returns IDs sorted by priority and time.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator.get_id(Priority.HIGH)
    id3 = generator.get_id(Priority.LOW)
    id4 = generator.get_id(Priority.NORMAL)
    id5 = generator.get_id(Priority.URGENT)
    id6 = generator.get_id(Priority.LOW)
    sorted_ids = sorted([id1, id2, id3, id4, id5, id6])
    assert sorted_ids == [id5, id2, id1, id4, id3, id6]


def test_id_conversion_to_int_and_back(generator):
    """
    Test that the to_int and from_int methods of a GemstoneID instance correctly convert IDs to and from integers.
    """
    id1: GemstoneID = generator.get_id(Priority.URGENT)
    id2 = id1.to_int()
    id3: GemstoneID = id1.from_int(id2)
    assert (id1.priority, id1.timestamp, id1.machine_id, id1.sequence_number) == (
        id3.priority,
        id3.timestamp,
        id3.machine_id,
        id3.sequence_number,
    )


def test_id_comparison_with_non_id(generator):
    """
    Test that comparing a GemstoneID instance with a non-ID object raises a TypeError.
    """
    id1 = generator.get_id(Priority.URGENT)
    id2 = "123"
    with pytest.raises(TypeError):
        _ = id1 == id2

    with pytest.raises(TypeError):
        _ = id1 < id2


def test_clock_moved_backwards_error(generator):
    """
    Test that a ClockMovedBackwardsError is raised when the clock moves backwards.
    """
    generator.last_timestamp = time.time_ns() // 1000000 + 1000
    with pytest.raises(ClockMovedBackwardsError):
        generator.get_id(Priority.NORMAL)


def test_gemstone_id_string_representation(generator):
    """
    Test that the to_string method of a GemstoneID instance returns a string.
    """
    id1 = generator.get_id(Priority.NORMAL)
    assert isinstance(id1.to_string(), str)


def test_machine_id_boundary():
    """
    Test that a ValueError is raised when the machine ID is greater than 255.
    """
    with pytest.raises(ValueError):
        GemstoneGenerator(256)  # Machine ID bitmask allows only up to 255


def test_id_ordering_by_priority(generator):
    """
    Test that GemstoneID instances are ordered by priority.
    """
    id1 = generator.get_id(Priority.LOW)
    id2 = generator.get_id(Priority.HIGH)
    assert id2 < id1


def test_id_ordering_by_timestamp(generator):
    """
    Test that GemstoneID instances are ordered by timestamp.
    """
    id1 = generator.get_id(Priority.NORMAL)
    time.sleep(0.001)
    id2 = generator.get_id(Priority.NORMAL)
    assert id1 < id2


def test_id_ordering_by_machine_id(generator, generator2):
    """
    Test that GemstoneID instances are ordered by machine ID.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator2.get_id(Priority.NORMAL)
    assert id1.machine_id < id2.machine_id


def test_id_ordering_by_sequence_number(generator):
    """
    Test that GemstoneID instances are ordered by sequence number.
    """
    id1 = generator.get_id(Priority.NORMAL)
    id2 = generator.get_id(Priority.NORMAL)
    assert id1.sequence_number < id2.sequence_number


def test_sequence_max_in_milisecond(generator):
    """
    Test that the sequence number resets to 0 when the maximum number of IDs is generated in a millisecond.
    """
    id1 = generator.get_id(Priority.NORMAL)
    for _ in range(4095):
        generator.get_id(Priority.NORMAL)
    id2 = generator.get_id(Priority.NORMAL)
    for _ in range(4095):
        generator.get_id(Priority.NORMAL)
    id3 = generator.get_id(Priority.NORMAL)
    assert id2.timestamp > id1.timestamp
    assert id3.timestamp > id2.timestamp


# Test that a ValueError is raised when creating using a generator with an invalid priority.
def test_create_gemstone_id_with_invalid_priority(generator):
    with pytest.raises(ValueError):
        generator.get_id(123)


# Test that a ValueError is raised when creating using building a generator with invalid machine ID.
def test_create_generator_with_invalid_machine_id():
    with pytest.raises(ValueError):
        GemstoneGenerator(256)


# Test that a ValueError is raised when creating using building a generator with invalid sequence ID.
def test_create_gemstone_id_with_invalid_sequence_number():
    with pytest.raises(ValueError):
        GemstoneID(Priority.NORMAL, time.time_ns() // 1000000, 255, 5000)


# Test that a ValueError is raised when creating using building a generator with invalid machine ID.
def test_create_gemstone_id_with_invalid_machine_id():
    with pytest.raises(ValueError):
        GemstoneID(Priority.NORMAL, time.time_ns() // 1000000, 256, 1)
