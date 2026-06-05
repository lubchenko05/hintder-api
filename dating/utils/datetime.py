"""Datetime helpers — all timestamps are stored as naive UTC.

Postgres ``TIMESTAMP WITHOUT TIME ZONE`` columns hold UTC wall-clock values.
Storing naive-UTC (rather than tz-aware) keeps comparisons trivial and avoids
the asyncpg tz-coercion surprises that bite mixed aware/naive arithmetic.
"""

from datetime import datetime, UTC


def utcnow() -> datetime:
    """Return the current UTC time as a naive ``datetime`` (no tzinfo)."""
    return datetime.now(UTC).replace(tzinfo=None)
