"""One-time (idempotent): import guides and stories from the frontend repo.

Reads ``dating-next/content/{guides,stories}/*.md``, maps frontmatter onto
``content_posts`` and renders the markdown once on the way in. Re-running is an
upsert by ``(kind, slug)``, so a partial run is safe to repeat.

    python scripts/import_content_md.py --content-dir ../dating-next/content
    python scripts/import_content_md.py --dry-run          # report only
    python scripts/import_content_md.py \\
        --api-url https://api.hintder.ai --api-key $KEY    # upsert via admin API

API mode exists for production: it needs no database connection, goes through
the exact ``PostUpsert`` contract the daily jobs use, and therefore also
exercises rendering and revalidation on the server side.

The migration's acceptance gate is the set of URLs before and after: this script
never invents or drops a slug, so ``sitemap`` must match the file listing
one-for-one.
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from dating.app import App
from dating.config import get_config
from dating.models.content import CONTENT_KINDS, SOURCE_IMPORT, STATUS_PUBLISHED
from dating.services.markdown import estimate_read_minutes, render_markdown

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into its frontmatter mapping and its body."""
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw
    data = yaml.safe_load(match.group(1)) or {}
    return data, raw[match.end() :]


def parse_read_time(value: Any, body_md: str) -> int:
    """``"6 min"`` → ``6``; anything unparseable falls back to the word count."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.search(r"\d+", value)
        if digits:
            return int(digits.group())
    return estimate_read_minutes(body_md)


def parse_date(value: Any) -> datetime:
    """Frontmatter ``date`` → an aware UTC timestamp."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "year"):  # datetime.date from the YAML parser
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def legacy_blocks(meta: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Rebuild ``blocks`` for a story written before the blocks format.

    Every story in the repo already uses ``blocks``; this exists so an older
    file (or one restored from history) still imports rather than silently
    losing its thread and metrics.
    """
    blocks: list[dict[str, Any]] = []
    if meta.get("metrics"):
        blocks.append({"type": "metrics", "metrics": meta["metrics"]})
    if meta.get("thread"):
        blocks.append({"type": "thread", "messages": meta["thread"]})
    if meta.get("opener"):
        blocks.append({"type": "opener", "opener": meta["opener"]})
    if meta.get("quote"):
        block: dict[str, Any] = {"type": "quote", "quote": meta["quote"]}
        if meta.get("quoteBy"):
            block["attribution"] = meta["quoteBy"]
        blocks.append(block)
    return blocks or None


def build_row(kind: str, slug: str, meta: dict[str, Any], body_md: str) -> dict[str, Any]:
    """Map one file onto the column set."""
    return {
        "locale": "en",
        "title": meta.get("title") or "",
        "seo_title": meta.get("seoTitle"),
        "subtitle": meta.get("subtitle"),
        "excerpt": meta.get("excerpt") or "",
        "body_md": body_md,
        "body_html": render_markdown(body_md),
        "blocks": meta.get("blocks") or legacy_blocks(meta),
        "category": meta.get("category") or "",
        "persona": meta.get("persona"),
        "read_time_minutes": parse_read_time(meta.get("readTime"), body_md),
        "keywords": meta.get("keywords"),
        "status": STATUS_PUBLISHED,
        "published_at": parse_date(meta.get("date")),
        "noindex": bool(meta.get("noindex", False)),
        "source": SOURCE_IMPORT,
    }


def to_payload(kind: str, slug: str, row: dict[str, Any]) -> dict[str, Any]:
    """The DB row, reshaped into the admin API's ``PostUpsert`` body.

    ``body_html`` is dropped on purpose: the server renders ``body_md`` itself,
    so both import modes produce HTML from the same renderer.
    """
    payload = {k: v for k, v in row.items() if k != "body_html"}
    payload["kind"] = kind
    payload["slug"] = slug
    published = payload.get("published_at")
    if published is not None:
        payload["published_at"] = published.isoformat()
    return payload


async def run_api(content_dir: Path, api_url: str, api_key: str) -> int:
    """Import by POSTing every file to ``/admin/content/posts``."""
    import httpx

    base = api_url.rstrip("/") + "/api/v1/admin/content/posts"
    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for kind in CONTENT_KINDS:
            folder = content_dir / kind
            if not folder.is_dir():
                continue
            files = sorted(folder.glob("*.md"))
            print(f"\n{kind}: {len(files)} files → {base}")
            for path in files:
                slug = path.stem
                try:
                    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
                    row = build_row(kind, slug, meta, body)
                    resp = await client.post(
                        base,
                        json=to_payload(kind, slug, row),
                        headers={"X-Automation-Key": api_key},
                    )
                    resp.raise_for_status()
                    was_created = resp.json()["created"]
                    created += was_created
                    updated += not was_created
                    print(f"  {'+' if was_created else '~'} {slug}")
                except Exception as exc:
                    failed += 1
                    print(f"  ✗ {slug}: {exc}")
    print(f"\ncreated {created} · updated {updated} · failed {failed}")
    return 1 if failed else 0


async def run(content_dir: Path, dry_run: bool) -> int:
    """Import every markdown file under ``content_dir``. Returns an exit code."""
    app = App(get_config())
    await app.setup()
    db = app.inj["db"]

    created = updated = failed = 0
    try:
        for kind in CONTENT_KINDS:
            folder = content_dir / kind
            if not folder.is_dir():
                print(f"! {folder} does not exist — skipping {kind}")
                continue

            files = sorted(folder.glob("*.md"))
            print(f"\n{kind}: {len(files)} files")

            for path in files:
                slug = path.stem
                try:
                    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
                    if not meta.get("title"):
                        raise ValueError("missing title in frontmatter")
                    row = build_row(kind, slug, meta, body)
                except Exception as exc:  # one bad file must not stop the import
                    failed += 1
                    print(f"  ✗ {slug}: {exc}")
                    continue

                if dry_run:
                    print(f"  · {slug} ({row['read_time_minutes']} min, "
                          f"{len(row['body_html'])} bytes html)")
                    continue

                _, was_created = await db.content.upsert(kind, slug, row)
                created += was_created
                updated += not was_created
                print(f"  {'+' if was_created else '~'} {slug}")
    finally:
        await app.close()

    print(f"\ncreated {created} · updated {updated} · failed {failed}")
    return 1 if failed else 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--content-dir",
        default="../dating-next/content",
        help="folder holding guides/ and stories/",
    )
    parser.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    parser.add_argument("--api-url", default=None, help="upsert via this API instead of the DB")
    parser.add_argument("--api-key", default=None, help="X-Automation-Key for --api-url")
    args = parser.parse_args()

    content_dir = Path(args.content_dir).expanduser().resolve()
    if not content_dir.is_dir():
        print(f"content dir not found: {content_dir}")
        return 1
    if args.api_url:
        if not args.api_key:
            print("--api-url requires --api-key")
            return 1
        return asyncio.run(run_api(content_dir, args.api_url, args.api_key))
    return asyncio.run(run(content_dir, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
