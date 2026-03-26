# pinginator/__main__.py
import asyncio
import os
import signal

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

    shutdown_event = asyncio.Event()
    subscribers: set[asyncio.Queue] = set()
    app = create_app(config, db, subscribers=subscribers, shutdown_event=shutdown_event)

    # Signal SSE connections to close on SIGTERM/SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    # Start ping workers for each host — store references to prevent GC
    tasks = set()
    for host in config.hosts:
        task = asyncio.create_task(
            ping_worker(host, config, db, subscribers=subscribers)
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    # Start rollup worker
    task = asyncio.create_task(
        rollup_worker(db, config.hosts, raw_retention_hours=config.raw_retention_hours)
    )
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    # Run uvicorn with short graceful shutdown timeout
    uv_config = uvicorn.Config(
        app, host="0.0.0.0", port=config.port, log_level="info",
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(uv_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
