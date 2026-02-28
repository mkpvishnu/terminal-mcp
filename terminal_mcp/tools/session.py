"""Tool handlers for terminal session operations."""

import logging
import time
from typing import TYPE_CHECKING

from terminal_mcp.pty_session import KEY_MAP

if TYPE_CHECKING:
    from terminal_mcp.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def handle_session_create(manager: "SessionManager", arguments: dict) -> dict:
    """
    Create a new PTY session.

    Required: command (str)
    Optional: label, rows, cols, idle_timeout, enable_snapshot
    """
    command = arguments.get("command")
    if not command:
        return {
            "success": False,
            "error": {
                "type": "validation_error",
                "message": "'command' is required",
            },
        }

    try:
        session = manager.create(
            command=command,
            label=arguments.get("label"),
            rows=arguments.get("rows", 24),
            cols=arguments.get("cols", 80),
            idle_timeout=arguments.get("idle_timeout"),
            enable_snapshot=arguments.get("enable_snapshot", False),
        )
        return {
            "success": True,
            "session_id": session.session_id,
            "label": session.label,
            "pid": session.pid,
            "created_at": session.created_at,
        }
    except RuntimeError as e:
        return {
            "success": False,
            "error": {"type": "session_limit_reached", "message": str(e)},
        }
    except Exception as e:
        logger.exception("Error creating session")
        return {
            "success": False,
            "error": {"type": "spawn_error", "message": str(e)},
        }


async def handle_session_send(manager: "SessionManager", arguments: dict) -> dict:
    """
    Send input or a control character to a session.

    Required: session_id
    Optional: input (str), press_enter (bool, default True),
              control_char (one of 'c', 'd', 'z', 'l', ']')
    """
    session_id = arguments.get("session_id")
    if not session_id:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'session_id' is required"},
        }

    try:
        session = manager.get(session_id)
    except KeyError as e:
        return {
            "success": False,
            "error": {"type": "not_found", "message": str(e)},
        }

    if not session.is_alive:
        return {
            "success": False,
            "error": {"type": "session_dead", "message": "Session process has exited"},
        }

    try:
        control_char = arguments.get("control_char")
        input_text = arguments.get("input")
        key = arguments.get("key")
        press_enter = arguments.get("press_enter", True)
        bytes_sent = 0

        # Mutual exclusivity: only one of input/control_char/key
        provided = sum(x is not None for x in (input_text, control_char, key))
        if provided > 1:
            return {
                "success": False,
                "error": {
                    "type": "validation_error",
                    "message": "Only one of 'input', 'control_char', or 'key' may be provided",
                },
            }

        if control_char is not None:
            valid_chars = {'c', 'd', 'z', 'l', ']'}
            if control_char not in valid_chars:
                return {
                    "success": False,
                    "error": {
                        "type": "validation_error",
                        "message": f"control_char must be one of {sorted(valid_chars)}",
                    },
                }
            bytes_sent = session.send_control(control_char)
        elif input_text is not None:
            bytes_sent = session.send(input_text, press_enter=press_enter)
        elif key is not None:
            if key not in KEY_MAP:
                return {
                    "success": False,
                    "error": {
                        "type": "validation_error",
                        "message": f"Unknown key: '{key}'. Valid keys: {sorted(KEY_MAP.keys())}",
                    },
                }
            bytes_sent = session.send_key(key)
        else:
            # Nothing to send — send a bare enter if press_enter is True
            if press_enter:
                bytes_sent = session.send("", press_enter=True)

        return {"success": True, "bytes_sent": bytes_sent}

    except Exception as e:
        logger.exception("Error sending to session %s", session_id)
        return {
            "success": False,
            "error": {"type": "send_error", "message": str(e)},
        }


async def handle_session_read(manager: "SessionManager", arguments: dict) -> dict:
    """
    Read output from a session.

    Required: session_id
    Optional: mode ("stream"|"snapshot", default "stream"),
              timeout (float, default 2.0), strip_ansi (bool, default True)
    """
    session_id = arguments.get("session_id")
    if not session_id:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'session_id' is required"},
        }

    try:
        session = manager.get(session_id)
    except KeyError as e:
        return {
            "success": False,
            "error": {"type": "not_found", "message": str(e)},
        }

    mode = arguments.get("mode", "stream")
    timeout = float(arguments.get("timeout", 2.0))
    strip_ansi = arguments.get("strip_ansi", True)

    try:
        if mode == "snapshot":
            output, bytes_read, prompt_detected = session.read_snapshot()
        else:
            output, bytes_read, prompt_detected = session.read_stream(
                timeout=timeout,
                strip_ansi_output=strip_ansi,
            )

        return {
            "success": True,
            "output": output,
            "bytes_read": bytes_read,
            "prompt_detected": prompt_detected,
            "is_alive": session.is_alive,
        }

    except Exception as e:
        logger.exception("Error reading from session %s", session_id)
        return {
            "success": False,
            "error": {"type": "read_error", "message": str(e)},
        }


async def handle_session_close(manager: "SessionManager", arguments: dict) -> dict:
    """
    Close a session gracefully.

    Required: session_id
    """
    session_id = arguments.get("session_id")
    if not session_id:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'session_id' is required"},
        }

    try:
        exit_status = manager.close(session_id)
        return {
            "success": True,
            "exit_status": exit_status,
        }
    except KeyError as e:
        return {
            "success": False,
            "error": {"type": "not_found", "message": str(e)},
        }
    except Exception as e:
        logger.exception("Error closing session %s", session_id)
        return {
            "success": False,
            "error": {"type": "close_error", "message": str(e)},
        }


async def handle_session_list(manager: "SessionManager", arguments: dict) -> dict:
    """
    List all active sessions.
    """
    try:
        sessions = manager.list_sessions()
        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions),
        }
    except Exception as e:
        logger.exception("Error listing sessions")
        return {
            "success": False,
            "error": {"type": "list_error", "message": str(e)},
        }
