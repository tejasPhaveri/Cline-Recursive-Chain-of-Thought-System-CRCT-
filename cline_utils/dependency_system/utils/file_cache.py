import os
import logging
from typing import Optional

from .cache_manager import cached
from .path_utils import normalize_path

logger = logging.getLogger(__name__)

@cached(
    "file_contents",
    key_func=lambda file_path: f"file_contents:{normalize_path(file_path)}:{os.path.getmtime(file_path) if os.path.exists(file_path) else 'missing'}"
)
def read_file_cached(file_path: str) -> Optional[str]:
    """Read a text file with caching based on modification time."""
    norm_path = normalize_path(file_path)
    if not os.path.exists(norm_path):
        logger.debug(f"File not found: {norm_path}")
        return None
    try:
        with open(norm_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.exception(f"Error reading file {norm_path}: {e}")
        return None