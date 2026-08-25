from datetime import date

from app.core.dates import today_in_ist
from tests.conftest import auth_headers

# Comfortably an adult, and stays that way — the alternative is a literal that
# quietly ages into a test failure.
ADULT_DOB = date(today_in_ist().year - 22, 6, 15).isoformat()

STUDENT = {
    "full_name": "Ananya Rao",
    "email": "ananya@example.com",
    "phone": "9845012345",
    "password": "kls12345",
    # Registration requires a date of birth and refuses under-18s. A fixed
    # date would start failing the day it drifts under the minimum, so this
    # is anchored to the clock rather than written out.
    "date_of_birth": ADULT_DOB,
}


def test_register_creates_pending_student(client):
    response = client.post("/api/v1/auth/register", json=STUDENT)
    assert response.status_code == 201
    assert response.json()["email"] == "ananya@example.com"
    assert response.json()["email_verified"] is False


def test_duplicate_email_is_rejected(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    response = client.post("/api/v1/auth/register", json=STUDENT)
    assert response.status_code == 409


def test_weak_password_is_rejected(client):
    response = client.post(
        "/api/v1/auth/register", json={**STUDENT, "password": "abcdefgh"}
    )
    assert response.status_code == 422


def test_landline_phone_is_rejected(client):
    response = client.post(
        "/api/v1/auth/register", json={**STUDENT, "phone": "1234567890"}
    )
    assert response.status_code == 422


def test_login_returns_tokens_and_user(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == STUDENT["email"]


def test_wrong_password_gives_401(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    response = client.post(
        "/api/v1/auth/login", json={"email": STUDENT["email"], "password": "wrong123"}
    )
    assert response.status_code == 401


def test_unknown_email_gives_same_401(client):
    """The message must not reveal whether the account exists."""
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "kls12345"}
    )
    assert response.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/v1/me/journey").status_code == 401


def test_refresh_issues_a_new_access_token(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_access_token_rejected_as_refresh_token(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401


def test_forgot_password_never_reveals_registration(client):
    assert (
        client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
        ).status_code
        == 204
    )


# ---------------------------------------------------------------------------
# Optional phone, and where the student is
# ---------------------------------------------------------------------------


def _user(db_session, email="ananya@example.com"):
    from app.models import User

    return db_session.query(User).filter(User.email == email).one()


def test_registering_without_a_phone_number_works(client, db_session):
    """
    Nothing in the platform sends an SMS or places a call, so requiring a
    number was collecting personal data with no purpose — which is exactly what
    the DPDP Act asks fiduciaries not to do.
    """
    payload = {k: v for k, v in STUDENT.items() if k != "phone"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert _user(db_session).phone is None


def test_an_empty_phone_is_stored_as_null_not_as_a_blank(client, db_session):
    # A form submitting "" for an untouched field must not write a value that
    # later reads as "they gave us a number".
    client.post("/api/v1/auth/register", json={**STUDENT, "phone": "   "})
    assert _user(db_session).phone is None


def test_a_phone_number_that_is_given_is_still_validated(client):
    # Optional is not the same as unchecked. A wrong number is worse than none,
    # because it looks like a way to reach someone.
    response = client.post(
        "/api/v1/auth/register", json={**STUDENT, "phone": "1234567890"}
    )
    assert response.status_code == 422


def test_state_and_country_are_stored(client, db_session):
    client.post(
        "/api/v1/auth/register",
        json={**STUDENT, "state": "Karnataka", "country": "India"},
    )
    user = _user(db_session)
    assert user.state == "Karnataka"
    assert user.country == "India"


def test_state_and_country_are_optional_and_trimmed(client, db_session):
    client.post(
        "/api/v1/auth/register",
        json={**STUDENT, "state": "  Kerala  ", "country": ""},
    )
    user = _user(db_session)
    assert user.state == "Kerala"
    assert user.country is None


def test_closing_an_account_clears_the_location(client, db_session):
    """
    State and country are personal data and go the same way as the name and
    the phone number. The certificate keeps only the name printed on it.
    """
    client.post(
        "/api/v1/auth/register",
        json={**STUDENT, "state": "Karnataka", "country": "India"},
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()["access_token"]

    assert client.request(
        "DELETE", "/api/v1/me/account",
        json={"password": STUDENT["password"]},
        headers=auth_headers(token),
    ).status_code == 204

    db_session.expire_all()
    from app.models import User

    user = db_session.query(User).filter(User.full_name == "Deleted user").one()
    assert user.phone is None
    assert user.state is None
    assert user.country is None
    assert user.date_of_birth is None
