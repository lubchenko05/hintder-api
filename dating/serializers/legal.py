"""Legal-document endpoint serializers."""

from dating.serializers.base import BaseSerializer


class LegalDocumentSerializer(BaseSerializer):
    """Markdown body of a legal document (TOS, Privacy, Refund)."""

    content: str
