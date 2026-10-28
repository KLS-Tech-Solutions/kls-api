"""
Local file storage.

Files moved off Cloudflare R2 onto this server's disk, which changes what can
go wrong. An object store has no notion of `..`, no partial writes visible to
readers, and no filesystem to escape from. A directory has all three.
"""

import uuid

import pytest

from app.services import storage
from app.services.storage import (
    MAX_PDF_BYTES,
    StorageError,
    content_disposition,
    read_bytes,
    save_chapter_pdf,
    upload_bytes,
)

PDF = b"%PDF-1.4\ntrailer\n%%EOF\n"


class TestRoundTrip:
    def test_what_goes_in_comes_back(self):
        key = upload_bytes(PDF, "certificates/round-trip.pdf", "application/pdf")
        assert key == "certificates/round-trip.pdf"
        assert read_bytes(key) == PDF

    def test_a_missing_file_is_none_rather_than_an_error(self):
        # Callers regenerate the PDF from the database record when the file has
        # gone. The record is the source of truth; the file is a rendering.
        assert read_bytes("certificates/never-written.pdf") is None

    def test_nested_directories_are_created(self):
        key = upload_bytes(PDF, "submissions/a/b/c/01.pdf", "application/pdf")
        assert read_bytes(key) == PDF

    def test_writing_twice_replaces_rather_than_appends(self):
        upload_bytes(b"%PDF-first", "chapters/replace.pdf", "application/pdf")
        upload_bytes(b"%PDF-second", "chapters/replace.pdf", "application/pdf")
        assert read_bytes("chapters/replace.pdf") == b"%PDF-second"

    def test_no_partial_file_is_left_behind(self):
        """
        Writes go to a temporary file and are renamed over the target, so a
        crash leaves either the old file or none — never a truncated PDF that
        opens to a grey screen and looks like a rendering bug.
        """
        upload_bytes(PDF, "certificates/atomic.pdf", "application/pdf")
        leftovers = list(storage.MEDIA_ROOT.rglob("*.part"))
        assert leftovers == []


class TestKeysCannotEscapeTheMediaRoot:
    """
    Keys are built internally today, so this guards against a future caller
    rather than a current one. The cost of being wrong is reading or writing
    arbitrary files as the service user, and `read_bytes` takes its argument
    from a database column — a thing some other bug can change.
    """

    @pytest.mark.parametrize(
        "key",
        [
            "../../../etc/passwd",
            "chapters/../../../../etc/shadow",
            "/etc/passwd",
            "chapters/../../outside.pdf",
        ],
    )
    def test_traversal_is_refused_on_write(self, key):
        with pytest.raises(StorageError):
            upload_bytes(PDF, key, "application/pdf")

    @pytest.mark.parametrize("key", ["../../../etc/passwd", "/etc/passwd"])
    def test_traversal_reads_as_missing(self, key):
        # Refused, and indistinguishable from a file that is simply not there.
        assert read_bytes(key) is None

    def test_an_ordinary_key_still_works(self):
        # The guard must not reject the normal case, which is the usual way a
        # path check of this kind gets quietly disabled later.
        assert upload_bytes(PDF, "chapters/ordinary.pdf", "application/pdf")


class TestLegacyKeys:
    """
    Records written before storage went private hold `/media/…` paths and full
    public-bucket URLs. They have to keep resolving without a data migration.
    """

    def test_a_media_prefixed_path_resolves(self):
        upload_bytes(PDF, "certificates/legacy.pdf", "application/pdf")
        assert read_bytes("/media/certificates/legacy.pdf") == PDF

    def test_an_old_public_url_resolves(self):
        upload_bytes(PDF, "certificates/legacy2.pdf", "application/pdf")
        assert (
            read_bytes("https://pub-xyz.r2.dev/certificates/legacy2.pdf") == PDF
        )


class TestChapterNotes:
    def test_a_genuine_pdf_is_stored_under_the_chapter_id(self):
        chapter_id = uuid.uuid4()
        key = save_chapter_pdf(PDF, chapter_id, "notes.pdf", "application/pdf")
        # Keyed by id, not by the uploaded filename — two chapters whose notes
        # are both "notes.pdf" must not overwrite each other, and a filename
        # from a browser must never reach the filesystem.
        assert key == f"chapters/{chapter_id}.pdf"
        assert read_bytes(key) == PDF

    def test_a_disguised_file_is_refused(self):
        with pytest.raises(StorageError, match="PDF"):
            save_chapter_pdf(
                b"<html>gotcha</html>", uuid.uuid4(), "x.pdf", "application/pdf"
            )

    def test_an_oversized_file_is_refused_before_it_is_sniffed(self):
        with pytest.raises(StorageError, match="25 MB"):
            save_chapter_pdf(
                b"x" * (MAX_PDF_BYTES + 1), uuid.uuid4(), "big.pdf", "application/pdf"
            )

    def test_a_refused_upload_leaves_nothing_on_disk(self):
        chapter_id = uuid.uuid4()
        with pytest.raises(StorageError):
            save_chapter_pdf(b"not a pdf", chapter_id, "x.pdf", "application/pdf")
        assert read_bytes(f"chapters/{chapter_id}.pdf") is None


