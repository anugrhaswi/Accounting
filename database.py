"""Database engine, session factory, and per-request session management."""

import os

from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# DB file lives at ~/accounting.db
DB_PATH = os.path.join(os.path.expanduser("~"), "accounting.db")
DATABASE_URL = "sqlite:///" + DB_PATH

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def get_db():
    """Return the DB session for the current request.

    Creates a new session on first call per request and stores it in flask.g.
    Closed and committed/rolled back automatically by teardown_request.
    """
    if "db" not in g:
        g.db = SessionLocal()
    return g.db
