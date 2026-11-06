"""Defense in depth for model prose and legacy API data; never log rejected values.

Heuristic only: not a complete DLP or semantic prompt-injection classifier.
"""

from __future__ import annotations

import re
from typing import Any

from app.security.injection import inspect, normalize, out_of_scope

REDACTED = "[REDACTED]"
BLOCKED = "[CONTENT BLOCKED: unsafe output]"
_SECRET_KEY = re.compile(
    r"^(?:(?:access|refresh|session|auth)[_ -]?)?token$|"
    r"^(?:password|passwd|secret|api[_ -]?key|authorization|cookie|private[_ -]?key|data[_ -]?kek)$|"
    r"[_ -](?:password|secret|api[_ -]?key)$",
    re.I,
)
_PROMPT_LEAK = re.compile(r"(?:system|developer)\s+(?:prompt|instructions?)\s*[:=]", re.I)
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        r"(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|jwt[_ -]?secret|data[_ -]?kek)"
        r"[\"'\s]*[:=][\"'\s]*[^\s,;\"'}]{1,}",
        re.I,
    ),
]


def redact_secrets(text: str) -> str:
    candidate = normalize(text)
    for pattern in _SECRET_PATTERNS:
        candidate = pattern.sub(REDACTED, candidate)
    return candidate if candidate != normalize(text) else text


def unsafe_output(value: Any) -> bool:
    """Reject whole structured outputs, including unsafe text hidden in nested fields."""
    from app.security.redact import mask

    if isinstance(value, dict):
        return any(
            (_SECRET_KEY.search(str(k)) and v not in (None, "", REDACTED)) or unsafe_output(v) for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(unsafe_output(v) for v in value)
    if not isinstance(value, str):
        return False
    normalized = inspect(value)
    return bool(
        normalized.detected
        or bool(_PROMPT_LEAK.search(normalized.text))
        or out_of_scope(normalized.text)
        or redact_secrets(normalized.text) != normalized.text
        or mask(value).counts
    )


def sanitize_public(value: Any, *, pii: bool = False) -> Any:
    """Read-time guard for legacy rows; does NOT mutate/hash-rewrite persisted audit data."""
    if isinstance(value, dict):
        return {k: REDACTED if _SECRET_KEY.search(str(k)) else sanitize_public(v, pii=pii) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_public(v, pii=pii) for v in value]
    if not isinstance(value, str):
        return value
    guard = inspect(value)
    if guard.detected or out_of_scope(guard.text) or _PROMPT_LEAK.search(guard.text):
        return BLOCKED
    cleaned = redact_secrets(guard.text)
    text = cleaned if cleaned != guard.text else value
    if pii:
        from app.security.redact import mask

        masked = mask(text)
        text = masked.text if masked.counts else text
    return text
