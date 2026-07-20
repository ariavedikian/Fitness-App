"""Shared helpers for catalogue text search (foods, exercises)."""


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so a user's ``%`` or ``_`` matches literally.

    Without this, searching "100%" would translate to a pattern where ``%``
    means "any characters" and match every row in the table. Kept in one place
    because it is security-relevant (wildcard injection) and used by every
    catalogue search — duplicating it risks the copies drifting apart.

    Pair with ``.ilike(pattern, escape="\\\\")`` so the backslash is honoured.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
