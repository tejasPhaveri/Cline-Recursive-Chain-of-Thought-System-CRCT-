"""
Utilities package initialization.
"""

from cline_utils.dependency_system.utils.batch_processor import (
    BatchProcessor,
    process_items,
    process_with_collector
)

from cline_utils.dependency_system.utils.cache_manager import (
    get_tracker_cache_key,
    get_from_tracker_cache,
    set_in_tracker_cache,
    get_from_suggestion_cache,
    set_in_suggestion_cache,
    get_from_metadata_cache,
    set_in_metadata_cache,
    get_from_path_cache,
    set_in_path_cache,
    clear_all_caches,
    cached
)

__all__ = [
    # batch_processor
    'BatchProcessor',
    'process_items',
    'process_with_collector',
    
    # cache_manager
    'get_tracker_cache_key',
    'get_from_tracker_cache',
    'set_in_tracker_cache',
    'get_from_suggestion_cache',
    'set_in_suggestion_cache',
    'get_from_metadata_cache',
    'set_in_metadata_cache',
    'get_from_path_cache',
    'set_in_path_cache',
    'clear_all_caches',
    'cached'
]
