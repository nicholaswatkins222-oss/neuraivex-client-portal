import bleach
from flask import flash, redirect


def strip_html(text: str) -> str:
    """Strip all HTML/script tags from user input."""
    if not text:
        return text
    return bleach.clean(text, tags=[], strip=True).strip()


def check_length(value: str, max_len: int, field_name: str):
    """Return (ok, error_message). Caller handles redirect."""
    if value and len(value) > max_len:
        return False, f'{field_name} must be {max_len} characters or fewer.'
    return True, None
