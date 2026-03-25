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
