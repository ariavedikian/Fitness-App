# FitTrack

A full-stack fitness and nutrition tracker: log meals and workouts, follow
calorie and macro goals worked out from your profile, chart your progress,
and — optionally — get meal ideas, photo calorie estimates and workout ideas
from Claude.

Built with FastAPI, SQLAlchemy and vanilla JavaScript (no frontend framework,
no build step) as a portfolio project, one tested milestone at a time.

## Features

**Nutrition**
- Food search across a local database *and* the millions of products in
  [Open Food Facts](https://world.openfoodfacts.org) — if that service is
  down, search carries on with local results and says so.
- Meal logging by servings or grams, a diary grouped by meal, and a dashboard
  of today's calories and macros against your goals.
- Goals calculated from your profile: Mifflin-St Jeor BMR → activity-adjusted
  TDEE → a target for losing, keeping or gaining weight, split into macros.

**Workouts**
- A catalogue of 30 strength and cardio exercises; log sets × reps × weight or
  duration and distance.
- Cardio calories estimated from each exercise's MET value and your weight,
  and netted against food on the dashboard (remaining = goal − eaten +
  burned).

**Progress**
- Daily weigh-ins with the change since the previous one, and a weight trend.
- Analytics: daily calories and macros over 7, 30 or 90 days, drawn by a small
  dependency-free SVG chart module (hover crosshair, tooltips, legends).

**AI features (optional, powered by Claude)**
- **Meal ideas** sized to what's left of today's calorie and macro budget.
- **Photo calorie estimates** — snap a meal, review and correct the portions,
  then log it. Nothing is logged without that review.
- **Workout ideas** built only from the exercise catalogue and balanced
  against your last week, with each exercise loggable from a pre-filled form.
- Off by default and hidden until configured; a per-user daily limit caps
  what one account can spend.

**Throughout**
- Mobile-first, responsive layout (the navigation collapses behind a Menu
  button on phones), 44 px touch targets, labelled controls and live status
  messages for screen readers.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic v2 |
| Data | SQLAlchemy 2.0 ORM + Alembic migrations; SQLite by default |
| Auth | bcrypt password hashing, signed `HttpOnly` session cookies |
| Frontend | Jinja2 page shells + vanilla ES modules; hand-rolled SVG charts |
| Integrations | Open Food Facts (httpx), Anthropic Python SDK (Claude) |
| Tests | pytest + FastAPI `TestClient` — 300+ tests, no network needed |

## Getting started

You'll need **Python 3.13**. From the project folder:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1      # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env
alembic upgrade head             # create the database schema
python -m app.db.seed            # load the food and exercise catalogues
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>, create an account, and fill in your
profile to get daily goals. The interactive API documentation is at
<http://127.0.0.1:8000/docs>.

`.env.example` documents every setting. The defaults suit local development;
to run with `DEBUG=false` you must set `SECRET_KEY` to a random value (the
app refuses to start otherwise) and `SESSION_HTTPS_ONLY=true` behind HTTPS.

### Turning on the AI features (optional)

Every suggestion or estimate is a billed call to the
[Anthropic API](https://platform.claude.com/docs), so the AI features are
opt-in.
Add both lines to `.env` and restart the server:

```
AI_ENABLED=true
ANTHROPIC_API_KEY=sk-ant-...
```

Without them the app works fully — the AI cards and buttons simply don't
appear. `AI_DAILY_LIMIT` (default 20 per user per rolling 24 hours) caps
usage, and `AI_ENABLED=false` works as a kill switch. The model and other
tuning settings are listed in `.env.example`.

## Running the tests

```powershell
pytest
```

Each test gets a fresh in-memory database, and third-party services are
switched off by default, so the suite never touches the network or a real
API key. The Claude integration is tested by running the real Anthropic SDK
against a mock HTTP transport, so the SDK's own request building and response
validation are exercised too.

## Architecture

An API-first, layered monolith. Pages are thin HTML shells; all data flows
through JSON endpoints under `/api`, which the browser fetches and renders —
the same endpoints could serve a mobile app.

```
Browser (HTML/CSS/JS ES modules, fetch → JSON)
   │
api/        HTTP only: parse the request, pick the status code
   │
services/   business logic — no HTTP; external services behind adapters
   │
models/     SQLAlchemy ORM models
   │
SQLite (any SQLAlchemy database via DATABASE_URL)
```

```
app/
├── main.py       # app factory: middleware, routers, static files
├── core/         # configuration, password hashing, templates, static serving
├── api/          # route handlers, one module per domain
├── services/     # business logic, plus the Open Food Facts and Claude adapters
├── models/       # SQLAlchemy ORM models
├── schemas/      # Pydantic request/response contracts
├── db/           # engine, sessions, catalogue seed script
├── static/       # css/main.css (design tokens) and one JS module per feature
└── templates/    # Jinja2 page shells
alembic/          # database migrations
tests/            # pytest suite, mirroring the modules above
```

### Design decisions worth a look

- **Logged entries are snapshots.** A meal or workout copies the food's or
  exercise's details when it's logged, so history never changes if the
  catalogue does.
- **One canonical form for data.** Metric units and nutrition per 100 g are
  stored; servings, imperial units and display rounding happen at the edges.
- **Third parties sit behind adapters and degrade gracefully.** Open Food
  Facts' messy JSON is normalised in one tested function; when it or Claude
  fails, the feature narrows instead of the page breaking.
- **The server owns the AI's inputs.** Prompts carry only numbers, fixed
  choices and catalogue names the server computed — never text a user typed.
  Replies are constrained to JSON schemas and validated into typed objects;
  workout ideas use a schema built from the catalogue, so Claude *can't*
  suggest an exercise the app doesn't have.
- **Security basics are built in.** Model and user text is rendered with
  `textContent`, never as HTML; uploads are type-checked by their bytes, not
  their claimed type; cookies are signed, `HttpOnly` and `SameSite=Lax`.

The full list, with the reasoning behind each choice, is in
[CLAUDE.md](CLAUDE.md) — the project's working guide.

## Project status

The planned feature milestones are complete. Not done yet: a live test of
the AI features against the Anthropic API (so far they've been verified with
the SDK against canned replies), running against PostgreSQL, and deployment.
Ideas for later include USDA FoodData Central as a second food source and
barcode lookup.
