"""Small, shared URL allow-list helpers for imported external links."""

from urllib.parse import urlsplit


def safe_external_url(value):
    """Return a usable HTTP(S) URL or ``None`` for blank/unsafe input."""
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate or any(ord(character) < 32 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def safe_internal_path(value):
    """Return a same-origin absolute path or ``None`` for unsafe navigation."""
    if value is None:
        return None
    candidate = str(value).strip()
    if (
        not candidate
        or any(ord(character) < 32 for character in candidate)
        or "\\" in candidate
    ):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return None
    return candidate
