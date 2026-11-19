"""Exceptions raised by the Pratibimb core engine."""


class PratibimbError(Exception):
    """Base class for all engine errors."""


class ValidationError(PratibimbError):
    """Input failed validation. Nothing was written."""


class NotFoundError(PratibimbError):
    """A referenced record does not exist."""


class SupersedeError(ValidationError):
    """Illegal correction: unknown target, wrong table, or already superseded."""
