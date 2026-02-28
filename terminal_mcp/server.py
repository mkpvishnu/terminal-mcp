"""MCP server entry point for terminal-mcp."""

import asyncio
import atexit
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from terminal_mcp.config import get_config
from terminal_mcp.session_manager import SessionManager
from terminal_mcp.tools.session import (
    handle_session_create,
    handle_session_send,
    handle_session_read,
    handle_session_close,
    handle_session_list,
    handle_session_resize,
    handle_session_exec,
)

# All logging MUST go to stderr (required for stdio transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# MCP application
app = Server("terminal-mcp")

# Global session manager (lazy singleton)
_manager: SessionManager | None = None


def get_manager() -> SessionManager:
    """Get or create the global SessionManager."""
    global _manager
    if _manager is None:
        _manager = SessionManager(get_config())
    return _manager


# Tool definitions
TOOLS = [
    Tool(
        name="session_create",
        description=(
            "Spawn a persistent PTY terminal session. Returns a session_id used by "
            "all other session_* tools. Supports interactive shells, SSH, REPLs, "
            "and database CLIs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run (e.g. 'bash', 'python3', 'ssh user@host')",
                },
                "label": {
                    "type": "string",
                    "description": "Human-readable label for the session",
                },
                "rows": {
                    "type": "integer",
                    "description": "Terminal height in rows",
                    "default": 24,
                },
                "cols": {
                    "type": "integer",
                    "description": "Terminal width in columns",
                    "default": 80,
                },
                "idle_timeout": {
                    "type": "integer",
                    "description": "Seconds before auto-closing idle session",
                    "default": 1800,
                },
                "enable_snapshot": {
                    "type": "boolean",
                    "description": "Enable pyte screen buffer for snapshot reads",
                    "default": False,
                },
                "scrollback_lines": {
                    "type": "integer",
                    "description": "Number of scrollback history lines to keep (requires enable_snapshot)",
                    "default": 1000,
                },
            },
            "required": ["command"],
        },
    ),
    Tool(
        name="session_send",
        description=(
            "Send input text, a control character, or a special key to an active session. "
            "Use control_char for signals (e.g. 'c' for Ctrl-C). "
            "Use key for special keys (e.g. 'up', 'tab', 'f1')."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID returned by session_create",
                },
                "input": {
                    "type": "string",
                    "description": "Text to send to the session",
                },
                "press_enter": {
                    "type": "boolean",
                    "description": "Append carriage return after input",
                    "default": True,
                },
                "control_char": {
                    "type": "string",
                    "description": "Control character to send: 'c' (SIGINT), 'd' (EOF), 'z' (SIGTSTP), 'l' (clear), ']' (telnet)",
                    "enum": ["c", "d", "z", "l", "]"],
                },
                "key": {
                    "type": "string",
                    "description": "Special key to send (arrow keys, function keys, etc.)",
                    "enum": [
                        "up", "down", "left", "right",
                        "home", "end", "page-up", "page-down",
                        "insert", "delete", "backspace",
                        "tab", "shift-tab", "escape", "enter",
                        "f1", "f2", "f3", "f4", "f5", "f6",
                        "f7", "f8", "f9", "f10", "f11", "f12",
                    ],
                },
                "password": {
                    "type": "string",
                    "description": "Password or secret to send (will not be logged)",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="session_resize",
        description="Resize the terminal window of an active session. Sends SIGWINCH to the process.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID returned by session_create",
                },
                "rows": {
                    "type": "integer",
                    "description": "New terminal height in rows",
                },
                "cols": {
                    "type": "integer",
                    "description": "New terminal width in columns",
                },
            },
            "required": ["session_id", "rows", "cols"],
        },
    ),
    Tool(
        name="session_read",
        description=(
            "Read output from a session. Stream mode waits for output to settle; "
            "snapshot mode returns the current terminal screen (requires enable_snapshot=true)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID returned by session_create",
                },
                "mode": {
                    "type": "string",
                    "description": "Read mode: 'stream' (default) or 'snapshot'",
                    "enum": ["stream", "snapshot"],
                    "default": "stream",
                },
                "timeout": {
                    "type": "number",
                    "description": "Settle timeout in seconds (stream mode)",
                    "default": 2.0,
                },
                "strip_ansi": {
                    "type": "boolean",
                    "description": "Strip ANSI escape sequences from output",
                    "default": True,
                },
                "scrollback": {
                    "type": "integer",
                    "description": "Lines of scrollback history to include (snapshot mode only)",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="session_close",
        description="Terminate a session gracefully. Sends EOF, then SIGHUP, then SIGKILL.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to close",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="session_list",
        description="List all active terminal sessions with their status and idle time.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="session_exec",
        description=(
            "Execute a command in a temporary session and return the output. "
            "The session is automatically cleaned up after execution."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "exec": {
                    "type": "string",
                    "description": "Command to execute in the session",
                },
                "command": {
                    "type": "string",
                    "description": "Shell to use (default: bash)",
                    "default": "bash",
                },
                "timeout": {
                    "type": "number",
                    "description": "Seconds to wait for command output",
                    "default": 5.0,
                },
                "rows": {
                    "type": "integer",
                    "description": "Terminal height in rows",
                    "default": 24,
                },
                "cols": {
                    "type": "integer",
                    "description": "Terminal width in columns",
                    "default": 80,
                },
            },
            "required": ["exec"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return available tools."""
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to the appropriate handler."""
    # Redact password from logged arguments
    log_args = arguments
    if name == "session_send" and "password" in arguments:
        log_args = {**arguments, "password": "***REDACTED***"}
    logger.info("Tool called: %s with args: %s", name, log_args)

    try:
        manager = get_manager()

        if name == "session_create":
            result = await handle_session_create(manager, arguments)
        elif name == "session_send":
            result = await handle_session_send(manager, arguments)
        elif name == "session_resize":
            result = await handle_session_resize(manager, arguments)
        elif name == "session_read":
            result = await handle_session_read(manager, arguments)
        elif name == "session_close":
            result = await handle_session_close(manager, arguments)
        elif name == "session_list":
            result = await handle_session_list(manager, arguments)
        elif name == "session_exec":
            result = await handle_session_exec(manager, arguments)
        else:
            result = {
                "success": False,
                "error": {"type": "unknown_tool", "message": f"Unknown tool: {name}"},
            }

    except Exception as e:
        logger.exception("Unhandled error in tool %s", name)
        result = {
            "success": False,
            "error": {"type": "internal", "message": str(e)},
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def run_server() -> None:
    """Start the MCP server over stdio."""
    logger.info("Starting terminal-mcp server...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    """Entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
