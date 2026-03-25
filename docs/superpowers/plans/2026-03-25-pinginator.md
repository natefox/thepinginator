# The Pinginator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Dockerized ping monitor that tracks latency/loss for N hosts, computes rolling stats with anomaly detection, and serves a single-page dashboard.

**Architecture:** Single Docker container with three async concerns — ping workers (subprocess), stats engine (mean/stddev/classification), and FastAPI server — sharing a SQLite database. Frontend is one HTML file with Chart.js.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, Chart.js (CDN), Docker (python:3.12-slim)

**Spec:** `docs/superpowers/specs/2026-03-25-pinginator-design.md`

---

## File Structure

```
thepinginator/
├── pinginator/
│   ├── __init__.py           # Package marker (empty)
│   ├── __main__.py           # Entry point: starts uvicorn + background tasks
│   ├── config.py             # Env var parsing + validation
│   ├── db.py                 # SQLite setup (WAL, schema), query helpers
│   ├── pinger.py             # Async ping worker per host
│   ├── stats.py              # Rolling stats, anomaly classification
│   ├── rollup.py             # Hourly rollup job + data retention purge
│   └── api.py                # FastAPI app, routes, static file serving
├── static/
│   └── index.html            # Single-page dashboard (Chart.js)
├── tests/
│   ├── __init__.py
│   ├── test_config.py        # Config parsing + validation tests
│   ├── test_pinger.py        # Ping output parsing tests
│   ├── test_stats.py         # Stats computation + classification tests
│   ├── test_rollup.py        # Rollup aggregation tests
│   ├── test_db.py            # DB schema + query tests
│   └── test_api.py           # API endpoint tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml            # pytest config
```

---

### Task 1: Project Scaffolding + Config

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `pinginator/__init__.py`
- Create: `pinginator/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi
uvicorn[standard]
aiosqlite
pytest
pytest-asyncio
httpx
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Install dependencies**

Run: `cd /Users/nfox/github/thepinginator && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 4: Create empty package files**

Create `pinginator/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 5: Write failing config tests**

```python
# tests/test_config.py
import os
import pytest
from pinginator.config import load_config


