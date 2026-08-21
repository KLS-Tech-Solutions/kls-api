"""
Unit tests — no HTTP client, no database, no fixtures.

The rest of the suite is integration-shaped: it drives the API and asserts on
what came back. That catches a great deal, but it exercises each helper only
through whatever path happens to reach it, so a helper can be wrong in a way no
endpoint currently triggers.

These call the functions directly and push them at their edges.
"""

import time
import uuid

import pytest

from app.core.ratelimit import Rule, RateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_url_token,
    hash_password,
    verify_password,
)
from app.services import numbering
from app.services.storage import MAX_IMAGE_BYTES, StorageError, _sniff, save_chapter_pdf

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
PDF = b"%PDF-1.4\ntrailer\n%%EOF\n"


# ---------------------------------------------------------------------------
# Document numbering
# ---------------------------------------------------------------------------


class TestNumbering:
    """
    The scheme that replaced `count(rows) + 1`. That version raced under
    concurrent enrolment and let anyone holding one certificate number guess
    every other one.
    """

    def test_the_alphabet_excludes_ambiguous_characters(self):
        # A certificate number gets read off paper and typed in. I/1, O/0 and
        # similar confusions must not be able to produce a different valid
        # number.
        assert not set(numbering.ALPHABET) & set("ILOU")
        assert len(numbering.ALPHABET) == 32

    def test_a_suffix_is_the_declared_length(self):
        assert len(numbering._suffix()) == numbering.LENGTH

    def test_suffixes_do_not_repeat(self):
        # 50 bits of entropy. A collision in a thousand draws would mean the
        # random source is not random.
        seen = {numbering._suffix() for _ in range(1000)}
        assert len(seen) == 1000

    def test_suffixes_are_not_sequential(self):
        # The tell of a counter: consecutive values, or all digits.
        suffixes = [numbering._suffix() for _ in range(20)]
        assert not any(s.isdigit() for s in suffixes)
        assert len(set(suffixes)) == 20

    def test_every_character_of_the_alphabet_is_reachable(self):
        # A slicing mistake that dropped the last symbol would still look
        # random and still pass every other test here.
        drawn = set("".join(numbering._suffix() for _ in range(2000)))
        assert drawn == set(numbering.ALPHABET)


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_a_password_is_never_recoverable_from_its_hash(self):
        hashed = hash_password("kls12345")
        assert "kls12345" not in hashed
        assert hashed.startswith("$argon2")

    def test_the_same_password_hashes_differently_each_time(self):
        # Per-hash salt. Identical hashes would let anyone with the table see
        # which accounts share a password.
        assert hash_password("kls12345") != hash_password("kls12345")

    def test_verification_accepts_the_right_password_and_nothing_else(self):
        hashed = hash_password("kls12345")
        assert verify_password("kls12345", hashed)
        assert not verify_password("kls12346", hashed)
        assert not verify_password("", hashed)
        assert not verify_password("KLS12345", hashed)

    def test_verification_survives_a_malformed_hash(self):
        # A corrupt row must produce a failed login, not a 500.
        assert not verify_password("anything", "not-a-hash")

    def test_an_access_token_carries_the_role_and_a_refresh_token_does_not(self):
        user_id = uuid.uuid4()
        access = decode_token(create_access_token(user_id, "student"), "access")
        refresh = decode_token(create_refresh_token(user_id), "refresh")

        assert access["role"] == "student"
        assert access["sub"] == str(user_id)
        # A refresh token with a role in it could be replayed as an access
        # token by anything that reads the claim without checking the type.
        assert "role" not in refresh

    def test_each_token_gets_its_own_identifier(self):
        user_id = uuid.uuid4()
        first = decode_token(create_access_token(user_id, "student"), "access")
        second = decode_token(create_access_token(user_id, "student"), "access")
        assert first["jti"] != second["jti"]

    def test_url_tokens_are_long_and_unique(self):
        tokens = {generate_url_token() for _ in range(500)}
        assert len(tokens) == 500
        assert all(len(t) >= 20 for t in tokens)


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


