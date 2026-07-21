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
- **Offer a commit at each self-contained green sub-step** (not batched to the
  milestone end); commit only once the owner confirms.
- Keep code production-quality — this is a portfolio piece.

**Browser-verification gotcha:** static JS/CSS have no cache headers, so the
browser often runs a **stale cached** copy after you edit a file. Force a
cache-bypassing reload (or `import('/static/js/x.js?v=' + Date.now())` to test
the fresh module) — don't debug a "bug" that's really a stale asset. (Proper
fix is tracked as a follow-up; see *Current state*.)

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
- **Outbound HTTP:** httpx (sync `Client`) for the Open Food Facts integration.
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
│   │   ├── base.py          # DeclarativeBase `Base` + enum_column helper
│   │   ├── session.py       # engine, SessionLocal, get_db() dependency
│   │   └── seed.py          # `python -m app.db.seed` — idempotent food + exercise seed
│   ├── models/              # user, profile, food, log_entry, exercise,
│   │                        #   workout_entry, weight_entry
│   ├── schemas/             # Pydantic shapes: user, profile, food, log, workout,
│   │                        #   weight
│   ├── services/            # business logic: user, profile, food, log, nutrition,
│   │                        #   off_client (OFF adapter), search (LIKE-escape),
│   │                        #   exercise, workout (MET math), workout_service,
│   │                        #   weight_service
│   ├── api/                 # routers: auth, profile, foods, log, exercises,
│   │                        #   workouts, weight, pages, health, deps
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
15. **External data crosses an adapter** — `map_off_product` is a pure function
    that normalises Open Food Facts' messy JSON into our shape and rejects
    unusable products, so the mess is quarantined in one tested place and the
    rest of the app only ever sees clean `OffFood`/`Food` values.
16. **Materialise external foods on log, not on search** — an OFF result carries
    a barcode but no local `id`; it becomes a `Food` row only when the user adds
    it (`import`), deduped on the unique `off_id`. Search stays read-only and the
    DB fills with foods people actually use. The server **re-fetches** at import
    time so persisted nutrition is ours, not the client's (extends #14).
17. **Degrade, don't break, on third-party failure** — OFF is flaky (intermittent
    503s, occasional outages). The client retries transient errors; the search
    service catches `OffUnavailableError` and returns local results with an
    `external` status the UI surfaces, so an outage narrows the feature instead
    of erroring the page.
