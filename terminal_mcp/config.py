"""Configuration management for terminal-mcp MCP server."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class TerminalConfig:
    """Configuration for the terminal-mcp MCP server."""

    max_sessions: int = 10
    idle_timeout: int = 1800  # 30 minutes
    default_rows: int = 24
    default_cols: int = 80
    read_settle_timeout: float = 2.0
    max_output_bytes: int = 100_000
    cleanup_interval: int = 60  # seconds between idle cleanup checks
    max_buffer_bytes: int = 1_000_000  # 1MB per-session buffer cap


_ENV_MAP = {
    "TERMINAL_MCP_MAX_SESSIONS": ("max_sessions", int),
    "TERMINAL_MCP_IDLE_TIMEOUT": ("idle_timeout", int),
    "TERMINAL_MCP_DEFAULT_ROWS": ("default_rows", int),
    "TERMINAL_MCP_DEFAULT_COLS": ("default_cols", int),
    "TERMINAL_MCP_READ_SETTLE_TIMEOUT": ("read_settle_timeout", float),
    "TERMINAL_MCP_MAX_OUTPUT_BYTES": ("max_output_bytes", int),
    "TERMINAL_MCP_CLEANUP_INTERVAL": ("cleanup_interval", int),
    "TERMINAL_MCP_MAX_BUFFER_BYTES": ("max_buffer_bytes", int),
}

# Global config singleton
_config: Optional[TerminalConfig] = None


def get_config() -> TerminalConfig:
    """Get or create the global configuration."""
    global _config
    if _config is None:
        _config = TerminalConfig()
        for env_var, (field_name, converter) in _ENV_MAP.items():
            value = os.environ.get(env_var)
            if value:
                try:
                    setattr(_config, field_name, converter(value))
                except (ValueError, TypeError):
                    pass  # invalid values silently ignored
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
