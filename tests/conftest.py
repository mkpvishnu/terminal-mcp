"""Shared pytest fixtures for terminal-mcp tests."""

import pytest
from unittest.mock import MagicMock, patch

from terminal_mcp.config import TerminalConfig, reset_config


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset the global config singleton between tests."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def test_config():
    """A TerminalConfig suitable for testing (small limits, short timeouts)."""
    return TerminalConfig(
        max_sessions=3,
        idle_timeout=5,
        default_rows=24,
        default_cols=80,
        read_settle_timeout=0.2,
        max_output_bytes=10_000,
        cleanup_interval=60,
    )


@pytest.fixture
def mock_pty_session():
    """A MagicMock that mimics a PTYSession."""
    session = MagicMock()
    session.session_id = "test1234"
    session.label = "bash"
    session.command = "/bin/bash"
    session.pid = 12345
    session.is_alive = True
    session.created_at = 1_700_000_000.0
    session.last_activity = 1_700_000_000.0
    session.idle_seconds = 0.0
    session.enable_snapshot = False
    return session
