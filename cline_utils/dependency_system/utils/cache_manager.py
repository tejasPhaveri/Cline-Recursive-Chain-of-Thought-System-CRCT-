import functools
import os
import json
import time
from typing import Dict, Any, Callable, TypeVar, Optional, List

from cline_utils.dependency_system.utils.path_utils import normalize_path

# Define type variable for decorating functions.
F = TypeVar('F', bound=Callable[..., Any])

# Define constants and global variables
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
TRACKER_CACHE_FILE = os.path.join(CACHE_DIR, 'tracker_cache.json')
SUGGESTION_CACHE_FILE = os.path.join(CACHE_DIR, 'suggestion_cache.json')
METADATA_CACHE_FILE = os.path.join(CACHE_DIR, 'metadata_cache.json')
PATH_CACHE_FILE = os.path.join(CACHE_DIR, 'path_cache.json')
MAX_CACHE_SIZE = 1000  # Maximum number of items in each cache

# Caches
tracker_cache: Dict[str, Any] = {}
suggestion_cache: Dict[str, Dict] = {}
metadata_cache: Dict[str, Dict] = {}  # Used for timestamps
path_cache: Dict[str, str] = {}

# Time tracking for cache entries
tracker_cache_access_times: Dict[str, float] = {}
suggestion_cache_access_times: Dict[str, float] = {}
metadata_cache_access_times: Dict[str, float] = {}
path_cache_access_times: Dict[str, float] = {}

# Dependency tracking between cache entries
tracker_cache_dependencies: Dict[str, List[str]] = {}
suggestion_cache_dependencies: Dict[str, List[str]] = {}
metadata_cache_dependencies: Dict[str, List[str]] = {}
path_cache_dependencies: Dict[str, List[str]] = {}

def get_tracker_cache_key(tracker_path: str, tracker_type: str) -> str:
    """
    Generate a cache key for tracker operations.

    Args:
        tracker_path: Path to the tracker file
        tracker_type: Type of tracker

    Returns:
        Cache key string
    """
    from cline_utils.dependency_system.utils.path_utils import normalize_path
    return f"{normalize_path(tracker_path)}:{tracker_type}"

def get_from_tracker_cache(key: str) -> Any:
    """Retrieves a value from the tracker cache if it exists and is not stale."""
    if key in tracker_cache:
        tracker_cache_access_times[key] = time.time()
        return tracker_cache[key]
    return None

def set_in_tracker_cache(key: str, value: Any, dependencies: Optional[List[str]] = None) -> None:
    """Sets a key-value pair in the tracker cache and tracks dependencies."""
    if len(tracker_cache) >= MAX_CACHE_SIZE:
        _cleanup_cache(tracker_cache, tracker_cache_access_times)
    tracker_cache[key] = value
    tracker_cache_access_times[key] = time.time()
    if dependencies:
        for dep in dependencies:
            if dep not in tracker_cache_dependencies:
                tracker_cache_dependencies[dep] = []
            tracker_cache_dependencies[dep].append(key)

def get_from_suggestion_cache(key: str) -> Any:
    """Retrieve a value from the suggestion cache"""
    if key in suggestion_cache:
        suggestion_cache_access_times[key] = time.time()
        return suggestion_cache[key]
    return None

def set_in_suggestion_cache(key: str, value: Any, dependencies: Optional[List[str]] = None) -> None:
    """Sets a key-value pair in the suggestion cache"""
    if len(suggestion_cache) >= MAX_CACHE_SIZE:
        _cleanup_cache(suggestion_cache, suggestion_cache_access_times)
    suggestion_cache[key] = value
    suggestion_cache_access_times[key] = time.time()
    if dependencies:
        for dep in dependencies:
            if dep not in suggestion_cache_dependencies:
                suggestion_cache_dependencies[dep] = []
            suggestion_cache_dependencies[dep].append(key)

def get_from_metadata_cache(key: str) -> Any:
    """Retrieve a value from the metadata cache"""
    if key in metadata_cache:
        metadata_cache_access_times[key] = time.time()
        return metadata_cache[key]
    return None

