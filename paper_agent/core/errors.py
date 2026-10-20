"""Explicitly safe error messages shared by application entry points."""


class PublicResearchError(RuntimeError):
    """A controlled research error whose message may be shown to users."""


def public_error_message(exc: Exception) -> str:
    """Expose controlled messages without leaking external error details."""
    return str(exc) if isinstance(exc, PublicResearchError) else type(exc).__name__
