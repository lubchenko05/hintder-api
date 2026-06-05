"""Base classes for request validators and response serializers.

Naming convention enforced by review:
- Request models end in ``Validator`` (e.g. ``ConsumeHintValidator``).
- Response models end in ``Serializer`` (e.g. ``HintBalanceSerializer``).
"""

from pydantic import BaseModel, ConfigDict


class BaseValidator(BaseModel):
    """Strict request-body validator — rejects unknown fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class BaseSerializer(BaseModel):
    """Response serializer with ORM round-tripping (``model_validate(orm_obj)``)."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
    )
