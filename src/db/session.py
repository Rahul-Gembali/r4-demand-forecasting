"""Database session management and connection pooling for R4 Forecasting.

Provides:
- Async and sync engine factories with PostgreSQL and SQLite support.
- Async session maker for FastAPI dependency injection (`get_db_session`).
- Context managers for scripts and workers.
- Schema creation and teardown helpers.
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from sqlalchemy import create_engine, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from src.core.config import settings
from src.db.models import Base


def normalize_database_url(url: str | None = None, sync: bool = False) -> str:
    """Normalize database connection string for async or sync driver."""
    raw_url = url or settings.database_url

    if sync:
        if raw_url.startswith("postgresql+asyncpg://"):
            return raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if raw_url.startswith("sqlite+aiosqlite:///"):
            return raw_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
        return raw_url
    else:
        if raw_url.startswith("postgresql://"):
            return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if raw_url.startswith("postgresql+psycopg2://"):
            return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if raw_url.startswith("postgresql+psycopg://"):
            return raw_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        if raw_url.startswith("sqlite:///") and not raw_url.startswith("sqlite+aiosqlite:///"):
            return raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return raw_url


def create_async_db_engine(
    url: str | None = None,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    """Create configured async SQLAlchemy engine."""
    db_url = normalize_database_url(url, sync=False)
    kwargs: dict[str, Any] = {"echo": echo}

    if "sqlite" in db_url:
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in db_url:
            kwargs["poolclass"] = NullPool
    else:
        # Default async pool is AsyncAdaptedQueuePool
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow
        kwargs["pool_pre_ping"] = True

    return create_async_engine(db_url, **kwargs)


def create_sync_db_engine(
    url: str | None = None,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> Engine:
    """Create configured sync SQLAlchemy engine (for Alembic and CLI scripts)."""
    db_url = normalize_database_url(url, sync=True)
    kwargs: dict[str, Any] = {"echo": echo}

    if "sqlite" in db_url:
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in db_url:
            kwargs["poolclass"] = NullPool
    else:
        kwargs["poolclass"] = QueuePool
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow
        kwargs["pool_pre_ping"] = True

    return create_engine(db_url, **kwargs)


# Default process-level engines and session factories
async_engine: AsyncEngine = create_async_db_engine()
sync_engine: Engine = create_sync_db_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session with automatic cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def async_session_scope(custom_engine: AsyncEngine | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for background jobs or scripts."""
    maker = (
        async_sessionmaker(bind=custom_engine, class_=AsyncSession, expire_on_commit=False)
        if custom_engine
        else AsyncSessionLocal
    )
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def sync_session_scope(custom_engine: Engine | None = None) -> Generator[Session, None, None]:
    """Sync context manager for CLI scripts, migrations, or tests."""
    maker = (
        sessionmaker(bind=custom_engine, class_=Session, expire_on_commit=False)
        if custom_engine
        else SyncSessionLocal
    )
    session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db_schema(engine: AsyncEngine | None = None) -> None:
    """Create all tables defined in Base.metadata."""
    target_engine = engine or async_engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db_schema(engine: AsyncEngine | None = None) -> None:
    """Drop all tables defined in Base.metadata."""
    target_engine = engine or async_engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
