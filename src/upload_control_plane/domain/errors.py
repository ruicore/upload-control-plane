"""Domain-level exceptions without transport or persistence dependencies."""


class DomainError(ValueError):
    """Base error for invalid domain operations."""


class InvalidPartConfigurationError(DomainError):
    """Raised when file size, part size, or part number constraints are invalid."""


class InvalidStateTransitionError(DomainError):
    """Raised when an upload session transition violates the state machine."""


class InvalidObjectNameError(DomainError):
    """Raised when a client-provided object or filename is unsafe."""
