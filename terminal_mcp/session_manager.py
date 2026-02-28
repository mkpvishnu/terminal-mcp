"""Session lifecycle management: creation, lookup, idle cleanup."""

import atexit
import logging
import threading
import time
from typing import Optional

from terminal_mcp.config import TerminalConfig
from terminal_mcp.pty_session import PTYSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Thread-safe manager for PTY sessions with idle cleanup."""

    def __init__(self, config: TerminalConfig):
        self.config = config
        self._sessions: dict[str, PTYSession] = {}
        self._lock = threading.Lock()

        # Background cleanup thread (daemon)
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="session-cleanup",
        )
        self._cleanup_thread.start()

        # Clean up all sessions on interpreter exit
        atexit.register(self.close_all)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        command: str,
        label: Optional[str] = None,
        rows: int = 24,
        cols: int = 80,
        idle_timeout: Optional[int] = None,
        enable_snapshot: bool = False,
        scrollback_lines: int = 1000,
    ) -> PTYSession:
        """Spawn a new PTY session and register it."""
        with self._lock:
            if len(self._sessions) >= self.config.max_sessions:
                raise RuntimeError(
                    f"Maximum number of sessions ({self.config.max_sessions}) reached"
                )
            session = PTYSession(
                command=command,
                label=label,
                rows=rows,
                cols=cols,
                enable_snapshot=enable_snapshot,
                scrollback_lines=scrollback_lines,
                max_buffer_bytes=self.config.max_buffer_bytes,
            )
            # Store optional per-session idle timeout
            if idle_timeout is not None:
                session._idle_timeout_override = idle_timeout
            self._sessions[session.session_id] = session
            logger.info("Session %s created: %s (pid=%s)", session.session_id, command, session.pid)
            return session

    def get(self, session_id: str) -> PTYSession:
        """Return a session by ID; raises KeyError if not found."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        return session

    def close(self, session_id: str) -> Optional[int]:
        """Close and remove a session. Returns exit status."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        exit_status = session.close()
        logger.info("Session %s closed (exit_status=%s)", session_id, exit_status)
        return exit_status

    def list_sessions(self) -> list[dict]:
        """Return a snapshot list of all active sessions."""
        with self._lock:
            sessions = list(self._sessions.values())
        return [
            {
                "session_id": s.session_id,
                "label": s.label,
                "command": s.command,
                "pid": s.pid,
                "is_alive": s.is_alive,
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "idle_seconds": round(s.idle_seconds, 1),
            }
            for s in sessions
        ]

    def close_all(self) -> None:
        """Close all sessions (called at exit)."""
        with self._lock:
            sids = list(self._sessions.keys())
        for sid in sids:
            try:
                self.close(sid)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    def _cleanup_loop(self) -> None:
        """Periodically remove idle or dead sessions."""
        while True:
            time.sleep(self.config.cleanup_interval)
            self._cleanup_idle()

    def _cleanup_idle(self) -> None:
        to_close: list[str] = []
        with self._lock:
            for sid, session in self._sessions.items():
                # Use per-session override if set, else global default
                timeout = getattr(session, '_idle_timeout_override', self.config.idle_timeout)
                if session.idle_seconds > timeout or not session.is_alive:
                    to_close.append(sid)

        for sid in to_close:
            try:
                logger.info("Auto-closing idle/dead session %s", sid)
                self.close(sid)
            except Exception:
                pass
