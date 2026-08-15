# Architecture

terminal-mcp is an MCP (Model Context Protocol) server that exposes interactive PTY sessions as tools for AI agents.

## Overview

```
AI Client (Claude, Copilot, Cursor, etc.)
    |
    | MCP JSON-RPC over stdio
    |
terminal-mcp Server
    |
    +-- SessionManager (thread-safe session lifecycle)
    |       |
    |       +-- PTYSession 1 (bash)
    |       |       +-- pexpect.spawn → /bin/bash
    |       |       +-- Reader Thread (daemon)
    |       |       +-- pyte Screen Buffer
    |       |
    |       +-- PTYSession 2 (python3)
    |       |       +-- pexpect.spawn → python3
    |       |       +-- Reader Thread (daemon)
    |       |       +-- pyte Screen Buffer
    |       |
    |       +-- Cleanup Thread (daemon)
    |
    +-- Tool Handlers (async, one per MCP tool)
    +-- Safety Gate (dangerous command detection)
    +-- Config (env var driven)
```

## Components

### MCP Server (`server.py`)

The entry point. Uses the `mcp` Python SDK to register 9 tools and serve them over stdio transport (newline-delimited JSON-RPC). Each tool call is dispatched to an async handler function.

The server runs on Python's `asyncio` event loop. All blocking PTY operations are wrapped in `asyncio.to_thread()` to avoid blocking the event loop during concurrent MCP requests.

### PTYSession (`pty_session.py`)

The core component. Each session wraps a real PTY allocated via `pexpect.spawn` (Unix) or `pexpect.PopenSpawn` (Windows).

**Initialization:**
- Spawns the child process with the requested command
- Starts a daemon reader thread
- Initializes a `pyte.HistoryScreen` for snapshot mode
- Generates a unique 8-character hex session ID

**Buffer management:**
- An in-memory `bytearray` accumulates all PTY output
- A `_total_bytes_written` counter tracks the absolute byte position (monotonically increasing, survives buffer trims)
- When the buffer exceeds `max_buffer_bytes`, older bytes are trimmed from the front
- A `threading.Lock` protects concurrent access to the buffer

**Reader thread:**
- Continuously reads from the PTY file descriptor in 4096-byte chunks
- Appends bytes to the buffer and feeds them to the pyte screen
- Detects alternate screen buffer sequences (ESC[?1049h) for TUI detection
- Detects OSC 133 shell integration markers for command boundary tracking
- Dies automatically when the child process exits

**Read modes:**

| Mode | Implementation |
|------|---------------|
| `stream` | Returns bytes written since the last read position. Polls until no new bytes arrive for `timeout` seconds |
| `snapshot` | Renders the current pyte virtual terminal screen as text |
| `diff` | Compares the current pyte screen against the previous snapshot, returns only changed lines |
| `auto` | Uses `snapshot` if a TUI is detected (alternate screen buffer active), otherwise falls back to `stream` |

**Pattern matching (`read_until_pattern`):**
- Used by `session_interact` (with `wait_for`) and `session_wait_for`
- Accepts an absolute `start_position` parameter to skip bytes from before the command was sent
- This prevents false matches against the echoed command text or stale buffer content
- Polls the buffer at 50ms intervals, testing the regex against new content

**Close sequence:**
1. Send EOF (Ctrl-D)
2. Wait up to 2 seconds for clean exit
3. Send SIGHUP (Unix) or `proc.terminate()` (Windows)
4. Wait up to 2 seconds
5. Send SIGKILL (Unix) or `proc.kill()` (Windows)

### SessionManager (`session_manager.py`)

Thread-safe lifecycle management for PTYSession instances.

- Stores sessions in a `dict[str, PTYSession]` protected by a `threading.Lock`
- The lock is NOT held during `PTYSession` construction (process spawn), only during dict access
- A background daemon thread runs the cleanup loop every 60 seconds
- Sessions are auto-closed when idle longer than their timeout or when the process has died
- `atexit` handler ensures all sessions are cleaned up on interpreter exit
- SIGTERM handler ensures cleanup on Docker stop, `kill`, or systemd

### Safety Gate (`safety.py`)

Detects dangerous commands before execution.

- 17 built-in regex patterns covering destructive operations:
  - File system: `rm -rf`, `dd`, `mkfs`
  - Database: `DROP TABLE`, `TRUNCATE`
  - Remote execution: `curl | sh`, `wget | sh`
  - Permissions: `chmod 777`, `chmod -R`, `chown -R`
  - System: `shutdown`, `reboot`, `kill -9`
- Extensible via `TERMINAL_MCP_DANGEROUS_PATTERNS` env var (semicolon-separated regexes)
- Can be disabled with `TERMINAL_MCP_SAFETY_GATE=off`
- When triggered, returns `requires_confirmation: true` instead of executing
- Resend with `confirmed: true` to bypass

### Output Processing (`output_buffer.py`)

- **ANSI stripping**: Comprehensive regex-based removal of terminal escape sequences including CSI, OSC, DCS, Kitty keyboard protocol, application keypad mode, and more
- **Prompt detection**: Heuristic-based detection of shell prompts (looks for common patterns like `$`, `#`, `>>>`, `>`)
- **Smart truncation**: Four strategies to prevent context overflow while preserving useful output:
  - `tail` (default): Keep the beginning, truncate the end
  - `head_tail`: Keep first 30% and last 70% with a line-count marker
  - `tail_only`: Keep only the end (ideal for build logs)
  - `none`: No truncation

## Data Flow

### Send + Read (session_interact)

```
1. Client calls session_interact(session_id, input="ls -la", wait_for="\$")
2. Handler snapshots buffer position: start_pos = current_buffer_end()
3. Handler sends input bytes to PTY via pexpect
4. Handler calls read_until_pattern(pattern="\$", start_position=start_pos)
5. Reader thread is continuously appending PTY output to buffer
6. read_until_pattern polls buffer[start_pos:] every 50ms
7. When pattern matches (or timeout): return captured text
8. Handler strips ANSI, truncates, and returns MCP response
```

### TUI Auto-Detection

```
1. Reader thread receives ESC[?1049h (alternate screen buffer enter)
2. Sets _tui_active = True
3. Client calls session_read(mode="auto")
4. auto mode sees _tui_active, switches to snapshot
5. Renders pyte screen buffer as text lines
6. Returns with mode_used="snapshot", tui_active=true
```

## Threading Model

terminal-mcp uses a multi-threaded design:

| Thread | Purpose | Lifecycle |
|--------|---------|-----------|
| Main (asyncio) | MCP server event loop, tool handlers | Entire server lifetime |
| Reader thread (per session) | Reads PTY output into buffer | Created with session, dies when process exits |
| Cleanup thread | Closes idle/dead sessions | Daemon, entire server lifetime |

All shared state is protected by locks:
- `SessionManager._lock` protects the sessions dictionary
- `PTYSession._buffer_lock` protects the output buffer and pyte screen

## Cross-Platform Support

| Feature | Unix (Linux/macOS) | Windows |
|---------|-------------------|---------|
| PTY backend | `pexpect.spawn` | `pexpect.PopenSpawn` |
| Process alive check | `child.isalive()` | `proc.poll() is None` |
| Graceful stop | `SIGHUP` signal | `proc.terminate()` |
| Force kill | `SIGKILL` signal | `proc.kill()` |
| Terminal resize | `setwinsize()` + SIGWINCH | Not supported (no-op) |
| Close cleanup | `child.close(force=True)` | No-op (handle cleanup via proc) |
