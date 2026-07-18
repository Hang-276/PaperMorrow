from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import runtime_settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if runtime_settings.database_url.startswith("sqlite") else {}
engine = create_engine(runtime_settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401
    from .migrations import run_migrations

    run_migrations(engine)
    Base.metadata.create_all(bind=engine)
