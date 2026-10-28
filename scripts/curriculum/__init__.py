"""
The launch catalogue: six internship streams, their tasks, and their notes.

**This is seed content, not application code.** `scripts/seed.py` deliberately
creates no domains, because demo data in a production database is impossible to
find and delete later. This package is the opposite case — real material we
intend students to work through — so it lives beside the seeder and is applied
on purpose, once, by `scripts/seed_content.py`.

Everything here is editable from the admin console afterwards. The script
creates; the console owns. Re-running will not clobber an edit an admin has
made — see the script's docstring for exactly what it will and will not touch.

Content is data rather than markup so `app/services/chapter_pdf.py` owns every
typographic decision, and so this file stays readable to someone who is
thinking about teaching rather than about PDFs.
"""

from dataclasses import dataclass, field

from app.services.chapter_pdf import Chapter


@dataclass
class TaskSpec:
    """One technical task. `order_number` 0 is reserved for the LinkedIn step."""

    order_number: int
    title: str
    description: str
    requirements: list[str]
    estimated_hours: int = 8
    require_live_demo: bool = False
    min_screenshots: int = 3


@dataclass
class Stream:
    slug: str
    title: str
    description: str
    duration: str
    difficulty: str           # beginner | intermediate | advanced
    icon: str
    display_order: int
    skills: list[str]
    outcomes: list[str]
    tasks: list[TaskSpec] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)


def _load() -> list[Stream]:
    """
    Imported lazily and in one place so the module order stays obvious, and so
    a syntax error in one stream names that stream rather than this file.
    """
    from scripts.curriculum import applied, web

    return [*web.STREAMS, *applied.STREAMS]


STREAMS: list[Stream] = _load()


def by_slug(slug: str) -> Stream:
    for stream in STREAMS:
        if stream.slug == slug:
            return stream
    raise KeyError(slug)
