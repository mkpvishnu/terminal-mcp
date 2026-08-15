# Tools Reference

terminal-mcp exposes **9 MCP tools** for creating and managing interactive terminal sessions.

---

## session_create

Spawn a persistent PTY terminal session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `command` | string | Yes | - | Shell command to run (e.g. `bash`, `python3`, `ssh user@host`) |
| `label` | string | No | command name | Human-readable label for the session |
| `rows` | integer | No | 24 | Terminal height in rows |
| `cols` | integer | No | 80 | Terminal width in columns |
| `idle_timeout` | integer | No | 1800 | Seconds of inactivity before auto-close |
| `enable_snapshot` | boolean | No | true | Deprecated - snapshot is always enabled |
| `scrollback_lines` | integer | No | 1000 | Lines of scrollback history to retain |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique 8-character hex ID |
| `label` | string | Session label |
| `pid` | integer | Process ID of the spawned process |
| `created_at` | float | Unix timestamp of creation |
| `snapshot_available` | boolean | Always `true` |

**Example:**

```
session_create  command="python3"  label="repl"  rows=40  cols=120
```

---

## session_send

Send input to an active session. Exactly one of `input`, `control_char`, `key`, or `password` must be provided.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | - | Target session ID |
| `input` | string | No | - | Text to type |
| `press_enter` | boolean | No | true | Append carriage return after input |
| `control_char` | string | No | - | Control character to send |
| `key` | string | No | - | Special key to press |
| `password` | string | No | - | Secret text (not logged) |
| `confirmed` | boolean | No | false | Bypass the dangerous command safety gate |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `bytes_sent` | integer | Number of bytes sent |

If the input matches a dangerous pattern and `confirmed` is `false`:

| Field | Type | Description |
|-------|------|-------------|
| `requires_confirmation` | boolean | Always `true` |
| `command` | string | The blocked command |
| `reason` | string | Why it was blocked |

### Supported Special Keys

| Key | Description | Key | Description |
|-----|-------------|-----|-------------|
| `up` | Arrow up | `f1` - `f12` | Function keys |
| `down` | Arrow down | `home` | Home |
| `left` | Arrow left | `end` | End |
| `right` | Arrow right | `page-up` | Page Up |
| `tab` | Tab | `page-down` | Page Down |
| `shift-tab` | Shift+Tab | `insert` | Insert |
| `escape` | Escape | `delete` | Delete |
| `enter` | Enter | `backspace` | Backspace |

### Supported Control Characters

| Char | Signal | Description |
|------|--------|-------------|
| `c` | SIGINT | Interrupt (Ctrl-C) |
| `d` | EOF | End of file / logout (Ctrl-D) |
| `z` | SIGTSTP | Suspend (Ctrl-Z) |
| `l` | - | Clear screen (Ctrl-L) |
| `]` | - | Telnet escape |

---

## session_read

Read output from a session. Supports four read modes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | - | Target session ID |
| `mode` | string | No | `auto` | Read mode: `auto`, `stream`, `snapshot`, `diff` |
| `timeout` | number | No | 2.0 | Settle timeout in seconds (stream/auto) |
| `strip_ansi` | boolean | No | true | Strip ANSI escape sequences |
| `scrollback` | integer | No | - | Lines of scrollback history (snapshot mode) |
| `truncation` | string | No | config default | `tail`, `head_tail`, `tail_only`, `none` |

### Read Modes

| Mode | When to Use | How It Works |
|------|-------------|--------------|
| `auto` | Default - works for everything | Auto-detects TUI apps and switches between stream and snapshot |
| `stream` | Shell commands, builds | Waits for output to settle, returns new bytes since last read |
| `snapshot` | TUI apps (htop, vim) | Returns the full rendered screen from pyte virtual terminal |
| `diff` | Monitoring TUI apps | Returns only screen lines that changed since the last read |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `output` | string | The terminal output |
| `bytes_read` | integer | Number of bytes read |
| `prompt_detected` | boolean | Whether a shell prompt was detected |
| `is_alive` | boolean | Whether the process is still running |
| `truncated` | boolean | Whether the output was truncated |
| `tui_active` | boolean | Whether a TUI app is detected |
| `mode_used` | string | Which read mode was actually used |
| `snapshot_available` | boolean | Whether snapshot mode is available |

Additional fields in `diff` mode:

| Field | Type | Description |
|-------|------|-------------|
| `changed_lines` | object | Map of line numbers to content |
| `is_first_read` | boolean | Whether this is the first diff read |

