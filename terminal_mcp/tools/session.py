"""Tool handlers for terminal session operations."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from terminal_mcp.pty_session import KEY_MAP
from terminal_mcp.output_buffer import strip_ansi, truncate_output
from terminal_mcp.config import get_config

if TYPE_CHECKING:
    from terminal_mcp.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def handle_session_create(manager: "SessionManager", arguments: dict) -> dict:
    """
    Create a new PTY session.

    Required: command (str)
    Optional: label, rows, cols, idle_timeout, enable_snapshot, scrollback_lines
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
        session = await asyncio.to_thread(
            manager.create,
            command=command,
            label=arguments.get("label"),
            rows=arguments.get("rows", 24),
            cols=arguments.get("cols", 80),
            idle_timeout=arguments.get("idle_timeout"),
            enable_snapshot=arguments.get("enable_snapshot", False),
            scrollback_lines=arguments.get("scrollback_lines", 1000),
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
              control_char (one of 'c', 'd', 'z', 'l', ']'),
              key, password
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
        password = arguments.get("password")
        press_enter = arguments.get("press_enter", True)
        bytes_sent = 0

        # Mutual exclusivity: only one of input/control_char/key/password
        provided = sum(x is not None for x in (input_text, control_char, key, password))
        if provided > 1:
            return {
                "success": False,
                "error": {
                    "type": "validation_error",
                    "message": "Only one of 'input', 'control_char', 'key', or 'password' may be provided",
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
            bytes_sent = await asyncio.to_thread(session.send_control, control_char)
        elif input_text is not None:
            bytes_sent = await asyncio.to_thread(session.send, input_text, press_enter=press_enter)
        elif key is not None:
            if key not in KEY_MAP:
                return {
                    "success": False,
                    "error": {
                        "type": "validation_error",
                        "message": f"Unknown key: '{key}'. Valid keys: {sorted(KEY_MAP.keys())}",
                    },
                }
            bytes_sent = await asyncio.to_thread(session.send_key, key)
        elif password is not None:
            logger.info("Sending password to session %s (redacted)", session_id)
            bytes_sent = await asyncio.to_thread(session.send_password, password)
        else:
            # Nothing to send — send a bare enter if press_enter is True
            if press_enter:
                bytes_sent = await asyncio.to_thread(session.send, "", press_enter=True)

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
              timeout (float, default 2.0), strip_ansi (bool, default True),
              scrollback (int, snapshot mode only)
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
    strip_ansi_output = arguments.get("strip_ansi", True)
    scrollback = arguments.get("scrollback")

    try:
        if mode == "snapshot":
            if scrollback is not None:
                output, total_lines = await asyncio.to_thread(
                    session.read_scrollback, lines_back=scrollback
                )
                if strip_ansi_output:
                    output = strip_ansi(output)
                bytes_read = len(output.encode('utf-8'))
                prompt_detected = False
            else:
                output, bytes_read, prompt_detected = await asyncio.to_thread(
                    session.read_snapshot
                )
                if strip_ansi_output:
                    output = strip_ansi(output)
                total_lines = None
        else:
            output, bytes_read, prompt_detected = await asyncio.to_thread(
                session.read_stream,
                timeout=timeout,
                strip_ansi_output=strip_ansi_output,
            )
            total_lines = None

        # Apply output truncation (Feature 1)
        output, was_truncated = truncate_output(output, get_config().max_output_bytes)

        result = {
            "success": True,
            "output": output,
            "bytes_read": bytes_read,
            "prompt_detected": prompt_detected,
            "is_alive": session.is_alive,
            "truncated": was_truncated,
        }
        if total_lines is not None:
            result["total_lines"] = total_lines
        return result

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
        exit_status = await asyncio.to_thread(manager.close, session_id)
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


async def handle_session_resize(manager: "SessionManager", arguments: dict) -> dict:
    """Resize a session's terminal window."""
    session_id = arguments.get("session_id")
    if not session_id:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'session_id' is required"},
        }

    rows = arguments.get("rows")
    cols = arguments.get("cols")
    if rows is None or cols is None:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'rows' and 'cols' are required"},
        }

    if not isinstance(rows, int) or rows <= 0:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'rows' must be a positive integer"},
        }

    if not isinstance(cols, int) or cols <= 0:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'cols' must be a positive integer"},
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
        session.resize(rows, cols)
        return {"success": True, "rows": rows, "cols": cols}
    except Exception as e:
        logger.exception("Error resizing session %s", session_id)
        return {
            "success": False,
            "error": {"type": "resize_error", "message": str(e)},
        }


async def handle_session_exec(manager: "SessionManager", arguments: dict) -> dict:
    """Execute a command in a temporary session and return output."""
    exec_cmd = arguments.get("exec")
    if not exec_cmd:
        return {
            "success": False,
            "error": {"type": "validation_error", "message": "'exec' is required"},
        }

    shell = arguments.get("command", "bash")
    timeout = float(arguments.get("timeout", 5.0))
    rows = arguments.get("rows", 24)
    cols = arguments.get("cols", 80)
    label = f"exec:{exec_cmd[:30]}"
    session = None

    try:
        session = await asyncio.to_thread(
            manager.create,
            command=shell,
            label=label,
            rows=rows,
            cols=cols,
        )
        # Consume startup output
        await asyncio.to_thread(session.read_stream, 1.0)
        # Send the command
        await asyncio.to_thread(session.send, exec_cmd, True)
        # Read the output
        output, bytes_read, prompt_detected = await asyncio.to_thread(
            session.read_stream, timeout
        )

        output, was_truncated = truncate_output(output, get_config().max_output_bytes)

        return {
            "success": True,
            "output": output,
            "bytes_read": bytes_read,
            "session_id": session.session_id,
            "truncated": was_truncated,
        }
    except RuntimeError as e:
        return {
            "success": False,
            "error": {"type": "session_limit_reached", "message": str(e)},
        }
    except Exception as e:
        logger.exception("Error in session_exec")
        return {
            "success": False,
            "error": {"type": "exec_error", "message": str(e)},
        }
    finally:
        if session is not None:
            try:
                await asyncio.to_thread(manager.close, session.session_id)
            except Exception:
                pass
