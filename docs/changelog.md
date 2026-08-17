# Changelog

## v0.4.7

- **chore: sync __init__.py version and add to release workflow** ([#29](https://github.com/mkpvishnu/terminal-mcp/pull/29))

All notable changes to terminal-mcp are documented here.

---

## v0.4.10

- **Safety gate for `session_exec`** — one-shot execution now checks commands against the dangerous command patterns before running. Previously only `session_send` and `session_interact` were gated ([#19](https://github.com/mkpvishnu/terminal-mcp/issues/19))

## v0.4.9

- **Buffer-trim correctness in `session_wait_for`** — `session_wait_for` now snapshots the absolute buffer position before matching, preventing false matches against stale buffer content that survived a buffer trim ([#20](https://github.com/mkpvishnu/terminal-mcp/issues/20))

## v0.4.8

- **Windows `close()` SIGKILL fallback** — on Windows, `close()` now uses `proc.terminate()` and `proc.kill()` instead of attempting POSIX signals (`SIGHUP`/`SIGKILL`) which don't exist on Windows ([#21](https://github.com/mkpvishnu/terminal-mcp/issues/21))

## v0.4.7

- **SessionManager lock optimization** — `SessionManager.create()` no longer holds the global lock during process spawn. Other operations (`get`, `close`, `list`) are no longer blocked while a new session is being created ([#22](https://github.com/mkpvishnu/terminal-mcp/issues/22))

## v0.4.6

- **Bump actions/github-script from 7 to 8** ([#14](https://github.com/mkpvishnu/terminal-mcp/pull/14))
- **Windows support** — added `pexpect.PopenSpawn` fallback for Windows, with platform-aware process management throughout ([#18](https://github.com/mkpvishnu/terminal-mcp/pull/18))

## v0.4.5

- **Remove stale publish.yml workflow** ([#13](https://github.com/mkpvishnu/terminal-mcp/pull/13))

## v0.4.4

- **Fix release push: use RELEASE_TOKEN for branch protection bypass** ([#12](https://github.com/mkpvishnu/terminal-mcp/pull/12))

## v0.4.3

- **Fix `wait_for` matching command echo** — `session_interact` with `wait_for` no longer matches the echoed input text. Pattern matching now starts from a buffer position anchored before the send ([#6](https://github.com/mkpvishnu/terminal-mcp/issues/6))
- **Fix `wait_for` matching stale buffer content** — uses a monotonic absolute byte counter that survives buffer trims ([#7](https://github.com/mkpvishnu/terminal-mcp/issues/7))
- **Idempotent `session_close`** — closing an already-closed session returns `success: true, already_closed: true` instead of an error ([#8](https://github.com/mkpvishnu/terminal-mcp/issues/8))
- **Comprehensive ANSI stripping** — handles Kitty keyboard protocol, application keypad mode, DCS sequences, and more ([#9](https://github.com/mkpvishnu/terminal-mcp/issues/9))

## v0.4.2

- **Fix `is_alive` race on Linux** — prevents `PtyProcessError` when child processes exit before `waitpid` can reap them

## v0.4.1

- **Auto TUI detection** — detects alternate screen buffer and auto-switches to snapshot mode
- **Output diff mode** — `mode="diff"` returns only changed screen lines
- **Intelligent truncation** — four strategies: `tail`, `head_tail`, `tail_only`, `none`
- **Always-on pyte** — snapshot mode always initialized, `enable_snapshot` deprecated
- **`read_mode` on session_interact** — choose read mode per call
- **Thread-safe screen reads** — buffer lock acquired before pyte reads

## v0.4.0

- **`session_interact` tool** — send + read in one call, halving round trips
- **`session_wait_for` tool** — block until regex pattern matches
- **Dangerous command gate** — 17 built-in patterns, extensible via env var
- **OSC 133 shell integration** — auto-detects command boundaries and exit codes

## v0.3.3

- **Buffer memory cap** — per-session buffer capped at 1MB (configurable)
- **Async event loop** — blocking PTY calls wrapped in `asyncio.to_thread()`
- **SIGTERM cleanup** — signal handler for Docker stop / systemd
- **Close race condition** — handles pexpect exceptions on already-reaped child

## v0.3.1

- **MCP registry publication** — `mcp-name` marker and `server.json`

## v0.3.0

- **Output truncation** — auto-truncation to `max_output_bytes`
- **Environment variable config** — `TERMINAL_MCP_*` env vars
- **`session_resize`** — dynamic terminal resize with SIGWINCH
- **Secret input** — `password` parameter on `session_send`
- **Scrollback buffer** — `pyte.HistoryScreen` with configurable depth
- **`session_exec`** — one-shot command execution
- **PyPI publishing** — `pip install terminal-mcp`

## v0.2.0

- **Special key support** — arrow keys, Tab, Escape, F1-F12, Home/End, etc.
- **Mutual exclusivity** — input types validated as mutually exclusive
- **CI/CD** — GitHub Actions CI (Python 3.10-3.13) and CodeQL scanning

## v0.1.0

- Initial release
- Persistent PTY sessions via pexpect
- Stream and snapshot read modes
- Control character support
- Session management with idle cleanup
