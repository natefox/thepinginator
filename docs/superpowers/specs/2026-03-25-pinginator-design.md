# The Pinginator — Design Spec

A lightweight, Dockerized ping monitoring tool that tracks latency and packet loss to N configurable hosts, stores long-term statistics, and serves a minimal web dashboard with anomaly detection.

## Architecture

Single Docker container running three concurrent concerns:

1. **Ping Worker** — async background tasks, one per host, running system `ping` via subprocess every 10 seconds. Parses RTT and stores results.
2. **Stats Engine** — computes rolling mean and standard deviation over a 24-hour window. Classifies current latency relative to baseline. Runs hourly rollup at the top of each hour, aggregating the *previous* completed hour.
3. **FastAPI Server** — serves the REST API and the single-page HTML dashboard.

All three share a single SQLite database file, mounted as a Docker volume for persistence. SQLite is configured with WAL journal mode and a busy timeout of 5 seconds for safe concurrent access.

All non-successful pings (timeout, DNS failure, network unreachable) are recorded as `success=0, rtt_ms=NULL`. No distinction is made between failure modes.

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12 | User preference, async support |
| Web framework | FastAPI | Lightweight, async-native, auto-generates OpenAPI |
| Database | SQLite via aiosqlite | Zero-config, file-based, async-compatible |
| Frontend | Single HTML file + Chart.js (CDN) | No build step, no Node, ~60KB JS |
| Container | python:3.12-slim | ~50MB base, minimal attack surface |
| Ping method | System `ping` via asyncio subprocess | Reliable ICMP, no raw socket permissions needed |

## Configuration

Environment variables only (simplest approach):

| Variable | Default | Description |
|----------|---------|-------------|
| `PING_HOSTS` | (required) | Comma-separated list of hosts/IPs |
| `PING_INTERVAL` | `10` | Seconds between pings per host |
| `PING_TIMEOUT` | `5` | Seconds before a ping is considered lost (must be < PING_INTERVAL) |
| `DATA_DIR` | `/data` | Directory for SQLite database file |
| `PORT` | `8080` | Web server port |

Startup validation: `PING_TIMEOUT` must be less than `PING_INTERVAL`. Exit with an error if violated.

Example:
```
PING_HOSTS=8.8.8.8,1.1.1.1,192.168.1.1
```

## Data Model

### Table: `pings`

Raw ping results. Retained for 7 days, then purged by the rollup job.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| timestamp | REAL | Unix timestamp |
| host | TEXT | Target host |
| rtt_ms | REAL | Round-trip time in ms (NULL if lost) |
| success | INTEGER | 1 = reply, 0 = timeout/loss |

Index: `(host, timestamp)`

### Table: `rollups`

Hourly aggregates. Retained indefinitely.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| hour | TEXT | ISO 8601 hour (e.g., `2026-03-25T14:00:00`) |
| host | TEXT | Target host |
| avg_ms | REAL | Mean RTT for the hour |
| min_ms | REAL | Minimum RTT |
| max_ms | REAL | Maximum RTT |
| stddev_ms | REAL | Standard deviation of RTT |
| count | INTEGER | Total pings in the hour |
| loss_pct | REAL | Percentage of lost pings |

Unique constraint: `(hour, host)`

RTT aggregates (avg_ms, min_ms, max_ms, stddev_ms) are computed over successful pings only (where rtt_ms is not NULL). The `loss_pct` captures the failure ratio separately.

## Anomaly Detection

Classification uses the trailing 24-hour window of raw ping data:

1. Compute `mean` and `stddev` of successful RTTs over the last 24 hours.
2. Compute the median of the last 5 successful pings (rtt_ms not NULL) as the "current" value (smooths single-ping noise). If fewer than 2 successful pings in the last 5, treat as packet loss.
3. Compare the current value to these baselines:

