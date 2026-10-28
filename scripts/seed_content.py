"""
Creates the launch catalogue: six streams, their batches, tasks and notes.

    python scripts/seed_content.py              # create what is missing
    python scripts/seed_content.py --pdfs-only  # re-render the chapter PDFs
    python scripts/seed_content.py --dry-run    # say what would happen

**Separate from `scripts/seed.py` on purpose.** That one creates only what the
platform cannot start without, and deliberately creates no catalogue, because
demo data in a production database is impossible to tell apart from real data
six months later. This script is the opposite: real teaching material we intend
students to work through, applied on purpose.

**It will not overwrite an admin's edits.** Matching is by slug for a domain and
by `(domain, order_number)` for a task or a chapter. Anything that already
exists is left exactly as it is — if an admin has rewritten a task brief in the
console, re-running this does not undo that. Only `--pdfs-only` rewrites
anything, and only the PDF file, never the chapter's title or summary.

Once this has run, everything it created is managed from the admin console:
Catalogue → Domains, Tasks, and Notes.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.dates import today_in_ist
from app.models import (
    BatchStatus,
    Difficulty,
    InternshipBatch,
    InternshipDomain,
    LearningChapter,
    PublishStatus,
    Task,
)
from app.services.chapter_pdf import render_chapter
from app.services.storage import save_chapter_pdf
from scripts.curriculum import STREAMS, Stream

DIFFICULTY = {
    "beginner": Difficulty.BEGINNER,
    "intermediate": Difficulty.INTERMEDIATE,
    "advanced": Difficulty.ADVANCED,
}

# The LinkedIn verification step is order_number 0 for every batch. The journey
# engine treats it specially: technical tasks are those with order_number > 0.
LINKEDIN_TASK = {
    "order_number": 0,
    "title": "Share your offer letter on LinkedIn",
    "description": (
        "Post your KLS Academy offer letter on LinkedIn and submit the link to "
        "the post. A reviewer checks it, and your technical tasks unlock.\n\n"
        "This exists for two reasons. It starts the public record of work you "
        "are about to do, which is the thing employers actually look at. And it "
        "confirms the offer letter reached a real person before any reviewing "
        "time is spent."
    ),
    "requirements": [
        "A public LinkedIn post, visible without signing in",
        "The offer letter image or PDF attached to the post",
        "A link to the post itself, not to your profile",
    ],
}


def _slugged(stream: Stream) -> str:
    return stream.slug


# ---------------------------------------------------------------------------


def upsert_domain(db: Session, stream: Stream, dry: bool) -> InternshipDomain | None:
    existing = db.scalar(
        select(InternshipDomain).where(InternshipDomain.slug == stream.slug)
    )
    if existing is not None:
        print(f"  domain   = {stream.slug} (exists, untouched)")
        return existing

    if dry:
        print(f"  domain   + {stream.slug}")
        return None

    domain = InternshipDomain(
        slug=stream.slug,
        title=stream.title,
        description=stream.description,
        duration=stream.duration,
        difficulty=DIFFICULTY[stream.difficulty],
        status=PublishStatus.ACTIVE,
        icon=stream.icon,
        display_order=stream.display_order,
        outcomes=list(stream.outcomes),
        skills=list(stream.skills),
    )
    db.add(domain)
    db.flush()
    print(f"  domain   + {stream.slug}")
    return domain


def upsert_batch(db: Session, domain: InternshipDomain, stream: Stream, dry: bool):
    existing = db.scalar(
        select(InternshipBatch).where(InternshipBatch.domain_id == domain.id)
    )
    if existing is not None:
        print("  batch    = Batch 01 (exists, untouched)")
        return existing

    if dry:
        print("  batch    + Batch 01")
        return None

    # Weeks are parsed from the duration string so the batch window matches what
    # the catalogue advertises, rather than being a number typed twice.
    weeks = next((int(w) for w in stream.duration.split() if w.isdigit()), 4)
    # India's calendar day — the server runs UTC and a batch that starts
    # 'today' should mean today where the students are.
    start = today_in_ist()

    batch = InternshipBatch(
        domain_id=domain.id,
        batch_name="Batch 01",
        start_date=start,
        end_date=start + timedelta(weeks=weeks),
        # ONGOING, not UPCOMING: the batch starts today, and enrolment on an
        # upcoming batch is not what the journey engine expects.
        status=BatchStatus.ONGOING,
        seats_total=50,
    )
    db.add(batch)
    db.flush()
    print("  batch    + Batch 01")
    return batch


def upsert_tasks(db: Session, batch: InternshipBatch, stream: Stream, dry: bool) -> None:
    specs = [LINKEDIN_TASK] + [
        {
            "order_number": t.order_number,
            "title": t.title,
            "description": t.description,
            "requirements": t.requirements,
            "estimated_hours": t.estimated_hours,
            "require_live_demo": t.require_live_demo,
            "min_screenshots": t.min_screenshots,
        }
        for t in stream.tasks
    ]

    for spec in specs:
        existing = db.scalar(
            select(Task).where(
                Task.batch_id == batch.id,
                Task.order_number == spec["order_number"],
            )
        )
        if existing is not None:
            print(f"  task     = {spec['order_number']}. {spec['title'][:46]}")
            continue
        if dry:
            print(f"  task     + {spec['order_number']}. {spec['title'][:46]}")
            continue

        is_linkedin = spec["order_number"] == 0
        db.add(
            Task(
                batch_id=batch.id,
                title=spec["title"],
                description=spec["description"],
                order_number=spec["order_number"],
                requirements=list(spec["requirements"]),
                estimated_hours=spec.get("estimated_hours", 2 if is_linkedin else 8),
                # The LinkedIn step is a link, not a project: no repository, no
                # screenshots, no written explanation.
                require_github=not is_linkedin,
                require_explanation=not is_linkedin,
                min_screenshots=0 if is_linkedin else spec["min_screenshots"],
                max_screenshots=0 if is_linkedin else 8,
                require_live_demo=spec.get("require_live_demo", False),
                is_active=True,
            )
        )
        print(f"  task     + {spec['order_number']}. {spec['title'][:46]}")


def upsert_chapters(
    db: Session, domain: InternshipDomain, stream: Stream, dry: bool, pdfs_only: bool
) -> None:
    for chapter in stream.chapters:
        existing = db.scalar(
            select(LearningChapter).where(
                LearningChapter.domain_id == domain.id,
                LearningChapter.order_number == chapter.number,
            )
        )

        if existing is not None and not pdfs_only:
            print(f"  chapter  = {chapter.number}. {chapter.title[:44]}")
            continue

        if dry:
            verb = "~" if existing is not None else "+"
            print(f"  chapter  {verb} {chapter.number}. {chapter.title[:44]}")
            continue

        row = existing
        if row is None:
            row = LearningChapter(
                domain_id=domain.id,
                title=chapter.title,
                summary=chapter.summary,
                order_number=chapter.number,
                difficulty=DIFFICULTY[chapter.level.lower()],
                estimated_minutes=chapter.minutes,
                status=PublishStatus.ACTIVE,
            )
            db.add(row)
            db.flush()

        pdf = render_chapter(chapter)
        # Keyed by chapter id, so re-rendering replaces the file in place and
        # every link that already exists keeps working.
        row.pdf_url = save_chapter_pdf(pdf, row.id, None, "application/pdf")
        row.pdf_filename = (
            f"KLS-{stream.slug}-chapter-{chapter.number}.pdf".replace("_", "-")
        )
        row.pdf_size_bytes = len(pdf)

        verb = "~" if existing is not None else "+"
        print(
            f"  chapter  {verb} {chapter.number}. {chapter.title[:44]} "
            f"({len(pdf) // 1024} KB)"
        )


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change and write nothing")
    parser.add_argument("--pdfs-only", action="store_true",
                        help="re-render chapter PDFs for chapters that exist")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        for stream in STREAMS:
            print(f"\n{stream.title}")
            print("-" * len(stream.title))

            domain = upsert_domain(db, stream, args.dry_run)

            if domain is None:
                # A dry run against a database where this domain does not exist:
                # there is no row to hang a batch or a chapter off, so report
                # what would be created and move on. Without this branch the
                # dry-run output would stop at the domain line and understate
                # the work by every task and chapter in the stream.
                print("  batch    + Batch 01")
                for order, title in [
                    (LINKEDIN_TASK["order_number"], LINKEDIN_TASK["title"]),
                    *((t.order_number, t.title) for t in stream.tasks),
                ]:
                    print(f"  task     + {order}. {title[:46]}")
                for chapter in stream.chapters:
                    print(f"  chapter  + {chapter.number}. {chapter.title[:44]}")
                continue

            batch = upsert_batch(db, domain, stream, args.dry_run)
            if batch is not None:
                upsert_tasks(db, batch, stream, args.dry_run)
            upsert_chapters(db, domain, stream, args.dry_run, args.pdfs_only)

        if args.dry_run:
            db.rollback()
            print("\nDry run — nothing was written.")
        else:
            db.commit()
            print(
                f"\nDone. {len(STREAMS)} streams, "
                f"{sum(len(s.chapters) for s in STREAMS)} chapters.\n"
                "Everything above is now editable in the admin console under "
                "Catalogue."
            )
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
