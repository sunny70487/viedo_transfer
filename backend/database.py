"""
Database engine and session configuration.
Supports PostgreSQL (production) and SQLite (development fallback).
Configure via DATABASE_URL environment variable.
"""

import os
import logging
from pathlib import Path

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Text,
    JSON,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger("database")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_URL = f"sqlite:///{_PROJECT_ROOT / 'tasks.db'}"

DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE_URL)

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=False,
)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine)


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)
    status = Column(String(20), nullable=False, default="queued")
    progress = Column(Float, default=0.0)
    message = Column(Text, default="")
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=True)
    source_name = Column(Text, nullable=True)
    batch_id = Column(String(36), nullable=True, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message or "",
            "result": self.result,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source_name": self.source_name,
            "batch_id": self.batch_id,
        }


def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    db_label = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    logger.info(f"Database initialized: {db_label.split('?')[0]}")
