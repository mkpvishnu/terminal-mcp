"""Tests for output_buffer utilities."""

import pytest
from terminal_mcp.output_buffer import strip_ansi, detect_prompt, truncate_output


class TestStripAnsi:
    def test_strips_color_codes(self):
        text = "\x1b[31mHello\x1b[0m"
        assert strip_ansi(text) == "Hello"

    def test_strips_bold(self):
        text = "\x1b[1mBold\x1b[0m"
        assert strip_ansi(text) == "Bold"

    def test_strips_cursor_movement(self):
        text = "\x1b[2Jclear screen"
        assert strip_ansi(text) == "clear screen"

    def test_strips_osc_sequences(self):
        text = "\x1b]0;window title\x07text"
        assert strip_ansi(text) == "text"

    def test_strips_mode_sequences(self):
        text = "\x1b[?25hshown"
        assert strip_ansi(text) == "shown"

    def test_no_ansi_unchanged(self):
        text = "plain text"
        assert strip_ansi(text) == "plain text"

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_strips_complex_prompt(self):
        text = "\x1b[32muser@host\x1b[0m:\x1b[34m~\x1b[0m$ "
        result = strip_ansi(text)
        assert "user@host" in result
        assert "\x1b" not in result


class TestDetectPrompt:
    def test_dollar_prompt(self):
        assert detect_prompt("user@host:~$ ") is True

    def test_hash_prompt(self):
        assert detect_prompt("root@server:~# ") is True

    def test_gt_prompt(self):
        assert detect_prompt("mysql> ") is True

    def test_percent_prompt(self):
        assert detect_prompt("zsh% ") is True

    def test_python_repl(self):
        assert detect_prompt(">>> ") is True

    def test_user_at_host(self):
        assert detect_prompt("vvishnu@macbook:~$") is True

    def test_no_prompt_mid_output(self):
        assert detect_prompt("Processing file...\nDone.") is False

    def test_empty_string(self):
        assert detect_prompt("") is False

    def test_multiline_with_prompt_at_end(self):
        text = "command output\nmore output\nuser@host:~$ "
        assert detect_prompt(text) is True

    def test_multiline_without_prompt(self):
        text = "line 1\nline 2\nline 3"
        assert detect_prompt(text) is False


class TestTruncateOutput:
    def test_short_text_not_truncated(self):
        text = "hello"
        result, truncated = truncate_output(text, max_bytes=100)
        assert result == "hello"
        assert truncated is False

    def test_long_text_truncated(self):
        text = "a" * 200
        result, truncated = truncate_output(text, max_bytes=100)
        assert truncated is True
        assert "[output truncated]" in result
        assert len(result.encode('utf-8')) > 100  # includes the suffix

    def test_exact_limit_not_truncated(self):
        text = "a" * 100
        result, truncated = truncate_output(text, max_bytes=100)
        assert truncated is False
        assert result == text

    def test_empty_string(self):
        result, truncated = truncate_output("", max_bytes=100)
        assert result == ""
        assert truncated is False

    def test_unicode_handled(self):
        text = "😀" * 30  # Each emoji is 4 bytes
        result, truncated = truncate_output(text, max_bytes=50)
        assert truncated is True
