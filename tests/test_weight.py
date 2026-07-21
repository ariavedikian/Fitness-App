"""Tests for body-weight tracking: record (with upsert + profile sync), read
history, and delete."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, User, WeightEntry
from app.services import weight_service
from app.services.nutrition import ActivityLevel, Goal, Sex

SIGNUP = {"email": "weigher@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def _current_user(db: Session) -> User:
    return db.scalar(select(User).where(User.email == SIGNUP["email"]))


def give_profile(db: Session, weight_kg: float = 70.0) -> None:
    """Attach a profile to the signed-in user. Call after ``sign_in``."""
    db.add(
        Profile(
            user_id=_current_user(db).id,
            height_cm=178.0,
            weight_kg=weight_kg,
            birth_date=date(1996, 1, 1),
            sex=Sex.MALE,
            activity_level=ActivityLevel.MODERATE,
            goal=Goal.MAINTAIN,
        )
    )
    db.commit()


# --------------------------------------------------------------------- record
def test_record_weigh_in_returns_unrounded_weight(
    client: TestClient,
) -> None:
    sign_in(client)

    response = client.post("/api/weight", json={"weight_kg": 81.6466})

    assert response.status_code == 201
    body = response.json()
    assert body["weight_kg"] == 81.6466  # not rounded — imperial round-trips
    assert body["date"] == date.today().isoformat()
    assert body["id"] is not None


def test_recording_today_syncs_profile_current_weight(
    client: TestClient, db: Session
) -> None:
    sign_in(client)
    give_profile(db, weight_kg=70.0)

    client.post("/api/weight", json={"weight_kg": 82.5})  # no date -> today

    # The profile's canonical current weight follows today's weigh-in.
    assert _current_user(db).profile.weight_kg == 82.5


def test_recording_a_past_date_does_not_touch_profile(
    client: TestClient, db: Session
) -> None:
    sign_in(client)
    give_profile(db, weight_kg=70.0)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    client.post("/api/weight", json={"date": yesterday, "weight_kg": 99.0})

    # Back-dated entries are history only; the profile is unchanged.
    assert _current_user(db).profile.weight_kg == 70.0


def test_recording_without_a_profile_still_succeeds(
    client: TestClient, db: Session
) -> None:
    sign_in(client)  # no profile

    response = client.post("/api/weight", json={"weight_kg": 82.5})

    assert response.status_code == 201
    assert _current_user(db).profile is None  # nothing to sync, no crash


def test_relogging_a_day_overwrites_in_place(client: TestClient) -> None:
    """One weigh-in per day: re-posting today's weight updates it rather than
    creating a second row or hitting the unique constraint."""
    sign_in(client)

    client.post("/api/weight", json={"weight_kg": 82.5})
    client.post("/api/weight", json={"weight_kg": 81.0})

    entries = client.get("/api/weight").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["weight_kg"] == 81.0


def test_record_rejects_nonsense_weight(client: TestClient) -> None:
    sign_in(client)

    assert client.post("/api/weight", json={"weight_kg": 0}).status_code == 422
    assert (
        client.post("/api/weight", json={"weight_kg": -5}).status_code == 422
    )
    assert (
        client.post("/api/weight", json={"weight_kg": 5000}).status_code == 422
    )


def test_record_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/weight", json={"weight_kg": 80}).status_code == 401


# ----------------------------------------------------------------- read history
def test_history_is_oldest_first(client: TestClient) -> None:
    sign_in(client)
    today = date.today()
    # Post out of chronological order to prove the endpoint sorts.
    for offset, kg in [(0, 80.0), (2, 82.0), (1, 81.0)]:
        day = (today - timedelta(days=offset)).isoformat()
        client.post("/api/weight", json={"date": day, "weight_kg": kg})

    dates = [e["date"] for e in client.get("/api/weight").json()["entries"]]

    assert dates == sorted(dates)  # ascending


def test_empty_history(client: TestClient) -> None:
    sign_in(client)

    assert client.get("/api/weight").json() == {"entries": []}


def test_history_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/weight").status_code == 401


# ---------------------------------------------------------------------- delete
def test_delete_own_entry(client: TestClient) -> None:
    sign_in(client)
    entry_id = client.post("/api/weight", json={"weight_kg": 82.5}).json()["id"]

    assert client.delete(f"/api/weight/{entry_id}").status_code == 204
    assert client.get("/api/weight").json()["entries"] == []


def test_delete_missing_entry_is_404(client: TestClient) -> None:
    sign_in(client)

    assert client.delete("/api/weight/999").status_code == 404


def test_delete_rejects_another_users_entry(db: Session) -> None:
    # Service-level so no session juggling: user B must not delete A's entry.
    a = User(email="a@example.com", hashed_password="x")
    b = User(email="b@example.com", hashed_password="x")
    db.add_all([a, b])
    db.commit()
    entry = WeightEntry(user_id=a.id, date=date.today(), weight_kg=80.0)
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert weight_service.delete_entry(db, b, entry.id) is False
    assert db.get(WeightEntry, entry.id) is not None  # still there
