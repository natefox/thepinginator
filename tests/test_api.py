# tests/test_api.py
import pytest
import time
from httpx import AsyncClient, ASGITransport
import aiosqlite

from pinginator.api import create_app
from pinginator.config import Config
from pinginator.db import init_db, insert_ping


@pytest.fixture
def config():
    return Config(
        hosts=["8.8.8.8", "1.1.1.1"],
        interval=10,
        timeout=5,
        data_dir="/tmp",
        port=8080,
        raw_retention_hours=24,
    )


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    await init_db(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def client(config, db):
    app = create_app(config, db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_hosts_empty(client):
    resp = await client.get("/api/hosts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["host"] == "8.8.8.8"
    assert data[0]["status"] == "insufficient_data"


async def test_hosts_with_data(client, db):
    now = time.time()
    for i in range(20):
        await insert_ping(db, timestamp=now - i * 10, host="8.8.8.8", rtt_ms=12.0 + i * 0.1, success=1)
    resp = await client.get("/api/hosts")
    data = resp.json()
    host_data = next(h for h in data if h["host"] == "8.8.8.8")
    assert host_data["status"] == "normal"
    assert host_data["current_rtt_ms"] is not None
    assert host_data["avg_24h_ms"] is not None


async def test_history_raw(client, db):
    now = time.time()
    for i in range(5):
        await insert_ping(db, timestamp=now - i * 10, host="8.8.8.8", rtt_ms=12.0, success=1)
    resp = await client.get("/api/history/8.8.8.8?range=1h")
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] == "8.8.8.8"
    assert data["range"] == "1h"
    assert len(data["data"]) == 5


async def test_history_unknown_host(client):
    resp = await client.get("/api/history/9.9.9.9?range=1h")
    assert resp.status_code == 404


async def test_history_invalid_range(client):
    resp = await client.get("/api/history/8.8.8.8?range=2h")
    assert resp.status_code == 422


async def test_history_rollup_range(client, db):
    from pinginator.db import insert_rollup
    await insert_rollup(
        db, hour="2026-03-24T14:00:00", host="8.8.8.8",
        avg_ms=12.0, min_ms=10.0, max_ms=15.0, stddev_ms=1.5,
        count=360, loss_pct=0.5,
    )
    resp = await client.get("/api/history/8.8.8.8?range=7d")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["avg_ms"] == 12.0


async def test_hosts_insufficient_data_boundary(client, db):
    """9 pings = insufficient_data, 10 pings = real status."""
    now = time.time()
    for i in range(9):
        await insert_ping(db, timestamp=now - i * 10, host="8.8.8.8", rtt_ms=12.0, success=1)
    resp = await client.get("/api/hosts")
    host_data = next(h for h in resp.json() if h["host"] == "8.8.8.8")
    assert host_data["status"] == "insufficient_data"

    # Add one more to reach 10
    await insert_ping(db, timestamp=now - 90, host="8.8.8.8", rtt_ms=12.0, success=1)
    resp = await client.get("/api/hosts")
    host_data = next(h for h in resp.json() if h["host"] == "8.8.8.8")
    assert host_data["status"] == "normal"