class TestContentDisposition:
    """
    Filenames here come from chapter titles and student names, which are
    user-supplied and go straight into a response header.
    """

    def test_it_asks_the_browser_to_save_by_default(self):
        header = content_disposition("Chapter One")["Content-Disposition"]
        assert header.startswith("attachment;")
        assert 'filename="Chapter One.pdf"' in header

    def test_inline_is_available_for_reading_in_the_browser(self):
        header = content_disposition("Chapter One", download=False)[
            "Content-Disposition"
        ]
        assert header.startswith("inline;")

    def test_a_quote_cannot_close_the_header_early(self):
        header = content_disposition('evil".pdf')["Content-Disposition"]
        # One opening and one closing quote, and nothing in between them that
        # could be read as a second parameter.
        assert header.count('"') == 2

    def test_a_newline_cannot_inject_another_header(self):
        # `x".pdf\r\nSet-Cookie: ...` as a chapter title would otherwise append
        # a header to every download of that chapter.
        header = content_disposition('x".pdf\r\nSet-Cookie: a=b')[
            "Content-Disposition"
        ]
        assert "\r" not in header and "\n" not in header
        assert ":" not in header.split('filename="')[1]
        assert header.count('"') == 2

    def test_a_path_cannot_be_smuggled_through_the_name(self):
        header = content_disposition("../../etc/passwd")["Content-Disposition"]
        assert "/" not in header.split('filename="')[1]

    def test_the_extension_is_always_pdf(self):
        assert '.pdf"' in content_disposition("report")["Content-Disposition"]
        assert '.pdf"' in content_disposition("report.pdf")["Content-Disposition"]

    def test_a_name_stripped_to_nothing_still_produces_a_filename(self):
        # A title of only punctuation would otherwise yield filename="" and a
        # browser saving the file as the URL's last segment.
        header = content_disposition("///")["Content-Disposition"]
        assert 'filename="document.pdf"' in header


# ---------------------------------------------------------------------------
# Configuration guards
# ---------------------------------------------------------------------------


class TestProductionConfigGuards:
    """
    Two mistakes that are silent until they are expensive: a media directory
    inside the code tree, which a redeploy deletes along with every issued
    certificate, and a remote database reached without TLS.
    """

    def _settings(self, **overrides):
        from app.core.config import Settings

        base = {
            "ENVIRONMENT": "production",
            "DEBUG": False,
            "SECRET_KEY": "x" * 48,
            "CORS_ORIGINS": ["https://academy.example.in"],
            "FIRST_SUPERADMIN_PASSWORD": "set",
            "MEDIA_ROOT": "/srv/kls/media",
            "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/kls",
        }
        return Settings(**{**base, **overrides})

    def test_a_correct_production_config_has_no_complaints(self):
        assert self._settings().validate_for_runtime() == []

    def test_a_relative_media_root_is_refused_in_production(self):
        problems = self._settings(MEDIA_ROOT="media").validate_for_runtime()
        assert any("MEDIA_ROOT" in p for p in problems)

    def test_a_relative_media_root_is_fine_in_development(self):
        # The default is "media", and a developer should not have to set an
        # absolute path to run the thing on a laptop.
        settings = self._settings(ENVIRONMENT="development", MEDIA_ROOT="media")
        assert not any("MEDIA_ROOT" in p for p in settings.validate_for_runtime())

    def test_a_remote_database_without_tls_is_refused(self):
        problems = self._settings(
            DATABASE_URL=(
                "postgresql+psycopg://postgres.abc:pw"
                "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
            )
        ).validate_for_runtime()
        assert any("sslmode" in p for p in problems)

    def test_a_remote_database_with_tls_passes(self):
        problems = self._settings(
            DATABASE_URL=(
                "postgresql+psycopg://postgres.abc:pw"
                "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
            )
        ).validate_for_runtime()
        assert not any("sslmode" in p for p in problems)

    def test_a_local_database_is_not_asked_for_tls(self):
        # Loopback never leaves the machine, so requiring TLS there is noise
        # that teaches people to ignore the startup warnings.
        for url in (
            "postgresql+psycopg://u:p@localhost:5432/kls",
            "postgresql+psycopg://u:p@127.0.0.1:5432/kls",
        ):
            problems = self._settings(DATABASE_URL=url).validate_for_runtime()
            assert not any("sslmode" in p for p in problems)

    @pytest.mark.parametrize(
        "url,remote",
        [
            # A driver with no network is not a remote database. The first
            # version of this asked whether the URL contained "@localhost",
            # which answered *true* for SQLite and then handed psycopg's
            # connect_timeout to it, where it is not a valid argument.
            ("sqlite:///./test.db", False),
            ("sqlite://", False),
            ("postgresql+psycopg://u:p@localhost:5432/kls", False),
            ("postgresql+psycopg://u:p@127.0.0.1:5432/kls", False),
            ("postgresql+psycopg://u:p@db:5432/kls", False),
            # A Unix socket: no host at all.
            ("postgresql+psycopg://u:p@/kls", False),
            ("postgresql+psycopg://u:p@aws-0-ap-south-1.pooler.supabase.com:5432/postgres", True),
            ("postgresql+psycopg://u:p@db.abcdef.supabase.co:5432/postgres", True),
            ("postgresql+psycopg://u:p@10.0.0.9:5432/kls", True),
        ],
    )
    def test_what_counts_as_remote(self, url, remote):
        assert self._settings(DATABASE_URL=url).is_remote_database is remote

    def test_an_unparseable_url_does_not_crash_startup(self):
        # It will fail at connect time with a better message than anything
        # this property could raise.
        assert self._settings(DATABASE_URL="not a url at all").is_remote_database is False

    def test_supabase_is_recognised_as_remote(self):
        settings = self._settings(
            DATABASE_URL=(
                "postgresql+psycopg://postgres.abc:pw"
                "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
            )
        )
        # This is what switches the connection pool to its remote tuning.
        assert settings.is_remote_database is True
        assert self._settings().is_remote_database is False
