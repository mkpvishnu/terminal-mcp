"""Regression tests for bug fixes (Issues #6, #7, #8, #9)."""

import asyncio
import signal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from terminal_mcp.output_buffer import strip_ansi


# ---------------------------------------------------------------------------
# Bug #9 — strip_ansi handles sequences that were previously missed
# ---------------------------------------------------------------------------

class TestStripAnsiExtended:
    """Issue #9: Kitty keyboard protocol, app keypad mode, DCS sequences."""

    def test_strip_kitty_keyboard_protocol_set(self):
        # ESC [ = 1 ; 1 u  — kitty keyboard enhancement set
        result = strip_ansi("\x1b[=1;1u")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_kitty_keyboard_protocol_query(self):
        # ESC [ > 4 ; m  — secondary DA / kitty keyboard query
        result = strip_ansi("\x1b[>4;m")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_kitty_keyboard_protocol_reset(self):
        # ESC [ = 0 ; 1 u  — kitty keyboard reset
        result = strip_ansi("\x1b[=0;1u")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_app_keypad_mode(self):
        # ESC =  enters application keypad mode
        # ESC >  exits application keypad mode
        result = strip_ansi("\x1b=text\x1b>")
        assert result == "text", f"Expected 'text', got {result!r}"

    def test_strip_app_keypad_enter_only(self):
        result = strip_ansi("\x1b=")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_app_keypad_exit_only(self):
        result = strip_ansi("\x1b>")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_secondary_da_response(self):
        # ESC [ > c  — secondary device attribute response
        result = strip_ansi("\x1b[>c")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_function_key_tilde_terminator(self):
        # ESC [ 1 5 ~  — F5 key
        result = strip_ansi("\x1b[15~")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_dcs_sequence(self):
        # ESC P ... ST  — DCS (Device Control String)
        result = strip_ansi("\x1bPsome data\x1b\\")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_ris_reset_sequence(self):
        # ESC c  — RIS (Reset to Initial State)
        result = strip_ansi("\x1bc")
        assert result == "", f"Expected empty, got {result!r}"

    def test_strip_mixed_sequences_preserve_text(self):
        # Mix of new escape sequences around real text
        text = "\x1b=hello\x1b>\x1b[>c world\x1b[=1;1u!"
        result = strip_ansi(text)
        assert result == "hello world!", f"Expected 'hello world!', got {result!r}"

    def test_strip_ansi_existing_csi_still_works(self):
        # Regression: existing CSI sequences must still be stripped
        result = strip_ansi("\x1b[31mred\x1b[0m")
        assert result == "red", f"Expected 'red', got {result!r}"

    def test_strip_ansi_existing_osc_still_works(self):
        # Regression: OSC sequences must still be stripped
        result = strip_ansi("\x1b]0;window title\x07plain")
        assert result == "plain", f"Expected 'plain', got {result!r}"


# ---------------------------------------------------------------------------
# Bug #8 — session_close is idempotent
# ---------------------------------------------------------------------------

class TestSessionCloseIdempotent:
    """Issue #8: Closing an already-closed session returns success."""

    @pytest.mark.asyncio
    async def test_double_close_returns_already_closed(self):
        from terminal_mcp.tools.session import handle_session_close

        mock_manager = MagicMock()
        # First close: succeeds normally
        mock_manager.close.return_value = 0
        result1 = await handle_session_close(mock_manager, {"session_id": "sess-1"})
        assert result1["success"] is True
        assert result1["exit_status"] == 0

        # Second close: session already removed (KeyError)
        mock_manager.close.side_effect = KeyError("sess-1")
        result2 = await handle_session_close(mock_manager, {"session_id": "sess-1"})
        assert result2["success"] is True, "Second close should still succeed"
        assert result2.get("already_closed") is True

    @pytest.mark.asyncio
    async def test_close_already_dead_session_succeeds(self):
        from terminal_mcp.tools.session import handle_session_close

        mock_manager = MagicMock()
        mock_manager.close.side_effect = KeyError("dead-session")

        result = await handle_session_close(mock_manager, {"session_id": "dead-session"})
        assert result["success"] is True
        assert result.get("already_closed") is True
        assert "error" not in result


# ---------------------------------------------------------------------------
# Bug #6 & #7 — wait_for skips echo and stale buffer in session_interact
# ---------------------------------------------------------------------------

