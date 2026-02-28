"""Dangerous command detection and confirmation gate."""
import re
from typing import Optional


# Default patterns for dangerous commands
DEFAULT_DANGEROUS_PATTERNS = [
    r'\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|.*-rf\s+|.*--no-preserve-root)',  # rm -rf, rm -f
    r'\bdd\s+',                          # dd (disk destroyer)
    r'\bmkfs\b',                         # format filesystem
    r'\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b',  # SQL destructive
    r'\bcurl\b.*\|\s*(ba)?sh\b',         # curl | sh
    r'\bwget\b.*\|\s*(ba)?sh\b',         # wget | sh
    r'\bchmod\s+777\b',                  # chmod 777
    r'\bchmod\s+-R\b',                   # recursive chmod
    r'\bchown\s+-R\b',                   # recursive chown
    r'>\s*/dev/sd[a-z]',                 # write to raw disk
    r'\b:(){ :\|:& };:\b',               # fork bomb
    r'\bshutdown\b',                     # shutdown
    r'\breboot\b',                       # reboot
    r'\binit\s+[06]\b',                  # init 0/6
    r'\bsystemctl\s+(stop|disable|mask)\b',  # systemctl stop
    r'\bkill\s+-9\s',                    # kill -9
    r'\bpkill\s+-9\b',                   # pkill -9
]

_compiled_patterns: Optional[list] = None


def _get_patterns() -> list:
    """Get compiled dangerous command patterns (lazy init)."""
    global _compiled_patterns
    if _compiled_patterns is None:
        import os

        # Allow custom patterns via env var (semicolon-separated)
        custom = os.environ.get("TERMINAL_MCP_DANGEROUS_PATTERNS", "")
        patterns = list(DEFAULT_DANGEROUS_PATTERNS)
        if custom:
            patterns.extend(p.strip() for p in custom.split(";") if p.strip())

        _compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
    return _compiled_patterns


def is_safety_gate_enabled() -> bool:
    """Check if the safety gate is enabled."""
    from terminal_mcp.config import get_config
    return get_config().safety_gate


def check_dangerous(command: str) -> Optional[str]:
    """
    Check if a command matches dangerous patterns.

    Returns the matched pattern description if dangerous, None if safe.
    """
    if not is_safety_gate_enabled():
        return None

    for pattern in _get_patterns():
        match = pattern.search(command)
        if match:
            return f"Matched dangerous pattern: {pattern.pattern}"
    return None


def reset_patterns() -> None:
    """Reset compiled patterns (for testing)."""
    global _compiled_patterns
    _compiled_patterns = None
