"""Offline test workspace. No developer paths, credentials or shared caches.

Bundled JSON remains covered by the inventory assertions; writes go to a copy.
Private Markdown is represented by explicit fixtures in the tests that need it.
"""
import os
from pathlib import Path
import shutil
import socket
import tempfile

import pytest

_workspace = tempfile.TemporaryDirectory(prefix="studentcrm-tests-")
WORKSPACE = Path(_workspace.name)
APP_DIR = Path(__file__).resolve().parents[1]
CRM_DIR = WORKSPACE / "07.Projects/StudentCRM"
shutil.copytree(APP_DIR / "data", CRM_DIR / "data", ignore=shutil.ignore_patterns("backups", "*.bak"))
(WORKSPACE / "OpenClaw/Data").mkdir(parents=True)
for name in ("students.json", "apple_ceo_class.json"):
    shutil.copy2(CRM_DIR / "data" / name, WORKSPACE / "OpenClaw/Data" / name)
os.environ["OPEN_CLAW_BASE_DIR"] = str(WORKSPACE)
os.environ["STUDENTCRM_CACHE_DIR"] = str(WORKSPACE / "cache")
os.environ["STUDENTCRM_DATA_BACKEND"] = "local"
for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ[key] = ""


@pytest.fixture
def test_workspace():
    return WORKSPACE


@pytest.fixture(autouse=True)
def fresh_read_caches(monkeypatch):
    from data_gateway import clear_gateway_memory_cache
    import digital_management_service as digital
    clear_gateway_memory_cache()
    for cache in (digital._CLOUD_NOTES_CACHE, digital._LOCAL_NOTES_CACHE):
        cache.update(timestamp=0.0, notes=[])
    attempted_connections = []

    def reject_network(sock, address):
        attempted_connections.append(address)
        raise AssertionError("Tests must stub the external HTTP boundary")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    yield
    clear_gateway_memory_cache()
    assert not attempted_connections, f"Unexpected network attempts: {attempted_connections}"


def pytest_sessionfinish(session, exitstatus):
    _workspace.cleanup()
