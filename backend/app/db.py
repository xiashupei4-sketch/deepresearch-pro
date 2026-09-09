"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    # Ensure the sqlite data dir exists
    if url.startswith("sqlite"):
        from app.config import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_async_engine(url, echo=False, pool_pre_ping=True)


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables (dev convenience); Alembic is used for real migrations."""
    from app import models  # noqa: F401  ensure model registry is populated

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移:为旧库补齐新增列(已存在则忽略)
        from sqlalchemy import text

        for stmt in (
            "ALTER TABLE research_sessions ADD COLUMN pinned BOOLEAN DEFAULT 0",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001 — column already exists
                pass
