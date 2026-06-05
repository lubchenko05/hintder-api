# dating-api

FastAPI backend for hintder (dating wingman). Python 3.12, async SQLAlchemy +
Postgres, Pydantic v2, Firebase auth, Paddle billing (mocked). See `CLAUDE.md`
for architecture and conventions.

## Quick start

```bash
# 1. Create the local Postgres role + database (one-time, by hand):
#    psql -c "CREATE ROLE dating LOGIN PASSWORD 'dating';"
#    psql -c "CREATE DATABASE dating OWNER dating;"

# 2. Python env + deps
python3.12 -m venv .venv && source .venv/bin/activate
make install-dev

# 3. Env file
cp secrets/local.env.example secrets/local.env   # edit JWT + Firebase as needed

# 4. Migrate + run
make migrate
make dev          # http://localhost:8010  · docs at /api/docs
```

## Make targets

| Target | What |
|---|---|
| `make dev` | uvicorn dev server (reload) |
| `make migrate` | `alembic upgrade head` |
| `make migrate-create msg="..."` | autogenerate a revision |
| `make lint` | mypy + isort + black + flake8 |
| `make format` | auto-fix (isort + autoflake + black) |
| `make test` | pytest |
| `make check` | lint + test (CI gate) |

## API surface (`/api/v1`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/firebase` | — | Firebase ID token → backend JWT (upserts user) |
| GET | `/me` | JWT | Profile + hint balance |
| GET | `/me/hints` | JWT | Balance only |
| GET | `/me/hints/history` | JWT | Consumption ledger (paged) |
| POST | `/reads/analyze` | JWT | Gemini: screenshots → structured profile analysis |
| POST | `/reads/messages` | JWT | Gemini: analysis + voice → 5 openers |
| POST | `/reads/reply` | JWT | Gemini: thread → next-move coaching |
| POST | `/reads/tweak` | JWT | Gemini: rewrite one message |
| GET | `/billing/packs` | — | Hint-pack catalogue |
| POST | `/billing/checkout` | JWT | Create checkout (mock URL while Paddle off) |
| POST | `/billing/mock/complete` | JWT | Dev-only: simulate webhook, grant hints |
| POST | `/paddle/webhook` | sig | Real Paddle grant path (HMAC-verified) |
| GET | `/legal/terms` | — | Commercial terms (14-day refund window) |

## Hints model

`users.free_hints` (3 on signup) + `users.paid_hints` (purchases). Spending goes
through `POST /hints/consume` (free bucket first, then paid — atomically, with a
`FOR UPDATE` lock — appending a row to `hint_consumptions`). The frontend gates on
balance and spends per generation op. Purchases are idempotent on the Paddle
transaction id.

## AI (Gemini)

Generation is **real Gemini 2.5 Flash** (`AI_MODEL`, vision + JSON structured
output) — no mocks. Set `AI_API_KEY` to a Google AI Studio key. The four
`/reads/*` endpoints return camelCase DTOs that mirror the frontend types.

## Paddle mock mode

With `PADDLE_API_KEY` blank, checkout returns a mock URL pointing at the frontend
`/checkout/mock` page; the frontend then calls `POST /billing/mock/complete` to
grant hints (simulating the webhook).
