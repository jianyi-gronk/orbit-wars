"""Non-enumerable identifiers used in public URLs."""

import re
import secrets

PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,15}$")


def new_public_id(prefix: str) -> str:
    """Create a random URL-safe identifier without exposing database UUIDs."""
    if not PREFIX_PATTERN.fullmatch(prefix):
        raise ValueError("public ID prefix must be lowercase and 2-16 characters")
    return f"{prefix}_{secrets.token_urlsafe(18)}"
