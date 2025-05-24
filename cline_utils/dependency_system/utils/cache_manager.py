"""
Cache management module with dynamic, TTL-based caching for dependency tracking system.
Supports on-demand cache creation, automatic expiration, and granular invalidation.
"""

import functools
import os
import time
import re
import json
from typing import Dict, Any, Callable, TypeVar, Optional, List, Tuple
import logging

from .path_utils import normalize_path, get_project_root # Added get_project_root

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])

# Configuration
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
DEFAULT_MAX_SIZE = 1000  # Default max items per cache
DEFAULT_TTL = 600  # 10 minutes in seconds
CACHE_SIZES = {
    "embeddings_generation": 100,  # Smaller for heavy data
    "key_generation": 5000,        # Larger for key maps
    "default": DEFAULT_MAX_SIZE
}

class Cache:
    """A single cache instance with LRU eviction, per-entry TTL, and dependency tracking."""
    def __init__(self, name: str, ttl: int = DEFAULT_TTL, max_size: int = DEFAULT_MAX_SIZE):
        self.name = name
        self.data: Dict[str, Tuple[Any, float, Optional[float]]] = {}  # (value, access_time, expiry_time)
        self.dependencies: Dict[str, List[str]] = {}  # key -> dependent keys
        self.reverse_deps: Dict[str, List[str]] = {}  # key -> keys that depend on it
        self.creation_time = time.time()
        self.default_ttl = ttl
        self.max_size = CACHE_SIZES.get(name, max_size)
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        if key in self.data:
            value, _, expiry = self.data[key]
            if expiry is None or time.time() < expiry:
                self.data[key] = (value, time.time(), expiry)  # Update access time
                self.hits += 1
                return value
            else:
                try:
                    # Ensure _remove_key is called to handle dependencies correctly
                    self._remove_key(key) 
                except KeyError: pass # Already deleted by another thread
        self.misses += 1
        return None

    def set(self, key: str, value: Any, dependencies: Optional[List[str]] = None, ttl: Optional[int] = None) -> None:
        if len(self.data) >= self.max_size:
            self._evict_lru()
        expiry = time.time() + (ttl if ttl is not None else self.default_ttl) if ttl != 0 else None
        self.data[key] = (value, time.time(), expiry)
        if dependencies:
            for dep in dependencies:
                if dep not in self.dependencies:
                    self.dependencies[dep] = []
                self.dependencies[dep].append(key)
                if key not in self.reverse_deps:
                    self.reverse_deps[key] = []
                self.reverse_deps[key].append(dep)

    def _evict_lru(self) -> None:
        if not self.data:
            return
        try:
            lru_key = min(self.data, key=lambda k: self.data[k][1])
            self._remove_key(lru_key)
        except ValueError: 
            pass
        except RuntimeError: 
            logger.warning(f"Cache '{self.name}': RuntimeError during LRU eviction. Cache may be highly contended.")


    def _remove_key(self, key: str) -> None: 
        try:
            if key in self.data:
                del self.data[key]
            
            # Clean up reverse dependencies: remove 'key' from the dependency lists of its dependents
            if key in self.reverse_deps:
                for dependent_key in list(self.reverse_deps.get(key, [])): # Iterate a copy
                    if dependent_key in self.dependencies: # Check if dependent_key still in self.dependencies
                        try:
                            self.dependencies[dependent_key].remove(key)
                            if not self.dependencies[dependent_key]:
                                del self.dependencies[dependent_key]
                        except (ValueError, KeyError): pass # Item already removed or dep dict changed
                try:
                    del self.reverse_deps[key] # Remove key from reverse_deps itself
                except KeyError: pass
            
        except KeyError: 
            pass

    def cleanup_expired(self) -> None:
        """Remove all expired entries."""
        current_time = time.time()
        try:
            items_to_check = list(self.data.items())
        except RuntimeError: 
            logger.warning(f"Cache '{self.name}': RuntimeError getting items for cleanup, likely high contention. Skipping this cleanup cycle.")
            return

        expired_keys_to_remove = [k for k, (_, _, expiry) in items_to_check if expiry and current_time > expiry]
        
        if expired_keys_to_remove:
            keys_actually_removed_count = 0
            for key_to_remove in expired_keys_to_remove:
                if key_to_remove in self.data: 
                    _val, _acc_time, exp_check_final = self.data[key_to_remove]
                    if exp_check_final and current_time > exp_check_final: 
                        self._remove_key(key_to_remove) 
                        keys_actually_removed_count +=1
            if keys_actually_removed_count > 0:
                 logger.debug(f"Cache '{self.name}': Cleaned up {keys_actually_removed_count} expired entries.")


    def is_expired(self) -> bool: 
        return (time.time() - self.creation_time) > self.default_ttl and not self.data

    def invalidate(self, key_pattern: str) -> None:
        """Invalidate entries matching a key pattern (supports regex). Also invalidates dependent entries."""
        compiled_pattern = re.compile(key_pattern)
        # Iterate over a copy of keys for safety during removal
        keys_to_remove_initial = [k for k in list(self.data.keys()) if compiled_pattern.match(k)]
        
        processed_for_invalidation = set()
        queue_to_invalidate = list(keys_to_remove_initial)

        while queue_to_invalidate:
            key_to_invalidate = queue_to_invalidate.pop(0)
            if key_to_invalidate in processed_for_invalidation:
                continue
            
            self._remove_key(key_to_invalidate) # Handles removal from self.data and basic reverse_deps cleanup
            processed_for_invalidation.add(key_to_invalidate)

            if key_to_invalidate in self.dependencies:
                dependent_keys_list = list(self.dependencies.get(key_to_invalidate, [])) 
                for dep_key in dependent_keys_list:
                    if dep_key not in processed_for_invalidation:
                        queue_to_invalidate.append(dep_key)
                try:
                    del self.dependencies[key_to_invalidate] 
                except KeyError:
                    pass
        
        if processed_for_invalidation:
            logger.debug(f"Cache '{self.name}': Invalidated {len(processed_for_invalidation)} entries matching pattern '{key_pattern}'.")


    def stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "size": len(self.data)}