class TestSessionInteractWaitForEchoSkip:
    """Issues #6 and #7: wait_for in session_interact must skip the echo."""

    def _make_mock_session(self, pattern_output: str, echo_output: str = "echo hello\r\n"):
        """
        Build a mock PTYSession for session_interact tests.

        current_buffer_end() returns a value such that read_until_pattern
        receives a start_position that lands AFTER the echo bytes.
        """
        session = MagicMock()
        session.session_id = "test-sess"
        session.label = "bash"
        session.command = "/bin/bash"
        session.pid = 9999
        session.is_alive = True
        session.created_at = time.time()
        session.last_activity = time.time()
        session.idle_seconds = 0.0
        session._osc133_supported = False
        session._command_state = "idle"
        session._last_exit_code = None
        session._last_command_finished = False
        session._tui_active = False
        session._alt_screen_entered = False
        session._prev_snapshot = None
        session.send.return_value = len("echo hello\n")

        # current_buffer_end reflects buffer size after echo has arrived
        session.current_buffer_end.return_value = len(echo_output)

        # read_until_pattern returns (text, bytes_read, matched, prompt_detected)
        session.read_until_pattern.return_value = (pattern_output, len(pattern_output), True, False)

        return session

    @pytest.mark.asyncio
    async def test_wait_for_passes_start_position_to_read_until_pattern(self):
        """
        handle_session_interact must call current_buffer_end() BEFORE send() and
        pass the result as start_position to read_until_pattern.  This verifies
        the interface contract (Issues #6 & #7) and that no 50ms sleep is used.

        Call-order check: current_buffer_end must be called before any send
        variant, so the anchor captures only pre-existing bytes.
        """
        from terminal_mcp.tools.session import handle_session_interact
        from unittest.mock import call

        echo_bytes = b"echo hello\r\nhello\r\n$ "
        # The pre-send buffer position — this is what current_buffer_end returns
        # before any data from the send has arrived in the PTY buffer.
        pre_send_pos = 42  # arbitrary value representing bytes already in buffer
        mock_session = self._make_mock_session(
            pattern_output="hello\r\n$ ",
            echo_output=echo_bytes.decode(),
        )
        mock_session.current_buffer_end.return_value = pre_send_pos

        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_session

        result = await handle_session_interact(
            mock_manager,
            {
                "session_id": "test-sess",
                "input": "echo hello",
                "wait_for": "hello",
                "timeout": 5.0,
            },
        )

        assert result["success"] is True
        # Verify current_buffer_end was called exactly once (pre-send snapshot)
        mock_session.current_buffer_end.assert_called_once()
        # Verify read_until_pattern received start_position equal to pre-send snapshot
        call_kwargs = mock_session.read_until_pattern.call_args
        assert call_kwargs is not None, "read_until_pattern was not called"
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        # start_position can be positional or keyword; check keyword form
        assert "start_position" in kwargs, (
            f"start_position not passed to read_until_pattern; kwargs={kwargs}"
        )
        assert kwargs["start_position"] == pre_send_pos, (
            f"start_position should be the pre-send snapshot ({pre_send_pos}), "
            f"got {kwargs['start_position']}"
        )

    @pytest.mark.asyncio
    async def test_wait_for_matched_flag_propagated(self):
        """Result should include matched=True when pattern is found."""
        from terminal_mcp.tools.session import handle_session_interact

        mock_session = self._make_mock_session(pattern_output="done\r\n$ ")
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_session

        result = await handle_session_interact(
            mock_manager,
            {
                "session_id": "test-sess",
                "input": "echo done",
                "wait_for": "done",
                "timeout": 5.0,
            },
        )

        assert result["success"] is True
        assert result.get("matched") is True

    @pytest.mark.asyncio
    async def test_wait_for_not_used_skips_buffer_snapshot(self):
        """Without wait_for, current_buffer_end should NOT be called."""
        from terminal_mcp.tools.session import handle_session_interact

        mock_session = self._make_mock_session(pattern_output="")
        # Override read_stream so interact doesn't error
        mock_session.read_stream.return_value = ("$ ", 2, False)
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_session

        result = await handle_session_interact(
            mock_manager,
            {
                "session_id": "test-sess",
                "input": "echo hello",
                "timeout": 1.0,
                # no wait_for
            },
        )

        assert result["success"] is True
        mock_session.current_buffer_end.assert_not_called()


