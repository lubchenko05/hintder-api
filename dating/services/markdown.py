"""Markdown → sanitised HTML for guides and stories.

Rendering moved here from the frontend so a post can be published without a
deploy. Two properties matter:

* **Parity.** The frontend rendered with remark + remark-gfm (CommonMark plus
  GitHub tables/strikethrough/autolinks). ``markdown-it-py`` in "gfm-like"
  configuration is the same grammar, so imported posts produce HTML equivalent
  to what the site served before — that equivalence is the migration's gate.
* **Safety.** Rendered HTML is stored and later injected with
  ``dangerouslySetInnerHTML``, so it passes an allowlist on the way in. nh3
  (ammonia) is the single security boundary: whatever it strips can never reach
  a reader, regardless of who wrote the markdown.
"""

import re

import nh3
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

# Tags a post may legitimately use. Anything else — script, style, iframe,
# object, embed, form — is dropped with its contents.
_ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "del",
    "code",
    "pre",
    "a",
    "img",
    "ul",
    "ol",
    "li",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "figure",
    "figcaption",
    "span",
}

_ALLOWED_ATTRS = {
    # No "target": markdown can't produce target=_blank, and without _blank the
    # noopener dance is moot. Author-supplied rel survives as-is.
    "a": {"href", "title", "rel"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "span": {"class"},
    "code": {"class"},
    "th": {"align"},
    "td": {"align"},
}

# Only real web links survive: no javascript:, no data: payloads.
_ALLOWED_SCHEMES = {"http", "https", "mailto"}

_WORDS_PER_MINUTE = 220


def _renderer() -> MarkdownIt:
    """A CommonMark+GFM renderer matching what the frontend used."""
    md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.use(front_matter_plugin)  # tolerate a stray frontmatter block, render nothing
    return md


_MD = _renderer()


def render_markdown(body_md: str) -> str:
    """Render markdown to HTML and pass it through the allowlist."""
    return sanitize_html(_MD.render(body_md or ""))


def sanitize_html(html: str) -> str:
    """Run HTML through the allowlist.

    Used both for our own rendered markdown and for HTML that arrives already
    rendered (an admin paste today, a webhook tomorrow) — one gate, one set of
    rules, no way around it.
    """
    return nh3.clean(
        html or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_ALLOWED_SCHEMES,
        # link_rel=None: nh3 would otherwise stamp noopener/noreferrer on every
        # link — including the internal cross-links between guides, which kills
        # referrer data and breaks byte-parity with the old frontend renderer.
        # Safe because target is not allowlisted, so no link can open a window
        # that could reach back via window.opener.
        link_rel=None,
    )


def estimate_read_minutes(body_md: str) -> int:
    """Reading time in whole minutes, never zero for a non-empty post."""
    words = len(re.findall(r"\w+", body_md or ""))
    if words == 0:
        return 0
    return max(1, round(words / _WORDS_PER_MINUTE))
