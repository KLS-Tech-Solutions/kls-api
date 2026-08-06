"""
Seeds the catalogue and the first super admin.

    docker compose exec api python scripts/seed.py

Idempotent — safe to run repeatedly.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    AdminProfile,
    BatchStatus,
    Difficulty,
    InternshipBatch,
    InternshipDomain,
    Task,
    User,
    UserRole,
    UserStatus,
)

DOMAINS = [
    {
        "slug": "full-stack-python",
        "title": "Full Stack Python Development",
        "description": (
            "Build and ship a complete web application — FastAPI services, a React "
            "front end, PostgreSQL persistence and a deployed live demo."
        ),
        "duration": "4 weeks",
        "difficulty": Difficulty.INTERMEDIATE,
        "icon": "code",
        "skills": ["Python", "FastAPI", "React", "PostgreSQL", "REST APIs", "Git"],
        "outcomes": [
            "Design and expose a REST API with authentication",
            "Model relational data and write efficient queries",
            "Connect a React front end to a live backend",
            "Deploy a full stack application end to end",
        ],
        "tasks": [
            ("REST API foundation", "Build a FastAPI service with registration, JWT login and a protected resource endpoint.", 10),
            ("React front end", "Build a responsive React interface that consumes the API from Task 1.", 12),
            ("Integration and deployment", "Connect both halves, add validation and deploy the application.", 14),
        ],
    },
    {
        "slug": "web-development",
        "title": "Web Development",
        "description": (
            "Master modern front-end engineering — semantic markup, responsive layout "
            "systems, component architecture and production deployment."
        ),
        "duration": "4 weeks",
        "difficulty": Difficulty.BEGINNER,
        "icon": "layout",
        "skills": ["HTML", "CSS", "JavaScript", "React", "Responsive Design", "Vercel"],
        "outcomes": [
            "Build accessible, responsive interfaces from a design",
            "Structure a component library that scales",
            "Handle state and data fetching in React",
            "Ship a production site with a custom domain",
        ],
        "tasks": [
            ("Responsive landing page", "Build an accessible, responsive marketing page from a supplied design.", 8),
            ("Component library", "Extract a reusable component set with consistent tokens.", 10),
            ("Deployed application", "Assemble the components into a working app and deploy it.", 12),
        ],
    },
    {
        "slug": "cyber-security",
        "title": "Cyber Security",
        "description": (
            "Work through practical security engineering — threat modelling, "
            "vulnerability assessment, secure coding practice and incident documentation."
        ),
        "duration": "4 weeks",
        "difficulty": Difficulty.ADVANCED,
        "icon": "shield",
        "skills": ["Threat Modelling", "OWASP Top 10", "Network Security", "Linux", "Reporting"],
        "outcomes": [
            "Run a structured vulnerability assessment",
            "Identify and remediate OWASP Top 10 issues",
            "Harden a Linux server against common attacks",
            "Write a professional security assessment report",
        ],
        "tasks": [
            ("Threat model", "Produce a threat model for a supplied application architecture.", 8),
            ("Vulnerability assessment", "Assess a deliberately vulnerable app and document every finding.", 12),
            ("Remediation and hardening", "Fix the findings and harden the host, with before/after evidence.", 12),
            ("Assessment report", "Write the professional report a client would receive.", 6),
        ],
    },
    {
        "slug": "generative-ai",
        "title": "Generative AI",
        "description": (
            "Build applications on top of large language models — prompt design, "
            "retrieval augmented generation, evaluation and cost-aware deployment."
        ),
        "duration": "4 weeks",
        "difficulty": Difficulty.INTERMEDIATE,
        "icon": "sparkles",
        "skills": ["Python", "LLM APIs", "RAG", "Vector Databases", "Prompt Engineering"],
        "outcomes": [
            "Design prompts that produce reliable structured output",
            "Build a retrieval augmented generation pipeline",
            "Evaluate model output quality systematically",
            "Ship an LLM-backed application to production",
        ],
        "tasks": [
            ("Structured prompting", "Build a service that returns reliable structured output from an LLM.", 10),
            ("RAG pipeline", "Ingest a document set and answer questions over it with citations.", 14),
            ("Evaluation and deployment", "Measure output quality, then deploy the application.", 12),
        ],
    },
    {
        "slug": "agentic-ai",
        "title": "Agentic AI",
        "description": (
            "Go beyond single prompts — design autonomous agents with tool use, memory, "
            "multi-step planning and human-in-the-loop control."
        ),
        "duration": "6 weeks",
        "difficulty": Difficulty.ADVANCED,
        "icon": "bot",
        "skills": ["Agent Architecture", "Tool Calling", "Orchestration", "Python", "Evaluation"],
        "outcomes": [
            "Architect an agent loop with tool calling",
            "Give an agent persistent memory and context control",
            "Add guardrails and human approval checkpoints",
            "Measure agent reliability across real tasks",
        ],
        "tasks": [
            ("Agent loop with tools", "Build an agent that plans and calls at least three tools.", 12),
            ("Memory and context", "Add persistent memory and deliberate context management.", 12),
            ("Guardrails", "Add human approval checkpoints and failure handling.", 10),
            ("Reliability evaluation", "Measure the agent across a task set and report the results.", 10),
        ],
    },
    {
        "slug": "data-science",
        "title": "Data Science",
        "description": (
            "Turn raw datasets into decisions — cleaning, exploratory analysis, "
            "statistical modelling and communicating findings to a business audience."
        ),
        "duration": "4 weeks",
        "difficulty": Difficulty.INTERMEDIATE,
        "icon": "chart",
        "skills": ["Python", "pandas", "NumPy", "Visualisation", "Statistics", "Jupyter"],
        "outcomes": [
            "Clean and reshape messy real-world data",
            "Run exploratory analysis that finds real signal",
            "Build and validate a predictive model",
            "Present findings clearly to non-technical stakeholders",
        ],
        "tasks": [
            ("Data cleaning", "Clean and reshape a deliberately messy dataset, documenting every decision.", 8),
            ("Exploratory analysis", "Find and evidence real signal, with clear visualisations.", 10),
            ("Predictive model", "Build, validate and interpret a model.", 12),
        ],
    },
]

LINKEDIN_TASK = (
    "Share your offer letter on LinkedIn",
    (
        "Download your offer letter, post it on LinkedIn tagging KLS Tech Solutions, "
        "then submit the post URL. Technical tasks unlock once an administrator "
        "verifies your post."
    ),
    1,
    [
        "Public LinkedIn post containing your offer letter",
        "Tag KLS Tech Solutions in the post",
        "Submit the direct post URL",
    ],
)

TECHNICAL_REQUIREMENTS = [
    "Public GitHub repository with a clear README",
    "Minimum three screenshots of the working project",
    "Detailed written explanation of your implementation",
    "Live demo link (optional but recommended)",
]


def seed() -> None:
    db = SessionLocal()
    try:
        created_domains = 0
        created_tasks = 0

        for spec in DOMAINS:
            domain = db.scalar(
                select(InternshipDomain).where(InternshipDomain.slug == spec["slug"])
            )
            if domain is None:
                domain = InternshipDomain(
                    slug=spec["slug"],
                    title=spec["title"],
                    description=spec["description"],
                    duration=spec["duration"],
                    difficulty=spec["difficulty"],
                    icon=spec["icon"],
                    skills=spec["skills"],
                    outcomes=spec["outcomes"],
                )
                db.add(domain)
                db.flush()
                created_domains += 1

            batch = db.scalar(
                select(InternshipBatch).where(InternshipBatch.domain_id == domain.id)
            )
            if batch is None:
                start = date.today() + timedelta(days=14)
                batch = InternshipBatch(
                    domain_id=domain.id,
                    batch_name=f"{domain.title} — Batch 01",
                    start_date=start,
                    end_date=start + timedelta(weeks=int(spec["duration"].split()[0])),
                    status=BatchStatus.UPCOMING,
                    seats_total=50,
                )
                db.add(batch)
                db.flush()

            existing_tasks = db.scalar(
                select(Task).where(Task.batch_id == batch.id)
            )
            if existing_tasks is None:
                title, description, hours, requirements = LINKEDIN_TASK
                db.add(
                    Task(
                        batch_id=batch.id,
                        title=title,
                        description=description,
                        order_number=0,
                        estimated_hours=hours,
                        requirements=requirements,
                        deadline=batch.start_date + timedelta(days=3),
                    )
                )
                created_tasks += 1

                # Task counts vary per domain — that is deliberate.
                for index, (t_title, t_desc, t_hours) in enumerate(spec["tasks"], start=1):
                    db.add(
                        Task(
                            batch_id=batch.id,
                            title=f"Task {index} — {t_title}",
                            description=t_desc,
                            order_number=index,
                            estimated_hours=t_hours,
                            requirements=TECHNICAL_REQUIREMENTS,
                            deadline=batch.start_date + timedelta(days=7 * index),
                        )
                    )
                    created_tasks += 1

        admin = db.scalar(
            select(User).where(User.email == settings.FIRST_SUPERADMIN_EMAIL.lower())
        )
        if admin is None:
            admin = User(
                full_name="KLS Administrator",
                email=settings.FIRST_SUPERADMIN_EMAIL.lower(),
                phone="+919000000000",
                password_hash=hash_password(settings.FIRST_SUPERADMIN_PASSWORD),
                role=UserRole.SUPER_ADMIN,
                status=UserStatus.ACTIVE,
                email_verified=True,
            )
            db.add(admin)
            db.flush()
            db.add(AdminProfile(user_id=admin.id, designation="Super Administrator"))
            print(f"Created super admin: {admin.email}")
            print("  Change this password immediately.")

        db.commit()
        print(f"Seed complete — {created_domains} domains, {created_tasks} tasks added.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