class TestFileSniffing:
    """
    Uploads are validated by content, not by the Content-Type the client
    claimed. The header is an assertion by whoever is calling; the magic bytes
    are evidence.
    """

    @pytest.mark.parametrize(
        "data,expected",
        [
            (PNG, "image/png"),
            (JPEG, "image/jpeg"),
            (WEBP, "image/webp"),
            (PDF, "application/pdf"),
        ],
    )
    def test_it_recognises_what_a_file_actually_is(self, data, expected):
        assert _sniff(data) == expected

    @pytest.mark.parametrize(
        "data",
        [
            b"<html><script>alert(1)</script></html>",
            b"GIF89a",                       # a real format, but not one we take
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            b"",
            b"RIFF____NOTW",                 # RIFF container that is not WebP
        ],
    )
    def test_it_refuses_everything_else(self, data):
        assert _sniff(data) is None

    def test_a_pdf_upload_must_really_be_a_pdf(self):
        with pytest.raises(StorageError, match="PDF"):
            save_chapter_pdf(b"<html>gotcha</html>", uuid.uuid4(), "x.pdf", "application/pdf")

    def test_an_oversized_pdf_is_refused_before_it_is_sniffed(self):
        # Size first: sniffing a 30 MB buffer to then reject it is wasted work,
        # and the message should be about the size, not the type.
        with pytest.raises(StorageError, match="25 MB"):
            save_chapter_pdf(b"x" * (26 * 1024 * 1024), uuid.uuid4(), "big.pdf", "application/pdf")

    def test_a_genuine_pdf_is_stored_under_the_chapter_id(self):
        chapter_id = uuid.uuid4()
        key = save_chapter_pdf(PDF, chapter_id, "notes.pdf", "application/pdf")
        # Keyed by id, not by filename — two chapters called "notes.pdf" must
        # not overwrite each other.
        assert key == f"chapters/{chapter_id}.pdf"

    def test_the_screenshot_limit_is_what_the_api_documents(self):
        assert MAX_IMAGE_BYTES == 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_it_allows_up_to_the_limit_then_refuses(self):
        limiter = RateLimiter()
        rule = Rule(limit=3, window=60)

        assert limiter.check("k", rule) is None
        assert limiter.check("k", rule) is None
        assert limiter.check("k", rule) is None
        # The fourth is one too many.
        assert limiter.check("k", rule) is not None

    def test_it_reports_how_long_to_wait(self):
        limiter = RateLimiter()
        rule = Rule(limit=1, window=60)
        limiter.check("k", rule)
        retry_after = limiter.check("k", rule)
        assert isinstance(retry_after, int)
        assert 1 <= retry_after <= 60

    def test_buckets_are_independent(self):
        # One account being attacked must not lock out everyone else behind
        # the same office connection.
        limiter = RateLimiter()
        rule = Rule(limit=1, window=60)
        limiter.check("login:1.2.3.4:victim@example.com", rule)
        limiter.check("login:1.2.3.4:victim@example.com", rule)

        assert limiter.check("login:1.2.3.4:someone@example.com", rule) is None

    def test_the_window_expires(self):
        limiter = RateLimiter()
        rule = Rule(limit=1, window=1)
        limiter.check("k", rule)
        assert limiter.check("k", rule) is not None

        time.sleep(1.05)
        # A fresh window, not a permanent ban.
        assert limiter.check("k", rule) is None

    def test_a_successful_login_clears_the_counter(self):
        # Someone who fumbles their password twice and then gets it right
        # must not be rate-limited on the next screen.
        limiter = RateLimiter()
        rule = Rule(limit=2, window=60)
        limiter.check("k", rule)
        limiter.check("k", rule)
        limiter.reset("k")
        assert limiter.check("k", rule) is None

    def test_resetting_a_bucket_that_does_not_exist_is_harmless(self):
        RateLimiter().reset("never-seen")


# ---------------------------------------------------------------------------
# Journey ordering
# ---------------------------------------------------------------------------


class TestJourneyOrder:
    def test_has_reached_orders_the_whole_journey(self):
        from app.services.journey import STAGE_ORDER, has_reached

        for index, stage in enumerate(STAGE_ORDER):
            for target_index, target in enumerate(STAGE_ORDER):
                assert has_reached(stage, target) is (target_index <= index)

    def test_there_is_no_payment_stage(self):
        from app.services.journey import STAGE_ORDER

        values = [s.value for s in STAGE_ORDER]
        assert "paid" not in values
        assert "payment_pending" not in values
        assert values[-1] == "certificate_issued"