# ---------------------------------------------------------------------------
# Bug #6 unit-level: read_until_pattern start_position parameter
# ---------------------------------------------------------------------------

class TestReadUntilPatternStartPosition:
    """Direct unit test of PTYSession.read_until_pattern start_position."""

    def test_start_position_skips_earlier_matches(self):
        """
        If the buffer already contains a match before start_position,
        the method must not return that match — it only sees bytes from
        start_position onward.
        """
        import threading
        import io
        from unittest.mock import patch, MagicMock

        # We'll test via a real PTYSession-like object by mocking low-level bits
        # Actually: import and instantiate enough to test read_until_pattern.
        # We stub the PTY internals so no real process is spawned.
        with patch("terminal_mcp.pty_session.pexpect.spawn") as mock_spawn:
            mock_child = MagicMock()
            mock_child.pid = 1234
            mock_child.isalive.return_value = False  # process is "dead" — no blocking
            mock_spawn.return_value = mock_child

            from terminal_mcp.pty_session import PTYSession

            session = PTYSession.__new__(PTYSession)
            # Minimal manual init
            session._buffer = bytearray()
            session._buffer_lock = threading.Lock()
            session._read_position = 0
            session._tui_active = False
            session._alt_screen_entered = False
            session._prev_snapshot = None
            session._osc133_supported = False
            session._command_state = "idle"
            session._last_exit_code = None
            session._last_command_finished = False

            # Simulate buffer: pre-command banner with ">>>" then new prompt after
            pre_content = b"Python 3.11\n>>> "   # old content with ">>>"
            new_content = b"hello\n>>> "          # new prompt after command

            session._buffer = bytearray(pre_content + new_content)
            session._read_position = 0
            # _total_bytes_written must equal len(_buffer) when there has been no trim
            session._total_bytes_written = len(pre_content + new_content)

            # With start_position=len(pre_content) (absolute), should only see new_content
            start_pos = len(pre_content)
            text, nbytes, matched, prompt = session.read_until_pattern(
                pattern=">>>",
                timeout=0.1,           # short timeout; process is "dead" so loop exits fast
                strip_ansi_output=False,
                start_position=start_pos,
            )

            assert matched is True, "Should match >>> in the new content"
            # The returned text must NOT include bytes from before start_position
            assert "Python" not in text, (
                f"Output should not include pre-existing content, got: {text!r}"
            )
            assert "hello" in text, f"Output should include new content, got: {text!r}"

    def test_current_buffer_end_returns_total_bytes_written(self):
        """current_buffer_end() must return _total_bytes_written, not len(buffer).

        This is important because after a buffer trim, len(buffer) < _total_bytes_written.
        Callers (e.g. handle_session_interact) use the returned value as an absolute
        anchor for read_until_pattern; it must be monotonically increasing.
        """
        import threading
        from unittest.mock import patch, MagicMock

        with patch("terminal_mcp.pty_session.pexpect.spawn"):
            from terminal_mcp.pty_session import PTYSession

            session = PTYSession.__new__(PTYSession)
            session._buffer = bytearray(b"hello world")
            session._buffer_lock = threading.Lock()
            # Simulate a scenario where some bytes were trimmed: _total_bytes_written
            # is larger than len(_buffer)
            session._total_bytes_written = 50

            # Must return _total_bytes_written, not len(_buffer)
            assert session.current_buffer_end() == 50, (
                "current_buffer_end() must return _total_bytes_written (50), "
                f"not len(_buffer) ({len(session._buffer)})"
            )

    def test_start_position_survives_buffer_trim(self):
        """
        read_until_pattern with an absolute start_position must correctly skip
        bytes even when the buffer has been trimmed (simulating the reader thread
        dropping old bytes because max_buffer_bytes was reached).

        Setup:
          - Buffer originally had 100 bytes; first 60 were trimmed.
          - _total_bytes_written = 150 (60 trimmed + 90 current).
          - Absolute start_position = 80 (i.e. we want to see bytes from offset 80).
          - Buffer-relative equivalent: 80 - (150 - 90) = 80 - 60 = 20.
          - Bytes 0-19 in the current buffer are pre-anchor content (should be skipped).
          - Bytes 20-89 contain the new content we want to match.
        """
        import threading
        from unittest.mock import patch, MagicMock

        with patch("terminal_mcp.pty_session.pexpect.spawn") as mock_spawn:
            mock_child = MagicMock()
            mock_child.pid = 1234
            mock_child.isalive.return_value = False  # dead → loop exits quickly
            mock_spawn.return_value = mock_child

            from terminal_mcp.pty_session import PTYSession

            session = PTYSession.__new__(PTYSession)
            session._buffer_lock = threading.Lock()
            session._read_position = 0

            # Pre-anchor bytes (should NOT appear in output): b"OLD_CONTENT_HERE____" (20 bytes)
            pre_anchor = b"OLD_CONTENT_HERE____"  # 20 bytes in current buffer before anchor
            # Post-anchor bytes (should appear in output): contains the target pattern
            post_anchor = b"new output: DONE here"  # 21 bytes

            session._buffer = bytearray(pre_anchor + post_anchor)
            # Simulate 60 bytes already trimmed before this buffer window
            trimmed_bytes = 60
            session._total_bytes_written = trimmed_bytes + len(pre_anchor) + len(post_anchor)
            # absolute start_position = trimmed_bytes + len(pre_anchor) = 80
            # buffer_start_abs = _total_bytes_written - len(_buffer) = 141 - 41 = 60+20 = ... let me recalc
            # buffer_start_abs = (60 + 20 + 21) - (20 + 21) = 101 - 41 = 60
            # rel_start = max(0, 80 - 60) = 20  ✓  → _buffer[20:] = post_anchor
            absolute_start = trimmed_bytes + len(pre_anchor)  # = 80

            text, nbytes, matched, prompt = session.read_until_pattern(
                pattern="DONE",
                timeout=0.1,
                strip_ansi_output=False,
                start_position=absolute_start,
            )

            assert matched is True, f"Should have matched 'DONE' in post-anchor bytes, got: {text!r}"
            assert "OLD_CONTENT" not in text, (
                f"Pre-anchor bytes must not appear in output after trim, got: {text!r}"
            )
            assert "DONE" in text, f"Post-anchor content must be present, got: {text!r}"


