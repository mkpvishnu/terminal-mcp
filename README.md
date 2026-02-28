# terminal-mcp

MCP server for persistent interactive terminal sessions — SSH, REPLs, and database CLIs inside Claude Code.

## Problem

Claude Code's built-in Bash tool runs each command in a fresh shell subprocess. That works fine for
one-shot commands, but it cannot handle:

- **SSH sessions** — logging in, running commands, and staying connected
- **Python / Node / Ruby REPLs** — entering an interpreter and sending multiple expressions
- **Database CLIs** — `psql`, `mysql`, `redis-cli`, and similar interactive prompts
- **Long-running processes** — anything that requires back-and-forth I/O after startup

`terminal-mcp` fills this gap by exposing a small set of MCP tools that create and manage real PTY
sessions. Each session runs as a persistent child process; you send input and read output across
multiple tool calls for as long as the session lives.

## Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `session_create` | Spawn a persistent PTY session. Returns a `session_id` used by all other tools. | `command` (required), `label`, `rows`, `cols`, `idle_timeout`, `enable_snapshot` |
| `session_send` | Send text or a control character to an active session. | `session_id` (required), `input`, `press_enter`, `control_char` (`c`, `d`, `z`, `l`, `]`) |
| `session_read` | Read output from a session. Stream mode waits for output to settle; snapshot mode returns the current terminal screen. | `session_id` (required), `mode` (`stream`\|`snapshot`), `timeout`, `strip_ansi` |
| `session_close` | Terminate a session gracefully: EOF, then SIGHUP, then SIGKILL. | `session_id` (required) |
| `session_list` | List all active sessions with their status and idle time. | — |

## Installation

### 1. Clone and install dependencies

```bash
git clone https://github.com/mkpvishnu/terminal-mcp.git
cd terminal-mcp
pip install pyte pexpect mcp
```

Or install in editable mode with all dependencies from `pyproject.toml`:

```bash
pip install -e ".[dev]"
```

### 2. Register in `~/.claude.json`

Add the server under the `mcpServers` key in your Claude Code config:

```json
{
  "mcpServers": {
    "terminal": {
      "command": "/opt/homebrew/opt/python@3.13/libexec/bin/python3",
      "args": ["-m", "terminal_mcp.server"],
      "env": {
        "PYTHONPATH": "/path/to/terminal-mcp"
      }
    }
  }
}
```

Replace `/path/to/terminal-mcp` with the absolute path to the cloned repository and adjust the
Python path to match your environment (`which python3` to find yours).

## Usage Examples

### SSH session

```
session_create  command="ssh user@myserver.example.com"
                label="prod-ssh"

# Wait for the password prompt, then send credentials
session_read    session_id="a1b2c3d4"   timeout=5.0

session_send    session_id="a1b2c3d4"   input="mypassword"

# Run a command on the remote host
session_send    session_id="a1b2c3d4"   input="df -h"
session_read    session_id="a1b2c3d4"

session_close   session_id="a1b2c3d4"
```

### Python REPL

```
session_create  command="python3"  label="repl"

session_read    session_id="e5f6g7h8"          # read the >>> prompt

session_send    session_id="e5f6g7h8"   input="import math"
session_send    session_id="e5f6g7h8"   input="print(math.sqrt(144))"
session_read    session_id="e5f6g7h8"
# output: "12.0"

session_close   session_id="e5f6g7h8"
```

### Sending Ctrl-C to interrupt a running command

```
session_send    session_id="a1b2c3d4"   control_char="c"
session_read    session_id="a1b2c3d4"
```

Supported control characters: `c` (SIGINT), `d` (EOF/logout), `z` (SIGTSTP/suspend),
`l` (clear screen), `]` (telnet escape).

## Architecture

Each session is backed by a real PTY allocated via `pexpect.spawn`. The design has four main
parts:

**Background reader thread.** A daemon thread continuously reads from the PTY file descriptor
in 4096-byte chunks and appends bytes to an in-memory buffer. The thread is lock-protected and
dies automatically when the child process exits.

**Output settling (`stream` mode).** `session_read` in stream mode polls the buffer until no new
bytes have arrived for `timeout` seconds (default 2 s), then returns everything written since the
last read call. A hard ceiling of `timeout + 10 s` prevents infinite blocking. This approach
handles prompts and partial output naturally without requiring the caller to know when the process
is done writing.

**Snapshot mode.** When a session is created with `enable_snapshot=True`, all PTY output is also
fed into a `pyte` virtual screen buffer. `session_read` with `mode="snapshot"` returns the
current rendered screen, which is useful for programs that use cursor movement to draw UIs (e.g.,
`vim`, `htop`, `ncdu`).

**Idle cleanup.** `SessionManager` runs a background cleanup loop (every 60 s by default) that
closes sessions that have been idle longer than their configured `idle_timeout`. The default
timeout is 30 minutes. The maximum number of concurrent sessions is also capped (default 10) to
prevent resource exhaustion.

## Configuration

`TerminalConfig` defaults (defined in `terminal_mcp/config.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `max_sessions` | `10` | Maximum number of concurrent sessions |
| `idle_timeout` | `1800` | Seconds before an idle session is auto-closed |
| `default_rows` | `24` | Default terminal height in rows |
| `default_cols` | `80` | Default terminal width in columns |
| `read_settle_timeout` | `2.0` | Seconds to wait for output to settle (stream mode) |
| `max_output_bytes` | `100000` | Maximum bytes returned in a single read |
| `cleanup_interval` | `60` | Seconds between idle session cleanup sweeps |

Per-session overrides for `rows`, `cols`, and `idle_timeout` can be passed directly to
`session_create`.

## Running Tests

```bash
pytest tests/ -v
```

`pytest-asyncio` is required for the async test suite and is included in the `dev` extras:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
