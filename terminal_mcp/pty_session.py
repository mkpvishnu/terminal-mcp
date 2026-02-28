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
    ):
        self.session_id = str(uuid.uuid4())[:8]
        self.command = command
        self.label = label or command.split()[0]
        self.rows = rows
        self.cols = cols
        self.enable_snapshot = enable_snapshot
        self.created_at = time.time()
        self.last_activity = time.time()

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

        # Optional pyte screen for snapshot mode
        self._screen: Optional[pyte.Screen] = None
        self._pyte_stream: Optional[pyte.Stream] = None
        if enable_snapshot:
            self._screen = pyte.Screen(cols, rows)
            self._pyte_stream = pyte.Stream(self._screen)

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
                    with self._buffer_lock:
                        self._buffer.extend(data)
                        if self._pyte_stream is not None:
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
        if self._screen is None:
            return "", 0, False
        display = "\n".join(self._screen.display)
        display = display.rstrip()
        return display, len(display.encode('utf-8')), False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
            if not self.process.isalive():
                break
            time.sleep(0.1)

        if self.process.isalive():
            try:
                self.process.kill(signal.SIGHUP)
            except Exception:
                pass
            for _ in range(20):
                if not self.process.isalive():
                    break
                time.sleep(0.1)

        if self.process.isalive():
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
