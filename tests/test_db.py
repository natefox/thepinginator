# tests/test_db.py
import pytest
import aiosqlite
from pinginator.db import init_db, insert_ping, get_pings, get_rollups, insert_rollup


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    await init_db(conn)
    yield conn
    await conn.close()


async def test_init_db_creates_tables(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "pings" in tables
    assert "rollups" in tables


async def test_init_db_sets_wal_mode(tmp_path):
    """WAL mode only works with file-based databases, not :memory:."""
    db_path = str(tmp_path / "test.db")
    conn = await aiosqlite.connect(db_path)
    await init_db(conn)
    cursor = await conn.execute("PRAGMA journal_mode")
    mode = (await cursor.fetchone())[0]
    assert mode == "wal"
    await conn.close()


async def test_insert_and_get_pings(db):
    await insert_ping(db, timestamp=1000.0, host="8.8.8.8", rtt_ms=12.5, success=1)
    await insert_ping(db, timestamp=1001.0, host="8.8.8.8", rtt_ms=None, success=0)
    rows = await get_pings(db, host="8.8.8.8", since=999.0)
    assert len(rows) == 2
    assert rows[0]["rtt_ms"] == 12.5
    assert rows[1]["rtt_ms"] is None
    assert rows[1]["success"] == 0


async def test_get_pings_filters_by_host(db):
    await insert_ping(db, timestamp=1000.0, host="8.8.8.8", rtt_ms=12.0, success=1)
    await insert_ping(db, timestamp=1000.0, host="1.1.1.1", rtt_ms=8.0, success=1)
    rows = await get_pings(db, host="1.1.1.1", since=999.0)
    assert len(rows) == 1
    assert rows[0]["host"] == "1.1.1.1"


async def test_insert_and_get_rollups(db):
    await insert_rollup(
        db,
        hour="2026-03-25T14:00:00",
        host="8.8.8.8",
        avg_ms=12.0,
        min_ms=10.0,
        max_ms=15.0,
        stddev_ms=1.5,
        count=360,
        loss_pct=0.5,
    )
    rows = await get_rollups(db, host="8.8.8.8", since_hour="2026-03-25T13:00:00")
    assert len(rows) == 1
    assert rows[0]["avg_ms"] == 12.0
    assert rows[0]["loss_pct"] == 0.5
