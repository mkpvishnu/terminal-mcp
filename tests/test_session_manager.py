"""Tests for SessionManager."""

import sys
import threading
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


class TestSessionManagerLockDuringSpawn:
    """Issue #22: create() must not hold the lock during PTYSession construction."""

    def test_lock_not_held_during_pty_construction(self):
        """Other operations must not be blocked while a session is spawning."""
        config = TerminalConfig(
            max_sessions=5,
            idle_timeout=60,
            default_rows=24,
            default_cols=80,
            read_settle_timeout=0.2,
            max_output_bytes=10_000,
            cleanup_interval=9999,
        )
        mgr = SessionManager(config)

        spawn_started = threading.Event()
        lock_acquired = threading.Event()

        original_init = None

        def slow_pty_init(self_pty, *args, **kwargs):
            spawn_started.set()
            lock_acquired.wait(timeout=5)
            original_init(self_pty, *args, **kwargs)

        try:
            from terminal_mcp.pty_session import PTYSession
            original_init = PTYSession.__init__

            with patch.object(PTYSession, '__init__', slow_pty_init):
                create_thread = threading.Thread(
                    target=lambda: mgr.create(command="/bin/echo hi"),
                )
                create_thread.start()

                spawn_started.wait(timeout=5)
                assert spawn_started.is_set(), "PTYSession init never started"

                acquired = mgr._lock.acquire(timeout=2)
                if acquired:
                    lock_acquired.set()
                    mgr._lock.release()
                else:
                    lock_acquired.set()
                    create_thread.join(timeout=5)
                    pytest.fail("Lock was held during PTYSession construction")

                create_thread.join(timeout=10)
        finally:
            mgr.close_all()

    def test_max_sessions_race_cleans_up(self):
        """If max_sessions is hit between pre-check and registration, the
        spawned session is closed and RuntimeError is raised."""
        config = TerminalConfig(
            max_sessions=1,
            idle_timeout=60,
            default_rows=24,
            default_cols=80,
            read_settle_timeout=0.2,
            max_output_bytes=10_000,
            cleanup_interval=9999,
        )
        mgr = SessionManager(config)

        mock_session = MagicMock()
        mock_session.session_id = "race-sess"

        def pty_side_effect(*args, **kwargs):
            mgr._sessions["snuck-in"] = MagicMock()
            return mock_session

        with patch("terminal_mcp.session_manager.PTYSession", side_effect=pty_side_effect):
            with pytest.raises(RuntimeError, match="Maximum number of sessions"):
                mgr.create(command="/bin/echo hi")

            mock_session.close.assert_called_once()
            assert "race-sess" not in mgr._sessions

        mgr._sessions.clear()
