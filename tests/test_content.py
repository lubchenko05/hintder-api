"""Content pipeline: markdown parity, sanitisation, and upsert preparation."""

from dating.bl.content import _prepare, post_path
from dating.serializers.content import PostUpsertValidator
from dating.services.markdown import (
    render_markdown,
    sanitize_html,
)


def test_render_produces_gfm_tables() -> None:
    html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<table>" in html and "<td>1</td>" in html


def test_sanitizer_strips_scripts_and_keeps_links() -> None:
    html = render_markdown("[x](https://a.com) <script>alert(1)</script>")
    assert "<script" not in html
    assert '<a href="https://a.com">' in html


def test_sanitizer_does_not_stamp_rel_on_internal_links() -> None:
    # Byte-parity with the old frontend renderer: no injected rel attributes.
    html = render_markdown("[guide](/guides/other-guide)")
    assert "rel=" not in html


def test_sanitizer_rejects_javascript_urls() -> None:
    assert "javascript" not in sanitize_html('<a href="javascript:alert(1)">x</a>')


def test_prepare_renders_and_fills_derived_fields() -> None:
    data = _prepare({"body_md": "# T\n\n" + "word " * 440, "status": "published"})
    assert data["body_html"].startswith("<h1>")
    assert data["read_time_minutes"] == 2
    assert data["published_at"] is not None


def test_prepare_sanitizes_prerendered_html() -> None:
    data = _prepare({"body_md": "", "body_html": "<p>ok</p><script>x</script>"})
    assert data["body_html"] == "<p>ok</p>"


def test_upsert_validator_rejects_unknown_block_type() -> None:
    try:
        PostUpsertValidator(kind="stories", slug="s", title="t", blocks=[{"type": "hologram"}])
        raise AssertionError("expected validation error")
    except ValueError:
        pass


def test_upsert_validator_normalises_slug() -> None:
    v = PostUpsertValidator(kind="guides", slug="  My-Slug ", title="t")
    assert v.slug == "my-slug"


def test_post_path_shape() -> None:
    assert post_path("guides", "x") == "/guides/x"
