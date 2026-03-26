# pinginator/api.py
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pinginator.config import Config
from pinginator.db import get_pings, get_rollups
from pinginator.stats import compute_stats, classify_status, median_of_last_n

VALID_RANGES = {"1h", "24h", "7d", "30d"}
RANGE_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
STATIC_DIR = Path(__file__).parent.parent / "static"
MAX_CHART_POINTS = 2000


def _downsample(data: list[dict], target: int) -> list[dict]:
    if len(data) <= target:
        return data
    step = len(data) / target
    result = []
    for i in range(target):
        idx = int(i * step)
        result.append(data[idx])
    if data[-1] not in result:
        result.append(data[-1])
    return result


def create_app(
    config: Config, db: aiosqlite.Connection,
    subscribers: set[asyncio.Queue] | None = None,
) -> FastAPI:
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
            data = _downsample(data, MAX_CHART_POINTS)
        else:
            days = 7 if range == "7d" else 30
            since_dt = datetime.now(timezone.utc) - timedelta(days=days)
            since_hour = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
            data = await get_rollups(db, host, since_hour=since_hour)

        return {"host": host, "range": range, "baseline": baseline, "data": data}

    @app.get("/api/recent")
    async def recent():
        """Return last 3 minutes of raw pings for all hosts, for live view backfill."""
        now = time.time()
        since = now - 180
        results = {}
        for host in config.hosts:
            pings = await get_pings(db, host, since=since)
            results[host] = [
                {
                    "host": host,
                    "timestamp": p["timestamp"],
                    "rtt_ms": p["rtt_ms"],
                    "success": bool(p["success"]),
                }
                for p in pings
            ]
        return results

    @app.get("/api/live")
    async def live():
        if subscribers is None:
            raise HTTPException(status_code=503, detail="Live streaming not available")

        queue = asyncio.Queue(maxsize=256)
        subscribers.add(queue)

        async def event_stream():
            try:
                while True:
                    data = await queue.get()
                    yield f"data: {json.dumps(data)}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                subscribers.discard(queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
