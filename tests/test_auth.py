from tests.conftest import auth_headers

STUDENT = {
    "full_name": "Ananya Rao",
    "email": "ananya@example.com",
    "phone": "9845012345",
    "password": "kls12345",
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
