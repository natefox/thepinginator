# tests/test_stats.py
import pytest
from pinginator.stats import compute_stats, classify_status, median_of_last_n


def test_compute_stats_basic():
    rtts = [10.0, 12.0, 14.0, 10.0, 12.0, 14.0]
    result = compute_stats(rtts)
    assert result["mean"] == pytest.approx(12.0)
    assert result["stddev"] == pytest.approx(1.632, abs=0.01)


def test_compute_stats_empty():
    result = compute_stats([])
    assert result is None


def test_classify_normal():
    assert classify_status(current=13.0, mean=12.0, stddev=2.0) == "normal"


def test_classify_elevated():
    assert classify_status(current=15.0, mean=12.0, stddev=2.0) == "elevated"


def test_classify_high():
    assert classify_status(current=17.0, mean=12.0, stddev=2.0) == "high"


def test_classify_below_mean_is_normal():
    assert classify_status(current=5.0, mean=12.0, stddev=2.0) == "normal"


def test_classify_zero_stddev_at_mean():
    assert classify_status(current=12.0, mean=12.0, stddev=0.0) == "normal"


def test_classify_zero_stddev_above_mean():
    assert classify_status(current=12.1, mean=12.0, stddev=0.0) == "elevated"


def test_classify_zero_stddev_below_mean():
    assert classify_status(current=11.0, mean=12.0, stddev=0.0) == "normal"


def test_median_of_last_n_basic():
    pings = [
        {"rtt_ms": 10.0, "success": 1},
        {"rtt_ms": 20.0, "success": 1},
        {"rtt_ms": 15.0, "success": 1},
        {"rtt_ms": 12.0, "success": 1},
        {"rtt_ms": 18.0, "success": 1},
    ]
    assert median_of_last_n(pings, n=5) == pytest.approx(15.0)


def test_median_of_last_n_skips_failures():
    pings = [
        {"rtt_ms": 10.0, "success": 1},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 20.0, "success": 1},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 15.0, "success": 1},
    ]
    assert median_of_last_n(pings, n=5) == pytest.approx(15.0)


def test_median_of_last_n_too_few_successful():
    pings = [
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": None, "success": 0},
        {"rtt_ms": 10.0, "success": 1},
    ]
    assert median_of_last_n(pings, n=5) is None


def test_median_of_last_n_empty():
    assert median_of_last_n([], n=5) is None
