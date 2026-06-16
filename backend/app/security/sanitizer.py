"""Log sanitizer — removes sensitive info from log output."""

from __future__ import annotations

import re

SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r'(api[_-]?key|apikey|token|secret|password|authorization)\s*[:=]\s*[\'"]?[\w\-\.]+', r'\1=***'),
    (r'(Bearer\s+)[\w\-\._]+', r'\1***'),
    (r'(Authorization:\s*Basic\s+)[\w=+/\-]+', r'\1***'),
    (r'(sk-[A-Za-z0-9]{20,})', 'sk-***'),
]


def sanitize(message: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
    return message


class SanitizingHandler:
    """Logging handler wrapper that sanitizes all log records."""

    def __init__(self, handler):
        self._handler = handler

    def emit(self, record):
        record.msg = sanitize(record.msg)
        self._handler.emit(record)
