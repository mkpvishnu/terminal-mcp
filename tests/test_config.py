"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch

from terminal_mcp.config import TerminalConfig, get_config, reset_config


class TestTerminalConfig:
    def test_default_values(self):
        config = TerminalConfig()
        assert config.max_sessions == 10
        assert config.idle_timeout == 1800
        assert config.default_rows == 24
        assert config.default_cols == 80
        assert config.read_settle_timeout == 2.0
        assert config.max_output_bytes == 100_000
        assert config.cleanup_interval == 60


class TestGetConfig:
    def test_singleton_caches_config(self):
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reset_clears_singleton(self):
        c1 = get_config()
        reset_config()
        c2 = get_config()
        assert c1 is not c2

    def test_max_sessions_from_env(self):
        with patch.dict(os.environ, {"TERMINAL_MCP_MAX_SESSIONS": "5"}):
            reset_config()
            config = get_config()
            assert config.max_sessions == 5

    def test_read_settle_timeout_float_from_env(self):
        with patch.dict(os.environ, {"TERMINAL_MCP_READ_SETTLE_TIMEOUT": "3.5"}):
            reset_config()
            config = get_config()
            assert config.read_settle_timeout == 3.5

    def test_multiple_env_vars(self):
        with patch.dict(os.environ, {
            "TERMINAL_MCP_MAX_SESSIONS": "20",
            "TERMINAL_MCP_IDLE_TIMEOUT": "600",
        }):
            reset_config()
            config = get_config()
            assert config.max_sessions == 20
            assert config.idle_timeout == 600
            assert config.default_rows == 24  # unchanged

    def test_invalid_env_var_ignored(self):
        with patch.dict(os.environ, {"TERMINAL_MCP_MAX_SESSIONS": "not_a_number"}):
            reset_config()
            config = get_config()
            assert config.max_sessions == 10  # default

    def test_empty_env_var_ignored(self):
        with patch.dict(os.environ, {"TERMINAL_MCP_MAX_SESSIONS": ""}):
            reset_config()
            config = get_config()
            assert config.max_sessions == 10  # default
