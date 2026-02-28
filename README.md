# terminal-mcp

**MCP server for interactive terminal sessions — SSH, REPLs, database CLIs, and TUI apps inside Claude Code.**

[![CI](https://github.com/mkpvishnu/terminal-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/mkpvishnu/terminal-mcp/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mkpvishnu/terminal-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/mkpvishnu/terminal-mcp/actions/workflows/codeql.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Why This Exists

If you've hit any of these limitations with Claude Code, terminal-mcp solves them:

- **"Claude Code can't handle interactive sessions"** — The built-in Bash tool runs each command in a fresh subprocess. No persistence, no back-and-forth.
- **"SSH not supported in Claude Code"** — You can't SSH into a server and run multiple commands across an active connection.
- **"Claude Code Bash tool doesn't support REPLs"** — Python, Node, Ruby, and other interpreters need a persistent session for multi-line interaction.
- **"How to use psql / mysql / redis-cli with Claude Code"** — Database CLIs require a live connection that survives across tool calls.
- **"Interactive terminal not working in Claude Code"** — TUI apps (htop, vim, ncdu, fzf) need a real PTY with special key support.
- **"Claude Code can't send arrow keys or Tab"** — The Bash tool has no concept of terminal escape sequences.

terminal-mcp fills this gap by exposing MCP tools that create and manage real PTY sessions. Each session runs as a persistent child process; you send input, special keys, and control characters and read output across multiple tool calls for as long as the session lives.

## Features

- **Persistent PTY sessions** — real terminal sessions that survive across tool calls
- **Special key support** — arrow keys, Tab, Escape, function keys (F1–F12), Home/End, Page Up/Down
- **Control characters** — Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-L, and telnet escape
- **Two read modes** — stream (waits for output to settle) and snapshot (pyte screen buffer for TUI apps)
- **ANSI stripping** — optional removal of escape sequences for clean text output
- **Idle cleanup** — automatic session cleanup after configurable timeout
- **Session management** — list, label, and manage multiple concurrent sessions

## Quickstart

### 1. Install

```bash
git clone https://github.com/mkpvishnu/terminal-mcp.git
cd terminal-mcp
pip install -e ".[dev]"
```

### 2. Register with Claude Code

Add to `~/.claude.json` (or your project's `.mcp.json`):

```json
{
  "mcpServers": {
    "terminal": {
      "command": "python3",
      "args": ["-m", "terminal_mcp.server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/terminal-mcp"
      }
    }
  }
}
```

Replace `/absolute/path/to/terminal-mcp` with the actual path. Use `which python3` to find your Python binary if needed.

### 3. Use it

```
session_create  command="python3"  label="repl"
session_read    session_id="abc123"
session_send    session_id="abc123"  input="print('hello')"
session_read    session_id="abc123"
session_close   session_id="abc123"
```

## Tool Reference

### session_create

Spawn a persistent PTY terminal session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `command` | string | Yes | — | Shell command to run (e.g. `bash`, `python3`, `ssh user@host`) |
| `label` | string | No | command name | Human-readable label |
| `rows` | integer | No | 24 | Terminal height |
| `cols` | integer | No | 80 | Terminal width |
| `idle_timeout` | integer | No | 1800 | Seconds before auto-close |
| `enable_snapshot` | boolean | No | false | Enable pyte screen buffer for snapshot reads |

**Returns:** `session_id`, `label`, `pid`, `created_at`

### session_send

Send input text, a control character, or a special key to an active session. Only one of `input`, `control_char`, or `key` may be provided per call.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | — | Session ID from `session_create` |
| `input` | string | No | — | Text to send |
| `press_enter` | boolean | No | true | Append carriage return after input |
| `control_char` | string | No | — | Control character: `c` `d` `z` `l` `]` |
| `key` | string | No | — | Special key (see table below) |

**Returns:** `bytes_sent`

#### Supported special keys

| Key | Description | Key | Description |
|-----|-------------|-----|-------------|
| `up` | Arrow up | `f1`–`f12` | Function keys |
| `down` | Arrow down | `home` | Home |
| `left` | Arrow left | `end` | End |
| `right` | Arrow right | `page-up` | Page Up |
| `tab` | Tab | `page-down` | Page Down |
| `shift-tab` | Shift+Tab | `insert` | Insert |
| `escape` | Escape | `delete` | Delete |
| `enter` | Enter | `backspace` | Backspace |

#### Supported control characters

| Char | Signal | Description |
|------|--------|-------------|
| `c` | SIGINT | Interrupt (Ctrl-C) |
| `d` | EOF | End of file / logout (Ctrl-D) |
| `z` | SIGTSTP | Suspend (Ctrl-Z) |
| `l` | — | Clear screen (Ctrl-L) |
| `]` | — | Telnet escape |

### session_read

Read output from a session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | — | Session ID |
| `mode` | string | No | `stream` | `stream` or `snapshot` |
| `timeout` | number | No | 2.0 | Settle timeout in seconds (stream mode) |
| `strip_ansi` | boolean | No | true | Strip ANSI escape sequences |

**Returns:** `output`, `bytes_read`, `prompt_detected`, `is_alive`

### session_close

Terminate a session gracefully (EOF → SIGHUP → SIGKILL).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Session ID to close |

**Returns:** `exit_status`

### session_list

List all active sessions with their status and idle time.

**Returns:** `sessions` (array), `count`

## Usage Examples

### SSH session

```
session_create  command="ssh user@myserver.example.com"  label="prod-ssh"
session_read    session_id="a1b2c3d4"  timeout=5.0
session_send    session_id="a1b2c3d4"  input="mypassword"
session_send    session_id="a1b2c3d4"  input="df -h"
session_read    session_id="a1b2c3d4"
session_close   session_id="a1b2c3d4"
```

### Python REPL

```
session_create  command="python3"  label="repl"
session_read    session_id="e5f6g7h8"
session_send    session_id="e5f6g7h8"  input="import math"
session_send    session_id="e5f6g7h8"  input="print(math.sqrt(144))"
session_read    session_id="e5f6g7h8"
session_close   session_id="e5f6g7h8"
```

### TUI navigation with special keys

```
session_create  command="python3 -m openclaw configure"  label="openclaw"
session_read    session_id="x1y2z3w4"  timeout=3.0
session_send    session_id="x1y2z3w4"  key="down"
session_send    session_id="x1y2z3w4"  key="down"
session_send    session_id="x1y2z3w4"  key="enter"
session_read    session_id="x1y2z3w4"
session_send    session_id="x1y2z3w4"  key="tab"
session_read    session_id="x1y2z3w4"
session_close   session_id="x1y2z3w4"
```

### Sending Ctrl-C to interrupt

```
session_send    session_id="a1b2c3d4"  control_char="c"
session_read    session_id="a1b2c3d4"
```

## Architecture

Each session is backed by a real PTY allocated via `pexpect.spawn`. The design has four main parts:

**Background reader thread.** A daemon thread continuously reads from the PTY file descriptor in 4096-byte chunks and appends bytes to an in-memory buffer. The thread is lock-protected and dies automatically when the child process exits.

**Output settling (stream mode).** `session_read` in stream mode polls the buffer until no new bytes have arrived for `timeout` seconds (default 2s), then returns everything written since the last read call. A hard ceiling of `timeout + 10s` prevents infinite blocking.

**Snapshot mode.** When a session is created with `enable_snapshot=true`, all PTY output is also fed into a `pyte` virtual screen buffer. `session_read` with `mode="snapshot"` returns the current rendered screen — useful for programs that use cursor movement (vim, htop, ncdu).

**Idle cleanup.** `SessionManager` runs a background cleanup loop (every 60s by default) that closes sessions idle longer than their `idle_timeout`. The default timeout is 30 minutes. Concurrent sessions are capped at 10 by default.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_sessions` | `10` | Maximum concurrent sessions |
| `idle_timeout` | `1800` | Seconds before auto-close |
| `default_rows` | `24` | Default terminal height |
| `default_cols` | `80` | Default terminal width |
| `read_settle_timeout` | `2.0` | Output settle timeout (stream mode) |
| `max_output_bytes` | `100000` | Max bytes per read |
| `cleanup_interval` | `60` | Seconds between cleanup sweeps |

Per-session overrides for `rows`, `cols`, and `idle_timeout` can be passed to `session_create`.

## Changelog

### v0.2.0

- **Special key support** — arrow keys, Tab, Escape, function keys (F1–F12), Home/End, Page Up/Down, and more via the `key` parameter on `session_send`
- **Mutual exclusivity** — `input`, `control_char`, and `key` are now validated as mutually exclusive
- Added GitHub Actions CI (Python 3.10–3.13) and CodeQL security scanning
- Added project metadata, classifiers, and MIT license

### v0.1.0

- Initial release
- Persistent PTY sessions via pexpect
- Stream and snapshot read modes
- Control character support (Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-L)
- Session management with idle cleanup

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `pytest tests/ -v`
5. Submit a pull request

## License

[MIT](LICENSE)
