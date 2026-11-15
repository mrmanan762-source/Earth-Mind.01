"""Security boundary helpers for the EarthMind backend tool infrastructure.

Responsibilities:
- Redact secrets (API keys, tokens, passwords) from logs, errors and payloads.
- Enforce request/result size limits.
- Provide a conservative, shared secret-detection regex set.

Design rules:
- All external API credentials remain backend-only and are never echoed to
  callers, logs or frontend responses.
- Redaction is applied defensively to both log lines and normalized error text.
"""

from typing import Any, Dict, Iterable, List

# Keys whose values must always be treated as secrets when redacting mappings.
SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "api-key",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "authorization",
    "auth",
    "credential",
    "client_secret",
    "private_key",
    "bearer",
)

REDACTION_MASK = "***REDACTED***"

# Common provider key prefixes / shapes to redact inside free text.
_SECRET_PATTERNS = (
    # OpenAI / Tavily style "sk-..." / "tvly-..." keys
    r"(?:sk|tvly|pk|rk|gsk|xox[baprs])-[A-Za-z0-9_\-]{8,}",
    # Google API keys
    r"AIza[0-9A-Za-z_\-]{20,}",
    # Bearer tokens
    r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}",
    # key=value / "key": "value" style assignments for sensitive names
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret)"
    r"(\s*[=:]\s*[\"']?)([^\s\"',}]{4,})",
)


def is_sensitive_key(key: str) -> bool:
    """Return True when a mapping key name indicates a secret value."""
    lowered = str(key).lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def redact_text(text: str) -> str:
    """Redact known secret shapes from a free-text string."""
    if not text:
        return text
    import re

    redacted = text
    for pattern in _SECRET_PATTERNS:
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue

        def _repl(match: "re.Match[str]") -> str:
            # Preserve the sensitive name / separator, mask only the value.
            if match.lastindex and match.lastindex >= 3:
                return f"{match.group(1)}{match.group(2)}{REDACTION_MASK}"
            return REDACTION_MASK

        redacted = compiled.sub(_repl, redacted)
    return redacted


def redact_mapping(data: Any, *, max_depth: int = 8) -> Any:
    """Recursively redact sensitive values from mappings/lists for safe logging."""
    if max_depth < 0:
        return REDACTION_MASK

    if isinstance(data, dict):
        return {
            key: (REDACTION_MASK if is_sensitive_key(key) else redact_mapping(value, max_depth=max_depth - 1))
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [redact_mapping(item, max_depth=max_depth - 1) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


def payload_size_bytes(payload: Any) -> int:
    """Estimate the serialized size of a payload in bytes."""
    import json

    if payload is None:
        return 0
    if isinstance(payload, bytes):
        return len(payload)
    if isinstance(payload, str):
        return len(payload.encode("utf-8", errors="ignore"))
    try:
        return len(json.dumps(payload, default=str).encode("utf-8", errors="ignore"))
    except (TypeError, ValueError):
        return len(str(payload).encode("utf-8", errors="ignore"))


def enforce_payload_limit(payload: Any, limit_bytes: int, *, label: str = "payload") -> None:
    """Raise ValueError when a payload exceeds the configured byte limit."""
    if limit_bytes <= 0:
        return
    size = payload_size_bytes(payload)
    if size > limit_bytes:
        raise ValueError(f"{label} size {size} bytes exceeds limit of {limit_bytes} bytes")


def sanitize_error_message(message: str) -> str:
    """Redact secrets from an error message string."""
    return redact_text(str(message))


def collect_secret_values(settings_obj: Any) -> List[str]:
    """Best-effort collection of configured secret values for exact-match redaction.

    Used only for defensive redaction; never persisted or returned to callers.
    """
    values: List[str] = []
    try:
        data = settings_obj.model_dump() if hasattr(settings_obj, "model_dump") else dict(settings_obj)
    except Exception:
        return values

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if is_sensitive_key(key) and isinstance(value, str) and value.strip():
                    values.append(value)
                else:
                    _walk(value)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)

    _walk(data)
    return values


def redact_known_values(text: str, known_values: Iterable[str]) -> str:
    """Redact any exact secret values that appear in a string."""
    if not text:
        return text
    redacted = text
    for value in known_values:
        if value and len(value) >= 4:
            redacted = redacted.replace(value, REDACTION_MASK)
    return redacted
