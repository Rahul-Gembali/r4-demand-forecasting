"""Structured logging configuration with automatic sensitive data redaction."""

import logging
import re
import sys
from typing import Any


class SensitiveDataFilter(logging.Filter):
    """Logging filter that automatically redacts API keys, tokens, and passwords from logs."""

    # Pre-compiled regex patterns for sensitive tokens
    PATTERNS: list[tuple[re.Pattern[str], str]] = [
        # Explicit R4 keys
        (re.compile(r"(r4-(?:admin|operator|viewer)-key-[\w\-]+)", re.IGNORECASE), "[REDACTED_API_KEY]"),
        # Generic Bearer tokens
        (re.compile(r"(Bearer\s+[\w\.\-_]{8,})", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        # Key-value secret patterns (password, secret, api_key, token, authorization)
        (
            re.compile(
                r"((?:password|secret|api_key|token|authorization|auth_token)\s*[:=]\s*['\"]?)([^'\"\s,\}]+)(['\"]?)",
                re.IGNORECASE,
            ),
            r"\1[REDACTED]\3",
        ),
    ]

    def _mask_text(self, text: str) -> str:
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _mask_value(self, val: Any) -> Any:
        if isinstance(val, str):
            return self._mask_text(val)
        if isinstance(val, dict):
            masked_dict = {}
            for k, v in val.items():
                k_str = str(k).lower()
                if any(sec in k_str for sec in ["password", "secret", "token", "api_key", "auth"]):
                    masked_dict[k] = "[REDACTED]"
                else:
                    masked_dict[k] = self._mask_value(v)
            return masked_dict
        if isinstance(val, (list, tuple)):
            masked_seq = [self._mask_value(x) for x in val]
            return tuple(masked_seq) if isinstance(val, tuple) else masked_seq
        return val

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._mask_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = self._mask_value(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(self._mask_value(v) for v in record.args)
        return True


def setup_logger(name: str = "r4_forecast", level: str = "INFO") -> logging.Logger:
    """Configures and returns a structured logger equipped with sensitive data redaction."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
    else:
        for h in logger.handlers:
            # Ensure filter is attached to existing handlers
            if not any(isinstance(f, SensitiveDataFilter) for f in h.filters):
                h.addFilter(SensitiveDataFilter())

    return logger


logger = setup_logger()
get_logger = setup_logger
