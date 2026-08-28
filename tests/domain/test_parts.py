import pytest

from upload_control_plane.domain.errors import InvalidPartConfigurationError
from upload_control_plane.domain.parts import (
    DEFAULT_PART_SIZE,
    GIB,
    MAX_PART_COUNT,
    MAX_PART_SIZE,
    MIB,
    MIN_PART_SIZE,
    choose_part_size,
    get_part_count,
    get_part_range,
)


def test_choose_part_size_defaults_to_64_mib_for_practical_uploads() -> None:
    assert choose_part_size(5 * GIB, None) == DEFAULT_PART_SIZE


def test_choose_part_size_accepts_5_mib_minimum_explicit_part_size() -> None:
    assert choose_part_size(5 * MIB, MIN_PART_SIZE) == MIN_PART_SIZE


def test_choose_part_size_rejects_non_final_part_below_5_mib() -> None:
    with pytest.raises(InvalidPartConfigurationError):
        choose_part_size(10 * MIB, MIN_PART_SIZE - 1)


def test_choose_part_size_accepts_5_gib_maximum_explicit_part_size() -> None:
    assert choose_part_size(MAX_PART_SIZE, MAX_PART_SIZE) == MAX_PART_SIZE


def test_choose_part_size_rejects_explicit_part_size_above_5_gib() -> None:
    with pytest.raises(InvalidPartConfigurationError):
        choose_part_size(MAX_PART_SIZE + 1, MAX_PART_SIZE + 1)


def test_choose_part_size_rounds_automatic_size_to_mib_for_10000_part_boundary() -> None:
    file_size = DEFAULT_PART_SIZE * MAX_PART_COUNT + 1

    part_size = choose_part_size(file_size, None)

    assert part_size == DEFAULT_PART_SIZE + MIB
    assert get_part_count(file_size, part_size) <= MAX_PART_COUNT


def test_choose_part_size_rejects_files_that_exceed_10000_5gib_parts() -> None:
    with pytest.raises(InvalidPartConfigurationError):
        choose_part_size(MAX_PART_SIZE * MAX_PART_COUNT + 1, None)


def test_get_part_range_returns_first_middle_and_smaller_final_ranges() -> None:
    file_size = (2 * DEFAULT_PART_SIZE) + 123

    first = get_part_range(file_size, DEFAULT_PART_SIZE, 1)
    middle = get_part_range(file_size, DEFAULT_PART_SIZE, 2)
    final = get_part_range(file_size, DEFAULT_PART_SIZE, 3)

    assert first.offset_start == 0
    assert first.offset_end_exclusive == DEFAULT_PART_SIZE
    assert first.expected_size == DEFAULT_PART_SIZE
    assert middle.offset_start == DEFAULT_PART_SIZE
    assert middle.offset_end_exclusive == 2 * DEFAULT_PART_SIZE
    assert middle.expected_size == DEFAULT_PART_SIZE
    assert final.offset_start == 2 * DEFAULT_PART_SIZE
    assert final.offset_end_exclusive == file_size
    assert final.expected_size == 123


def test_get_part_range_rejects_part_numbers_outside_one_based_count() -> None:
    with pytest.raises(InvalidPartConfigurationError):
        get_part_range(64 * MIB, DEFAULT_PART_SIZE, 0)

    with pytest.raises(InvalidPartConfigurationError):
        get_part_range(64 * MIB, DEFAULT_PART_SIZE, 2)
