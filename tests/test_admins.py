"""Admin invitation flow — nobody should ever be emailed a working password."""

from app.core.security import hash_password
from app.models import AdminProfile, User, UserRole, UserStatus
from tests.conftest import auth_headers


def make_super_admin(db_session, email="owner@klsacademy.example.com"):
    admin = User(
        full_name="KLS Owner",
        email=email,
        phone="+919000000000",
        password_hash=hash_password("owner12345"),
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(AdminProfile(user_id=admin.id))
    db_session.commit()
    return admin


def sign_in(client, email, password):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]


def test_invite_creates_pending_admin_with_link(client, db_session):
    make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    response = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={
            "full_name": "Reviewer One",
            "email": "reviewer@klsacademy.example.com",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["admin"]["status"] == "pending"
    assert body["admin"]["role"] == "admin"
    # SMTP is disabled in tests, so nothing is delivered — but the link is
    # always returned so an inviter can pass it on directly.
    assert body["email_delivered"] is False
    assert "/accept-invite?token=" in body["invite_url"]


def test_pending_admin_cannot_sign_in_before_accepting(client, db_session):
    make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={"full_name": "Reviewer", "email": "pending@klsacademy.example.com"},
    )

    # There is no password to guess — the placeholder hash is a random token.
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "pending@klsacademy.example.com", "password": "anything123"},
    )
    assert response.status_code == 401


def test_accept_invite_activates_and_allows_sign_in(client, db_session):
    make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    invite = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={"full_name": "Reviewer", "email": "reviewer@klsacademy.example.com"},
    ).json()
    invite_token = invite["invite_url"].split("token=")[1]

    preview = client.get(f"/api/v1/auth/invite/{invite_token}")
    assert preview.status_code == 200
    assert preview.json()["email"] == "reviewer@klsacademy.example.com"

    accepted = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": invite_token, "password": "reviewer123"},
    )
    assert accepted.status_code == 204

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@klsacademy.example.com", "password": "reviewer123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["status"] == "active"


def test_invite_token_is_single_use(client, db_session):
    make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    invite = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={"full_name": "Reviewer", "email": "once@klsacademy.example.com"},
    ).json()
    invite_token = invite["invite_url"].split("token=")[1]

    client.post(
        "/api/v1/auth/accept-invite",
        json={"token": invite_token, "password": "reviewer123"},
    )
    reused = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": invite_token, "password": "different123"},
    )
    assert reused.status_code == 400


def test_reinviting_invalidates_the_previous_link(client, db_session):
    make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    first = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={"full_name": "Reviewer", "email": "again@klsacademy.example.com"},
    ).json()["invite_url"].split("token=")[1]

    second = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(token),
        json={"full_name": "Reviewer", "email": "again@klsacademy.example.com"},
    ).json()["invite_url"].split("token=")[1]

    assert first != second
    assert client.get(f"/api/v1/auth/invite/{first}").status_code == 400
    assert client.get(f"/api/v1/auth/invite/{second}").status_code == 200


def test_plain_admin_cannot_invite(client, db_session):
    make_super_admin(db_session)
    owner_token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    invite = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(owner_token),
        json={"full_name": "Reviewer", "email": "plain@klsacademy.example.com"},
    ).json()["invite_url"].split("token=")[1]

    client.post(
        "/api/v1/auth/accept-invite",
        json={"token": invite, "password": "reviewer123"},
    )
    reviewer_token = sign_in(client, "plain@klsacademy.example.com", "reviewer123")

    response = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(reviewer_token),
        json={"full_name": "Someone", "email": "nope@klsacademy.example.com"},
    )
    assert response.status_code == 403


def test_last_super_admin_cannot_be_suspended(client, db_session):
    owner = make_super_admin(db_session)
    token = sign_in(client, "owner@klsacademy.example.com", "owner12345")

    second = make_super_admin(db_session, email="second@klsacademy.example.com")

    # Suspending one is fine while another remains active.
    ok = client.patch(
        f"/api/v1/admin/admins/{second.id}",
        headers=auth_headers(token),
        json={"status": "suspended"},
    )
    assert ok.status_code == 200

    # Suspending yourself is refused outright.
    self_change = client.patch(
        f"/api/v1/admin/admins/{owner.id}",
        headers=auth_headers(token),
        json={"status": "suspended"},
    )
    assert self_change.status_code == 409
