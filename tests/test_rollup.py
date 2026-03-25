# tests/test_rollup.py
import pytest
import aiosqlite
from datetime import datetime, timezone

from pinginator.db import init_db, insert_ping
from pinginator.rollup import compute_hourly_rollup, run_rollup, purge_old_pings


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    await init_db(conn)
    yield conn
    await conn.close()


async def _insert_test_pings(db, host, hour_str, count=10, rtt_base=10.0, failures=0):
    """Insert test pings spread across the given hour."""
    hour_dt = datetime.fromisoformat(hour_str).replace(tzinfo=timezone.utc)
    base_ts = hour_dt.timestamp()
    for i in range(count):
        ts = base_ts + i * (3600 / count)
        if i < failures:
            await insert_ping(db, timestamp=ts, host=host, rtt_ms=None, success=0)
        else:
            await insert_ping(db, timestamp=ts, host=host, rtt_ms=rtt_base + i, success=1)


async def test_compute_hourly_rollup(db):
    await _insert_test_pings(db, "8.8.8.8", "2026-03-25T14:00:00", count=10, rtt_base=10.0)
    rollup = await compute_hourly_rollup(db, "8.8.8.8", "2026-03-25T14:00:00")
    assert rollup is not None
    assert rollup["count"] == 10
    assert rollup["loss_pct"] == pytest.approx(0.0)
    assert rollup["avg_ms"] == pytest.approx(14.5)
    assert rollup["min_ms"] == pytest.approx(10.0)
    assert rollup["max_ms"] == pytest.approx(19.0)


async def test_compute_hourly_rollup_with_losses(db):
    await _insert_test_pings(db, "8.8.8.8", "2026-03-25T14:00:00", count=10, failures=3)
    rollup = await compute_hourly_rollup(db, "8.8.8.8", "2026-03-25T14:00:00")
    assert rollup["loss_pct"] == pytest.approx(30.0)
    assert rollup["count"] == 10
    assert rollup["min_ms"] == pytest.approx(13.0)


async def test_compute_hourly_rollup_no_data(db):
    rollup = await compute_hourly_rollup(db, "8.8.8.8", "2026-03-25T14:00:00")
    assert rollup is None


async def test_run_rollup_inserts_to_table(db):
    await _insert_test_pings(db, "8.8.8.8", "2026-03-25T14:00:00", count=10)
    await run_rollup(db, ["8.8.8.8"], "2026-03-25T14:00:00")
    cursor = await db.execute("SELECT * FROM rollups WHERE host = '8.8.8.8'")
    rows = await cursor.fetchall()
    assert len(rows) == 1


async def test_purge_old_pings(db):
    await _insert_test_pings(db, "8.8.8.8", "2026-03-25T14:00:00", count=5)
    deleted = await purge_old_pings(db, before=datetime(2026, 3, 26, tzinfo=timezone.utc).timestamp())
    assert deleted == 5
    cursor = await db.execute("SELECT COUNT(*) FROM pings")
    count = (await cursor.fetchone())[0]
    assert count == 0
