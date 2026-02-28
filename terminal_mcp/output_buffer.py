"""Output buffer utilities: ANSI stripping, prompt detection, truncation."""

import re

# Comprehensive ANSI escape sequence pattern
ANSI_PATTERN = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'      # CSI sequences: ESC [ ... letter
    r'|\x1b\][^\x07]*\x07'         # OSC sequences: ESC ] ... BEL
    r'|\x1b[()][AB012]'            # Charset sequences: ESC ( x
    r'|\x1b\[[\?]?[0-9;]*[hlm]'   # Mode sequences: ESC [ ? ... h/l/m
    r'|\x1b[A-Z]'                  # Single-letter ESC sequences
    r'|\x0f|\x0e'                   # Shift in/out
)

# Prompt detection pattern: ends with common prompt chars or contains user@host
PROMPT_PATTERN = re.compile(
    r'[$#>%]\s*$'           # Ends with $, #, >, or %
    r'|>>>\s*$'             # Python REPL
    r'|\w+@[\w.-]+[:#~]'   # user@host: patterns
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub('', text)


def detect_prompt(text: str) -> bool:
    """Heuristic detection of a shell/REPL prompt at end of output."""
    lines = text.rstrip().split('\n')
    if not lines:
        return False
    last_line = lines[-1].strip()
    return bool(PROMPT_PATTERN.search(last_line))


def truncate_output(text: str, max_bytes: int = 100_000) -> tuple[str, bool]:
    """
    Truncate text to at most max_bytes UTF-8 bytes.

    Returns:
        (possibly-truncated text, was_truncated: bool)
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return truncated + "\n... [output truncated]", True