| Status | Condition | Color |
|--------|-----------|-------|
| Normal | Within mean ± 1σ | Green |
| Elevated | Between mean + 1σ and mean + 2σ | Yellow |
| High | Above mean + 2σ | Red |

**Edge cases:**
- Fewer than 10 data points in 24h window: status = "Insufficient Data" (gray)
- 100% packet loss: status = "Down" (red)
- Host newly added: uses all available data until 24h is reached

## API Endpoints

### `GET /api/hosts`

Returns list of monitored hosts with current status.

```json
[
  {
    "host": "8.8.8.8",
    "current_rtt_ms": 12.3,
    "status": "normal",
    "avg_24h_ms": 14.1,
    "stddev_24h_ms": 3.2,
    "loss_24h_pct": 0.1
  }
]
```

### `GET /api/history/{host}`

Query params: `range` = `1h` | `24h` | `7d` | `30d`

- `1h` and `24h`: returns raw pings (timestamp, rtt_ms, success)
- `7d` and `30d`: returns rollup data from the `rollups` table (hour, avg_ms, min_ms, max_ms, loss_pct). If rollups are not yet available (app just started), returns an empty data array.

**Errors:** Returns 404 for hosts not in `PING_HOSTS`. Returns 422 for invalid `range` values.

```json
{
  "host": "8.8.8.8",
  "range": "24h",
  "baseline": {"mean_ms": 14.1, "stddev_ms": 3.2},
  "data": [
    {"timestamp": 1711360000, "rtt_ms": 12.3, "success": 1},
    ...
  ]
}
```

### `GET /api/health`

Returns `{"status": "ok"}`. Used by Docker healthcheck.

### `GET /`

Serves the single-page HTML dashboard.

## Frontend Design

Single HTML file (`static/index.html`) served by FastAPI's static file support.

### Layout (top to bottom)

1. **Header bar** — app name, auto-refresh indicator, host count, uptime
2. **Host cards row** — one card per host showing: current RTT (large), status badge, 24h avg, stddev, loss%, mini sparkline (last 30 min)
3. **Main latency chart** — Chart.js line chart, all hosts overlaid, with mean line and ±1σ shaded band. Time range selector: 1h, 24h, 7d, 30d
4. **Packet loss chart** — smaller Chart.js line chart below

### Behavior

- Auto-fetches `/api/hosts` and `/api/history/{host}` every 12 seconds (offset from 10s ping interval to avoid aliasing)
- Time range buttons re-fetch history for all hosts
- Dark theme (background #0f1117, cards #161b22)
- Chart.js loaded from CDN (`https://cdn.jsdelivr.net/npm/chart.js`) — browser (not container) needs internet access
- Responsive: cards stack on narrow screens

## Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1
CMD ["python", "-m", "pinginator"]
```

### docker-compose.yml

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

volumes:
  pinginator-data:
```

## Project Structure

```
thepinginator/
├── pinginator/
│   ├── __main__.py       # Entry point: starts FastAPI + ping workers
│   ├── config.py         # Environment variable parsing
│   ├── db.py             # SQLite setup, migrations, queries
│   ├── pinger.py         # Async ping worker (subprocess)
│   ├── stats.py          # Stats computation, anomaly classification
│   ├── api.py            # FastAPI routes
│   └── rollup.py         # Hourly rollup job, data retention cleanup
├── static/
│   └── index.html        # Single-page dashboard
├── Dockerfile
├── docker-compose.yml
├── requirements.txt      # fastapi, uvicorn, aiosqlite
└── README.md
```

## Testing Strategy

- **Unit tests**: stats computation (mean, stddev, classification logic) with known inputs
- **Integration test**: ping parser against real `ping` output samples (Linux and macOS formats)
- **API tests**: FastAPI TestClient against an in-memory SQLite DB
- **Manual**: `docker compose up`, verify dashboard loads and updates

## Dependencies

```
fastapi
uvicorn[standard]
aiosqlite
```

Three dependencies total. No ORM, no migration framework, no frontend build tools.
