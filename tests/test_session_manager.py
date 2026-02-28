"""Tests for SessionManager."""

import sys
import time
import pytest
from unittest.mock import patch, MagicMock

from terminal_mcp.session_manager import SessionManager
from terminal_mcp.config import TerminalConfig


@pytest.fixture
def config():
    return TerminalConfig(
        max_sessions=3,
        idle_timeout=5,
        default_rows=24,
        default_cols=80,
        read_settle_timeout=0.2,
        max_output_bytes=10_000,
        cleanup_interval=9999,  # disable auto-cleanup during tests
    )


@pytest.fixture
def manager(config):
    mgr = SessionManager(config)
    yield mgr
    mgr.close_all()


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestSessionManagerCreate:
    def test_create_session(self, manager):
        session = manager.create(command="/bin/echo hi")
        assert session.session_id is not None
        assert session.command == "/bin/echo hi"
        time.sleep(0.3)
        manager.close(session.session_id)

    def test_create_with_label(self, manager):
        session = manager.create(command="/bin/echo hi", label="my-test")
        assert session.label == "my-test"
        manager.close(session.session_id)

    def test_max_sessions_enforced(self, manager):
        """Creating more sessions than max_sessions raises RuntimeError."""
        sessions = []
        for _ in range(3):
            s = manager.create(command="/bin/echo hi")
            sessions.append(s)
        with pytest.raises(RuntimeError, match="Maximum number of sessions"):
            manager.create(command="/bin/echo overflow")
        # cleanup
        for s in sessions:
            try:
                manager.close(s.session_id)
            except Exception:
                pass

    def test_get_existing_session(self, manager):
        session = manager.create(command="/bin/echo hi")
        fetched = manager.get(session.session_id)
        assert fetched.session_id == session.session_id
        manager.close(session.session_id)

    def test_get_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="Session not found"):
            manager.get("nonexistent")

    def test_close_removes_session(self, manager):
        session = manager.create(command="/bin/echo hi")
        manager.close(session.session_id)
        with pytest.raises(KeyError):
            manager.get(session.session_id)

    def test_close_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="Session not found"):
            manager.close("nonexistent")

    def test_list_sessions_empty(self, manager):
        result = manager.list_sessions()
        assert isinstance(result, list)

    def test_list_sessions_with_entries(self, manager):
        session = manager.create(command="/bin/echo hi", label="test-session")
        result = manager.list_sessions()
        assert len(result) == 1
        entry = result[0]
        assert entry["session_id"] == session.session_id
        assert entry["label"] == "test-session"
        assert "pid" in entry
        assert "is_alive" in entry
        assert "created_at" in entry
        assert "last_activity" in entry
        assert "idle_seconds" in entry
        manager.close(session.session_id)

    def test_close_all(self, manager):
        manager.create(command="/bin/echo a")
        manager.create(command="/bin/echo b")
        assert len(manager.list_sessions()) == 2
        manager.close_all()
        assert len(manager.list_sessions()) == 0
