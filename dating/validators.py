"""Reusable Pydantic ``Annotated`` types for request validation.

One source of truth for common field constraints so serializers don't inline
``Field(min_length=1)`` everywhere.
"""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
"""Trimmed string with at least one character."""

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
"""Single-line text, ≤255 chars (column-bounded)."""

LongText = Annotated[str, StringConstraints(min_length=1, max_length=10_000, strip_whitespace=True)]
"""Multi-line text up to 10k chars."""


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _validate_email(value: str) -> str:
    """Lower-case + format-check an email; raise ``ValueError`` if malformed."""
    s = value.strip().lower()
    if not _EMAIL_RE.match(s):
        raise ValueError("Invalid email address")
    return s


Email = Annotated[str, AfterValidator(_validate_email)]
"""Normalised (lower-cased, validated) email address."""
