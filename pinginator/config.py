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
    raw_retention_hours: int


def load_config() -> Config:
    hosts_raw = os.environ.get("PING_HOSTS", "")
    if not hosts_raw.strip():
        print("ERROR: PING_HOSTS environment variable is required", file=sys.stderr)
        sys.exit(1)

    hosts = [h.strip() for h in hosts_raw.split(",") if h.strip()]
    interval = int(os.environ.get("PING_INTERVAL", "1"))
    timeout_raw = os.environ.get("PING_TIMEOUT")
    timeout = int(timeout_raw) if timeout_raw else max(1, interval - 1)
    raw_retention_hours = int(os.environ.get("RAW_RETENTION_HOURS", "24"))
    data_dir = os.environ.get("DATA_DIR", "/data")
    port = int(os.environ.get("PORT", "8080"))

    if timeout > interval:
        print(
            f"ERROR: PING_TIMEOUT ({timeout}) must not exceed PING_INTERVAL ({interval})",
            file=sys.stderr,
        )
        sys.exit(1)

    return Config(
        hosts=hosts,
        interval=interval,
        timeout=timeout,
        data_dir=data_dir,
        port=port,
        raw_retention_hours=raw_retention_hours,
    )
