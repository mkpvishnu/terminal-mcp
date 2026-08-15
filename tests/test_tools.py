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
    session._osc133_supported = False
    session._command_state = "idle"
    session._last_exit_code = None
    session._last_command_finished = False
    session._tui_active = False
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

    @pytest.mark.asyncio
    async def test_create_with_scrollback_lines(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_create
        mock_manager.create.return_value = mock_session

        await handle_session_create(
            mock_manager,
            {"command": "/bin/bash", "enable_snapshot": True, "scrollback_lines": 500},
        )
        call_kwargs = mock_manager.create.call_args[1]
        assert call_kwargs["scrollback_lines"] == 500


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

    @pytest.mark.asyncio
    async def test_send_key_up(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send_key.return_value = 3

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "up"}
        )
        assert result["success"] is True
        assert result["bytes_sent"] == 3
        mock_session.send_key.assert_called_once_with("up")

    @pytest.mark.asyncio
    async def test_send_key_tab(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send_key.return_value = 1

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "tab"}
        )
        assert result["success"] is True
        mock_session.send_key.assert_called_once_with("tab")

    @pytest.mark.asyncio
    async def test_send_key_f12(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send_key.return_value = 4

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "f12"}
        )
        assert result["success"] is True
        mock_session.send_key.assert_called_once_with("f12")

    @pytest.mark.asyncio
    async def test_send_invalid_key(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "nonexistent"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"
        assert "nonexistent" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_send_key_and_input_mutual_exclusivity(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "up", "input": "hello"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"
        assert "Only one of" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_send_key_and_control_char_mutual_exclusivity(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "key": "up", "control_char": "c"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"
        assert "Only one of" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_send_password(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session
        mock_session.send_password.return_value = 9

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "password": "secret"}
        )
        assert result["success"] is True
        assert result["bytes_sent"] == 9
        mock_session.send_password.assert_called_once_with("secret")

    @pytest.mark.asyncio
    async def test_password_and_input_mutual_exclusivity(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "password": "secret", "input": "hello"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"
        assert "Only one of" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_password_and_key_mutual_exclusivity(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "password": "secret", "key": "enter"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_password_and_control_char_mutual_exclusivity(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_send
        mock_manager.get.return_value = mock_session

        result = await handle_session_send(
            mock_manager, {"session_id": "abcd1234", "password": "secret", "control_char": "c"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"


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
            mock_manager, {"session_id": "abcd1234", "mode": "stream"}
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
            {"session_id": "abcd1234", "mode": "stream", "timeout": 5.0, "strip_ansi": False},
        )
        mock_session.read_stream.assert_called_once_with(timeout=5.0, strip_ansi_output=False)

    @pytest.mark.asyncio
    async def test_read_includes_truncated_false(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_stream.return_value = ("short output", 12, False)

        result = await handle_session_read(
            mock_manager, {"session_id": "abcd1234", "mode": "stream"}
        )
        assert result["success"] is True
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_read_truncates_large_output(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        # 200KB of output
        large_output = "x" * 200_000
        mock_session.read_stream.return_value = (large_output, 200_000, False)

        result = await handle_session_read(
            mock_manager, {"session_id": "abcd1234", "mode": "stream"}
        )
        assert result["success"] is True
        assert result["truncated"] is True
        assert "[output truncated]" in result["output"]

    @pytest.mark.asyncio
    async def test_read_with_scrollback(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_scrollback.return_value = ("history line\ncurrent line", 2)

        result = await handle_session_read(
            mock_manager,
            {"session_id": "abcd1234", "mode": "snapshot", "scrollback": 10},
        )
        assert result["success"] is True
        assert result["output"] == "history line\ncurrent line"
        assert result["total_lines"] == 2
        mock_session.read_scrollback.assert_called_once_with(lines_back=10)

    @pytest.mark.asyncio
    async def test_snapshot_strip_ansi_applied(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        ansi_output = "\x1b[32mgreen text\x1b[0m"
        mock_session.read_snapshot.return_value = (ansi_output, len(ansi_output), False)

        result = await handle_session_read(
            mock_manager,
            {"session_id": "abcd1234", "mode": "snapshot", "strip_ansi": True},
        )
        assert result["success"] is True
        assert "\x1b[" not in result["output"]
        assert "green text" in result["output"]

    @pytest.mark.asyncio
    async def test_snapshot_strip_ansi_false_preserves_sequences(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        ansi_output = "\x1b[32mgreen text\x1b[0m"
        mock_session.read_snapshot.return_value = (ansi_output, len(ansi_output), False)

        result = await handle_session_read(
            mock_manager,
            {"session_id": "abcd1234", "mode": "snapshot", "strip_ansi": False},
        )
        assert result["success"] is True
        assert "\x1b[" in result["output"]

    @pytest.mark.asyncio
    async def test_scrollback_strip_ansi_applied(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        ansi_output = "\x1b[31mred line\x1b[0m\nnormal line"
        mock_session.read_scrollback.return_value = (ansi_output, 2)

        result = await handle_session_read(
            mock_manager,
            {"session_id": "abcd1234", "mode": "snapshot", "scrollback": 5, "strip_ansi": True},
        )
        assert result["success"] is True
        assert "\x1b[" not in result["output"]
        assert "red line" in result["output"]


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
        # session_close is now idempotent: closing an already-gone session
        # returns success with already_closed=True (Issue #8 fix).
        from terminal_mcp.tools.session import handle_session_close
        mock_manager.close.side_effect = KeyError("Session not found: bad-id")

        result = await handle_session_close(mock_manager, {"session_id": "bad-id"})
        assert result["success"] is True
        assert result.get("already_closed") is True


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


# ---------------------------------------------------------------------------
# session_resize
# ---------------------------------------------------------------------------

class TestHandleSessionResize:
    @pytest.mark.asyncio
    async def test_resize_success(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_resize
        mock_manager.get.return_value = mock_session

        result = await handle_session_resize(
            mock_manager, {"session_id": "abcd1234", "rows": 40, "cols": 120}
        )
        assert result["success"] is True
        assert result["rows"] == 40
        assert result["cols"] == 120
        mock_session.resize.assert_called_once_with(40, 120)

    @pytest.mark.asyncio
    async def test_resize_dead_session(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_resize
        mock_session.is_alive = False
        mock_manager.get.return_value = mock_session

        result = await handle_session_resize(
            mock_manager, {"session_id": "abcd1234", "rows": 40, "cols": 120}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "session_dead"

    @pytest.mark.asyncio
    async def test_resize_missing_session_id(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_resize
        result = await handle_session_resize(
            mock_manager, {"rows": 40, "cols": 120}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_resize_missing_dimensions(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_resize
        mock_manager.get.return_value = mock_session

        result = await handle_session_resize(
            mock_manager, {"session_id": "abcd1234", "rows": 40}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_resize_not_found(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_resize
        mock_manager.get.side_effect = KeyError("Session not found: bad-id")

        result = await handle_session_resize(
            mock_manager, {"session_id": "bad-id", "rows": 40, "cols": 120}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "not_found"

    @pytest.mark.asyncio
    async def test_resize_invalid_rows(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_resize
        mock_manager.get.return_value = mock_session

        result = await handle_session_resize(
            mock_manager, {"session_id": "abcd1234", "rows": -1, "cols": 80}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"


# ---------------------------------------------------------------------------
# session_exec
# ---------------------------------------------------------------------------

class TestHandleSessionExec:
    @pytest.mark.asyncio
    async def test_exec_success(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.return_value = mock_session
        mock_session.read_stream.side_effect = [
            ("$ ", 2, True),  # startup
            ("hello world\n$ ", 15, True),  # command output
        ]
        mock_session.send.return_value = 11

        result = await handle_session_exec(
            mock_manager, {"exec": "echo hello world"}
        )
        assert result["success"] is True
        assert result["output"] == "hello world\n$ "
        mock_manager.close.assert_called_once_with("abcd1234")

    @pytest.mark.asyncio
    async def test_exec_missing_exec(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_exec
        result = await handle_session_exec(mock_manager, {})
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_exec_with_custom_shell(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.return_value = mock_session
        mock_session.read_stream.side_effect = [
            ("% ", 2, True),
            ("output\n% ", 10, True),
        ]
        mock_session.send.return_value = 5

        result = await handle_session_exec(
            mock_manager, {"exec": "ls -la", "command": "zsh", "timeout": 10.0}
        )
        assert result["success"] is True
        call_kwargs = mock_manager.create.call_args[1]
        assert call_kwargs["command"] == "zsh"

    @pytest.mark.asyncio
    async def test_exec_session_limit_error(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.side_effect = RuntimeError("Maximum number of sessions (3) reached")

        result = await handle_session_exec(
            mock_manager, {"exec": "echo hi"}
        )
        assert result["success"] is False
        assert result["error"]["type"] == "session_limit_reached"

    @pytest.mark.asyncio
    async def test_exec_always_cleans_up(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.return_value = mock_session
        mock_session.read_stream.side_effect = [
            ("$ ", 2, True),  # startup
            Exception("read failed"),  # command output fails
        ]
        mock_session.send.return_value = 5

        result = await handle_session_exec(
            mock_manager, {"exec": "bad-command"}
        )
        assert result["success"] is False
        # Session should still be cleaned up
        mock_manager.close.assert_called_once_with("abcd1234")

    @pytest.mark.asyncio
    async def test_exec_truncates_large_output(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.return_value = mock_session
        large_output = "y" * 200_000
        mock_session.read_stream.side_effect = [
            ("$ ", 2, True),
            (large_output, 200_000, False),
        ]
        mock_session.send.return_value = 10

        result = await handle_session_exec(
            mock_manager, {"exec": "find /"}
        )
        assert result["success"] is True
        assert result["truncated"] is True
        assert "[output truncated]" in result["output"]

    @pytest.mark.asyncio
    async def test_exec_blocks_dangerous_command(self, mock_manager):
        from terminal_mcp.tools.session import handle_session_exec
        result = await handle_session_exec(
            mock_manager, {"exec": "rm -rf /important"}
        )
        assert result["success"] is False
        assert result["requires_confirmation"] is True
        assert result["command"] == "rm -rf /important"
        mock_manager.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_exec_allows_dangerous_command_when_confirmed(self, mock_manager, mock_session):
        from terminal_mcp.tools.session import handle_session_exec
        mock_manager.create.return_value = mock_session
        mock_session.read_stream.side_effect = [
            ("$ ", 2, True),
            ("removed\n$ ", 11, True),
        ]
        mock_session.send.return_value = 15

        result = await handle_session_exec(
            mock_manager, {"exec": "rm -rf /important", "confirmed": True}
        )
        assert result["success"] is True
        mock_manager.create.assert_called_once()
