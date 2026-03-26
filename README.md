# The Pinginator

A lightweight, Dockerized network monitoring tool that continuously pings configurable hosts, tracks latency and packet loss, and serves a real-time web dashboard with anomaly detection.

![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **1-second ping interval** — see every ping as it happens, like running `ping` in a terminal
- **Real-time live view** — SSE-powered heatmap strips and live charts with zero polling delay
- **Anomaly detection** — statistical baseline (mean +/- standard deviation) with status classification (Normal / Elevated / High / Down)
- **Real-time dashboard** — single-page UI with Chart.js latency and packet loss graphs, auto-refreshing every 12 seconds
- **Data retention** — 7 days of raw ping data, unlimited hourly rollups
- **REST API** — JSON endpoints for host status, history, and health checks
- **Single container** — SQLite storage, no external dependencies

## Quick Start

### Docker Compose (recommended)

```yaml
services:
  pinginator:
    image: ghcr.io/natefox/thepinginator:latest
    ports:
      - "8080:8080"
    environment:
      - PING_HOSTS=8.8.8.8,1.1.1.1,google.com
    volumes:
      - pinginator-data:/data
    restart: unless-stopped

volumes:
  pinginator-data:
```

```bash
docker compose up -d
# Open http://localhost:8080
```

### Docker Run

```bash
docker run -d \
  -p 8080:8080 \
  -e PING_HOSTS=8.8.8.8,1.1.1.1 \
  -v pinginator-data:/data \
  ghcr.io/natefox/thepinginator:latest
```

### From Source

```bash
export PING_HOSTS=8.8.8.8,1.1.1.1
python -m pinginator
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PING_HOSTS` | *(required)* | Comma-separated hosts or IPs to monitor |
| `PING_INTERVAL` | `1` | Seconds between pings per host |
| `PING_TIMEOUT` | `PING_INTERVAL - 1` | Ping timeout in seconds (auto-calculated if not set) |
| `RAW_RETENTION_HOURS` | `24` | Hours to keep raw ping data before purging |
| `DATA_DIR` | `/data` | Directory for the SQLite database |
| `PORT` | `8080` | Web server port |

## Dashboard

The dashboard displays:

- **Live view** with real-time SSE streaming — per-host heatmap strips (color-coded by latency), live-updating line chart, and running statistics. Every ping appears the instant it completes.
- **Host cards** with current RTT, status badge, and 24h statistics
- **Latency chart** with all hosts overlaid and +/-1 standard deviation bands
- **Packet loss chart** over time
- **View selector** — Live, 1h, 24h, 7d, 30d

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web dashboard |
| `GET /api/hosts` | All hosts with current status and 24h stats |
| `GET /api/history/{host}?range=24h` | Ping history (ranges: `1h`, `24h`, `7d`, `30d`) |
| `GET /api/live` | SSE stream of real-time ping results |
| `GET /api/health` | Health check (`{"status": "ok"}`) |

## Architecture

```
┌─────────────────────────────────────┐
│           Docker Container          │
│                                     │
│  ┌───────────┐  ┌───────────────┐   │
│  │ Ping      │  │ FastAPI       │   │
│  │ Workers   │  │ Server (:8080)│   │
│  │ (1/host)  │  │               │   │
│  └─────┬─────┘  └───────┬───────┘   │
│        │                │           │
│        ▼                ▼           │
│  ┌─────────────────────────────┐    │
│  │  SQLite (WAL mode)          │    │
│  │  /data/pinginator.db        │    │
│  └─────────────────────────────┘    │
│        ▲                            │
│  ┌─────┴─────┐                      │
│  │ Rollup    │ (hourly aggregation) │
│  │ Worker    │                      │
│  └───────────┘                      │
└─────────────────────────────────────┘
```

## Status Classification

| Status | Condition |
|--------|-----------|
| **Normal** | Current RTT within 1 standard deviation of 24h mean |
| **Elevated** | 1-2 standard deviations above mean |
| **High** | More than 2 standard deviations above mean |
| **Down** | 100% packet loss |

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Build Docker image
docker compose build
```

## License

MIT
