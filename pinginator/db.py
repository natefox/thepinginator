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
