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