OSC 133 shell integration fields (when supported):

| Field | Type | Description |
|-------|------|-------------|
| `osc133` | boolean | Whether shell integration is active |
| `command_state` | string | `idle`, `running`, or `finished` |
| `exit_code` | integer | Exit code of the last command |
| `command_complete` | boolean | Whether the last command completed |

---

## session_interact

Send input and read output in a single call. Combines `session_send` + `session_read` to halve LLM round trips. Supports all input types and optional regex-based waiting.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | - | Target session ID |
| `input` | string | No | - | Text to type |
| `press_enter` | boolean | No | true | Append carriage return |
| `control_char` | string | No | - | Control character |
| `key` | string | No | - | Special key |
| `password` | string | No | - | Secret text |
| `wait_for` | string | No | - | Regex pattern to wait for in output |
| `timeout` | number | No | 5.0 | Seconds to wait |
| `strip_ansi` | boolean | No | true | Strip ANSI escape sequences |
| `confirmed` | boolean | No | false | Bypass dangerous command gate |
| `read_mode` | string | No | `stream` | `auto`, `stream`, `snapshot`, `diff` |
| `truncation` | string | No | config default | Truncation mode |

**Returns:** Same fields as `session_read` plus `bytes_sent` and `matched` (when `wait_for` is used).

**Example - send command and wait for prompt:**

```
session_interact  session_id="a1b2c3d4"  input="ls -la"  wait_for="\$\s*$"  timeout=5
```

---

## session_wait_for

Wait for a regex pattern to appear in session output. Use this when you've already sent a command with `session_send` and want to wait for specific output.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | - | Target session ID |
| `pattern` | string | Yes | - | Regex pattern to wait for |
| `timeout` | number | No | 30.0 | Max seconds to wait |
| `strip_ansi` | boolean | No | true | Strip ANSI escape sequences |
| `truncation` | string | No | config default | Truncation mode |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `output` | string | Output captured until the pattern matched (or timeout) |
| `bytes_read` | integer | Number of bytes read |
| `matched` | boolean | Whether the pattern was found |
| `prompt_detected` | boolean | Whether a shell prompt was detected |
| `is_alive` | boolean | Whether the process is running |

**Example - wait for build completion:**

```
session_wait_for  session_id="a1b2c3d4"  pattern="Build complete|ERROR"  timeout=120
```

---

## session_exec

Execute a command in a temporary session and return the output. The session is created, the command runs, output is captured, and the session is automatically cleaned up.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `exec` | string | Yes | - | Command to execute |
| `command` | string | No | `bash` | Shell to use |
| `timeout` | number | No | 5.0 | Seconds to wait for output |
| `rows` | integer | No | 24 | Terminal height |
| `cols` | integer | No | 80 | Terminal width |
| `truncation` | string | No | config default | Truncation mode |
| `confirmed` | boolean | No | false | Bypass dangerous command gate |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `output` | string | Command output |
| `bytes_read` | integer | Number of bytes |
| `session_id` | string | ID of the temporary session |
| `truncated` | boolean | Whether the output was truncated |

**Example:**

```
session_exec  exec="git log --oneline -5"  timeout=10
```

---

## session_close

Terminate a session gracefully. Uses a three-step shutdown sequence:

1. Send EOF (Ctrl-D)
2. Wait 2s, then send SIGHUP (Unix) or `proc.terminate()` (Windows)
3. Wait 2s, then send SIGKILL (Unix) or `proc.kill()` (Windows)

Closing an already-closed session returns success with `already_closed: true` (idempotent).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Session ID to close |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `exit_status` | integer | Process exit code |
| `already_closed` | boolean | `true` if session was already terminated |

---

## session_resize

Resize the terminal dimensions of an active session. Sends SIGWINCH to notify the process.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Session ID |
| `rows` | integer | Yes | New height |
| `cols` | integer | Yes | New width |

**Returns:** `rows`, `cols` confirming the new dimensions.

---

## session_list

List all active sessions with their status.

No parameters required.

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `sessions` | array | List of session objects |
| `count` | integer | Number of active sessions |

Each session object contains:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session ID |
| `label` | string | Session label |
| `command` | string | The command running |
| `pid` | integer | Process ID |
| `is_alive` | boolean | Whether process is running |
| `created_at` | float | Unix timestamp |
| `last_activity` | float | Last activity timestamp |
| `idle_seconds` | float | Seconds since last activity |
| `tui_active` | boolean | Whether a TUI app is detected |
| `snapshot_available` | boolean | Whether snapshot mode is available |
