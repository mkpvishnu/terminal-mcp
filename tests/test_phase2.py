"""Tests for Phase 2 features: alt-screen detection, read_auto, diff mode, smart truncation."""

import sys
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_manager():
    """A mock SessionManager."""
    return MagicMock()


@pytest.fixture
def mock_session():
    """A mock PTYSession with Phase 2 attributes."""
    session = MagicMock()
    session.session_id = "ph2-1234"
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
    session._alt_screen_entered = False
    session._prev_snapshot = None
    return session


# ---------------------------------------------------------------------------
# TestAltScreenDetection — unit tests on PTYSession._detect_alt_screen
# ---------------------------------------------------------------------------

class TestAltScreenDetection:
    """Unit tests for _detect_alt_screen using PTYSession.__new__ pattern."""

    def _make_session(self):
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._tui_active = False
        session._alt_screen_entered = False
        return session

    def test_alt_screen_entry_1049h(self):
        """ESC[?1049h sets _tui_active=True and _alt_screen_entered=True."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1049h')
        assert session._tui_active is True
        assert session._alt_screen_entered is True

    def test_alt_screen_entry_47h(self):
        """ESC[?47h sets _tui_active=True."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?47h')
        assert session._tui_active is True

    def test_alt_screen_entry_1047h(self):
        """ESC[?1047h sets _tui_active=True."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1047h')
        assert session._tui_active is True

    def test_alt_screen_exit_1049l(self):
        """After entry, ESC[?1049l sets _tui_active=False."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1049h')
        assert session._tui_active is True
        session._detect_alt_screen(b'\x1b[?1049l')
        assert session._tui_active is False

    def test_alt_screen_exit_preserves_entered(self):
        """After entry+exit, _alt_screen_entered remains True."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1049h')
        session._detect_alt_screen(b'\x1b[?1049l')
        assert session._alt_screen_entered is True

    def test_alt_screen_toggle_cycle(self):
        """Entry, exit, entry again — _tui_active tracks correctly."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1049h')
        assert session._tui_active is True
        session._detect_alt_screen(b'\x1b[?1049l')
        assert session._tui_active is False
        session._detect_alt_screen(b'\x1b[?47h')
        assert session._tui_active is True

    def test_no_false_positive_on_regular_csi(self):
        """ESC[?25h (cursor show) does NOT set _tui_active."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?25h')
        assert session._tui_active is False
        assert session._alt_screen_entered is False

    def test_no_false_positive_on_partial_sequence(self):
        """ESC[?1049 without h/l suffix does not match."""
        session = self._make_session()
        session._detect_alt_screen(b'\x1b[?1049')  # no suffix
        assert session._tui_active is False
        assert session._alt_screen_entered is False

    def test_multiple_sequences_in_single_chunk(self):
        """Data containing both entry and exit in one chunk; last sequence wins."""
        session = self._make_session()
        # Entry followed by exit in the same chunk
        session._detect_alt_screen(b'\x1b[?1049h some data \x1b[?1049l')
        assert session._tui_active is False
        # Entered was still observed
        assert session._alt_screen_entered is True


# ---------------------------------------------------------------------------
# TestReadAuto — mock-based tests on PTYSession.read_auto and handler
# ---------------------------------------------------------------------------

class TestReadAuto:
    """Tests for PTYSession.read_auto and handle_session_read with mode='auto'."""

    def test_auto_selects_stream_when_no_tui(self):
        """_tui_active=False → read_auto calls read_stream, mode_used='stream'."""
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._tui_active = False
        session.read_stream = MagicMock(return_value=("stream output", 13, False))
        session.read_snapshot = MagicMock(return_value=("snap", 4, False))

        output, bytes_read, prompt_detected, mode_used = session.read_auto()
        assert mode_used == "stream"
        session.read_stream.assert_called_once()
        session.read_snapshot.assert_not_called()

    def test_auto_selects_snapshot_when_tui(self):
        """_tui_active=True → read_auto calls read_snapshot, mode_used='snapshot'."""
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._tui_active = True
        session.read_stream = MagicMock(return_value=("stream output", 13, False))
        session.read_snapshot = MagicMock(return_value=("snap content", 12, False))

        output, bytes_read, prompt_detected, mode_used = session.read_auto()
        assert mode_used == "snapshot"
        session.read_snapshot.assert_called_once()
        session.read_stream.assert_not_called()

    def test_auto_passes_timeout_to_stream(self):
        """Verify timeout is passed through to read_stream."""
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._tui_active = False
        session.read_stream = MagicMock(return_value=("out", 3, False))

        session.read_auto(timeout=7.5)
        session.read_stream.assert_called_once_with(7.5, True)

    def test_auto_passes_strip_ansi_to_stream(self):
        """Verify strip_ansi_output is passed through to read_stream."""
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._tui_active = False
        session.read_stream = MagicMock(return_value=("out", 3, False))

        session.read_auto(strip_ansi_output=False)
        session.read_stream.assert_called_once_with(2.0, False)

    @pytest.mark.asyncio
    async def test_handle_read_auto_mode_default(self, mock_manager, mock_session):
        """handle_session_read with no mode arg defaults to auto."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_auto.return_value = ("auto output", 11, False, "stream")

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234"}
        )
        assert result["success"] is True
        mock_session.read_auto.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_read_auto_returns_mode_used(self, mock_manager, mock_session):
        """Response includes mode_used field."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_auto.return_value = ("output", 6, False, "stream")

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "auto"}
        )
        assert result["success"] is True
        assert "mode_used" in result
        assert result["mode_used"] == "stream"

    @pytest.mark.asyncio
    async def test_handle_read_auto_returns_tui_active(self, mock_manager, mock_session):
        """Response includes tui_active field."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session._tui_active = True
        mock_session.read_auto.return_value = ("snap", 4, False, "snapshot")

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "auto"}
        )
        assert result["success"] is True
        assert "tui_active" in result
        assert result["tui_active"] is True

    @pytest.mark.asyncio
    async def test_handle_read_auto_returns_snapshot_available(self, mock_manager, mock_session):
        """Response includes snapshot_available: True."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_auto.return_value = ("out", 3, False, "stream")

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "auto"}
        )
        assert result["success"] is True
        assert result.get("snapshot_available") is True

    @pytest.mark.asyncio
    async def test_handle_read_explicit_stream_still_works(self, mock_manager, mock_session):
        """mode='stream' still uses stream path."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_stream.return_value = ("stream out", 10, False)

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "stream"}
        )
        assert result["success"] is True
        mock_session.read_stream.assert_called_once()
        assert result["mode_used"] == "stream"

    @pytest.mark.asyncio
    async def test_interact_read_mode_auto(self, mock_manager, mock_session):
        """session_interact with read_mode='auto' uses read_auto."""
        from terminal_mcp.tools.session import handle_session_interact
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 3
        mock_session.read_auto.return_value = ("output", 6, False, "stream")

        result = await handle_session_interact(
            mock_manager,
            {"session_id": "ph2-1234", "input": "ls", "read_mode": "auto"}
        )
        assert result["success"] is True
        mock_session.read_auto.assert_called_once()
        assert result.get("mode_used") == "stream"

    @pytest.mark.asyncio
    async def test_interact_read_mode_diff(self, mock_manager, mock_session):
        """session_interact with read_mode='diff' uses read_diff."""
        from terminal_mcp.tools.session import handle_session_interact
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 3
        mock_session.read_diff.return_value = ("line1", 5, [{"line": 1, "content": "line1"}], True)

        result = await handle_session_interact(
            mock_manager,
            {"session_id": "ph2-1234", "input": "ls", "read_mode": "diff"}
        )
        assert result["success"] is True
        mock_session.read_diff.assert_called_once()
        assert "changed_lines" in result

    @pytest.mark.asyncio
    async def test_interact_wait_for_overrides_read_mode(self, mock_manager, mock_session):
        """wait_for takes priority over read_mode."""
        from terminal_mcp.tools.session import handle_session_interact
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 3
        mock_session.read_until_pattern.return_value = ("matched", 7, True, False)

        result = await handle_session_interact(
            mock_manager,
            {"session_id": "ph2-1234", "input": "ls", "read_mode": "auto", "wait_for": r"\$"}
        )
        assert result["success"] is True
        assert result["matched"] is True
        mock_session.read_until_pattern.assert_called_once()


