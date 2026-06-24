"""Multipart part sizing and byte-range calculations."""

from dataclasses import dataclass

from upload_control_plane.domain.errors import InvalidPartConfigurationError

MIB = 1024 * 1024
GIB = 1024 * MIB
MIN_PART_SIZE = 5 * MIB
DEFAULT_PART_SIZE = 64 * MIB
MAX_PART_SIZE = 5 * GIB
MAX_PART_COUNT = 10_000


@dataclass(frozen=True, slots=True)
class PartRange:
    part_number: int
    offset_start: int
    offset_end_exclusive: int
    expected_size: int


def ceil_div(dividend: int, divisor: int) -> int:
    if divisor <= 0:
        raise InvalidPartConfigurationError("divisor must be positive")
    return -(-dividend // divisor)


def round_up_to_mib(value: int) -> int:
    return ceil_div(value, MIB) * MIB


def choose_part_size(file_size_bytes: int, requested_part_size_bytes: int | None) -> int:
    """Choose or validate a multipart part size under S3-compatible limits."""
    if file_size_bytes <= 0:
        raise InvalidPartConfigurationError("file size must be positive")

    if requested_part_size_bytes is not None:
        part_size = requested_part_size_bytes
        if part_size < MIN_PART_SIZE:
            raise InvalidPartConfigurationError("part size must be at least 5 MiB")
        if part_size > MAX_PART_SIZE:
            raise InvalidPartConfigurationError("part size must be at most 5 GiB")
    else:
        minimum_to_fit = ceil_div(file_size_bytes, MAX_PART_COUNT)
        part_size = round_up_to_mib(max(DEFAULT_PART_SIZE, MIN_PART_SIZE, minimum_to_fit))
        if part_size > MAX_PART_SIZE:
            raise InvalidPartConfigurationError("file requires a part size greater than 5 GiB")

    if get_part_count(file_size_bytes, part_size) > MAX_PART_COUNT:
        raise InvalidPartConfigurationError("file requires more than 10,000 parts")

    return part_size


def get_part_count(file_size_bytes: int, part_size_bytes: int) -> int:
    if file_size_bytes <= 0:
        raise InvalidPartConfigurationError("file size must be positive")
    if part_size_bytes <= 0:
        raise InvalidPartConfigurationError("part size must be positive")
    return ceil_div(file_size_bytes, part_size_bytes)


def get_part_range(file_size_bytes: int, part_size_bytes: int, part_number: int) -> PartRange:
    """Return the expected byte range for a one-based multipart part number."""
    if part_size_bytes < MIN_PART_SIZE:
        raise InvalidPartConfigurationError("part size must be at least 5 MiB")
    if part_size_bytes > MAX_PART_SIZE:
        raise InvalidPartConfigurationError("part size must be at most 5 GiB")

    part_count = get_part_count(file_size_bytes, part_size_bytes)
    if part_count > MAX_PART_COUNT:
        raise InvalidPartConfigurationError("file requires more than 10,000 parts")
    if part_number < 1 or part_number > part_count:
        raise InvalidPartConfigurationError("part number is outside the expected range")

    offset_start = (part_number - 1) * part_size_bytes
    offset_end_exclusive = min(offset_start + part_size_bytes, file_size_bytes)
    return PartRange(
        part_number=part_number,
        offset_start=offset_start,
        offset_end_exclusive=offset_end_exclusive,
        expected_size=offset_end_exclusive - offset_start,
    )
