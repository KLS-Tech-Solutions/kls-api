import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO if settings.DEBUG else logging.WARNING)

_problems = settings.validate_for_runtime()
if _problems:
    message = "Configuration problems:\n  - " + "\n  - ".join(_problems)
    if settings.is_production:
        # Refuse to serve traffic with a guessable signing key.
        raise RuntimeError(message)
    logging.warning(message)


app = FastAPI(
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


@app.on_event("startup")
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
        logging.info("Database connection OK")
    except Exception as exc:  # noqa: BLE001
        logging.error(
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


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return {"service": settings.PROJECT_NAME, "docs": "/docs"}


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
