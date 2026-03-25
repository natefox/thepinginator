# tests/test_pinger.py
import pytest
from pinginator.pinger import parse_ping_output


def test_parse_linux_success():
    output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n"
        "rtt min/avg/max/mdev = 12.300/12.300/12.300/0.000 ms\n"
    )
    result = parse_ping_output(output, returncode=0)
    assert result["success"] is True
    assert result["rtt_ms"] == pytest.approx(12.3)


def test_parse_macos_success():
    output = (
        "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n"
        "64 bytes from 8.8.8.8: icmp_seq=0 ttl=118 time=14.567 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "1 packets transmitted, 1 packets received, 0.0% packet loss\n"
        "round-trip min/avg/max/stddev = 14.567/14.567/14.567/0.000 ms\n"
    )
    result = parse_ping_output(output, returncode=0)
    assert result["success"] is True
    assert result["rtt_ms"] == pytest.approx(14.567)


def test_parse_timeout():
    output = (
        "PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.\n"
        "\n"
        "--- 10.0.0.1 ping statistics ---\n"
        "1 packets transmitted, 0 received, 100% packet loss, time 0ms\n"
    )
    result = parse_ping_output(output, returncode=1)
    assert result["success"] is False
    assert result["rtt_ms"] is None


def test_parse_dns_failure():
    output = "ping: unknown host badhost.invalid\n"
    result = parse_ping_output(output, returncode=2)
    assert result["success"] is False
    assert result["rtt_ms"] is None


def test_parse_empty_output():
    result = parse_ping_output("", returncode=1)
    assert result["success"] is False
    assert result["rtt_ms"] is None
