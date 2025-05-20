import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional, Set

from .config_manager import ConfigManager
from .path_utils import normalize_path, get_project_root

logger = logging.getLogger(__name__)


def _get_snapshot_dir() -> str:
    config = ConfigManager()
    project_root = get_project_root()
    memory_dir = config.get_path("memory_dir", "cline_docs")
    snapshot_dir = normalize_path(os.path.join(project_root, memory_dir, "dependency_snapshots"))
    os.makedirs(snapshot_dir, exist_ok=True)
    return snapshot_dir


def get_snapshot_path(key: str) -> str:
    sanitized = key.replace(os.sep, "_")
    return os.path.join(_get_snapshot_dir(), f"{sanitized}.json")


def load_snapshot(key: str) -> Optional[Dict[str, Any]]:
    path = get_snapshot_path(key)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading snapshot {path}: {e}")
    return None


def save_snapshot(key: str, data: Dict[str, Any]) -> None:
    path = get_snapshot_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving snapshot {path}: {e}")


def compute_state_hash(paths: Set[str], global_map_path: Optional[str]) -> str:
    tokens = []
    for p in sorted(paths):
        if os.path.exists(p):
            tokens.append(f"{normalize_path(p)}:{os.path.getmtime(p)}")
    if global_map_path and os.path.exists(global_map_path):
        tokens.append(f"{normalize_path(global_map_path)}:{os.path.getmtime(global_map_path)}")
    joined = "|".join(tokens)
    return hashlib.md5(joined.encode()).hexdigest()
