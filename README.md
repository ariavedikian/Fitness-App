# FitTrack

A full-stack fitness and nutrition tracking web application — food logging,
calorie and macro goals, workout tracking, and progress analytics.

**Stack:** FastAPI · SQLAlchemy · SQLite (PostgreSQL-ready) · vanilla HTML/CSS/JS

## Architecture

An API-first, layered monolith. Pages are served as a thin HTML shell; all
data flows through JSON endpoints under `/api`, so the frontend (or a future
mobile client) is fully decoupled from the backend.

```
app/
├── main.py       # app factory & wiring
├── core/         # configuration, security helpers
├── api/          # HTTP route handlers (one module per domain)
├── services/     # business logic (no HTTP, no SQL)
├── models/       # SQLAlchemy ORM models
├── schemas/      # Pydantic request/response shapes
├── db/           # engine & session management
├── static/       # css, js
└── templates/    # HTML pages
tests/            # pytest suite
```

## Setup (Windows)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env    # then set a real SECRET_KEY
alembic upgrade head      # create the database schema
```

## Run

```powershell
uvicorn app.main:app --reload
```

- App: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/health
- Interactive API docs: http://127.0.0.1:8000/docs

## Database migrations

Schema changes are versioned with Alembic. After editing a model:

```powershell
alembic revision --autogenerate -m "describe the change"   # write the migration
alembic upgrade head                                       # apply it
alembic downgrade -1                                       # undo the last one
alembic current                                            # which revision is applied
```

Always read the generated migration before applying it — autogenerate is a
good first draft, not a final answer.

## Test

```powershell
pytest
```
