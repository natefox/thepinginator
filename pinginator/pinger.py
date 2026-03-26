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


async def ping_worker(
    host: str, config: Config, db: aiosqlite.Connection,
    subscribers: set[asyncio.Queue] | None = None,
) -> None:
    while True:
        result = await ping_once(host, config.timeout)
        ts = time.time()
        await insert_ping(
            db,
            timestamp=ts,
            host=host,
            rtt_ms=result["rtt_ms"],
            success=1 if result["success"] else 0,
        )
        if subscribers is not None:
            event = {
                "host": host,
                "timestamp": ts,
                "rtt_ms": result["rtt_ms"],
                "success": result["success"],
            }
            for queue in list(subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        await asyncio.sleep(config.interval)
