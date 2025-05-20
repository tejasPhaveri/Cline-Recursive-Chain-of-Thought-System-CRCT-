"""Utility functions for reading files with caching support."""

import os
from typing import Optional

from .cache_manager import cached
from .path_utils import normalize_path


@cached(
    "file_contents",
    key_func=lambda path: f"read_file:{normalize_path(path)}:{os.path.getmtime(path) if os.path.exists(path) else 'na'}",
    ttl=0,
)
def read_file_cached(file_path: str) -> Optional[str]:
    """Return the content of ``file_path`` using the cache.

    If the file does not exist or cannot be read, ``None`` is returned.
    The cache key includes the file's modification time so the
    cached value automatically refreshes when the file changes.
    """
    norm_path = normalize_path(file_path)
    if not os.path.isfile(norm_path):
        return None
    try:
        with open(norm_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

