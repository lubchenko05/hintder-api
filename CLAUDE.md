# CLAUDE.md

Guidance for Claude Code when working in `dating-api/` (the hintder backend).

## Git Rules (MUST FOLLOW)

**Never run `git commit`, `git push`, or `git tag` without explicit permission
from the user in the current turn.** Staging (`git add`) is fine. Editing files
is fine — just don't finalize into commits/pushes/tags. The user manages this
repository's git setup themselves.

## Project Overview

hintder is a dating wingman app. A user uploads a screenshot of a match's
profile (or a stalled chat thread) and gets opener / reply suggestions in a
chosen tone. Hints are consumable credits: the first 3 are free, more are sold
as one-time packs via Paddle (no subscriptions).

- **`dating-next/`** — Next.js 16 / React 19 frontend (sibling repo)
- **`dating-api/`** — this FastAPI / Python 3.12 backend

Payments go through **Paddle** (Merchant of Record). Paddle requires a refund
window be stated; ours is **14 days** — keep every "refund within N days" string
in sync (`config.refund_window_days`).

## Commands

```bash
make dev            # uvicorn dev server (python main.py)
make test           # pytest
make lint           # mypy + isort + black + flake8 (the CI gate's lint half)
make format         # isort + autoflake + black (auto-fix)
make migrate        # alembic upgrade head
make migrate-create msg="add foo"   # autogenerate a revision
make install-dev    # pip install ci deps + editable install
```

## Conventions (non-negotiable)

- **Python 3.12** — use native `str | None`, `list[X]` syntax. Do **not** add
  `from __future__ import annotations`.
- **No relative imports.** Always import from the `dating` package root
  (`ban-relative-imports` in flake8). Local (function-body) imports are allowed
  only to break import cycles / defer heavy deps, and the module must still
  carry a docstring.
- **Docstrings everywhere** — every module, public class, and public function
  has one (`flake8-docstrings`). `__init__.py` re-export shims need only a
  module docstring.
- **mypy strict** — `disallow_untyped_defs`, `disallow_untyped_calls`,
  `disallow_any_generics`, `strict_optional`. Annotate everything.
- **black + isort**, line length 100.

## Architecture (layered)

Request flow: `views → bl → storages/services → models/DB`.

- **`config.py`** — pydantic-settings, env-driven, prod secrets via GCP Secret
  Manager fallback. `get_config()` returns a cached singleton.
- **`app.py`** — `App` + `Inj` DI container. `setup()` builds the DB engine,
  sessionmaker, `DBStorage`, and services into `inj`; `close()` disposes them.
- **`routers.py`** — aggregates all v1 routers under `/api/v1`; `/api/health`
  is the liveness probe.
- **`models/`** — SQLAlchemy 2.0 `Mapped[]` ORM models. Register each in
  `models/__init__.py` so Alembic autogenerate sees it.
- **`storages/`** — async data access. One class per entity extending
  `BaseStorage`; `DBStorage` aggregates them (`db.user`, `db.hint`, …). `get_*`
  returns `Model | None`, paired with `get_*_or_error` raising `NotFoundException`.
- **`bl/`** — business logic. Pure orchestration over storages/services; never
  imports FastAPI; raises `AppException` subclasses. Callable from views/tasks/scripts.
- **`services/`** — external integrations behind swappable seams:
  - `ai.py` — `AIClient` protocol + `GeminiAIClient` (Gemini 2.5 Flash, vision +
    JSON structured output). No mocks; needs `AI_API_KEY`. Returns camelCase DTOs
    that mirror the frontend `@/types` so responses are drop-in.
  - `paddle.py` — `PaddleService`. Mock checkout while `paddle_enabled` is False;
    real HMAC webhook verification.
- **`serializers/`** — Pydantic v2. Request models end in `Validator`
  (`extra="forbid"`); response models end in `Serializer` (`from_attributes=True`).
- **`views/`** — thin FastAPI handlers; decode/validate, call `bl`, serialize.
- **`dependencies/`** — `Depends()` wrappers: `inj` (service handles), `auth`
  (token → current user), `lifecycle`, `pagination`.

## Auth

Two-layer: the client sends a **Firebase ID token** to `POST /api/v1/auth/firebase`;
`bl/auth` verifies it (Firebase Admin SDK), upserts the `User` (Firebase UID is
the PK), and returns a **backend-issued JWT**. Subsequent requests send that JWT
as a Bearer token; `dependencies/auth` decodes it to the current user.

## Hints model

`User` carries two integer counters: `free_hints` (granted once, default 3) and
`paid_hints` (topped up by purchases). A read drains free first, then paid.
Every spend is appended to `HintConsumption` (audit log). Purchases are recorded
in `Purchase`; Paddle webhook events in `PaddleEvent` (idempotency by Paddle
transaction id).

## No worker

Processing is synchronous and simple — there is **no** ARQ/Redis worker, no
Cloud Run Jobs. A read is a normal request that calls the AI client and returns.

## Deploy

Cloud Run. Multi-stage `Dockerfile`, listens on `$PORT` (8080). Prod secrets
resolve via GCP Secret Manager (`utils/secret_manager.py`) keyed by the
UPPER_SNAKE env-var name.
