"""Logging com remoção de segredos (cookies, tokens, senhas, credenciais em URIs)."""

from __future__ import annotations

import logging
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(sessionid|csrftoken|ds_user_id|mid|ig_did|rur)=([^;\s&\"']+)"), r"\1=***"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1***"),
    (re.compile(r"(?i)(password|senha|secret|token|cookie)(\"?\s*[:=]\s*\"?)([^\s\"',;&]+)"), r"\1\2***"),
    (re.compile(r"(?i)(mongodb(?:\+srv)?://|redis://)([^:@/\s]+):([^@/\s]+)@"), r"\1\2:***@"),
    (re.compile(r"(?i)(redis://):([^@/\s]+)@"), r"\1:***@"),
]


def redact(text: str) -> str:
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - mensagem malformada
            return True
        record.msg = redact(message)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("pymongo", "urllib3", "instaloader"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def safe_error_summary(exc: BaseException, limit: int = 300) -> str:
    text = redact(f"{type(exc).__name__}: {exc}")
    return text if len(text) <= limit else text[: limit - 1] + "…"