def set_in_metadata_cache(key: str, value: Any, dependencies: Optional[List[str]] = None) -> None:
    """Set a value in the metadata cache"""
    if len(metadata_cache) >= MAX_CACHE_SIZE:
      _cleanup_cache(metadata_cache, metadata_cache_access_times)
    metadata_cache[key] = value
    metadata_cache_access_times[key] = time.time()
    if dependencies:
      for dep in dependencies:
        if dep not in metadata_cache_dependencies:
          metadata_cache_dependencies[dep] = []
        metadata_cache_dependencies[dep].append(key)

def get_from_path_cache(key: str) -> Any:
    """Retrieve a value from the path cache."""
    if key in path_cache:
        path_cache_access_times[key] = time.time()
        return path_cache[key]
    return None

def set_in_path_cache(key: str, value: Any, dependencies: Optional[List[str]] = None) -> None:
    """Set a value in the path cache."""
    if len(path_cache) >= MAX_CACHE_SIZE:
        _cleanup_cache(path_cache, path_cache_access_times)
    path_cache[key] = value
    path_cache_access_times[key] = time.time()
    if dependencies:
        for dep in dependencies:
            if dep not in path_cache_dependencies:
                path_cache_dependencies[dep] = []
            path_cache_dependencies[dep].append(key)


def _cleanup_cache(cache: Dict, access_times: Dict) -> None:
    """
    Removes the least recently used items from the cache if it exceeds
    the maximum size.

    Args:
        cache: The cache dictionary.
        access_times: A dictionary storing the last access time of each item.
    """
    if len(cache) >= MAX_CACHE_SIZE:
        oldest_key = min(access_times, key=access_times.get)
        del cache[oldest_key]
        del access_times[oldest_key]

def clear_all_caches() -> None:
    """Clears all the caches"""
    global tracker_cache, suggestion_cache, metadata_cache, path_cache
    global tracker_cache_access_times, suggestion_cache_access_times, metadata_cache_access_times, path_cache_access_times

    tracker_cache = {}
    suggestion_cache = {}
    metadata_cache = {}
    path_cache = {}
    tracker_cache_access_times = {}
    suggestion_cache_access_times = {}
    metadata_cache_access_times = {}
    path_cache_access_times = {}

def invalidate_dependent_entries(cache_name: str, key: str) -> None:
    """
    Invalidate cache entries that depend on a given key.

    Args:
      cache_name: The name of the cache ('tracker', 'suggestion', 'metadata', 'path').
      key: The key of the modified entry.
    """
    if cache_name == 'tracker':
        cache = tracker_cache
        access_times = tracker_cache_access_times
        dependencies = tracker_cache_dependencies
    elif cache_name == 'suggestion':
        cache = suggestion_cache
        access_times = suggestion_cache_access_times
        dependencies = suggestion_cache_dependencies
    elif cache_name == 'metadata':
      cache = metadata_cache
      access_times = metadata_cache_access_times
      dependencies = metadata_cache_dependencies
    elif cache_name == 'path':
        cache = path_cache
        access_times = path_cache_access_times
        dependencies = path_cache_dependencies
    else:
      return

    if key in dependencies:
        dependent_keys = dependencies.pop(key)
        for dep_key in dependent_keys:
            if dep_key in cache:
                del cache[dep_key]
                del access_times[dep_key]
                # Recursively invalidate dependencies of dependent keys.
                invalidate_dependent_entries(cache_name, dep_key)

def file_modified(file_path: str, project_root: str, cache_type: str = "all"):
    """
    Call this function whenever a file is modified.  This is crucial for
    invalidating the cache.  Now with granular invalidation based on file type.

    Args:
        file_path: The path to the modified file.
        project_root: The project root directory.
        cache_type: The type of analysis cache to invalidate ('all', 'code', 'file', 'py', 'js', 'md', etc.)
    """
    if cache_type == "all":
        invalidate_dependent_entries(
            'path',
            f"analysis:.*:{normalize_path(file_path)}:"
            f"{normalize_path(project_root)}:.*"
        )
    else:
        invalidate_dependent_entries(
            'path',
            f"analysis:{cache_type}:{normalize_path(file_path)}:"
            f"{normalize_path(project_root)}:.*"
        )