class CacheManager:
    """Manages multiple caches with persistence and cleanup."""
    def __init__(self, persist: bool = False):
        self.caches: Dict[str, Cache] = {}
        self.persist = persist
        if persist:
            os.makedirs(CACHE_DIR, exist_ok=True)
            self._load_persistent_caches()

    def get_cache(self, cache_name: str, ttl: int = DEFAULT_TTL) -> Cache:
        """Retrieve or create a cache by name."""
        if cache_name not in self.caches or self.caches[cache_name].is_expired():
            self.caches[cache_name] = Cache(cache_name, ttl)
            logger.debug(f"Spun up new cache: {cache_name} with TTL {ttl}s")
        return self.caches[cache_name]

    def cleanup(self) -> None:
        """Remove expired caches."""
        expired = [name for name, cache in list(self.caches.items()) if cache.is_expired()]
        for name in expired:
            if self.persist:
                self._save_cache(name)
            if name in self.caches: 
                del self.caches[name]
                logger.debug(f"Spun down expired cache: {name}")
        for cache in list(self.caches.values()): 
            cache.cleanup_expired()

    def clear_all(self) -> None:
        if self.persist:
            for name in list(self.caches.keys()): 
                self._save_cache(name)
        self.caches.clear()
        logger.info("All caches cleared.")

    def _save_cache(self, cache_name: str) -> None:
        if cache_name in self.caches:
            cache_file = os.path.join(CACHE_DIR, f"{cache_name}.json")
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    current_cache_data_items = list(self.caches[cache_name].data.items())
                    data = {
                        "data": {k: v[0] for k, v in current_cache_data_items if v[2] is None or v[2] > time.time()},
                        "dependencies": dict(self.caches[cache_name].dependencies) 
                    }
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Failed to save cache {cache_name}: {e}")

    def _load_persistent_caches(self) -> None: 
        if not os.path.exists(CACHE_DIR): return 
        for cache_file in os.listdir(CACHE_DIR):
            if cache_file.endswith('.json'):
                cache_name = cache_file[:-5]
                try:
                    with open(os.path.join(CACHE_DIR, cache_file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        cache = Cache(cache_name)
                        for key, value in data.get("data", {}).items(): 
                            cache.set(key, value, ttl=0) 
                        cache.dependencies = data.get("dependencies", {})
                        self.caches[cache_name] = cache
                    logger.debug(f"Loaded persistent cache: {cache_name}")
                except Exception as e:
                    logger.error(f"Failed to load cache {cache_name}: {e}")

cache_manager = CacheManager(persist=False)  

def get_tracker_cache_key(tracker_path: str, tracker_type: str) -> str:
    return f"tracker:{normalize_path(tracker_path)}:{tracker_type}"

def clear_all_caches() -> None:
    """Clear all caches in the manager."""
    cache_manager.clear_all()

def invalidate_dependent_entries(cache_name: str, key_pattern: str) -> None: 
    """Invalidate cache entries matching a key pattern in a specific cache."""
    cache = cache_manager.get_cache(cache_name)
    cache.invalidate(key_pattern) 

def file_modified(file_path: str, project_root: str, cache_type: str = "all") -> None:
    """Invalidate caches when a file is modified."""
    norm_path = normalize_path(file_path)
    # Use raw f-string for regex pattern
    key_pattern_to_invalidate = rf".*(?::|\||^){re.escape(norm_path)}(?:\||$).*" # FIXED
    
    caches_to_scan = [cache_manager.get_cache(cache_name) for cache_name in list(cache_manager.caches.keys())] \
                     if cache_type == "all" else \
                     [cache_manager.get_cache(cache_type)]
    
    for cache_instance in caches_to_scan:
        if cache_instance: 
            cache_instance.invalidate(key_pattern_to_invalidate)
    logger.debug(f"Invalidated entries matching path '{norm_path}' (pattern '{key_pattern_to_invalidate}') in cache(s) type '{cache_type}'.")


def tracker_modified(tracker_path: str, tracker_type: str, project_root: str, cache_type: str = "all") -> None:
    """Invalidate caches when a tracker is modified."""
    norm_path = normalize_path(tracker_path)
    key_pattern_for_tracker: str
    
    if cache_type == "all":
        # Use raw f-string for regex pattern
        generic_path_pattern = rf".*(?::|\||^){re.escape(norm_path)}(?:\||$).*" # FIXED
        specific_tracker_data_pattern = rf"^tracker_data_structured:{re.escape(norm_path)}:.*" # FIXED
        
        cache_data_struct = cache_manager.get_cache("tracker_data_structured")
        if cache_data_struct:
            cache_data_struct.invalidate(specific_tracker_data_pattern)
            logger.debug(f"Invalidated '{specific_tracker_data_pattern}' in 'tracker_data_structured'.")

        for cache_name_iter in list(cache_manager.caches.keys()):
            if cache_name_iter != "tracker_data_structured": 
                cache_instance_iter = cache_manager.get_cache(cache_name_iter)
                if cache_instance_iter:
                    cache_instance_iter.invalidate(generic_path_pattern)
        logger.debug(f"Additionally scanned other caches for generic pattern '{generic_path_pattern}'.")

    else: 
        if cache_type == "tracker_data_structured":
            key_pattern_for_tracker = rf"^tracker_data_structured:{re.escape(norm_path)}:.*" # FIXED
        else: 
            key_pattern_for_tracker = rf".*(?::|\||^){re.escape(norm_path)}(?:\||$).*" # FIXED
        
        cache_instance_tracker = cache_manager.get_cache(cache_type)
        if cache_instance_tracker:
            cache_instance_tracker.invalidate(key_pattern_for_tracker)
        logger.debug(f"Invalidated entries for tracker '{norm_path}' (pattern '{key_pattern_for_tracker}') in cache type '{cache_type}'.")


def cached(cache_name: str, key_func: Optional[Callable] = None, ttl: Optional[int] = DEFAULT_TTL):
    """Decorator for caching with dynamic dependencies and TTL."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            effective_key_func = key_func
            if effective_key_func is None:
                def default_key_func_impl(*d_args, **d_kwargs):
                    actual_args_for_key = d_args
                    if d_args:
                        first_arg = d_args[0]
                        # Check if func is a method of first_arg's class or first_arg itself
                        is_method = False
                        try:
                            # For instance methods
                            if hasattr(first_arg, func.__name__) and getattr(first_arg, func.__name__).__func__ == func.__func__:
                                is_method = True
                        except AttributeError: # func might not have __func__ (e.g. built-in or C extension)
                            pass
                        if not is_method and hasattr(type(first_arg), func.__name__):
                            # For class methods (where first_arg is cls) or instance methods called via class
                             try:
                                 if getattr(type(first_arg), func.__name__).__func__ == func.__func__:
                                     is_method = True
                             except AttributeError:
                                 pass
                        
                        if is_method:
                               actual_args_for_key = d_args[1:]

                    d_key_parts = [str(arg_item) for arg_item in actual_args_for_key] + \
                                [f"{k_item}={v_item}" for k_item, v_item in sorted(d_kwargs.items())]
                    return f"{func.__name__}::{'|'.join(d_key_parts)}"
                effective_key_func = default_key_func_impl
            
            key = effective_key_func(*args, **kwargs)
            cache_ttl_to_use = ttl if ttl is not None else DEFAULT_TTL
            cache = cache_manager.get_cache(cache_name, cache_ttl_to_use)
            
            result = cache.get(key)
            if result is not None:
                return result
            
            result = func(*args, **kwargs)
            
            dependencies_list_from_result = []
            value_to_cache = result
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
                value_to_cache, dependencies_list_from_result = result
            elif func.__name__ in ['load_embedding', 'load_metadata', 'analyze_file', 'analyze_project', 'get_file_type']:
                # Check if first arg (after potential self/cls) is an existing file path
                actual_first_arg_for_dep = args[0] if args else None
                if args:
                    first_arg = args[0]
                    is_method = False
                    try:
                        if hasattr(first_arg, func.__name__) and getattr(first_arg, func.__name__).__func__ == func.__func__:
                            is_method = True
                    except AttributeError: pass
                    if not is_method and hasattr(type(first_arg), func.__name__):
                         try:
                             if getattr(type(first_arg), func.__name__).__func__ == func.__func__:
                                 is_method = True
                         except AttributeError: pass
                    
                    if is_method: # If it's a method, the path argument is likely the second one
                        if len(args) > 1 : actual_first_arg_for_dep = args[1]
                        else: actual_first_arg_for_dep = None 
                    # Else, actual_first_arg_for_dep remains args[0] (for standalone functions)

                if actual_first_arg_for_dep and isinstance(actual_first_arg_for_dep, str) and os.path.exists(actual_first_arg_for_dep):
                    dependencies_list_from_result.append(f"file:{normalize_path(actual_first_arg_for_dep)}")
            
            cache.set(key, value_to_cache, dependencies_list_from_result, ttl=cache_ttl_to_use)
            
            cache_manager.cleanup() 
            return value_to_cache
        return wrapper
    return decorator

def check_file_modified(file_path: str) -> bool:
    """Check if a file has been modified, updating metadata cache."""
    norm_path = normalize_path(file_path)
    cache_key = f"timestamp:{norm_path}"
    cache = cache_manager.get_cache("metadata") 
    
    current_project_root = get_project_root()

    if not os.path.exists(file_path):
        if cache.get(cache_key) is not None: 
            cache.invalidate(cache_key) 
            file_modified(norm_path, current_project_root) 
            return True 
        return False 

    current_timestamp = os.path.getmtime(file_path)
    cached_timestamp_val = cache.get(cache_key) 
    
    if cached_timestamp_val is None or current_timestamp > cached_timestamp_val:
        cache.set(cache_key, current_timestamp, ttl=None) 
        file_modified(norm_path, current_project_root) 
        return True
    return False

def get_file_type_cached(file_path: str) -> str:
    """Cached version of get_file_type."""
    from .path_utils import get_file_type
    return get_file_type(file_path)

def get_cache_stats(cache_name: str) -> Dict[str, int]:
    """Get hit/miss stats for a cache."""
    cache = cache_manager.get_cache(cache_name)
    return cache.stats()