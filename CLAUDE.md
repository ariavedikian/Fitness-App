# FitTrack — Project Guide

A full-stack fitness and nutrition tracking web app (MyFitnessPal-style), built
incrementally as a mentoring/portfolio project. This file is the entry point for
any new session: read it first to know where we are and how the project is built.

## Working style (important)

This is a **teaching project**. The developer is the owner; work as a senior
engineer and mentor, not a code generator:

- Explain what we're building **before** writing code, and why each design
  decision is made.
- Work **one small milestone (or sub-step) at a time**; ask for confirmation
  before starting the next.
- When multiple approaches exist, explain the tradeoffs and **recommend one**.
- Make small, incremental changes. Don't rewrite existing files unless necessary.
- After each change: run `pytest`, and for UI work **verify in a real browser**
  (drive the actual flow), not just tests.
- Keep code production-quality — this is a portfolio piece.

## Tech stack

- **Language:** Python 3.13
- **Web framework:** FastAPI 0.139 (chosen over Flask for typing, built-in
  validation, and auto-generated `/docs`)
- **Server:** uvicorn 0.51
- **ORM / migrations:** SQLAlchemy 2.0 (typed declarative style) + Alembic 1.18
- **Database:** SQLite now, **PostgreSQL-ready** via a single `DATABASE_URL`
  setting (the whole point of using the ORM)
- **Config:** pydantic-settings (reads `.env`)
- **Auth:** bcrypt password hashing + Starlette `SessionMiddleware` (signed
  cookies) + itsdangerous
- **Validation:** Pydantic v2 (+ email-validator)
- **Templating:** Jinja2 (server renders HTML shells only)
- **Frontend:** vanilla HTML/CSS/JS as **ES modules** — no framework, no build step
- **Tests:** pytest + FastAPI `TestClient` (httpx)
- Always work inside the **virtualenv** at `venv/`.

## Architecture

An **API-first, layered monolith**. Pages are thin HTML shells; all data flows
through JSON endpoints under `/api`, which the frontend fetches and renders. The
same endpoints would serve a future mobile app.

```
Browser (HTML/CSS/JS, fetch → JSON)
   │
api/        HTTP concerns only: parse request, choose status code, return response
   │
services/   business logic — no HTTP, no knowledge of requests
   │
models/     SQLAlchemy ORM models (the schema as Python)
   │
SQLite  →  (later) PostgreSQL
```