def tracker_modified(tracker_path: str, tracker_type: str, project_root: str, cache_type: str = "all"):
    """
    Call this function whenever a tracker file is modified.  This is crucial for
    invalidating the cache.

    Args:
        tracker_path: The path to the modified tracker file.
        tracker_type: The type of tracker.
        project_root: The project root directory.
        cache_type: The type of analysis cache to invalidate ('all', 'code', 'file', 'py', 'js', 'md', etc.)
    """
    if cache_type == "all":
        invalidate_dependent_entries(
            'tracker',
            get_tracker_cache_key(tracker_path, tracker_type)
        )
    else:
        invalidate_dependent_entries(
            'tracker',
            f"analysis:{cache_type}:.*:{normalize_path(tracker_path)}:"
            f"{normalize_path(project_root)}:.*"
        )
        
def cached(cache_name: str, key_func=None):
    """
    Decorator for caching function results, with support for dependency tracking and invalidation.

    Args:
        cache_name: Name of the cache to use ('tracker', 'suggestion', 'metadata', 'path')
        key_func: Optional function to generate cache key from function arguments

    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default key is function name + args + kwargs
                key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Get from appropriate cache
            if cache_name == 'tracker':
                result = get_from_tracker_cache(key)
            elif cache_name == 'suggestion':
                result = get_from_suggestion_cache(key)
            elif cache_name == 'metadata':
                result = get_from_metadata_cache(key)
            elif cache_name == 'path':
                result = get_from_path_cache(key)
            elif cache_name == 'file_type':
                result = get_from_path_cache(key)
            else:
                raise ValueError(f"Unknown cache name: {cache_name}")

            if result is not None:
                return result

            # Cache miss, call function
            result = func(*args, **kwargs)

            # Determine dependencies (this is where you'd customize based on your function)
            dependencies = []
            # Example:  If caching load_embedding, the dependency is the file itself.
            if func.__name__ == 'load_embedding':
                dependencies.append(f"file:{args[0]}:{args[1]}")  # file:key:embeddings_dir
            # Add other dependency logic as needed for other functions.
            # Example: If caching load_metadata, depend on the metadata file.
            elif func.__name__ == 'load_metadata':
                dependencies.append(f"file:{normalize_path(args[0])}")

            # Store in appropriate cache
            if cache_name == 'tracker':
                set_in_tracker_cache(key, result, dependencies)
            elif cache_name == 'suggestion':
                set_in_suggestion_cache(key, result, dependencies)
            elif cache_name == 'metadata':
                set_in_metadata_cache(key, result, dependencies)
            elif cache_name == 'path':
                set_in_path_cache(key, result, dependencies)
            elif cache_name == 'file_type':
                set_in_path_cache(key, result, dependencies)

            return result
        return wrapper
    return decorator


def check_file_modified(file_path: str) -> bool:
    """
    Checks if a file has been modified since the last recorded timestamp.
    If modified, invalidates relevant cache entries.

    Args:
        file_path: The path to the file.
        project_root: The project root directory.

    Returns:
        True if the file was modified, False otherwise.
    """
    from cline_utils.dependency_system.utils.path_utils import normalize_path, get_file_type
    
    norm_path = normalize_path(file_path)
    cache_key = f"timestamp:{norm_path}"
    current_timestamp = os.path.getmtime(file_path)

    cached_timestamp = get_from_metadata_cache(cache_key)

    if cached_timestamp is None:
        # First time seeing this file, store the timestamp
        set_in_metadata_cache(cache_key, current_timestamp)
        return False  # Consider it not modified for the first run
    
    try:
        current_timestamp = os.path.getmtime(file_path)
    except FileNotFoundError:
        return False

    if current_timestamp > cached_timestamp:
        # File has been modified
        set_in_metadata_cache(cache_key, current_timestamp)  # Update the timestamp
        file_type = get_file_type(file_path)
        file_modified(file_path, os.path.dirname(file_path), file_type)  # Invalidate analysis cache with file type
        return True

    return False

@cached('file_type', key_func=lambda file_path: normalize_path(file_path))
def get_file_type_cached(file_path: str) -> str:
    """
    Cached version of get_file_type.  Avoids redundant file type checks.

    Args:
        file_path: The path to the file.

    Returns:
        The file type string (e.g., "py", "js", "md").
    """
    from cline_utils.dependency_system.utils.path_utils import get_file_type
    return get_file_type(file_path)
