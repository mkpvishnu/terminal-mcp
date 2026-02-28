"""Tests for PTYSession."""

import sys
import time
import pytest
import pyte

from terminal_mcp.pty_session import PTYSession


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionBasic:
    """Basic PTYSession tests using /bin/echo or /bin/cat."""

    def test_create_session_with_echo(self):
        """Test that a session can be created."""
        session = PTYSession(command="/bin/echo hello")
        assert session.session_id is not None
        assert len(session.session_id) == 8
        assert session.command == "/bin/echo hello"
        assert session.label == "/bin/echo"
        assert session.rows == 24
        assert session.cols == 80
        assert session.created_at > 0
        # Wait for process to finish
        time.sleep(0.5)
        session.close()

    def test_custom_label(self):
        """Test custom label."""
        session = PTYSession(command="/bin/echo hello", label="my-label")
        assert session.label == "my-label"
        time.sleep(0.5)
        session.close()

    def test_custom_dimensions(self):
        """Test custom rows/cols."""
        session = PTYSession(command="/bin/echo hello", rows=40, cols=120)
        assert session.rows == 40
        assert session.cols == 120
        time.sleep(0.5)
        session.close()

    def test_session_has_pid(self):
        """Test that PID is set."""
        session = PTYSession(command="/bin/echo hello")
        assert session.pid > 0
        time.sleep(0.5)
        session.close()

    def test_read_stream_gets_output(self):
        """Test reading output from echo command."""
        session = PTYSession(command="/bin/echo hello_world")
        # Give the reader thread time to capture output
        time.sleep(0.3)
        output, bytes_read, prompt_detected = session.read_stream(timeout=0.5)
        session.close()
        assert "hello_world" in output

    def test_close_returns_exit_status(self):
        """Test that close() returns an integer exit status."""
        session = PTYSession(command="/bin/echo bye")
        time.sleep(0.5)
        exit_status = session.close()
        # exit_status might be None if process already reaped, or 0 for success
        assert exit_status is None or isinstance(exit_status, int)

    def test_idle_seconds_increases(self):
        """Test idle_seconds property."""
        session = PTYSession(command="/bin/echo hi")
        t1 = session.idle_seconds
        time.sleep(0.2)
        t2 = session.idle_seconds
        assert t2 >= t1
        session.close()


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionSnapshot:
    """Tests for pyte snapshot mode."""

    def test_snapshot_mode_disabled_returns_empty(self):
        """Without enable_snapshot, read_snapshot returns empty."""
        session = PTYSession(command="/bin/echo hi", enable_snapshot=False)
        time.sleep(0.3)
        output, bytes_read, _ = session.read_snapshot()
        session.close()
        assert output == ""
        assert bytes_read == 0

    def test_snapshot_mode_enabled(self):
        """With enable_snapshot=True, read_snapshot returns screen content."""
        session = PTYSession(command="/bin/echo hello_snap", enable_snapshot=True)
        time.sleep(0.5)
        output, bytes_read, _ = session.read_snapshot()
        session.close()
        # The screen should have captured some content
        assert isinstance(output, str)


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionClose:
    """Tests for session close behavior."""

    def test_close_dead_process(self):
        """Closing an already-dead process should not raise."""
        session = PTYSession(command="/bin/echo done")
        time.sleep(0.5)
        # Process should have exited; close should be graceful
        exit_status = session.close()
        assert exit_status is None or isinstance(exit_status, int)


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionResize:
    def test_resize_updates_dimensions(self):
        session = PTYSession(command="/bin/cat", rows=24, cols=80)
        time.sleep(0.3)
        session.resize(40, 120)
        assert session.rows == 40
        assert session.cols == 120
        session.close()

    def test_resize_with_pyte_screen(self):
        session = PTYSession(command="/bin/cat", rows=24, cols=80, enable_snapshot=True)
        time.sleep(0.3)
        session.resize(50, 132)
        assert session.rows == 50
        assert session.cols == 132
        assert session._screen.lines == 50
        assert session._screen.columns == 132
        session.close()


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionScrollback:
    def test_history_screen_used_when_scrollback_positive(self):
        session = PTYSession(
            command="/bin/echo hello", enable_snapshot=True, scrollback_lines=500
        )
        time.sleep(0.3)
        assert isinstance(session._screen, pyte.HistoryScreen)
        session.close()

    def test_plain_screen_when_scrollback_zero(self):
        session = PTYSession(
            command="/bin/echo hello", enable_snapshot=True, scrollback_lines=0
        )
        time.sleep(0.3)
        assert type(session._screen) is pyte.Screen
        session.close()

    def test_scrollback_empty_without_snapshot(self):
        session = PTYSession(command="/bin/echo hello", enable_snapshot=False)
        time.sleep(0.3)
        text, total = session.read_scrollback(lines_back=10)
        assert text == ""
        assert total == 0
        session.close()

    def test_scrollback_returns_screen_with_zero_lines_back(self):
        session = PTYSession(
            command="/bin/echo test_scrollback_output",
            enable_snapshot=True,
            scrollback_lines=100,
        )
        time.sleep(0.5)
        text, total = session.read_scrollback(lines_back=0)
        assert isinstance(text, str)
        session.close()


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")
class TestPTYSessionBufferCap:
    def test_buffer_stays_capped_via_reader_loop(self):
        """Exercise the actual _reader_loop trim path by sending data through the PTY."""
        cap = 4096
        session = PTYSession(command="/bin/cat", max_buffer_bytes=cap)
        time.sleep(0.2)  # let /bin/cat start up

        # Send ~10 KB total — well above the 4 KB cap — in 512-byte chunks
        chunk = b"x" * 512
        for _ in range(20):
            session.process.send(chunk)
            time.sleep(0.02)

        # Give the reader thread time to process all incoming data
        time.sleep(0.5)

        with session._buffer_lock:
            buf_len = len(session._buffer)
            pos = session._read_position

        # Allow one read-chunk (4096 bytes) of overshoot before the trim fires
        assert buf_len <= cap + 4096, (
            f"Buffer ({buf_len}) exceeds cap ({cap}) + one read-chunk (4096)"
        )
        assert 0 <= pos <= buf_len, (
            f"read_position ({pos}) is out of range [0, {buf_len}]"
        )
        session.close()

    def test_read_after_buffer_trim(self):
        """Verify read_stream() works correctly after the reader loop has trimmed the buffer."""
        cap = 2048
        session = PTYSession(command="/bin/cat", max_buffer_bytes=cap)
        time.sleep(0.2)  # let /bin/cat start up

        # Send enough data to force multiple trim cycles
        chunk = b"y" * 512
        for _ in range(12):
            session.process.send(chunk)
            time.sleep(0.02)

        # Give the reader thread time to trim
        time.sleep(0.5)

        # read_stream() must not crash and must return a valid string
        output, bytes_read, _ = session.read_stream(timeout=0.5)
        assert isinstance(output, str), "read_stream() should return a str"
        session.close()