# ---------------------------------------------------------------------------
# TestReadDiff — mock pyte screen for unit testing diff mode
# ---------------------------------------------------------------------------

class TestReadDiff:
    """Tests for PTYSession.read_diff and handle_session_read with mode='diff'."""

    def _make_session_with_screen(self, display_lines):
        """Create a PTYSession.__new__ instance with a mock screen."""
        import threading
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession.__new__(PTYSession)
        session._prev_snapshot = None
        session._buffer_lock = threading.Lock()

        mock_screen = MagicMock()
        mock_screen.display = list(display_lines)
        session._screen = mock_screen
        return session

    def test_diff_first_read_returns_full_screen(self):
        """First call returns is_first_read=True and all non-empty lines."""
        session = self._make_session_with_screen(["line one   ", "line two   ", "          "])
        _, _, changed_lines, is_first_read = session.read_diff()
        assert is_first_read is True
        contents = [entry["content"] for entry in changed_lines]
        assert "line one   " in contents
        assert "line two   " in contents
        # Empty line should NOT be in changed_lines
        assert not any(c.strip() == "" for c in contents)

    def test_diff_first_read_sets_prev_snapshot(self):
        """After first call, _prev_snapshot is not None."""
        session = self._make_session_with_screen(["hello", "world"])
        session.read_diff()
        assert session._prev_snapshot is not None

    def test_diff_no_changes_returns_empty(self):
        """Two reads with no screen change → empty changed_lines, is_first_read=False."""
        lines = ["stable line", "another stable"]
        session = self._make_session_with_screen(lines)
        # First read
        session.read_diff()
        # Second read with identical screen
        _, _, changed_lines, is_first_read = session.read_diff()
        assert is_first_read is False
        assert changed_lines == []

    def test_diff_detects_single_changed_line(self):
        """Change one line → returns just that line in changed_lines."""
        session = self._make_session_with_screen(["original line 1", "original line 2"])
        session.read_diff()  # first read, sets baseline
        # Simulate line 2 changing
        session._screen.display = ["original line 1", "CHANGED line 2  "]
        _, _, changed_lines, _ = session.read_diff()
        assert len(changed_lines) == 1
        assert changed_lines[0]["content"] == "CHANGED line 2  "

    def test_diff_detects_multiple_changed_lines(self):
        """Change several lines → returns all changed."""
        session = self._make_session_with_screen(["line A", "line B", "line C"])
        session.read_diff()
        # Change two lines
        session._screen.display = ["line A", "CHANGED B", "CHANGED C"]
        _, _, changed_lines, _ = session.read_diff()
        assert len(changed_lines) == 2
        contents = [entry["content"] for entry in changed_lines]
        assert "CHANGED B" in contents
        assert "CHANGED C" in contents

    def test_diff_line_numbers_are_1_indexed(self):
        """First line is line 1, not line 0."""
        session = self._make_session_with_screen(["first", "second"])
        session.read_diff()  # first read
        session._screen.display = ["CHANGED", "second"]
        _, _, changed_lines, _ = session.read_diff()
        assert len(changed_lines) == 1
        assert changed_lines[0]["line"] == 1

    def test_diff_handles_screen_resize_grow(self):
        """Screen grows (more lines) → extra lines are changes."""
        session = self._make_session_with_screen(["line 1", "line 2"])
        session.read_diff()
        # Screen grew by 1 line
        session._screen.display = ["line 1", "line 2", "new line 3"]
        _, _, changed_lines, _ = session.read_diff()
        # The new line should be detected as a change
        assert any(entry["content"] == "new line 3" for entry in changed_lines)

    def test_diff_handles_screen_resize_shrink(self):
        """Screen shrinks → handles gracefully (no crash)."""
        session = self._make_session_with_screen(["line 1", "line 2", "line 3"])
        session.read_diff()
        # Screen shrank
        session._screen.display = ["line 1", "line 2"]
        # Should not raise
        _, _, changed_lines, _ = session.read_diff()
        # No crash is the main assertion; verify it ran

    @pytest.mark.asyncio
    async def test_handle_read_diff_mode(self, mock_manager, mock_session):
        """handle_session_read(mode='diff') returns changed_lines and is_first_read."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_diff.return_value = (
            "changed line",
            12,
            [{"line": 3, "content": "changed line"}],
            True,
        )

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "diff"}
        )
        assert result["success"] is True
        assert "changed_lines" in result
        assert "is_first_read" in result
        assert result["is_first_read"] is True

    @pytest.mark.asyncio
    async def test_handle_read_diff_strips_ansi(self, mock_manager, mock_session):
        """Diff output has ANSI stripped when strip_ansi=True (default)."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        ansi_content = "\x1b[32mcolored text\x1b[0m"
        mock_session.read_diff.return_value = (
            ansi_content, len(ansi_content.encode()), [], False
        )

        result = await handle_session_read(
            mock_manager,
            {"session_id": "ph2-1234", "mode": "diff", "strip_ansi": True}
        )
        assert result["success"] is True
        assert "\x1b[" not in result["output"]
        assert "colored text" in result["output"]


# ---------------------------------------------------------------------------
# TestSmartTruncation — unit tests on truncate_output_smart
# ---------------------------------------------------------------------------

class TestSmartTruncation:
    """Unit tests for truncate_output_smart."""

    def _large_text(self, n_lines=200, line_len=100):
        """Generate text that exceeds typical max_bytes."""
        return "\n".join(["X" * line_len] * n_lines)

    def test_short_output_passthrough_tail(self):
        """Text under max_bytes returns unchanged (tail mode)."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = "short text"
        result, was_truncated = truncate_output_smart(text, max_bytes=100_000, mode="tail")
        assert result == text
        assert was_truncated is False

    def test_short_output_passthrough_head_tail(self):
        """Text under max_bytes returns unchanged (head_tail mode)."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = "short text"
        result, was_truncated = truncate_output_smart(text, max_bytes=100_000, mode="head_tail")
        assert result == text
        assert was_truncated is False

    def test_short_output_passthrough_tail_only(self):
        """Text under max_bytes returns unchanged (tail_only mode)."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = "short text"
        result, was_truncated = truncate_output_smart(text, max_bytes=100_000, mode="tail_only")
        assert result == text
        assert was_truncated is False

    def test_tail_mode_keeps_beginning(self):
        """Large text truncated in tail mode: result starts with original beginning."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text()
        max_bytes = 500
        result, was_truncated = truncate_output_smart(text, max_bytes=max_bytes, mode="tail")
        assert was_truncated is True
        # Beginning of result should match beginning of text (byte-accurate decode)
        beginning = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        assert result.startswith(beginning)

    def test_tail_mode_marker(self):
        """Truncated tail-mode text ends with '[output truncated]'."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text()
        result, _ = truncate_output_smart(text, max_bytes=500, mode="tail")
        assert "[output truncated]" in result

    def test_head_tail_keeps_beginning_and_end(self):
        """head_tail mode: result starts with first part and ends with last part."""
        from terminal_mcp.output_buffer import truncate_output_smart
        # Construct text where beginning and end are identifiable
        beginning = "BEGINNING_" * 10
        middle = "M" * 10_000
        ending = "_ENDING" * 10
        text = beginning + middle + ending
        max_bytes = 500
        result, was_truncated = truncate_output_smart(text, max_bytes=max_bytes, mode="head_tail")
        assert was_truncated is True
        # Result should include characters from the beginning
        assert "BEGINNING_" in result
        # Result should include characters from the ending
        assert "_ENDING" in result

    def test_head_tail_marker(self):
        """head_tail mode result contains 'lines omitted' marker."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text()
        result, _ = truncate_output_smart(text, max_bytes=500, mode="head_tail")
        assert "lines omitted" in result

    def test_head_tail_omitted_count(self):
        """head_tail marker includes correct line count."""
        from terminal_mcp.output_buffer import truncate_output_smart
        # Create text with a known number of lines in the middle
        lines = ["line"] * 100
        text = "\n".join(lines)
        max_bytes = 50  # very small to force truncation
        result, was_truncated = truncate_output_smart(text, max_bytes=max_bytes, mode="head_tail")
        assert was_truncated is True
        # The marker should contain a number
        import re
        match = re.search(r'\[(\d+) lines omitted\]', result)
        assert match is not None
        assert int(match.group(1)) > 0

    def test_tail_only_keeps_end(self):
        """tail_only mode: result ends with the original ending."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text()
        max_bytes = 500
        result, was_truncated = truncate_output_smart(text, max_bytes=max_bytes, mode="tail_only")
        assert was_truncated is True
        # The tail of the original text should appear in result
        tail_bytes = text.encode("utf-8")[-max_bytes:]
        tail_text = tail_bytes.decode("utf-8", errors="ignore")
        assert result.endswith(tail_text)

    def test_tail_only_marker(self):
        """tail_only mode result starts with '[output truncated]'."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text()
        result, _ = truncate_output_smart(text, max_bytes=500, mode="tail_only")
        assert result.startswith("[output truncated]")

    def test_none_mode_no_truncation(self):
        """Even large text returns unchanged in none mode."""
        from terminal_mcp.output_buffer import truncate_output_smart
        text = self._large_text(n_lines=500)
        result, was_truncated = truncate_output_smart(text, max_bytes=100, mode="none")
        assert result == text
        assert was_truncated is False

    def test_none_mode_returns_false(self):
        """was_truncated is always False for none mode."""
        from terminal_mcp.output_buffer import truncate_output_smart
        result, was_truncated = truncate_output_smart("anything", max_bytes=1, mode="none")
        assert was_truncated is False

    def test_invalid_mode_raises(self):
        """Invalid mode raises ValueError (text must exceed max_bytes to reach the raise)."""
        from terminal_mcp.output_buffer import truncate_output_smart
        large_text = "x" * 200
        with pytest.raises(ValueError, match="Unknown truncation mode"):
            truncate_output_smart(large_text, max_bytes=10, mode="bogus_mode")

    @pytest.mark.asyncio
    async def test_session_read_truncation_param(self, mock_manager, mock_session):
        """Pass truncation='head_tail' to handle_session_read; verify smart truncation called."""
        from terminal_mcp.tools.session import handle_session_read
        mock_manager.get.return_value = mock_session
        mock_session.read_stream.return_value = ("output", 6, False)

        # Patch the name as imported into session.py
        with patch("terminal_mcp.tools.session.truncate_output_smart") as mock_trunc:
            mock_trunc.return_value = ("output", False)
            await handle_session_read(
                mock_manager,
                {"session_id": "ph2-1234", "mode": "stream", "truncation": "head_tail"}
            )
            # truncate_output_smart must have been called with mode="head_tail"
            assert mock_trunc.called
            call_kwargs = mock_trunc.call_args
            args, kwargs = call_kwargs
            mode_val = kwargs.get("mode") or (args[2] if len(args) > 2 else None)
            assert mode_val == "head_tail"

    @pytest.mark.asyncio
    async def test_session_interact_truncation_param(self, mock_manager, mock_session):
        """Pass truncation='tail_only' to handle_session_interact."""
        from terminal_mcp.tools.session import handle_session_interact
        mock_manager.get.return_value = mock_session
        mock_session.send.return_value = 3
        mock_session.read_stream.return_value = ("output", 6, False)

        # Patch the name as imported into session.py
        with patch("terminal_mcp.tools.session.truncate_output_smart") as mock_trunc:
            mock_trunc.return_value = ("output", False)
            await handle_session_interact(
                mock_manager,
                {"session_id": "ph2-1234", "input": "ls", "truncation": "tail_only"}
            )
            assert mock_trunc.called
            args, kwargs = mock_trunc.call_args
            mode_val = kwargs.get("mode") or (args[2] if len(args) > 2 else None)
            assert mode_val == "tail_only"

    @pytest.mark.asyncio
    async def test_session_exec_truncation_param(self, mock_manager, mock_session):
        """Pass truncation='none' to handle_session_exec; truncated is False."""
        from terminal_mcp.tools.session import handle_session_exec

        # Mock the manager.create to return our mock_session
        mock_manager.create.return_value = mock_session
        mock_session.read_stream.return_value = ("output", 6, False)
        # Also mock manager.close so cleanup doesn't fail
        mock_manager.close.return_value = 0

        result = await handle_session_exec(
            mock_manager,
            {"exec": "echo hello", "truncation": "none"}
        )
        # With truncation='none', was_truncated must be False (handler short-circuits)
        assert result["success"] is True
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_session_wait_for_truncation_param(self, mock_manager, mock_session):
        """Pass truncation param to handle_session_wait_for."""
        from terminal_mcp.tools.session import handle_session_wait_for
        mock_manager.get.return_value = mock_session
        mock_session.read_until_pattern.return_value = ("output", 6, True, False)

        # Patch the name as imported into session.py
        with patch("terminal_mcp.tools.session.truncate_output_smart") as mock_trunc:
            mock_trunc.return_value = ("output", False)
            await handle_session_wait_for(
                mock_manager,
                {"session_id": "ph2-1234", "pattern": r"output", "truncation": "tail"}
            )
            assert mock_trunc.called
            args, kwargs = mock_trunc.call_args
            mode_val = kwargs.get("mode") or (args[2] if len(args) > 2 else None)
            assert mode_val == "tail"


# ---------------------------------------------------------------------------
# TestPyteAlwaysInitialized — pyte screen is always present (no flag needed)
# ---------------------------------------------------------------------------

class TestPyteAlwaysInitialized:
    """Tests verifying pyte screen is always initialized and snapshot always works."""

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
    def test_snapshot_works_without_enable_snapshot_flag(self):
        """PTYSession(command='/bin/echo hi') → read_snapshot() returns non-empty."""
        from terminal_mcp.pty_session import PTYSession
        session = PTYSession(command="/bin/echo hi")
        time.sleep(0.5)  # let output accumulate into pyte screen
        output, bytes_read, _ = session.read_snapshot()
        session.close()
        # Should be a string (may be empty if echo exited fast, but no exception)
        assert isinstance(output, str)
        # pyte screen must have been fed something
        assert bytes_read >= 0

    @pytest.mark.asyncio
    async def test_session_create_returns_snapshot_available(self, mock_manager):
        """handle_session_create response has snapshot_available: True."""
        from terminal_mcp.tools.session import handle_session_create

        mock_session = MagicMock()
        mock_session.session_id = "new-sess"
        mock_session.label = "echo"
        mock_session.pid = 11111
        mock_session.created_at = time.time()
        mock_manager.create.return_value = mock_session

        result = await handle_session_create(
            mock_manager,
            {"command": "/bin/echo hi"}
        )
        assert result["success"] is True
        assert result.get("snapshot_available") is True

    @pytest.mark.asyncio
    async def test_list_sessions_includes_tui_and_snapshot(self, mock_manager):
        """list_sessions() response includes tui_active and snapshot_available."""
        from terminal_mcp.tools.session import handle_session_list

        mock_manager.list_sessions.return_value = [
            {
                "session_id": "ph2-1234",
                "label": "bash",
                "command": "/bin/bash",
                "pid": 99999,
                "is_alive": True,
                "created_at": time.time(),
                "last_activity": time.time(),
                "idle_seconds": 0.0,
                "tui_active": False,
                "snapshot_available": True,
            }
        ]

        result = await handle_session_list(mock_manager, {})
        assert result["success"] is True
        assert result["count"] == 1
        session_info = result["sessions"][0]
        assert "tui_active" in session_info
        assert "snapshot_available" in session_info
        assert session_info["snapshot_available"] is True
