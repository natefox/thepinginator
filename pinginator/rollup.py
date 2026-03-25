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
        prev_hour = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        hour_str = prev_hour.strftime("%Y-%m-%dT%H:%M:%S")
        await run_rollup(db, hosts, hour_str)

        cutoff = time.time() - (7 * 24 * 3600)
        await purge_old_pings(db, before=cutoff)

        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sleep_seconds = (next_hour - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
