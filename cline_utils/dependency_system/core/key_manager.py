"""
Core module for key management.
Handles key generation, validation, and sorting.
"""

import argparse
import time
import os
import re
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict

from cline_utils.dependency_system.utils.path_utils import normalize_path, HIERARCHICAL_KEY_PATTERN, KEY_PATTERN
from cline_utils.dependency_system.utils.config_manager import ConfigManager

import logging
logger = logging.getLogger(__name__)

# Constants
ASCII_A = 65  # ASCII value for 'A'

# Moved from dependency_analyzer to break circular dependency
def get_file_type_for_key(file_path: str) -> str:
    """
    Determines the file type based on its extension.
    Simplified version for key management purposes.
    
    Args:
        file_path: The path to the file.
    Returns:
        The file type as a string (e.g., "py", "js", "md", "generic").
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    if ext == ".py":
        return "py"
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        return "js"
    elif ext in (".md", ".rst"):
        return "md"
    elif ext in (".html", ".htm"):
        return "html"
    elif ext == ".css":
        return "css"
    else:
        return "generic"

def generate_keys(root_paths: List[str], excluded_dirs: Set[str] = None,
                 excluded_extensions: Set[str] = None, tracker_type: str = "main") -> Tuple[
                     Dict[str, str], List[str], Dict[str, List[Tuple[str, str]]], Dict[str, str]]:
    """
    Generate hierarchical keys for files and directories.
    Args:
        root_paths: List of root directory paths to process
        excluded_dirs: Optional set of directory names to exclude
        excluded_extensions: Optional set of file extensions to exclude
        tracker_type: Type of tracker ('main', 'doc', 'mini') - impacts key structure
    Returns:
        Tuple containing:
        - Dictionary mapping hierarchical keys to file/directory paths
        - List of newly assigned keys
        - Dictionary of initial dependency suggestions (directory <-> file)
        - Dictionary mapping file paths to their module path (for mini-trackers)
    """
    logger.info(f"generate_keys called with root_paths: {root_paths}, excluded_dirs: {excluded_dirs}, excluded_extensions: {excluded_extensions}, tracker_type: {tracker_type}")
    
    # Default exclusions if none provided
    if excluded_dirs is None:
        config_manager = ConfigManager()
        excluded_dirs = set(config_manager.get_excluded_dirs())
        logger.info(f"Using default excluded_dirs: {excluded_dirs}")
    
    if excluded_extensions is None:
        config_manager = ConfigManager()
        excluded_extensions = set(config_manager.get_excluded_extensions())
        logger.info(f"Using default excluded_extensions: {excluded_extensions}")
    
    # Handle single string input
    if isinstance(root_paths, str):
        root_paths = [root_paths]
    
    # Validate all root paths exist
    for root_path in root_paths:
        if not os.path.exists(root_path):
            logger.error(f"Root path does not exist: {root_path}")
            raise FileNotFoundError(f"Root path '{root_path}' does not exist.")
    
    dir_to_letter: Dict[str, str] = {}
    key_map: Dict[str, str] = {}
    new_keys: List[str] = []  # Track newly assigned keys
    initial_suggestions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # Track the 'x' suggestions

    def process_directory(dir_path: str, parent_key: str = None, tier: int = 1):
        """Recursively processes directories and files."""
        nonlocal dir_to_letter, key_map, new_keys, initial_suggestions

        # Skip excluded directories
        if os.path.basename(dir_path) in excluded_dirs:
            logger.info(f"Skipping excluded directory: {dir_path}")
            return
        
        if parent_key is None:  # Top-level directory
            dir_name = os.path.basename(dir_path)
            dir_letter = chr(ASCII_A + len(dir_to_letter))
            norm_dir_path = normalize_path(dir_path).replace("\\", "/")
            dir_to_letter[norm_dir_path] = dir_letter
            
            # Key structure depends on tracker_type
            if tracker_type == "mini":
                key = f"M{tier}{dir_letter}"  # Add 'M' prefix for mini-trackers
            else:
                key = f"{tier}{dir_letter}"
            
            logger.info(f"Assigning key: {key} to top-level directory: {dir_path}")
            
            if key not in key_map:
                key_map[key] = norm_dir_path.replace("\\", "/")
                new_keys.append(key)  # Record new key
            
            module_path = norm_dir_path  # For top-level, module path is the dir itself
        else:
            key = parent_key
            logger.info(f"Using parent key: {key} for directory: {dir_path}")
        
        try:
            items = sorted(os.listdir(dir_path))  # Get items only once
        except OSError as e:
            logger.error(f"Error accessing directory '{dir_path}': {e}")
            return
        
        file_count = 1
        subdir_count = 1
        
        for item_name in items:
            item_path = os.path.join(dir_path, item_name)
            norm_item_path = normalize_path(item_path).replace("\\", "/")
            
            if item_name in excluded_dirs or item_name == "__pycache__" or item_name == ".gitkeep":
                logger.info(f"Skipping excluded item: {item_name}")
                continue
            
            # Skip files with excluded extensions
            _, ext = os.path.splitext(item_name)
            if ext in excluded_extensions:
                logger.info(f"Skipping file with excluded extension: {item_name}")
                continue
            
            if os.path.isfile(item_path):
                file_key = f"{key}{file_count}"
                logger.info(f"Assigning file key: {file_key} to file: {item_path}")
                
                if file_key not in key_map:
                    key_map[file_key] = norm_item_path
                    new_keys.append(file_key)  # Record new key

                # Add 'x' dependency suggestion
                initial_suggestions[key].append((file_key, "x"))
                initial_suggestions[file_key].append((key, "x"))
                
                file_count += 1
            elif os.path.isdir(item_path):
                subdir_letter = chr(97 + subdir_count - 1)
                subdir_key = f"{tier + 1}{key}{subdir_letter}"
                
                logger.info(f"Assigning subdir key: {subdir_key} to directory: {item_path}")
                
                if subdir_key not in key_map:
                    key_map[subdir_key] = norm_item_path
                    new_keys.append(subdir_key)  # Record new key
                
                # Add 'x' dependency suggestion
                initial_suggestions[key].append((subdir_key, "x"))
                initial_suggestions[subdir_key].append((key, "x"))
                
                subdir_count += 1
                process_directory(item_path, subdir_key, tier + 1, module_path)
        
        logger.info(f"Finished processing directory: {dir_path}")
    
    for root_path in root_paths:
        logger.info(f"Processing root path: {root_path}")
        process_directory(root_path)
    
    logger.info(f"Generated keys: {key_map}")
    return key_map, new_keys, initial_suggestions

def validate_key(key: str) -> bool:
    """
    Validate if a key follows the hierarchical key format.
    Args:
        key: The hierarchical key to validate
    Returns:
        True if valid, False otherwise
    """
    return bool(re.match(HIERARCHICAL_KEY_PATTERN, key))

def get_path_from_key(key: str, key_map: Dict[str, str]) -> Optional[str]:
    """
    Get the file/directory path corresponding to a hierarchical key.
    Args:
        key: The hierarchical key
        keymap: Dictionary mapping keys to paths
    Returns:
        The file/directory path or None if key not found
    """
    return key_map.get(key)

def get_key_from_path(path: str, key_map: Dict[str, str]) -> Optional[str]:
    """
    Get the hierarchical key corresponding to a file/directory path.
    Args:
        path: The file/directory path
        keymap: Dictionary mapping keys to paths
    Returns:
        The hierarchical key or None if path not found
    """
    norm_path = normalize_path(path).replace("\\", "/")
    for k, v in key_map.items():
        if v == norm_path:
            return k
    return None

def sort_keys(keys: List[str]) -> List[str]:
    """
    Sort hierarchical keys in a natural order.
    Args:
        keys: List of hierarchical keys to sort
    Returns:
        Sorted list of keys
    """
    def sort_key(key):
        parts = re.findall(KEY_PATTERN, key)
        return [int(p) if p.isdigit() else p for p in parts]
    
    return sorted(keys, key=sort_key)

def regenerate_keys(root_paths: List[str], excluded_dirs: Set[str] = None,
                   excluded_extensions: Set[str] = None, tracker_type: str = "main") -> Tuple[
                       Dict[str, str], List[str], Dict[str, List[Tuple[str, str]]], Dict[str, str]]:
    """
    Regenerates keys for the given root paths. This function is explicitly added
    to allow for dynamic key updates. It simply calls `generate_keys` with the same
    arguments.
    Args:
        root_paths: List of root directory paths to process
        excluded_dirs: Optional set of directory names to exclude
        excluded_extensions: Optional set of file extensions to exclude
        tracker_type: Type of tracker ('main', 'doc', 'mini') - impacts key structure
    Returns:
        Tuple containing:
        - Dictionary mapping hierarchical keys to file/directory paths
        - List of newly assigned keys
        - Dictionary of initial dependency suggestions (directory <-> file)
        - Dictionary mapping file paths to their module path (for mini-trackers)
    """
    return generate_keys(root_paths, excluded_dirs, excluded_extensions, tracker_type)

# EoF