- **schemas/** (Pydantic) are the boundary contract: what callers may send in and
  what we send back. Response schemas are an allowlist, so sensitive columns
  (e.g. `hashed_password`) can't leak.
- **core/** holds cross-cutting concerns: `config`, `security`, `templates`.
- Features are built as **vertical slices**: model + schema + service + api + UI
  together, one domain at a time.
- CSS is **mobile-first** throughout (base styles target phones; `min-width`
  media queries add room for larger screens).

## Folder structure

```
fitness-app/
├── app/
│   ├── main.py              # app factory create_app(); wires middleware + routers
│   ├── core/
│   │   ├── config.py        # Settings (env/.env); DATABASE_URL, SECRET_KEY, sessions
│   │   ├── security.py      # bcrypt hash_password / verify_password
│   │   └── templates.py     # shared Jinja2 + static dir paths
│   ├── db/
│   │   ├── base.py          # DeclarativeBase `Base`
│   │   ├── session.py       # engine, SessionLocal, get_db() dependency
│   │   └── seed.py          # `python -m app.db.seed` — idempotent food seed data
│   ├── models/              # SQLAlchemy models: user, profile, food, log_entry
│   ├── schemas/             # Pydantic shapes: user, profile, food, log
│   ├── services/            # business logic: user, profile, food, log, nutrition
│   ├── api/                 # routers: auth, profile, foods, log, pages, health, deps
│   ├── static/{css,js}/     # main.css (design tokens); ES modules per feature
│   └── templates/           # base + page templates (Jinja2)
├── alembic/                 # migrations (env.py reads DATABASE_URL from settings)
│   └── versions/            # one file per schema change; chained via down_revision
├── tests/                   # pytest; conftest.py has db + client fixtures
├── .env / .env.example      # secrets/config (.env is gitignored)
├── requirements.txt         # pinned runtime deps
├── requirements-dev.txt     # runtime + pytest/httpx
└── fittrack.db              # local SQLite (gitignored)
```

## Design decisions (with rationale)

1. **SQLAlchemy ORM + Alembic** — write Python, not SQLite-specific SQL, so the
   SQLite→PostgreSQL move is one config line. Migrations version the schema.
2. **Config via env vars / `.env`** — 12-factor; `DATABASE_URL` and `SECRET_KEY`
   never hardcoded. `SECRET_KEY` **refuses to boot with the dev default when
   `DEBUG=false`**.
3. **Session cookies, not JWT** — simpler and safer for a same-origin web app.
   Cookie is signed (tamper-proof), `HttpOnly` (JS can't read it), `SameSite=lax`
   (basic CSRF defense). Only an opaque `user_id` is stored; everything else is
   looked up fresh per request.
4. **bcrypt** for passwords — one-way hash with a per-user salt; deliberately slow.
5. **Metric internal storage** (cm/kg) is canonical; imperial input is converted
   to metric in JS (`units.js`) before it's sent. One unit system in the DB.
6. **Store `birth_date`, not age** — age recomputes from it (a stored age rots).
   Age helpers take an injectable `today` for deterministic tests.
7. **Enums stored by value** (`values_callable`), e.g. `"male"` not `"MALE"`, so
   the DB string matches the JSON on the wire.
8. **Nutrition stored per 100 g** (canonical) + `serving_size_g` + `serving_label`.
   Any quantity scales by one multiplication; matches Open Food Facts for the
   upcoming API integration. Per-serving values are derived, never stored.
9. **Log entries SNAPSHOT nutrition** — a `LogEntry` copies the food's numbers at
   log time (`food_id` is a `SET NULL` soft link only). History is immutable, and
   foods that were only searched (future external API) are still loggable.
10. **Goals computed on request, never stored** — always current with the profile.
11. **Validation at the schema boundary** (Pydantic); pure functions
    (`nutrition.py`) assume valid input and stay dependency-free/trivially testable.
12. **Round once, at the display boundary** — totals sum unrounded values and
    round last, so per-entry rounding errors don't accumulate.
13. **Don't leak existence** — deleting a missing/other-user resource returns
    `404` (not `403`); login failures use one vague message for wrong
    email/password.
14. **Server owns data, client owns presentation** — the API returns canonical
    values; the browser does display math (per-serving, remaining, imperial).

## Coding conventions

**Backend**
- SQLAlchemy **2.0 typed style**: `Mapped[...]` + `mapped_column(...)`.
- App factory `create_app()`; routers included there, prefix `/api/...` per domain.
- FastAPI **dependency injection**: `get_db`, `get_current_user` (401 if anon),
  `get_optional_user` (None if anon, for pages).
- One module per domain in each layer; services never import FastAPI.
- Pinned dependencies. Add runtime deps to `requirements.txt`, dev-only to
  `requirements-dev.txt`, and record the exact version.
- Comments explain **why** (a constraint), not what the next line does.
- **Migrations:** `alembic revision --autogenerate -m "..."` then **always read
  the generated file before** `alembic upgrade head`. SQLite uses batch mode.
- **Gotcha:** a Pydantic/SQLAlchemy field named `date` shadows the `date` type in
  its own annotation — spell it `datetime.date`.

**Frontend**
- ES modules; **`api.js` is the single fetch wrapper** (JSON, error normalization,
  cookies, AbortController support) — features call it, never `fetch` directly.
- Each page's template imports a per-feature `init...()` function.
- Build DOM with `createElement` + **`textContent` (never `innerHTML`)** to avoid
  XSS — matters once food data comes from external APIs.
- Live search is **debounced** and uses **AbortController** to drop stale responses.
- CSS uses **design tokens** (CSS custom properties in `:root`), mobile-first,
  BEM-ish class names. Touch targets ≥ 44px; inputs ≥ 16px (avoids iOS zoom).

**Testing**
- `pytest`; `conftest.py` provides a `db` fixture (in-memory SQLite with
  `StaticPool` so one connection is shared across threads) and a `client` fixture
  (overrides `get_db`). Test files mirror the module under test.
- Assert real behavior (e.g. duplicate insert raises `IntegrityError`), and
  hand-compute expected numbers in comments for domain math.

## Completed features (milestones 1–6)

1. **Foundation** — venv, config system, `/health`, pytest, git.
2. **DB + auth** — `User` model; register / login / logout / `me`; bcrypt; sessions.
3. **Frontend foundation + auth UI** — base layout, mobile-first `main.css`,
   `api.js` wrapper, login/register pages, redirect-protected pages.
4. **Profile & goals** — `Profile` (one-to-one w/ User); Mifflin-St Jeor BMR →
   TDEE → calorie goal → macro split (`nutrition.py`); profile form (imperial UI);
   dashboard goal cards.
5. **Food DB & search** — `Food` (per-100 g); `GET /api/foods/search` (escaped
   LIKE, prefix-first ranking); 30-food seed; debounced search UI.
6. **Meal logging + dashboard "today" view** — `LogEntry` (snapshot);
   `POST/GET/DELETE /api/log` with day totals; log-from-search `<dialog>`;
   `/diary` page (grouped by meal, delete, totals-vs-goals); dashboard cards show
   consumed-vs-goal + progress bar + today's meals.

## Planned milestones (next → later)

- **NEXT — External nutrition API (Open Food Facts):** hybrid approach — search
  the API live and persist a food locally only when it's logged (snapshot makes
  this clean). New concepts: outbound async HTTP client, mapping the external
  response into our `FoodRead` shape (adapter pattern), handling a slow/down third
  party. No API key needed for Open Food Facts. USDA FoodData Central can be added
  later for better whole-food data (needs a free key).
- **Workout logging** — exercises with sets/reps/weight or duration/calories.
- **Progress tracking** — body-weight entries over time.
- **Charts & analytics** — weight/calorie/macro trends.
- **AI features** — meal recommendations, photo calorie estimation, personalized
  workout recommendations.

## How to run

```powershell
.\venv\Scripts\Activate.ps1          # activate the virtualenv
pip install -r requirements-dev.txt  # first time / after dep changes
alembic upgrade head                 # apply migrations (creates fittrack.db)
python -m app.db.seed                # load the 30 reference foods
uvicorn app.main:app --reload        # http://127.0.0.1:8000  (docs at /docs)
pytest                               # run the test suite
```

Add a schema change:
```powershell
alembic revision --autogenerate -m "describe change"   # then READ the file
alembic upgrade head
```

## Current state

- **87 tests passing.** Four migrations applied (users → profiles → foods →
  log_entries).
- **Dev accounts in `fittrack.db`** (created while testing; safe to ignore or
  delete the DB and re-migrate/re-seed for a clean slate):
  - `demo@example.com` / `correct-horse-battery` — has a profile + a logged entry.
  - `newbie@example.com` / `another-good-password` — no profile (exercises empty
    states).
- Milestone 6 is complete and committed-ready. **Resume at the External nutrition
  API milestone** (see above).