def test_load_config_parses_hosts(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8,1.1.1.1")
    cfg = load_config()
    assert cfg.hosts == ["8.8.8.8", "1.1.1.1"]


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    cfg = load_config()
    assert cfg.interval == 10
    assert cfg.timeout == 5
    assert cfg.data_dir == "/data"
    assert cfg.port == 8080


def test_load_config_custom_values(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    monkeypatch.setenv("PING_INTERVAL", "30")
    monkeypatch.setenv("PING_TIMEOUT", "10")
    monkeypatch.setenv("DATA_DIR", "/tmp/test")
    monkeypatch.setenv("PORT", "9090")
    cfg = load_config()
    assert cfg.interval == 30
    assert cfg.timeout == 10
    assert cfg.data_dir == "/tmp/test"
    assert cfg.port == 9090


def test_load_config_missing_hosts_raises(monkeypatch):
    monkeypatch.delenv("PING_HOSTS", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_timeout_gte_interval_raises(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    monkeypatch.setenv("PING_INTERVAL", "5")
    monkeypatch.setenv("PING_TIMEOUT", "5")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_strips_whitespace(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", " 8.8.8.8 , 1.1.1.1 ")
    cfg = load_config()
    assert cfg.hosts == ["8.8.8.8", "1.1.1.1"]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/nfox/github/thepinginator && source .venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.config'`

- [ ] **Step 7: Implement config.py**

```python
# pinginator/config.py
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    hosts: list[str]
    interval: int
    timeout: int
    data_dir: str
    port: int


def load_config() -> Config:
    hosts_raw = os.environ.get("PING_HOSTS", "")
    if not hosts_raw.strip():
        print("ERROR: PING_HOSTS environment variable is required", file=sys.stderr)
        sys.exit(1)

    hosts = [h.strip() for h in hosts_raw.split(",") if h.strip()]
    interval = int(os.environ.get("PING_INTERVAL", "10"))
    timeout = int(os.environ.get("PING_TIMEOUT", "5"))
    data_dir = os.environ.get("DATA_DIR", "/data")
    port = int(os.environ.get("PORT", "8080"))

    if timeout >= interval:
        print(
            f"ERROR: PING_TIMEOUT ({timeout}) must be less than PING_INTERVAL ({interval})",
            file=sys.stderr,
        )
        sys.exit(1)

    return Config(
        hosts=hosts,
        interval=interval,
        timeout=timeout,
        data_dir=data_dir,
        port=port,
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All 6 tests PASS

- [ ] **Step 9: Commit**

```bash
git add pinginator/ tests/ requirements.txt pyproject.toml
git commit -m "feat: project scaffolding and config parsing with tests"
```

---

### Task 2: Database Layer

**Files:**
- Create: `pinginator/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing DB tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.db'`

- [ ] **Step 3: Implement db.py**

```python
# pinginator/db.py
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS pings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    host TEXT NOT NULL,
    rtt_ms REAL,
    success INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pings_host_ts ON pings (host, timestamp);

CREATE TABLE IF NOT EXISTS rollups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour TEXT NOT NULL,
    host TEXT NOT NULL,
    avg_ms REAL,
    min_ms REAL,
    max_ms REAL,
    stddev_ms REAL,
    count INTEGER NOT NULL,
    loss_pct REAL NOT NULL,
    UNIQUE(hour, host)
);
"""


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()


async def insert_ping(
    db: aiosqlite.Connection,
    timestamp: float,
    host: str,
    rtt_ms: float | None,
    success: int,
) -> None:
    await db.execute(
        "INSERT INTO pings (timestamp, host, rtt_ms, success) VALUES (?, ?, ?, ?)",
        (timestamp, host, rtt_ms, success),
    )
    await db.commit()


async def get_pings(
    db: aiosqlite.Connection, host: str, since: float
) -> list[dict]:
    cursor = await db.execute(
        "SELECT timestamp, host, rtt_ms, success FROM pings "
        "WHERE host = ? AND timestamp >= ? ORDER BY timestamp",
        (host, since),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def insert_rollup(
    db: aiosqlite.Connection,
    hour: str,
    host: str,
    avg_ms: float | None,
    min_ms: float | None,
    max_ms: float | None,
    stddev_ms: float | None,
    count: int,
    loss_pct: float,
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO rollups "
        "(hour, host, avg_ms, min_ms, max_ms, stddev_ms, count, loss_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (hour, host, avg_ms, min_ms, max_ms, stddev_ms, count, loss_pct),
    )
    await db.commit()


async def get_rollups(
    db: aiosqlite.Connection, host: str, since_hour: str
) -> list[dict]:
    cursor = await db.execute(
        "SELECT hour, host, avg_ms, min_ms, max_ms, stddev_ms, count, loss_pct "
        "FROM rollups WHERE host = ? AND hour >= ? ORDER BY hour",
        (host, since_hour),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def delete_old_pings(db: aiosqlite.Connection, before: float) -> int:
    cursor = await db.execute(
        "DELETE FROM pings WHERE timestamp < ?", (before,)
    )
    await db.commit()
    return cursor.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pinginator/db.py tests/test_db.py
git commit -m "feat: database layer with schema, queries, and tests"
```

---

### Task 3: Ping Worker

**Files:**
- Create: `pinginator/pinger.py`
- Create: `tests/test_pinger.py`

- [ ] **Step 1: Write failing pinger tests**

The pinger has two parts: parsing `ping` output, and the async worker loop. We test the parser with real output samples.

```python
# tests/test_pinger.py
import pytest
from pinginator.pinger import parse_ping_output


def test_parse_linux_success():
    output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n"
        "rtt min/avg/max/mdev = 12.300/12.300/12.300/0.000 ms\n"
    )
    result = parse_ping_output(output, returncode=0)
    assert result["success"] is True
    assert result["rtt_ms"] == pytest.approx(12.3)


def test_parse_macos_success():
    output = (
        "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n"
        "64 bytes from 8.8.8.8: icmp_seq=0 ttl=118 time=14.567 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "1 packets transmitted, 1 packets received, 0.0% packet loss\n"
        "round-trip min/avg/max/stddev = 14.567/14.567/14.567/0.000 ms\n"
    )
    result = parse_ping_output(output, returncode=0)
    assert result["success"] is True
    assert result["rtt_ms"] == pytest.approx(14.567)


def test_parse_timeout():
    output = (
        "PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.\n"
        "\n"
        "--- 10.0.0.1 ping statistics ---\n"
        "1 packets transmitted, 0 received, 100% packet loss, time 0ms\n"
    )
    result = parse_ping_output(output, returncode=1)
    assert result["success"] is False
    assert result["rtt_ms"] is None


def test_parse_dns_failure():
    output = "ping: unknown host badhost.invalid\n"
    result = parse_ping_output(output, returncode=2)
    assert result["success"] is False
    assert result["rtt_ms"] is None


def test_parse_empty_output():
    result = parse_ping_output("", returncode=1)
    assert result["success"] is False
    assert result["rtt_ms"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pinger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.pinger'`

- [ ] **Step 3: Implement pinger.py**

```python
# pinginator/pinger.py
import asyncio
import re
import time

import aiosqlite

from pinginator.config import Config
from pinginator.db import insert_ping

# Matches "time=12.3 ms" or "time=12.345 ms" in ping output
_RTT_PATTERN = re.compile(r"time[=<]([\d.]+)\s*ms")


def parse_ping_output(output: str, returncode: int) -> dict:
    if returncode != 0 or not output.strip():
        # Check if there's still a time= in the output (some systems return 1 on partial loss)
        match = _RTT_PATTERN.search(output)
        if match:
            return {"success": True, "rtt_ms": float(match.group(1))}
        return {"success": False, "rtt_ms": None}

    match = _RTT_PATTERN.search(output)
    if match:
        return {"success": True, "rtt_ms": float(match.group(1))}
    return {"success": False, "rtt_ms": None}


async def ping_once(host: str, timeout: int) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(timeout), host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return parse_ping_output(stdout.decode(errors="replace"), proc.returncode)
    except Exception:
        return {"success": False, "rtt_ms": None}


async def ping_worker(host: str, config: Config, db: aiosqlite.Connection) -> None:
    while True:
        result = await ping_once(host, config.timeout)
        await insert_ping(
            db,
            timestamp=time.time(),
            host=host,
            rtt_ms=result["rtt_ms"],
            success=1 if result["success"] else 0,
        )
        await asyncio.sleep(config.interval)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pinger.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pinginator/pinger.py tests/test_pinger.py
git commit -m "feat: ping worker with output parser and tests"
```

---

### Task 4: Stats Engine

**Files:**
- Create: `pinginator/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write failing stats tests**

```python
# tests/test_stats.py
import pytest
from pinginator.stats import compute_stats, classify_status, median_of_last_n


def test_compute_stats_basic():
    rtts = [10.0, 12.0, 14.0, 10.0, 12.0, 14.0]
    result = compute_stats(rtts)
    assert result["mean"] == pytest.approx(12.0)
    assert result["stddev"] == pytest.approx(1.632, abs=0.01)


def test_compute_stats_empty():
    result = compute_stats([])
    assert result is None


def test_classify_normal():
    # mean=12, stddev=2, current=13 -> within 1 sigma
    assert classify_status(current=13.0, mean=12.0, stddev=2.0) == "normal"


def test_classify_elevated():
    # mean=12, stddev=2, current=15 -> between 1 and 2 sigma above
    assert classify_status(current=15.0, mean=12.0, stddev=2.0) == "elevated"


def test_classify_high():
    # mean=12, stddev=2, current=17 -> more than 2 sigma above
    assert classify_status(current=17.0, mean=12.0, stddev=2.0) == "high"


def test_classify_below_mean_is_normal():
    # Below mean by any amount is always normal (low latency = good)
    assert classify_status(current=5.0, mean=12.0, stddev=2.0) == "normal"


def test_classify_zero_stddev_at_mean():
    # Perfectly stable — same as mean is normal
    assert classify_status(current=12.0, mean=12.0, stddev=0.0) == "normal"


def test_classify_zero_stddev_above_mean():
    # Any increase from perfectly stable is elevated
    assert classify_status(current=12.1, mean=12.0, stddev=0.0) == "elevated"


def test_classify_zero_stddev_below_mean():
    # Below mean with zero stddev is still normal (latency improved)
    assert classify_status(current=11.0, mean=12.0, stddev=0.0) == "normal"


def test_median_of_last_n_basic():
    pings = [
        {"rtt_ms": 10.0, "success": 1},
        {"rtt_ms": 20.0, "success": 1},
        {"rtt_ms": 15.0, "success": 1},
        {"rtt_ms": 12.0, "success": 1},
        {"rtt_ms": 18.0, "success": 1},
    ]
    assert median_of_last_n(pings, n=5) == pytest.approx(15.0)


def test_median_of_last_n_skips_failures():
    pings = [
        {"rtt_ms": 10.0, "success": 1},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 20.0, "success": 1},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 15.0, "success": 1},
    ]
    assert median_of_last_n(pings, n=5) == pytest.approx(15.0)


def test_median_of_last_n_too_few_successful():
    pings = [
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 10.0, "success": 1},
    ]
    # Fewer than 2 successful -> returns None
    assert median_of_last_n(pings, n=5) is None


def test_median_of_last_n_empty():
    assert median_of_last_n([], n=5) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.stats'`

- [ ] **Step 3: Implement stats.py**

```python
# pinginator/stats.py
import statistics


def compute_stats(rtts: list[float]) -> dict | None:
    if not rtts:
        return None
    mean = statistics.mean(rtts)
    stddev = statistics.pstdev(rtts)
    return {"mean": mean, "stddev": stddev}


def classify_status(current: float, mean: float, stddev: float) -> str:
    if current <= mean:
        return "normal"

    if stddev == 0.0:
        return "elevated"

    deviation = (current - mean) / stddev
    if deviation <= 1.0:
        return "normal"
    elif deviation <= 2.0:
        return "elevated"
    else:
        return "high"


def median_of_last_n(pings: list[dict], n: int) -> float | None:
    recent = pings[-n:] if len(pings) >= n else pings
    successful_rtts = [p["rtt_ms"] for p in recent if p["success"] and p["rtt_ms"] is not None]
    if len(successful_rtts) < 2:
        return None
    return statistics.median(successful_rtts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pinginator/stats.py tests/test_stats.py
git commit -m "feat: stats engine with anomaly classification and tests"
```

---

### Task 5: Rollup Job

**Files:**
- Create: `pinginator/rollup.py`
- Create: `tests/test_rollup.py`

- [ ] **Step 1: Write failing rollup tests**

```python
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
    # avg/min/max computed over 7 successful pings only
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
    # Purge anything before a timestamp after all the test pings
    deleted = await purge_old_pings(db, before=datetime(2026, 3, 26, tzinfo=timezone.utc).timestamp())
    assert deleted == 5
    cursor = await db.execute("SELECT COUNT(*) FROM pings")
    count = (await cursor.fetchone())[0]
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rollup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.rollup'`

- [ ] **Step 3: Implement rollup.py**

```python
# pinginator/rollup.py
import asyncio
import statistics
import time
from datetime import datetime, timedelta, timezone

import aiosqlite

from pinginator.db import insert_rollup, delete_old_pings


async def compute_hourly_rollup(
    db: aiosqlite.Connection, host: str, hour_str: str
) -> dict | None:
    hour_dt = datetime.fromisoformat(hour_str).replace(tzinfo=timezone.utc)
    start_ts = hour_dt.timestamp()
    end_ts = (hour_dt + timedelta(hours=1)).timestamp()

    cursor = await db.execute(
        "SELECT rtt_ms, success FROM pings "
        "WHERE host = ? AND timestamp >= ? AND timestamp < ?",
        (host, start_ts, end_ts),
    )
    rows = await cursor.fetchall()
    if not rows:
        return None

    total = len(rows)
    successful_rtts = [r[0] for r in rows if r[1] == 1 and r[0] is not None]
    failures = total - len(successful_rtts)
    loss_pct = (failures / total) * 100.0

    if successful_rtts:
        avg_ms = statistics.mean(successful_rtts)
        min_ms = min(successful_rtts)
        max_ms = max(successful_rtts)
        stddev_ms = statistics.pstdev(successful_rtts)
    else:
        avg_ms = min_ms = max_ms = stddev_ms = None

    return {
        "hour": hour_str,
        "host": host,
        "avg_ms": avg_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "stddev_ms": stddev_ms,
        "count": total,
        "loss_pct": loss_pct,
    }


async def run_rollup(
    db: aiosqlite.Connection, hosts: list[str], hour_str: str
) -> None:
    for host in hosts:
        rollup = await compute_hourly_rollup(db, host, hour_str)
        if rollup:
            await insert_rollup(db, **rollup)


async def purge_old_pings(db: aiosqlite.Connection, before: float) -> int:
    return await delete_old_pings(db, before)


async def rollup_worker(db: aiosqlite.Connection, hosts: list[str]) -> None:
    while True:
        now = datetime.now(timezone.utc)
        # Compute rollup for the previous completed hour
        prev_hour = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        hour_str = prev_hour.strftime("%Y-%m-%dT%H:%M:%S")
        await run_rollup(db, hosts, hour_str)

        # Purge pings older than 7 days
        cutoff = time.time() - (7 * 24 * 3600)
        await purge_old_pings(db, before=cutoff)

        # Sleep until the next hour boundary
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sleep_seconds = (next_hour - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rollup.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pinginator/rollup.py tests/test_rollup.py
git commit -m "feat: hourly rollup job with purge and tests"
```

---

### Task 6: API Routes

**Files:**
- Create: `pinginator/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pinginator.api'`

- [ ] **Step 3: Implement api.py**

```python
# pinginator/api.py
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pinginator.config import Config
from pinginator.db import get_pings, get_rollups
from pinginator.stats import compute_stats, classify_status, median_of_last_n

VALID_RANGES = {"1h", "24h", "7d", "30d"}
RANGE_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app(config: Config, db: aiosqlite.Connection) -> FastAPI:
    app = FastAPI(title="Pinginator", docs_url=None, redoc_url=None)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/hosts")
    async def hosts():
        now = time.time()
        since_24h = now - 86400
        results = []
        for host in config.hosts:
            pings = await get_pings(db, host, since=since_24h)
            successful_rtts = [p["rtt_ms"] for p in pings if p["success"] and p["rtt_ms"] is not None]
            total = len(pings)
            failures = total - len(successful_rtts)

            stats = compute_stats(successful_rtts)
            current = median_of_last_n(pings, n=5)

            if total == 0 or len(successful_rtts) < 10:
                status = "insufficient_data"
                entry = {
                    "host": host,
                    "current_rtt_ms": current,
                    "status": status,
                    "avg_24h_ms": stats["mean"] if stats else None,
                    "stddev_24h_ms": stats["stddev"] if stats else None,
                    "loss_24h_pct": (failures / total * 100) if total > 0 else None,
                }
            elif current is None:
                status = "down"
                entry = {
                    "host": host,
                    "current_rtt_ms": None,
                    "status": status,
                    "avg_24h_ms": stats["mean"],
                    "stddev_24h_ms": stats["stddev"],
                    "loss_24h_pct": failures / total * 100,
                }
            else:
                status = classify_status(current, stats["mean"], stats["stddev"])
                entry = {
                    "host": host,
                    "current_rtt_ms": round(current, 2),
                    "status": status,
                    "avg_24h_ms": round(stats["mean"], 2),
                    "stddev_24h_ms": round(stats["stddev"], 2),
                    "loss_24h_pct": round(failures / total * 100, 2),
                }
            results.append(entry)
        return results

    @app.get("/api/history/{host}")
    async def history(host: str, range: str = Query("24h")):
        if host not in config.hosts:
            raise HTTPException(status_code=404, detail=f"Host '{host}' not monitored")
        if range not in VALID_RANGES:
            raise HTTPException(status_code=422, detail=f"Invalid range '{range}'. Must be one of: {', '.join(sorted(VALID_RANGES))}")

        now = time.time()
        since_24h = now - 86400
        pings_24h = await get_pings(db, host, since=since_24h)
        successful_rtts = [p["rtt_ms"] for p in pings_24h if p["success"] and p["rtt_ms"] is not None]
        stats = compute_stats(successful_rtts)
        baseline = {"mean_ms": round(stats["mean"], 2), "stddev_ms": round(stats["stddev"], 2)} if stats else None

        if range in ("1h", "24h"):
            since = now - RANGE_SECONDS[range]
            data = await get_pings(db, host, since=since)
        else:
            days = 7 if range == "7d" else 30
            since_dt = datetime.now(timezone.utc) - timedelta(days=days)
            since_hour = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
            data = await get_rollups(db, host, since_hour=since_hour)

        return {"host": host, "range": range, "baseline": baseline, "data": data}

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pinginator/api.py tests/test_api.py
git commit -m "feat: API routes with host status, history, and health endpoints"
```

---

### Task 7: Entry Point

**Files:**
- Create: `pinginator/__main__.py`

- [ ] **Step 1: Implement __main__.py**

```python
# pinginator/__main__.py
import asyncio
import os

import aiosqlite
import uvicorn

from pinginator.api import create_app
from pinginator.config import load_config
from pinginator.db import init_db
from pinginator.pinger import ping_worker
from pinginator.rollup import rollup_worker


async def main():
    config = load_config()
    db_path = os.path.join(config.data_dir, "pinginator.db")
    os.makedirs(config.data_dir, exist_ok=True)

    db = await aiosqlite.connect(db_path)
    await init_db(db)

    app = create_app(config, db)

    # Start ping workers for each host — store references to prevent GC
    tasks = set()
    for host in config.hosts:
        task = asyncio.create_task(ping_worker(host, config, db))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    # Start rollup worker
    task = asyncio.create_task(rollup_worker(db, config.hosts))
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    # Run uvicorn
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=config.port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify module runs (syntax check)**

Run: `python -c "import pinginator.__main__"` (with PING_HOSTS unset, expect SystemExit)

- [ ] **Step 3: Commit**

```bash
git add pinginator/__main__.py
git commit -m "feat: entry point wiring up all components"
```

---

### Task 8: Frontend Dashboard

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: Create the single-page dashboard**

Create `static/index.html` — a single HTML file containing all CSS and JS inline. Dark theme. Sections:

1. **Header** — "pinginator" branding, host count, auto-refresh indicator
2. **Host cards** — one per host, showing: current RTT (large number), status badge (NORMAL/ELEVATED/HIGH/DOWN/INSUFFICIENT DATA), 24h avg, stddev, loss%, mini sparkline SVG (last 30 min of data points)
3. **Main latency chart** — Chart.js line chart with all hosts, mean line, ±1σ shaded band, time range buttons (1h/24h/7d/30d)
4. **Packet loss chart** — Chart.js line chart below main chart

Key behaviors:
- Fetches `/api/hosts` every 12s to update cards
- Fetches `/api/history/{host}?range=<selected>` every 12s to update charts
- Status badge colors: normal=#4ade80, elevated=#facc15, high=#f87171, down=#f87171, insufficient_data=#888
- Card border color matches status
- Chart.js loaded from `https://cdn.jsdelivr.net/npm/chart.js`
- The ±1σ band is drawn using Chart.js annotation plugin or a custom dataset with fill between
- Responsive grid: cards wrap on narrow screens

Color scheme:
- Background: #0f1117
- Cards: #161b22
- Borders: #2a2f3a
- Text primary: #e0e0e0
- Text secondary: #888

This file will be ~400-500 lines. Implement it as a complete, self-contained HTML document.

- [ ] **Step 2: Verify file serves correctly**

Run a quick test (no real pings needed):
```bash
PING_HOSTS=8.8.8.8 DATA_DIR=/tmp/pinginator-test python -m pinginator &
sleep 2
curl -s http://localhost:8080/ | head -5
curl -s http://localhost:8080/api/health
kill %1
```
Expected: HTML content returned, health returns `{"status":"ok"}`

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: single-page dashboard with Chart.js graphs"
```

---

### Task 9: Docker

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create .dockerignore**

```
.venv
__pycache__
*.pyc
.git
.superpowers
docs
tests
.pytest_cache
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pinginator/ pinginator/
COPY static/ static/
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1
CMD ["python", "-m", "pinginator"]
```

- [ ] **Step 3: Create docker-compose.yml**

```yaml
services:
  pinginator:
    build: .
    ports:
      - "8080:8080"
    environment:
      - PING_HOSTS=8.8.8.8,1.1.1.1
    volumes:
      - pinginator-data:/data
    restart: unless-stopped

volumes:
  pinginator-data:
```

- [ ] **Step 4: Build and test**

Run: `cd /Users/nfox/github/thepinginator && docker compose build`
Expected: Image builds successfully

Run: `docker compose up -d && sleep 5 && curl -s http://localhost:8080/api/health && docker compose down`
Expected: `{"status":"ok"}`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: Docker setup with compose and healthcheck"
```

---

### Task 10: Run Full Test Suite + Final Verification

- [ ] **Step 1: Run all tests**

Run: `cd /Users/nfox/github/thepinginator && source .venv/bin/activate && pytest tests/ -v`
Expected: All tests pass (config: 6, db: 5, pinger: 5, stats: 13, rollup: 5, api: 8 = 42 total)

- [ ] **Step 2: Docker end-to-end test**

```bash
docker compose up -d
sleep 15
curl -s http://localhost:8080/api/hosts | python -m json.tool
curl -s http://localhost:8080/api/health
curl -s http://localhost:8080/ | head -3
docker compose down
```

Expected: Hosts endpoint returns data with real ping results, health is ok, dashboard HTML is served.

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup and verification"
```
