import os

from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///" + os.path.join(os.path.expanduser("~"), "accounting.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    if "db" not in g:
        g.db = SessionLocal()
    return g.db
