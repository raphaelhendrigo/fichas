from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fichas.settings import settings


def _build_engine():
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if url in (
            "sqlite+pysqlite://",
            "sqlite://",
            "sqlite+pysqlite:///:memory:",
            "sqlite:///:memory:",
        ):
            return create_engine(
                url,
                connect_args=connect_args,
                poolclass=StaticPool,
                future=True,
            )
        return create_engine(url, connect_args=connect_args, future=True)
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
