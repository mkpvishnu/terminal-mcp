"""Tests for tool handler functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_manager():
    """A mock SessionManager."""
    return MagicMock()


@pytest.fixture
def mock_session():
    """A mock PTYSession."""
    session = MagicMock()
    session.session_id = "abcd1234"
    session.label = "bash"
    session.command = "/bin/bash"
    session.pid = 99999
    session.is_alive = True
    session.created_at = time.time()
    session.last_activity = time.time()
    session.idle_seconds = 0.0
    return session


# ---------------------------------------------------------------------------
# session_create
# ---------------------------------------------------------------------------

class TestHandleSessionCreate:
    @pytest.mark.asyncio
    async def test_create_success(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_create
        mock_manager.create.return_value = mock_session

        result = await handle_session_create(mock_manager, {"command": "/bin/bash"})

        assert result["success"] is True
        assert result["session_id"] == "abcd1234"
        assert result["pid"] == 99999
        mock_manager.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_missing_command(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_create
        result = await handle_session_create(mock_manager, {})
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_create_max_sessions_error(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_create
        mock_manager.create.side_effect = RuntimeError("Maximum number of sessions (3) reached")

        result = await handle_session_create(mock_manager, {"command": "/bin/bash"})
        assert result["success"] is False
        assert result["error"]["type"] == "session_limit_reached"

    @pytest.mark.asyncio
    async def test_create_with_options(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_create
        mock_manager.create.return_value = mock_session

        await handle_session_create(
            mock_manager,
            {
                "command": "/bin/bash",
                "label": "my-shell",
                "rows": 40,
                "cols": 120,
                "idle_timeout": 600,
                "enable_snapshot": True,
            },
        )
        call_kwargs = mock_manager.create.call_args[1]
        assert call_kwargs["label"] == "my-shell"
        assert call_kwargs["rows"] == 40
        assert call_kwargs["cols"] == 120
        assert call_kwargs["idle_timeout"] == 600
        assert call_kwargs["enable_snapshot"] is True


# ---------------------------------------------------------------------------
# session_send
# ---------------------------------------------------------------------------

class TestHandleSessionSend:
    @pytest.mark.asyncio
    async def test_send_text(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 5

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "input": "hello"}
        )
        assert result["success"] is True
        assert result["bytes_sent"] == 5
        mock_session.send.assert_called_once_with("hello", press_enter=True)

    @pytest.mark.asyncio
    async def test_send_without_enter(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 3

        result = await handle_session_send(
            mock_manager,
            {"session_id": "abcd1234", "input": "abc", "press_enter": False},
        )
        assert result["success"] is True
        mock_session.send.assert_called_once_with("abc", press_enter=False)

    @pytest.mark.asyncio
    async def test_send_control_char(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send_control.return_value = 1

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "control_char": "c"}
        )
        assert result["success"] is True
        mock_session.send_control.assert_called_once_with("c")

    @pytest.mark.asyncio
    async def test_send_invalid_control_char(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "control_char": "x"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_send_missing_session_id(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_send
        result = await handle_session_send(mock_manager, {"input": "hi"})
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_send_dead_session(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_session.is_alive = False
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "input": "hello"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "session_dead"

    @pytest.mark.asyncio
    async def test_send_not_found(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.side_effect = KeyError("Session not found: bad-id")

        result = await handle_session_send(
            mock_manager, {"session_id": "bad-id", "input": "hello"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "not_found"


# ---------------------------------------------------------------------------
# session_read
# ---------------------------------------------------------------------------

class TestHandleSessionRead:
    @pytest.mark.asyncio
    async def test_read_stream(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_stream.return_value = ("hello output\n", 13, True)

        result = await handle_session_read(
            mock_manager, {"session_id": "abcd1234"}
        )
        assert result["success"] is True
        assert result["output"] == "hello output\n"
        assert result["bytes_read"] == 13
        assert result["prompt_detected"] is True
        assert result["is_alive"] is True

    @pytest.mark.asyncio
    async def test_read_snapshot(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_snapshot.return_value = ("screen content", 14, False)

        result = await handle_session_read(
            mock_manager, {"session_id": "abcd1234", "mode": "snapshot"}
        )
        assert result["success"] is True
        assert result["output"] == "screen content"
        mock_session.read_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_missing_session_id(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_read
        result = await handle_session_read(mock_manager, {})
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_read_not_found(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.side_effect = KeyError("Session not found: bad-id")

        result = await handle_session_read(
            mock_manager, {"session_id": "bad-id"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "not_found"

    @pytest.mark.asyncio
    async def test_read_passes_timeout_and_strip_ansi(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_stream.return_value = ("out", 3, False)

        await handle_session_read(
            mock_manager,
            {"session_id": "abcd1234", "timeout": 5.0, "strip_ansi": False},
        )
        mock_session.read_stream.assert_called_once_with(timeout=5.0, strip_ansi_output=False)


# ---------------------------------------------------------------------------
# session_close
# ---------------------------------------------------------------------------

class TestHandleSessionClose:
    @pytest.mark.asyncio
    async def test_close_success(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_close
        mock_manager.close.return_value = 0

        result = await handle_session_close(mock_manager, {"session_id": "abcd1234"})
        assert result["success"] is True
        assert result["exit_status"] == 0

    @pytest.mark.asyncio
    async def test_close_missing_session_id(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_close
        result = await handle_session_close(mock_manager, {})
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_close_not_found(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_close
        mock_manager.close.side_effect = KeyError("Session not found: bad-id")

        result = await handle_session_close(mock_manager, {"session_id": "bad-id"})
        assert result["success"] is False
        assert result["error"]["type"] == "not_found"


# ---------------------------------------------------------------------------
# session_list
# ---------------------------------------------------------------------------

class TestHandleSessionList:
    @pytest.mark.asyncio
    async def test_list_empty(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_list
        mock_manager.list_sessions.return_value = []

        result = await handle_session_list(mock_manager, {})
        assert result["success"] is True
        assert result["sessions"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_with_sessions(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_list
        mock_manager.list_sessions.return_value = [
            {
                "session_id": "abcd1234",
                "label": "bash",
                "command": "/bin/bash",
                "pid": 99999,
                "is_alive": True,
                "created_at": 1_700_000_000.0,
                "last_activity": 1_700_000_000.0,
                "idle_seconds": 0.0,
            }
        ]

        result = await handle_session_list(mock_manager, {})
        assert result["success"] is True
        assert result["count"] == 1
        assert result["sessions"][0]["session_id"] == "abcd1234"
