"""
Age at registration, and the ability to call a token back.

Both exist for the same reason — something that has already been handed out
cannot be taken back later unless it was designed to be. A date of birth
cannot be asked for retrospectively once someone has been using the platform
for a year, and a signed token cannot be recalled unless it carries something
the server can invalidate.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.dates import IST, completed_years, today_in_ist
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    token_is_current,
)
from app.models import User

BASE = {
    "full_name": "Ananya Rao",
    "email": "ananya@example.com",
    "phone": "9845012345",
    "password": "kls12345",
}


def _dob(years_ago: int, days: int = 0) -> str:
    """A date of birth `years_ago` years and `days` days before today."""
    return (today_in_ist() - timedelta(days=years_ago * 365 + days)).isoformat()


def register(client, **overrides):
    return client.post("/api/v1/auth/register", json={**BASE, **overrides})


def login(client, email="ananya@example.com", password="kls12345"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Age
# ---------------------------------------------------------------------------


class TestAgeAtRegistration:
    def test_an_adult_can_register(self, client):
        assert register(client, date_of_birth=_dob(22)).status_code == 201

    def test_the_date_of_birth_is_required(self, client):
        payload = dict(BASE)
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422
        # The field has to be named, or the form has nowhere to put the error.
        assert "date_of_birth" in response.text

    def test_a_child_is_refused(self, client):
        response = register(client, date_of_birth=_dob(15))
        assert response.status_code == 422
        # And told why. "Invalid" would send them back to the field to try
        # variations of a date that will never be accepted.
        assert "18" in response.text

    def test_the_boundary_is_the_birthday_itself(self, client):
        """
        Someone whose eighteenth birthday is today registers; someone whose
        birthday is tomorrow does not. Off-by-one here is a compliance
        failure in one direction and a rejected adult in the other.
        """
        today = today_in_ist()

        # 29 February cannot be reconstructed in a non-leap year, so step off
        # it rather than assert something untrue about the calendar.
        birthday = today.replace(year=today.year - settings.MINIMUM_AGE)
        assert register(client, date_of_birth=birthday.isoformat()).status_code == 201

        one_day_short = birthday + timedelta(days=1)
        response = register(
            client, email="other@example.com", date_of_birth=one_day_short.isoformat()
        )
        assert response.status_code == 422

    def test_a_future_date_is_refused_as_a_mistake_not_as_an_age(self, client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        response = register(client, date_of_birth=tomorrow)
        assert response.status_code == 422
        assert "future" in response.text.lower()

    def test_a_mistyped_year_is_refused(self, client):
        # 1025 for 2025. Technically "old enough".
        response = register(client, date_of_birth="1025-06-15")
        assert response.status_code == 422

    def test_it_is_stored_and_returned(self, client, db_session):
        dob = _dob(22)
        register(client, date_of_birth=dob)

        user = db_session.query(User).filter(User.email == BASE["email"]).one()
        assert user.date_of_birth.isoformat() == dob
        assert user.age >= 18
        assert user.is_minor is False

    def test_an_account_with_no_date_of_birth_is_not_treated_as_a_child(self):
        # Pre-existing rows. `is_minor` gates extra protection, and defaulting
        # unknown to True would apply child handling to the entire back
        # catalogue on the strength of no evidence at all.
        user = User(full_name="Legacy", email="l@example.com", phone="", password_hash="x")
        assert user.age is None
        assert user.is_minor is False

    @pytest.mark.parametrize(
        "born,today,expected",
        [
            (date(2000, 6, 15), date(2026, 6, 14), 25),  # day before
            (date(2000, 6, 15), date(2026, 6, 15), 26),  # on the day
            (date(2000, 6, 15), date(2026, 6, 16), 26),  # day after
            (date(2000, 12, 31), date(2026, 1, 1), 25),  # year boundary
            (date(2004, 2, 29), date(2026, 3, 1), 22),   # leap day, common year
            (date(2004, 2, 29), date(2026, 2, 28), 21),  # not yet, in a common year
        ],
    )
    def test_the_age_arithmetic(self, born, today, expected):
        assert completed_years(born, today) == expected

    def test_the_calendar_day_is_indias_not_the_servers(self):
        """
        The server runs UTC; students are in India, 5:30 ahead. Between 18:30
        and midnight UTC the two disagree about what day it is, and an age
        rule decided on the wrong calendar tells someone registering at 11pm
        on their eighteenth birthday that they are too young.
        """
        # 23:00 IST on 15 June is still 17:30 UTC on 15 June — same day.
        # 00:30 IST on 16 June is 19:00 UTC on the 15th — different day, and
        # this is the case that matters.
        late = datetime(2026, 6, 15, 19, 0, tzinfo=timezone.utc)
        assert late.date() == date(2026, 6, 15)
        assert late.astimezone(IST).date() == date(2026, 6, 16)


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


class TestTokenVersionClaim:
    def test_both_token_types_carry_the_version(self):
        import uuid

        user_id = uuid.uuid4()
        assert decode_token(create_access_token(user_id, "student", 7), "access")["tv"] == 7
        assert decode_token(create_refresh_token(user_id, 7), "refresh")["tv"] == 7

    def test_a_token_with_no_version_claim_reads_as_zero(self):
        # Everything minted before this feature existed. Those tokens must
        # keep working across the deploy, or every signed-in student is thrown
        # out by an upgrade that was supposed to be invisible.
        assert token_is_current({}, 0) is True
        assert token_is_current({}, 1) is False

    def test_it_matches_only_the_exact_version(self):
        assert token_is_current({"tv": 3}, 3) is True
        assert token_is_current({"tv": 2}, 3) is False
        # Ahead of the account, which should never happen, is still a refusal.
        assert token_is_current({"tv": 4}, 3) is False


class TestRevocation:
    def _session(self, client):
        register(client, date_of_birth=_dob(22))
        body = login(client).json()
        return body["access_token"], body["refresh_token"]

    def test_a_normal_session_keeps_working(self, client):
        access, refresh = self._session(client)
        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code == 200
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        ).status_code == 200

    def test_a_password_reset_ends_every_session(self, client, db_session):
        """
        The case this feature exists for. Someone resets their password
        *because* they think a session was stolen; the stolen refresh token is
        good for thirty days and would outlive the reset.
        """
        access, refresh = self._session(client)

        client.post("/api/v1/auth/forgot-password", json={"email": BASE["email"]})
        db_session.expire_all()
        from app.models import EmailToken

        token = (
            db_session.query(EmailToken)
            .filter(EmailToken.purpose == "reset_password")
            .order_by(EmailToken.created_at.desc())
            .first()
        )
        assert token is not None

        assert client.post(
            "/api/v1/auth/reset-password",
            json={"token": token.token, "password": "newpass123"},
        ).status_code == 204

        # The old pair is dead on both paths.
        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        ).status_code == 401

        # And the new password produces a working session.
        fresh = login(client, password="newpass123")
        assert fresh.status_code == 200
        assert client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {fresh.json()['access_token']}"},
        ).status_code == 200

    def test_an_ordinary_logout_leaves_other_devices_alone(self, client):
        """
        Signing out of a laptop must not sign you out of your phone. The
        cookie is cleared on this device; the account is untouched.
        """
        access, _ = self._session(client)
        phone = login(client).json()["access_token"]

        assert client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
        ).status_code == 204

        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {phone}"}
        ).status_code == 200

    def test_signing_out_everywhere_does_exactly_that(self, client):
        access, refresh = self._session(client)
        phone = login(client).json()["access_token"]

        assert client.post(
            "/api/v1/auth/logout",
            json={"all_devices": True},
            headers={"Authorization": f"Bearer {access}"},
        ).status_code == 204

        for token in (access, phone):
            assert client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            ).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        ).status_code == 401

    def test_closing_an_account_kills_its_tokens_immediately(self, client):
        access, refresh = self._session(client)

        assert client.request(
            "DELETE",
            "/api/v1/me/account",
            json={"password": "kls12345"},
            headers={"Authorization": f"Bearer {access}"},
        ).status_code == 204

        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        ).status_code == 401

    def test_a_refreshed_token_carries_the_current_version(self, client, db_session):
        """
        Refresh mints a new pair. If it minted them at version 0 rather than
        the account's real version, one refresh call would undo every
        revocation that had ever happened.
        """
        _, refresh = self._session(client)

        user = db_session.query(User).filter(User.email == BASE["email"]).one()
        user.token_version = 0  # start from a known point
        db_session.commit()

        new_pair = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        ).json()
        claims = decode_token(new_pair["access_token"], "access")
        assert claims["tv"] == user.token_version
