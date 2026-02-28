"""Configuration management for terminal-mcp MCP server."""

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


# Global config singleton
_config: Optional[TerminalConfig] = None


def get_config() -> TerminalConfig:
    """Get or create the global configuration."""
    global _config
    if _config is None:
        _config = TerminalConfig()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
