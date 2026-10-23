import os

# Must run before app modules create the engine.
os.environ["FROLLS_DATABASE_URL"] = "postgresql+asyncpg://frolls:frolls@localhost:5432/frolls_test"
os.environ["FROLLS_DB_NULL_POOL"] = "true"

import asyncio  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402, F401
from app.db import Base, engine  # noqa: E402
from app.game.server import server  # noqa: E402


async def _create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _truncate() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    asyncio.run(_create_schema())


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Empty database and fresh in-memory server for every test."""
    from app.main import app

    asyncio.run(_truncate())
    server.__init__()
    with TestClient(app) as c:
        yield c


class FixedDice:
    """Every die shows the same face (capped at its size)."""

    def __init__(self, face: int) -> None:
        self.face = face

    def randint(self, low: int, high: int) -> int:
        return max(low, min(self.face, high))


@pytest.fixture
def dice(monkeypatch: pytest.MonkeyPatch) -> FixedDice:
    """Rolls with known results: set `dice.face`."""
    from app.dice import engine

    fixed = FixedDice(10)
    monkeypatch.setattr(engine, "_rng", fixed)
    return fixed
