import os
import pytest
from pinginator.config import load_config


def test_load_config_parses_hosts(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8,1.1.1.1")
    cfg = load_config()
    assert cfg.hosts == ["8.8.8.8", "1.1.1.1"]


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    cfg = load_config()
    assert cfg.interval == 1
    assert cfg.timeout == 1  # auto-calculated: max(1, interval - 1)
    assert cfg.data_dir == "/data"
    assert cfg.port == 8080
    assert cfg.raw_retention_hours == 24


def test_load_config_custom_values(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    monkeypatch.setenv("PING_INTERVAL", "30")
    monkeypatch.setenv("PING_TIMEOUT", "10")
    monkeypatch.setenv("DATA_DIR", "/tmp/test")
    monkeypatch.setenv("PORT", "9090")
    cfg = load_config()
    assert cfg.interval == 30
    assert cfg.timeout == 10
    assert cfg.data_dir == "/tmp/test"
    assert cfg.port == 9090


def test_load_config_missing_hosts_raises(monkeypatch):
    monkeypatch.delenv("PING_HOSTS", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_timeout_gt_interval_raises(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", "8.8.8.8")
    monkeypatch.setenv("PING_INTERVAL", "5")
    monkeypatch.setenv("PING_TIMEOUT", "6")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_strips_whitespace(monkeypatch):
    monkeypatch.setenv("PING_HOSTS", " 8.8.8.8 , 1.1.1.1 ")
    monkeypatch.setenv("PING_INTERVAL", "10")
    cfg = load_config()
    assert cfg.hosts == ["8.8.8.8", "1.1.1.1"]
