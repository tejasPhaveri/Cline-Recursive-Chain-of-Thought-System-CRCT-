"""
Core module for path utilities.

Handles path normalization, validation, and comparison.
"""

import os
import re
from typing import List, Optional, Set, Union, Tuple

# Constants for key pattern matching
HIERARCHICAL_KEY_PATTERN = r'^(\d+)([A-Z])([a-z\d]*)$'
KEY_PATTERN = r'(\d+)|([A-Z])|([a-z]+)|(\d+)'

def normalize_path(path: str) -> str:
    """
    Normalize a file path for consistent comparison.
    
    Args:
        path: Path to normalize
        
    Returns:
        Normalized path
    """
    if not path:
        return ""
        
    # Convert to absolute path if not already
    if not os.path.isabs(path):
        path = os.path.abspath(path)
        
    # Normalize path separators and case (case-insensitive on Windows)
    normalized = os.path.normpath(path)
    
    # On Windows, convert to lowercase for case-insensitive comparison
    if os.name == 'nt':
        normalized = normalized.lower()
        
    return normalized

def get_file_type(file_path: str) -> str:
    """
    Determines the file type based on its extension.
    
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

def resolve_relative_path(source_dir: str, relative_path: str, default_extension: str = '.js') -> str:
    """
    Resolve a relative import path to an absolute path based on the source directory.
    
    Args:
        source_dir: The directory of the source file (e.g., 'h:/path/to/project').
        relative_path: The relative import path (e.g., './module3' or '../utils/helper').
        default_extension: The file extension to append if none is present (default is '.js').
        
    Returns:
        The resolved absolute path (e.g., 'h:/path/to/project/module3.js').
    """
    # Combine the source directory and relative path, then normalize it
    resolved = os.path.normpath(os.path.join(source_dir, relative_path))
    
    # Append the default extension if no extension is present
    if not os.path.splitext(resolved)[1]:
        resolved += default_extension
        
    return resolved

def get_relative_path(path: str, base_path: str) -> str:
    """
    Get a path relative to a base path.
    
    Args:
        path: Path to convert
        base_path: Base path to make relative to
        
    Returns:
        Relative path
    """
    norm_path = normalize_path(path)
    norm_base = normalize_path(base_path)
    
    try:
        return os.path.relpath(norm_path, norm_base)
    except ValueError:
        # If paths are on different drives (Windows), return the normalized path
        return norm_path

def get_project_root() -> str:
    """
    Find the project root directory.
    
    Returns:
        Path to the project root directory
    """
    # Start from the current directory
    current_dir = os.path.abspath(os.getcwd())
    root_indicators = ['.git', '.clinerules', 'pyproject.toml', 'setup.py', 'package.json', 'Cargo.toml', 'CMakeLists.txt']
    
    while current_dir != os.path.dirname(current_dir):
        for indicator in root_indicators:
            if os.path.exists(os.path.join(current_dir, indicator)):
                return current_dir
        
        # Move up one directory
        current_dir = os.path.dirname(current_dir)
    
    # If no root indicators found, return the current working directory
    return os.path.abspath(os.getcwd())

def join_paths(base_path: str, *paths: str) -> str:
    """
    Join paths and normalize the result.
    
    Args:
        base_path: Base path
        *paths: Additional path components
        
    Returns:
        Joined and normalized path
    """
    return normalize_path(os.path.join(base_path, *paths))

def is_path_excluded(path: str, excluded_paths: List[str]) -> bool:
    """
    Check if a path should be excluded based on a list of exclusion patterns.
    
    Args:
        path: Path to check
        excluded_paths: List of exclusion patterns
        
    Returns:
        True if the path should be excluded, False otherwise
    """
    if not excluded_paths:
        return False
        
    norm_path = normalize_path(path)
    
    for excluded in excluded_paths:
        # Handle glob patterns
        if '*' in excluded:
            pattern = excluded.replace('*', '.*')
            if re.search(pattern, norm_path):
                return True
        elif norm_path.startswith(normalize_path(excluded)) or norm_path == normalize_path(excluded):
            return True
            
    return False

def is_subpath(path: str, parent_path: str) -> bool:
    """
    Check if a path is a subpath of another path.
    
    Args:
        path: Path to check
        parent_path: Potential parent path
        
    Returns:
        True if path is a subpath of parent_path, False otherwise
    """
    norm_path = normalize_path(path)
    norm_parent = normalize_path(parent_path)
    
    # Check if the normalized path starts with the normalized parent path
    # and ensure it's a proper subpath (not just a string prefix)
    if norm_path.startswith(norm_parent):
        # If the parent path doesn't end with a separator, ensure the next character is a separator
        if not norm_parent.endswith(os.sep):
            return norm_path[len(norm_parent):].startswith(os.sep)
        return True
        
    return False

def get_common_path(paths: List[str]) -> str:
    """
    Find the common path prefix for a list of paths.
    
    Args:
        paths: List of paths
        
    Returns:
        Common path prefix
    """
    if not paths:
        return ""
        
    # Normalize all paths
    norm_paths = [normalize_path(p) for p in paths]
    
    # Use os.path.commonpath
    try:
        return os.path.commonpath(norm_paths)
    except ValueError:
        # If paths are on different drives (Windows), return empty string
        return ""
