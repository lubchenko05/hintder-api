"""Legal-document endpoints — serve static markdown files.

The terms, privacy, and refund documents live as markdown in ``dating/static``
and are served verbatim; the frontend renders them. Keeping them as files (not
DB rows or hardcoded strings) makes them easy to edit and review in git.
"""

from pathlib import Path

from fastapi import APIRouter

from dating.serializers.legal import LegalDocumentSerializer
from dating.utils.error_handler import NotFoundException

router = APIRouter()

_STATIC_DIR = Path(__file__).parent.parent / "static"
_DOCS = {
    "terms-of-service": _STATIC_DIR / "terms_of_service.md",
    "privacy-policy": _STATIC_DIR / "privacy_policy.md",
    "refund-policy": _STATIC_DIR / "refund_policy.md",
}


def _read_doc(slug: str) -> LegalDocumentSerializer:
    """Read a legal markdown file by slug, 404 if it's missing."""
    path = _DOCS[slug]
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NotFoundException(f"{slug} document not found") from exc
    return LegalDocumentSerializer(content=content)


@router.get("/legal/terms-of-service", response_model=LegalDocumentSerializer, tags=["legal"])
async def get_terms_of_service() -> LegalDocumentSerializer:
    """Return the Terms of Service markdown."""
    return _read_doc("terms-of-service")


@router.get("/legal/privacy-policy", response_model=LegalDocumentSerializer, tags=["legal"])
async def get_privacy_policy() -> LegalDocumentSerializer:
    """Return the Privacy Policy markdown."""
    return _read_doc("privacy-policy")


@router.get("/legal/refund-policy", response_model=LegalDocumentSerializer, tags=["legal"])
async def get_refund_policy() -> LegalDocumentSerializer:
    """Return the Refund Policy markdown."""
    return _read_doc("refund-policy")
