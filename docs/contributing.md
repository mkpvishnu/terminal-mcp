# Contributing

Contributions to terminal-mcp are welcome! This guide covers how to set up the development environment, run tests, and submit changes.

## Getting Started

### Prerequisites

- Python 3.10 or later
- Git
- A Unix-like environment (Linux or macOS) for full PTY support

### Setup

```bash
git clone https://github.com/mkpvishnu/terminal-mcp.git
cd terminal-mcp
pip install -e ".[dev]"
```

The `[dev]` extra installs test dependencies: `pytest`, `pytest-asyncio`, and `pytest-cov`.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_pty_session.py -v

# Run with coverage
pytest tests/ --cov=terminal_mcp --cov-report=term-missing
```

The test suite includes:
- **Unit tests** for PTYSession, SessionManager, output processing, safety gate, and config
- **Tool handler tests** for all 9 MCP tools (mocked PTY interactions)
- **Integration tests** that spawn real PTY processes (skipped on Windows)
- **Regression tests** for previously fixed bugs

## Project Structure

```
terminal-mcp/
  terminal_mcp/
    __init__.py           # Package metadata
    server.py             # MCP server entry point and tool registration
    pty_session.py        # PTYSession class (core PTY management)
    session_manager.py    # SessionManager (lifecycle, cleanup)
    output_buffer.py      # ANSI stripping, prompt detection, truncation
    safety.py             # Dangerous command detection
    config.py             # Configuration (env var parsing)
    tools/
      __init__.py
      session.py          # Tool handler functions
  tests/
    conftest.py           # Shared fixtures
    test_pty_session.py   # PTYSession unit tests
    test_session_manager.py # SessionManager tests
    test_tools.py         # Tool handler tests
    test_phase1.py        # Phase 1 feature tests
    test_phase2.py        # Phase 2 feature tests
    test_bugfixes.py      # Regression tests
    test_output_buffer.py # Output processing tests
    test_config.py        # Configuration tests
  docs/                   # Documentation
  assets/                 # Banner, demo GIF
  pyproject.toml          # Build config and dependencies
  server.json             # MCP registry metadata
```

## Making Changes

1. **Fork the repository** on GitHub
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/my-feature main
   ```
3. **Write your code** following the existing patterns
4. **Add tests** for new functionality
5. **Run the full test suite** and make sure it passes:
   ```bash
   pytest tests/ -v
   ```
6. **Commit** with a clear, descriptive message:
   ```bash
   git commit -m "feat: add support for XYZ"
   ```
7. **Push** and open a pull request

## Code Style

- Follow existing patterns in the codebase
- Use type hints for function signatures
- Keep functions focused - one function, one responsibility
- Write async handlers for MCP tools (use `asyncio.to_thread()` for blocking calls)
- Protect shared state with locks

## Commit Message Convention

Use conventional commit prefixes:

| Prefix | When to Use |
|--------|-------------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `perf:` | Performance improvements |
| `docs:` | Documentation changes |
| `test:` | Test additions/changes |
| `refactor:` | Code changes that don't fix bugs or add features |
| `chore:` | Maintenance (CI, deps, config) |

## Pull Request Labels

PRs must have one of these labels for the release workflow:

| Label | Version Bump |
|-------|-------------|
| `patch`, `bug`, `dependencies` | Patch (0.0.x) |
| `minor`, `feature` | Minor (0.x.0) |
| `major` | Major (x.0.0) |

## Reporting Issues

Open an issue on GitHub with:
- A clear description of the problem or feature request
- Steps to reproduce (for bugs)
- Your environment (OS, Python version, MCP client)
- Relevant error messages or logs

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](../LICENSE).