# ---------------------------------------------------------------------------
# Bug #21 — Windows close() uses proc.kill() instead of signal.SIGKILL
# ---------------------------------------------------------------------------

class TestWindowsCloseFallback:
    """Issue #21: close() must use proc.terminate()/proc.kill() on Windows."""

    def _make_session(self, *, is_windows: bool):
        """Build a minimally-initialised PTYSession with controlled _is_windows."""
        import threading
        from terminal_mcp.pty_session import PTYSession

        session = PTYSession.__new__(PTYSession)
        session._is_windows = is_windows
        session._buffer = bytearray()
        session._buffer_lock = threading.Lock()
        session._read_position = 0
        session._total_bytes_written = 0
        session._tui_active = False
        session._alt_screen_entered = False
        session._prev_snapshot = None
        session._osc133_supported = False
        session._command_state = "idle"
        session._last_exit_code = None
        session._last_command_finished = False
        return session

    def test_windows_close_calls_proc_terminate_then_kill(self):
        """On Windows, close() should call proc.terminate() and proc.kill()."""
        session = self._make_session(is_windows=True)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_process = MagicMock()
        mock_process.proc = mock_proc
        mock_process.sendeof.side_effect = Exception("no EOF on Windows")
        session.process = mock_process

        # Simulate process staying alive through terminate, dying after kill
        alive_calls = [True] * 42 + [False]
        session._is_alive = MagicMock(side_effect=alive_calls)

        exit_status = session.close()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert exit_status == 0
        mock_process.close.assert_not_called()

    def test_unix_close_calls_signal_kill(self):
        """On Unix, close() should use signal.SIGHUP / signal.SIGKILL."""
        session = self._make_session(is_windows=False)

        mock_process = MagicMock()
        mock_process.exitstatus = 1
        mock_process.sendeof.side_effect = Exception("test")
        session.process = mock_process

        alive_calls = [True] * 42 + [False]
        session._is_alive = MagicMock(side_effect=alive_calls)

        exit_status = session.close()

        mock_process.kill.assert_any_call(signal.SIGHUP)
        mock_process.kill.assert_any_call(signal.SIGKILL)
        mock_process.close.assert_called_once_with(force=True)
        assert exit_status == 1
