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
    inspect,
    text,
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


class FolderRecord(Base):
    __tablename__ = "folders"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(String(36), nullable=True, index=True)
    sort_order = Column(Float, nullable=False, default=0.0)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


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
    folder_id = Column(String(36), nullable=True, index=True)
    sort_order = Column(Float, nullable=False, default=0.0)

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
            "folder_id": self.folder_id,
            "sort_order": self.sort_order,
        }


def _run_migrations():
    """Add missing columns / tables introduced after initial release."""
    insp = inspect(engine)

    if insp.has_table("tasks"):
        existing = {col["name"] for col in insp.get_columns("tasks")}
        if "folder_id" not in existing:
            is_pg = DATABASE_URL.startswith("postgresql")
            col_type = "VARCHAR(36)" if is_pg else "VARCHAR(36)"
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN folder_id {col_type}"))
            logger.info("Migration: added folder_id column to tasks table")

            if is_pg:
                with engine.begin() as conn:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_tasks_folder_id ON tasks (folder_id)"
                    ))

    if insp.has_table("folders"):
        folder_cols = {col["name"] for col in insp.get_columns("folders")}
        if "sort_order" not in folder_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE folders ADD COLUMN sort_order FLOAT DEFAULT 0.0"))
            logger.info("Migration: added sort_order column to folders table")
        if "parent_id" not in folder_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE folders ADD COLUMN parent_id VARCHAR(36)"))
            logger.info("Migration: added parent_id column to folders table")

    if insp.has_table("tasks"):
        task_cols = {col["name"] for col in insp.get_columns("tasks")}
        if "sort_order" not in task_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN sort_order FLOAT DEFAULT 0.0"))
            logger.info("Migration: added sort_order column to tasks table")


def init_db():
    """Create tables if they don't exist, then run incremental migrations."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    db_label = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    logger.info(f"Database initialized: {db_label.split('?')[0]}")