18. **One table, a type discriminator, nullable columns** — `WorkoutEntry` holds
    both strength and cardio in one table (a `type` plus nullable metric columns)
    rather than separate tables. The schema layer can't enforce which metrics are
    required (that depends on the exercise's type, a DB lookup), so the *service*
    validates against the type and clears the columns that don't apply.
19. **Net calories add exercise back to the budget** — the dashboard shows
    `remaining = goal − eaten + burned` (MyFitnessPal's model): logging a workout
    lets you eat more. Only calories net out; macros stay consumed-vs-goal.
20. **Weight is a time-series; the profile holds the current value** — weigh-ins
    live in their own `WeightEntry` table (one per day, unique `(user_id, date)`
    that doubles as the query index). `Profile.weight_kg` stays the canonical
    "current weight" driving goals + cardio calories, and recording *today's*
    weigh-in syncs it so the two never diverge; back-dated entries are history
    only. Chosen over deriving the profile weight from the series (too invasive
    for M9) or leaving them independent (silent divergence).
21. **Per-entry deltas are presentation math** — the weight API returns pure,
    unrounded facts oldest-first; the client computes each "change since the
    previous weigh-in" and rounds for display (extends #14). Unrounded so
    imperial input round-trips (180 lb → 81.6466 kg → 180 lb).

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

## Completed features (milestones 1–9)

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
7. **External nutrition API (Open Food Facts)** — hybrid search over our local DB
   **plus** millions of OFF products, no API key. `off_client.py` is an adapter:
   pure `map_off_product` normalises OFF's messy JSON (kJ→kcal, missing servings,
   comma decimals) into an `OffFood`, and a sync `httpx` client (`search_off` /
   `fetch_off_product`) retries OFF's intermittent 503s. `Food` gains a unique
   `off_id` (barcode). `search_all` merges local-first, dedupes OFF against
   already-imported barcodes, and **degrades gracefully** when OFF is down
   (`FoodSearchResponse.external` = ok/unavailable/disabled). Foods are
   **materialised on Add**: `POST /api/foods/import` re-fetches server-side (never
   trusting client numbers) and get-or-creates the local `Food`; the existing log
   flow is unchanged. Search UI tags OFF hits, shows a degraded-source notice, and
   imports before logging.
8. **Workout logging + dashboard net calories** — the nutrition pattern applied to
   exercise. `Exercise` catalogue (30 seeded, cardio carries a MET, strength a
   muscle group); pure `workout.py` estimates calories burned (`kcal = MET ×
   weight_kg × hours`). One `WorkoutEntry` table holds both shapes — a `type`
   discriminator with nullable strength (sets/reps/weight) and cardio
   (duration/distance) columns — snapshotting the exercise like meal logging. The
   service validates metrics against the type and estimates cardio calories from
   the profile's weight (degrading to none without a profile). `GET
   /api/exercises/search`; `POST/GET/DELETE /api/workouts`. `/workouts` page:
   search → type-aware `<dialog>` → today's list. Dashboard folds burned calories
   in as **net calories** (remaining = goal − eaten + burned, MyFitnessPal-style;
   macros untouched).
9. **Progress tracking (body-weight over time)** — a `WeightEntry` time-series,
   one weigh-in per day (unique `(user_id, date)`, index-backed). `weight_service`
   upserts a day in place and, for *today's* weigh-in, syncs `Profile.weight_kg`
   (the canonical current weight behind goals + cardio calories); back-dated
   entries are history only. `POST/GET/DELETE /api/weight` returns the series
   oldest-first and unrounded. `/progress` page: an imperial weigh-in form
   (pre-filled from the profile) + a history list showing each entry's change
   from the previous one (deltas computed client-side). The dashboard gains a
   **Weight** card (current weight + change since the last weigh-in).

## Planned milestones (next → later)

- **NEXT — Charts & analytics** — weight/calorie/macro trends (the weight series
  from M9 is already stored oldest-first, ready to chart).
- **AI features** — meal recommendations, photo calorie estimation, personalized
  workout recommendations.
- **Later food-data enhancements** — USDA FoodData Central as a second source
  (better whole-food data; needs a free key), and barcode-scan lookup (the OFF
  `fetch_off_product` path already supports barcodes).

## How to run

```powershell
.\venv\Scripts\Activate.ps1          # activate the virtualenv
pip install -r requirements-dev.txt  # first time / after dep changes
alembic upgrade head                 # apply migrations (creates fittrack.db)
python -m app.db.seed                # load reference foods + exercises
uvicorn app.main:app --reload        # http://127.0.0.1:8000  (docs at /docs)
pytest                               # run the test suite
```

Add a schema change:
```powershell
alembic revision --autogenerate -m "describe change"   # then READ the file
alembic upgrade head
```

## Current state

- **170 tests passing.** Eight migrations applied (users → profiles → foods →
  log_entries → foods.off_id → exercises → workout_entries → weight_entries).
- **External calls in tests are disabled by default** via an autouse `_offline`
  fixture in `tests/conftest.py` (sets `settings.off_enabled = False`); tests that
  exercise the OFF path re-enable it and stub `off_client` — nothing hits the
  network. OFF search uses a **sync** `httpx.Client` (chosen over the originally
  planned async, for consistency with the sync route/DB stack).
- **Dev accounts in `fittrack.db`** (created while testing; safe to ignore or
  delete the DB and re-migrate/re-seed for a clean slate):
  - `demo@example.com` / `correct-horse-battery` — has a profile + logged entries,
    plus one OFF food imported during M7 testing (`off_id` set — exercises dedupe),
    and two weigh-ins added during M9 testing (profile weight synced to 179 lb).
  - `newbie@example.com` / `another-good-password` — no profile (exercises empty
    states).
- A dev-server launch config lives at the **workspace-root** `.claude/launch.json`
  (one level above this repo), used by the browser preview tooling.
- **Known gap:** static assets (`/static/js/*.js`, CSS) are served by `StaticFiles`
  with no cache headers, so browsers can run a **stale cached** copy after a change
  (bit us again verifying M9's dashboard.js — a plain reload kept the old module;
  `import('/static/js/x.js?v='+Date.now())` confirmed the fresh one). Needs
  cache-busting/versioned asset URLs — tracked as a follow-up task.
- Milestone 9 is complete and committed-ready. **Resume at Charts & analytics.**
