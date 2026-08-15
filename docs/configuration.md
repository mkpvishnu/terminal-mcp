# Configuration

terminal-mcp is configured via environment variables prefixed with `TERMINAL_MCP_`. Since the server runs as a subprocess of your MCP client, these variables must be set in the client's configuration, not in your shell profile.

## Settings Reference

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Max sessions | `TERMINAL_MCP_MAX_SESSIONS` | `10` | Maximum number of concurrent PTY sessions |
| Idle timeout | `TERMINAL_MCP_IDLE_TIMEOUT` | `1800` | Seconds of inactivity before a session is auto-closed (30 minutes) |
| Default rows | `TERMINAL_MCP_DEFAULT_ROWS` | `24` | Default terminal height for new sessions |
| Default cols | `TERMINAL_MCP_DEFAULT_COLS` | `80` | Default terminal width for new sessions |
| Read settle timeout | `TERMINAL_MCP_READ_SETTLE_TIMEOUT` | `2.0` | Seconds to wait for output to settle in stream mode |
| Max output bytes | `TERMINAL_MCP_MAX_OUTPUT_BYTES` | `100000` | Maximum bytes returned per read operation (100KB) |
| Cleanup interval | `TERMINAL_MCP_CLEANUP_INTERVAL` | `60` | Seconds between idle session cleanup sweeps |
| Buffer cap | `TERMINAL_MCP_MAX_BUFFER_BYTES` | `1000000` | Maximum per-session PTY buffer size in bytes (1MB) |
| Safety gate | `TERMINAL_MCP_SAFETY_GATE` | `on` | Enable/disable the dangerous command safety gate (`on` or `off`) |
| Dangerous patterns | `TERMINAL_MCP_DANGEROUS_PATTERNS` | built-in | Additional dangerous command patterns (semicolon-separated regexes) |
| Truncation mode | `TERMINAL_MCP_TRUNCATION_MODE` | `tail` | Default output truncation strategy |

## Per-Session Overrides

Some settings can be overridden per session via `session_create`:

| Parameter | Setting It Overrides |
|-----------|---------------------|
| `rows` | `TERMINAL_MCP_DEFAULT_ROWS` |
| `cols` | `TERMINAL_MCP_DEFAULT_COLS` |
| `idle_timeout` | `TERMINAL_MCP_IDLE_TIMEOUT` |
| `scrollback_lines` | No global env var (defaults to 1000) |

Set `scrollback_lines=0` to disable scrollback history for a session.

## Client Configuration Examples

### Claude Code

Add to `~/.claude.json` (global) or `.mcp.json` (per-project):

```json
{
  "mcpServers": {
    "terminal": {
      "command": "uvx",
      "args": ["terminal-mcp"],
      "env": {
        "TERMINAL_MCP_MAX_SESSIONS": "20",
        "TERMINAL_MCP_IDLE_TIMEOUT": "3600",
        "TERMINAL_MCP_SAFETY_GATE": "off",
        "TERMINAL_MCP_TRUNCATION_MODE": "head_tail"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "terminal": {
      "command": "uvx",
      "args": ["terminal-mcp"],
      "env": {
        "TERMINAL_MCP_MAX_SESSIONS": "20",
        "TERMINAL_MCP_IDLE_TIMEOUT": "3600"
      }
    }
  }
}
```

### VS Code / Cursor

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "terminal-mcp": {
      "command": "uvx",
      "args": ["terminal-mcp"],
      "env": {
        "TERMINAL_MCP_MAX_SESSIONS": "20",
        "TERMINAL_MCP_IDLE_TIMEOUT": "3600"
      }
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "terminal": {
      "command": "uvx",
      "args": ["terminal-mcp"],
      "env": {
        "TERMINAL_MCP_MAX_SESSIONS": "20"
      }
    }
  }
}
```

### Manual / Testing

When running the server manually for testing:

```bash
TERMINAL_MCP_MAX_SESSIONS=20 TERMINAL_MCP_SAFETY_GATE=off uvx terminal-mcp
```

## Truncation Modes

Output truncation prevents large command outputs from overflowing the AI's context window. Four strategies are available:

| Mode | Behavior | Best For |
|------|----------|----------|
| `tail` (default) | Keeps the beginning of the output, truncates the end | General use |
| `head_tail` | Keeps first 30% and last 70%, inserts a line-count marker | Logs with useful header and footer |
| `tail_only` | Keeps only the end of the output | Build logs, compilation output |
| `none` | No truncation | When you need everything |

Set globally via `TERMINAL_MCP_TRUNCATION_MODE` or per-call via the `truncation` parameter on `session_read`, `session_interact`, `session_exec`, and `session_wait_for`.

## Buffer Management

Each session maintains an in-memory byte buffer that accumulates all PTY output. When this buffer exceeds `max_buffer_bytes`, older bytes are trimmed from the front.

The buffer uses an absolute position counter (`_total_bytes_written`) that is monotonically increasing and survives trims. This ensures that pattern matching and read operations always reference the correct position in the output stream, even after old data has been discarded.

To increase the buffer for sessions with large output:

```json
{
  "env": {
    "TERMINAL_MCP_MAX_BUFFER_BYTES": "5000000"
  }
}
```
