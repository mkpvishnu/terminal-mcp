"""Output buffer utilities: ANSI stripping, prompt detection, truncation."""

import re

# Comprehensive ANSI escape sequence pattern.
# Order matters: longer / more-specific alternatives must come first so that
# the regex engine does not stop at an incomplete prefix.
ANSI_PATTERN = re.compile(
    r'\x1b\]'                               # OSC: ESC ] ... BEL or ST
    r'[^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1bP[^\x1b]*\x1b\\'                 # DCS: ESC P ... ST
    r'|\x1b\[[?>=!]?[0-9;]*[a-zA-Z~]'      # CSI: ESC [ [?>=!] params letter/~
    r'|\x1b\[[0-9;]*"[a-zA-Z]'             # CSI with " introducer to final char
    r'|\x1b[()][AB012]'                     # Charset: ESC ( x  /  ESC ) x
    r'|\x1b[>=]'                            # App keypad/cursor mode: ESC > or ESC =
    r'|\x1b[A-Z\\^_@]'                      # Single-char uppercase ESC sequences
    r'|\x1b[a-z]'                           # Single-char lowercase ESC sequences (e.g. ESC c = RIS)
    r'|\x0f|\x0e'                           # Shift-In / Shift-Out (SI / SO)
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


def truncate_output_smart(
    text: str, max_bytes: int = 100_000, mode: str = "tail"
) -> tuple[str, bool]:
    """
    Intelligently truncate text with multiple strategies.

    Modes:
        "tail"      - Keep the beginning, cut the end (same as truncate_output).
        "head_tail" - Keep first 30% + last 70%, insert omitted-line marker.
        "tail_only" - Keep only the end of the text.
        "none"      - Never truncate, return text unchanged.

    Args:
        text:      The text to truncate.
        max_bytes: Maximum UTF-8 byte budget (default 100,000).
        mode:      Truncation strategy.

    Returns:
        (possibly-truncated text, was_truncated: bool)
    """
    if mode == "none":
        return text, False

    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text, False

    if mode == "tail":
        truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
        return truncated + "\n... [output truncated]", True

    if mode == "tail_only":
        # Keep the last max_bytes of the text.
        truncated = encoded[-max_bytes:].decode('utf-8', errors='ignore')
        return "[output truncated] ...\n" + truncated, True

    if mode == "head_tail":
        head_budget = int(max_bytes * 0.30)
        tail_budget = max_bytes - head_budget  # remaining 70%

        head_bytes = encoded[:head_budget]
        tail_bytes = encoded[-tail_budget:]

        # Decode safely (drop partial multi-byte chars at boundaries)
        head_text = head_bytes.decode('utf-8', errors='ignore')
        tail_text = tail_bytes.decode('utf-8', errors='ignore')

        # Count omitted lines: figure out what was cut from the middle.
        # The omitted region starts right after the head bytes and ends
        # right before the tail bytes.
        omitted_bytes = encoded[head_budget:-tail_budget]
        omitted_lines = omitted_bytes.count(b'\n')
        omitted_byte_count = len(omitted_bytes)

        if omitted_lines == 0:
            marker = f"\n... [{omitted_byte_count} bytes omitted] ...\n"
        else:
            marker = f"\n... [{omitted_lines} lines omitted] ...\n"
        return head_text + marker + tail_text, True

    raise ValueError(f"Unknown truncation mode: {mode!r}")
