"""PTY session: wraps pexpect.spawn with a background reader thread and optional pyte screen."""

import re
import signal
import threading
import time
import uuid
from typing import Optional

import pexpect
import pyte

from terminal_mcp.output_buffer import strip_ansi, detect_prompt

KEY_MAP: dict[str, str] = {
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "page-up": "\x1b[5~",
    "page-down": "\x1b[6~",
    "insert": "\x1b[2~",
    "delete": "\x1b[3~",
    "backspace": "\x7f",
    "tab": "\t",
    "shift-tab": "\x1b[Z",
    "escape": "\x1b",
    "enter": "\r",
    "f1": "\x1bOP",
    "f2": "\x1bOQ",
    "f3": "\x1bOR",
    "f4": "\x1bOS",
    "f5": "\x1b[15~",
    "f6": "\x1b[17~",
    "f7": "\x1b[18~",
    "f8": "\x1b[19~",
    "f9": "\x1b[20~",
    "f10": "\x1b[21~",
    "f11": "\x1b[23~",
    "f12": "\x1b[24~",
}


class PTYSession:
    """A persistent interactive terminal session backed by a PTY."""

    def __init__(
        self,
        command: str,
        label: Optional[str] = None,
        rows: int = 24,
        cols: int = 80,
        enable_snapshot: bool = False,
        scrollback_lines: int = 1000,
        max_buffer_bytes: int = 1_000_000,
    ):
        self.session_id = str(uuid.uuid4())[:8]
        self.command = command
        self.label = label or command.split()[0]
        self.rows = rows
        self.cols = cols
        self.enable_snapshot = enable_snapshot
        self.scrollback_lines = scrollback_lines
        self.created_at = time.time()
        self.last_activity = time.time()
        self._max_buffer_bytes = max_buffer_bytes
        # OSC 133 shell integration tracking
        self._osc133_supported = False
        self._last_command_finished = False
        self._last_exit_code: Optional[int] = None
        self._command_state: str = "idle"  # "idle" | "prompt" | "running" | "output"

        # Spawn the PTY process via pexpect
        self.process = pexpect.spawn(
            command,
            dimensions=(rows, cols),
            encoding=None,   # binary mode – we decode manually
            timeout=None,
        )

        # Stream buffer: bytes accumulated by the background reader
        self._buffer: bytearray = bytearray()
        self._buffer_lock = threading.Lock()
        self._read_position: int = 0  # tracks where the caller last read to

        # pyte virtual terminal (always initialised)
        if scrollback_lines > 0:
            self._screen = pyte.HistoryScreen(cols, rows, history=scrollback_lines)
        else:
            self._screen = pyte.Screen(cols, rows)
        self._pyte_stream = pyte.Stream(self._screen)

        # TUI / alt-screen tracking
        self._tui_active: bool = False
        self._alt_screen_entered: bool = False
        self._prev_snapshot: Optional[list[str]] = None

        # Start background reader thread (daemon so it dies with the process)
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name=f"pty-reader-{self.session_id}",
        )
        self._reader_thread.start()

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Continuously read from PTY fd into the buffer."""
        while True:
            try:
                data = self.process.read_nonblocking(size=4096, timeout=0.1)
                if data:
                    # Scan for OSC 133 shell integration markers
                    self._parse_osc133(data)
                    self._detect_alt_screen(data)
                    with self._buffer_lock:
                        self._buffer.extend(data)
                        if len(self._buffer) > self._max_buffer_bytes:
                            trim = len(self._buffer) - self._max_buffer_bytes
                            del self._buffer[:trim]
                            if self._read_position >= trim:
                                self._read_position -= trim
                            else:
                                self._read_position = 0
                        try:
                            self._pyte_stream.feed(
                                data.decode('utf-8', errors='replace')
                            )
                        except Exception:
                            pass
                    self.last_activity = time.time()
            except pexpect.TIMEOUT:
                # No data available yet – just loop
                if not self.process.isalive():
                    break
                continue
            except pexpect.EOF:
                # Process exited
                break
            except Exception:
                break

    # Alt-screen buffer detection: ESC[?{1049,47,1047}{h=enter,l=exit}
    _ALT_SCREEN_PATTERN = re.compile(
        rb'\x1b\[\?(1049|47|1047)([hl])'
    )

    # OSC 133 marker pattern: ESC ] 133 ; {marker} [; {params}] BEL  or  ESC \
    _OSC133_PATTERN = re.compile(
        rb'\x1b\]133;([A-D])(?:;([^\x07\x1b]*))?(?:\x07|\x1b\\)'
    )

    def _parse_osc133(self, data: bytes) -> None:
        """Parse OSC 133 sequences from raw PTY data and update state."""
        for match in self._OSC133_PATTERN.finditer(data):
            self._osc133_supported = True
            marker = match.group(1).decode('ascii', errors='replace')
            params = match.group(2)

            if marker == 'A':
                # Prompt start
                self._command_state = "prompt"
            elif marker == 'B':
                # Command start (user pressed Enter, command about to run)
                self._command_state = "running"
            elif marker == 'C':
                # Output start
                self._command_state = "output"
            elif marker == 'D':
                # Command finished
                self._last_command_finished = True
                self._command_state = "idle"
                if params:
                    try:
                        self._last_exit_code = int(params.decode('ascii', errors='replace'))
                    except (ValueError, AttributeError):
                        pass

    def _detect_alt_screen(self, data: bytes) -> None:
        """Detect alternate screen buffer entry/exit sequences and update TUI state."""
        for match in self._ALT_SCREEN_PATTERN.finditer(data):
            suffix = match.group(2)
            if suffix == b'h':
                self._tui_active = True
                self._alt_screen_entered = True
            elif suffix == b'l':
                self._tui_active = False

    # ------------------------------------------------------------------
    # Send operations
    # ------------------------------------------------------------------

    def send(self, text: str, press_enter: bool = True) -> int:
        """Send text to the PTY. Returns number of bytes sent."""
        if press_enter:
            self.process.sendline(text)
            bytes_sent = len(text.encode()) + 1  # +1 for \r
        else:
            self.process.send(text)
            bytes_sent = len(text.encode())
        self.last_activity = time.time()
        return bytes_sent

    def send_control(self, char: str) -> int:
        """
        Send a control character.

        Supported chars: 'c' (SIGINT), 'd' (EOF), 'z' (SIGTSTP),
                         'l' (clear screen), ']' (telnet escape).
        Returns 1 if sent, 0 if char unknown.
        """
        ctrl_map = {
            'c': '\x03',   # SIGINT
            'd': '\x04',   # EOF
            'z': '\x1a',   # SIGTSTP
            'l': '\x0c',   # Form feed / clear
            ']': '\x1d',   # Telnet escape
        }
        if char in ctrl_map:
            self.process.send(ctrl_map[char])
            self.last_activity = time.time()
            return 1
        return 0

    def send_key(self, key: str) -> int:
        """
        Send a special key (arrow, function key, etc.).

        See KEY_MAP for supported key names.
        Returns the number of bytes sent, or 0 if the key is unknown.
        """
        seq = KEY_MAP.get(key)
        if seq is None:
            return 0
        self.process.send(seq)
        self.last_activity = time.time()
        return len(seq)

    def send_password(self, password: str) -> int:
        """Send a password to the PTY without logging it. Returns bytes sent."""
        self.process.sendline(password)
        self.last_activity = time.time()
        return len(password.encode()) + 1  # +1 for \r

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY window. Sends SIGWINCH to the child process."""
        self.process.setwinsize(rows, cols)
        self.rows = rows
        self.cols = cols
        self._screen.resize(rows, cols)
        self.last_activity = time.time()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def read_stream(
        self,
        timeout: float = 2.0,
        strip_ansi_output: bool = True,
    ) -> tuple[str, int, bool]:
        """
        Read new output since the last read call.

        Waits until no new bytes arrive for `timeout` seconds (settling).
        Returns: (output_text, bytes_read, prompt_detected)
        """
        absolute_deadline = time.time() + timeout + 10.0  # hard ceiling
        settle_deadline = time.time() + timeout

        with self._buffer_lock:
            last_size = len(self._buffer)

        while time.time() < absolute_deadline:
            time.sleep(0.05)
            with self._buffer_lock:
                current_size = len(self._buffer)

            if current_size > last_size:
                # New data arrived – reset settle timer
                last_size = current_size
                settle_deadline = time.time() + timeout

            if time.time() >= settle_deadline:
                break

        # Extract bytes since last read
        with self._buffer_lock:
            new_data = bytes(self._buffer[self._read_position:])
            self._read_position = len(self._buffer)

        output = new_data.decode('utf-8', errors='replace')
        prompt_detected = detect_prompt(output)

        if strip_ansi_output:
            output = strip_ansi(output)

        return output, len(new_data), prompt_detected

    def read_snapshot(self) -> tuple[str, int, bool]:
        """
        Return the current pyte screen display.

        Returns: (display_text, bytes_read, prompt_detected)
        Only works when enable_snapshot=True.
        """
        with self._buffer_lock:
            display = "\n".join(self._screen.display)
        display = display.rstrip()
        return display, len(display.encode('utf-8')), False

    def read_auto(
        self,
        timeout: float = 2.0,
        strip_ansi_output: bool = True,
    ) -> tuple[str, int, bool, str]:
        """
        Auto-select read mode based on alternate screen buffer state.

        If a TUI is active (alt-screen entered), returns a pyte snapshot.
        Otherwise, returns the stream output (new bytes since last read).

        Returns: (output, bytes_read, prompt_detected, mode)
            mode is either "snapshot" or "stream".
        """
        if self._tui_active:
            output, bytes_read, prompt_detected = self.read_snapshot()
            return output, bytes_read, prompt_detected, "snapshot"
        else:
            output, bytes_read, prompt_detected = self.read_stream(
                timeout, strip_ansi_output
            )
            return output, bytes_read, prompt_detected, "stream"

    def read_diff(self) -> tuple[str, int, list[dict], bool]:
        """
        Return only changed lines since the last snapshot read.

        Returns: (formatted_diff_text, bytes_read, changed_lines, is_first_read)
          - formatted_diff_text: newline-joined content of changed lines (or full screen on first read)
          - bytes_read: UTF-8 byte count of the formatted text
          - changed_lines: list of {"line": N, "content": "..."} dicts (1-indexed line numbers)
          - is_first_read: True if _prev_snapshot was None (first call)

        Note: bytes_read in diff mode represents the byte size of the formatted
        diff text, not the number of raw PTY bytes received (unlike stream mode).
        """
        with self._buffer_lock:
            current = list(self._screen.display)

        if self._prev_snapshot is None:
            # First read: return all non-empty lines
            self._prev_snapshot = current
            changed_lines = [
                {"line": i + 1, "content": line}
                for i, line in enumerate(current)
                if line.strip()
            ]
            formatted = "\n".join(line.rstrip() for line in current).rstrip("\n")
            return formatted, len(formatted.encode("utf-8")), changed_lines, True

        # Subsequent reads: compare line-by-line
        prev = self._prev_snapshot
        max_lines = max(len(current), len(prev))
        changed_indices: list[int] = []

        for i in range(max_lines):
            if i >= len(prev):
                # Screen grew — new line is a change
                changed_indices.append(i)
            elif i >= len(current):
                # Screen shrank — previously existing line is gone (skip)
                continue
            elif current[i] != prev[i]:
                changed_indices.append(i)

        changed_lines = [
            {"line": i + 1, "content": current[i]}
            for i in changed_indices
        ]
        formatted = "\n".join(entry["content"] for entry in changed_lines)
        self._prev_snapshot = current
        return formatted, len(formatted.encode("utf-8")), changed_lines, False

    def read_scrollback(self, lines_back: int = 0) -> tuple[str, int]:
        """
        Read scrollback history plus current screen content.

        Args:
            lines_back: Number of history lines to include (0 = current screen only).

        Returns: (display_text, total_lines)
        """
        current_lines = [line.rstrip() for line in self._screen.display]

        if lines_back > 0 and hasattr(self._screen, 'history'):
            history = self._screen.history.top
            history_lines = []
            for row in list(history)[-lines_back:]:
                line = "".join(row[col].data for col in sorted(row.keys()))
                history_lines.append(line.rstrip())
            all_lines = history_lines + current_lines
        else:
            all_lines = current_lines

        # Strip trailing empty lines
        while all_lines and not all_lines[-1]:
            all_lines.pop()

        text = "\n".join(all_lines)
        return text, len(all_lines)

    def read_until_pattern(
        self,
        pattern: str,
        timeout: float = 30.0,
        strip_ansi_output: bool = True,
    ) -> tuple[str, int, bool, bool]:
        """
        Read output until pattern matches or timeout expires.

        Returns: (output_text, bytes_read, matched, prompt_detected)
        """
        compiled = re.compile(pattern)
        deadline = time.time() + timeout

        # Snapshot the start position
        with self._buffer_lock:
            start_pos = self._read_position

        accumulated_text = ""

        while time.time() < deadline:
            with self._buffer_lock:
                # Re-clamp start_pos in case the reader thread trimmed the
                # buffer since the last iteration (stale pointer guard).
                start_pos = min(start_pos, len(self._buffer))
                new_data = bytes(self._buffer[start_pos:])

            if new_data:
                decoded = new_data.decode('utf-8', errors='replace')
                if strip_ansi_output:
                    decoded = strip_ansi(decoded)
                accumulated_text = decoded

                if compiled.search(accumulated_text):
                    # Update read position
                    with self._buffer_lock:
                        actual_new_data = bytes(self._buffer[start_pos:])
                        self._read_position = len(self._buffer)
                    prompt_detected = detect_prompt(accumulated_text)
                    return accumulated_text, len(actual_new_data), True, prompt_detected

            # Check if process died
            if not self._is_alive():
                break

            time.sleep(0.05)

        # Timeout expired or process died
        with self._buffer_lock:
            actual_new_data = bytes(self._buffer[start_pos:])
            self._read_position = len(self._buffer)

        if not accumulated_text and actual_new_data:
            accumulated_text = actual_new_data.decode('utf-8', errors='replace')
            if strip_ansi_output:
                accumulated_text = strip_ansi(accumulated_text)

        prompt_detected = detect_prompt(accumulated_text)
        return accumulated_text, len(actual_new_data), False, prompt_detected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _is_alive(self) -> bool:
        """Check if process is alive, returning False if already reaped."""
        try:
            return self.process.isalive()
        except Exception:
            return False

    def close(self) -> Optional[int]:
        """
        Gracefully shut down the session.

        Sequence: EOF → 2s wait → SIGHUP → 2s wait → SIGKILL.
        Returns the exit status code (or None if unavailable).
        """
        try:
            self.process.sendeof()
        except Exception:
            pass

        # Wait up to 2s for clean exit
        for _ in range(20):
            if not self._is_alive():
                break
            time.sleep(0.1)

        if self._is_alive():
            try:
                self.process.kill(signal.SIGHUP)
            except Exception:
                pass
            for _ in range(20):
                if not self._is_alive():
                    break
                time.sleep(0.1)

        if self._is_alive():
            try:
                self.process.kill(signal.SIGKILL)
            except Exception:
                pass
            time.sleep(0.5)

        exit_status = self.process.exitstatus
        try:
            self.process.close(force=True)
        except Exception:
            pass
        return exit_status

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        """Whether the underlying process is still running."""
        return self.process.isalive()

    @property
    def pid(self) -> int:
        """PID of the spawned process."""
        return self.process.pid

    @property
    def idle_seconds(self) -> float:
        """Seconds since last I/O activity."""
        return time.time() - self.last_activity
