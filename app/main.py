import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO if settings.DEBUG else logging.WARNING)

_problems = settings.validate_for_runtime()
if _problems:
    message = "Configuration problems:\n  - " + "\n  - ".join(_problems)
    if settings.is_production:
        # Refuse to serve traffic with a guessable signing key.
        raise RuntimeError(message)
    logger.warning(message)


def check_database_connection() -> None:
    """
    Fail loudly and specifically on startup rather than returning a 500 from
    the first login attempt. A wrong password in DATABASE_URL is otherwise
    indistinguishable from "the login endpoint is broken".
    """
    from sqlalchemy import text

    from app.core.database import engine

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "\n"
            "=========================================================\n"
            " Cannot connect to the database.\n"
            "\n"
            " %s\n"
            "\n"
            " Check DATABASE_URL in .env. Special characters in the\n"
            " password must be percent-encoded ONCE:\n"
            "   @ -> %%40    # -> %%23    / -> %%2F    : -> %%3A\n"
            "=========================================================",
            exc,
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_database_connection()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Backend for KLS Academy — the verified virtual internship platform. "
        "Serves academy.klstechsolutions.in and admin.klstechsolutions.in."
    ),
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if not settings.is_production else None,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """
    Response headers every browser understands and every audit asks for.

    No Content-Security-Policy: this API only ever returns JSON, PDFs and
    images, so a policy governing script sources would be decoration. The
    frontends set their own, where it means something.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # The admin console must never be framed — an invisible iframe plus a
    # misplaced click is how an administrator approves something they cannot
    # see.
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if settings.is_production:
        # Only in production: sending HSTS from a local http:// server pins the
        # browser to https for localhost and breaks every other project on the
        # machine.
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    """
    Keeps FastAPI's `{"detail": [{loc, msg, type}]}` shape, which both
    frontends map onto individual form fields via loc[-1].
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        # jsonable_encoder strips the raw exception objects Pydantic puts in ctx.
        content={"detail": jsonable_encoder(exc.errors())},
    )


# There is deliberately no static mount for ./media. Student documents,
# screenshots and study notes are served only through authenticated routes
# that check who is asking — mounting the directory would put every stored
# file back on a public URL, which is the exposure this design removed.


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return {"service": settings.PROJECT_NAME, "docs": "/docs"}


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
