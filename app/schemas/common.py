import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for anything read out of SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


__all__ = ["ORMModel", "Message", "uuid", "datetime", "date"]
