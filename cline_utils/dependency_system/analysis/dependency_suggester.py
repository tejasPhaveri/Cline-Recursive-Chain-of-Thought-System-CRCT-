# analysis/dependency_suggester.py

"""
Analysis module for dependency suggestion.
Suggests potential dependencies based on code analysis and embeddings.
"""

import json
import re
import os
from typing import Dict, List, Tuple, Optional, Any

# Import only from lower-level modules
from cline_utils.dependency_system.utils.path_utils import normalize_path, resolve_relative_path, is_subpath
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, clear_all_caches
from cline_utils.dependency_system.analysis.dependency_analyzer import analyze_file

# Logger setup (assuming it's configured elsewhere)
import logging
logger = logging.getLogger(__name__)

def clear_caches():
    """Clear all internal caches."""
    clear_all_caches()

@cached('metadata', key_func=lambda metadata_path: f"metadata:{normalize_path(metadata_path)}:{os.path.getmtime(metadata_path) if os.path.exists(metadata_path) else '0'}")
def load_metadata(metadata_path: str) -> Dict[str, Any]:
    """
    Load metadata file with caching.

    Args:
        metadata_path: Path to the metadata file
    Returns:
        Dictionary containing metadata or empty dict on failure
    """
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        return metadata
    except FileNotFoundError:
        logger.warning(f"Metadata file not found at {metadata_path}. Run generate-embeddings first.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in metadata file {metadata_path}: {e}")
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error reading metadata {metadata_path}: {e}")
        return {}

@cached('suggestion', key_func=lambda file_path, project_root, threshold: f"suggestion:{normalize_path(file_path)}:{normalize_path(project_root)}:{threshold}")
def suggest_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float = 0.7) -> List[Tuple[str, float]]:
    """
    Suggest dependencies for a file based on embeddings and code analysis.

    Args:
        file_path: Path to the file to analyze
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions (0.0 to 1.0)
    Returns:
        List of (dependency_key, confidence) tuples
    """
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return []

    norm_path = normalize_path(file_path)
    file_ext = os.path.splitext(norm_path)[1].lower()

    if file_ext == '.py':
        return suggest_python_dependencies(norm_path, key_map, project_root, threshold)
    elif file_ext in ('.js', '.ts'):
        return suggest_javascript_dependencies(norm_path, key_map, project_root, threshold)
    elif file_ext in ('.md', '.rst'):
        return suggest_documentation_dependencies(norm_path, key_map, project_root, threshold)
    else:
        return suggest_generic_dependencies(norm_path, key_map, project_root, threshold)

def suggest_python_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float) -> List[Tuple[str, float]]:
    """
    Suggest dependencies for a Python file.

    Args:
        file_path: Path to the Python file (normalized)
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions
    Returns:
        List of (dependency_key, confidence) tuples
    """
    # Analyze file for explicit dependencies
    analysis = analyze_file(file_path)
    if "error" in analysis:
        logger.warning(f"Failed to analyze {file_path}: {analysis['error']}")
        return []

    explicit_deps = _identify_python_dependencies(file_path, analysis, {k: analyze_file(v) for k, v in key_map.items()}, project_root)
    explicit_suggestions = [(key_map.get(dep_path), 1.0) for dep_path, _ in explicit_deps if dep_path in key_map]

    # Get semantic dependencies
    semantic_suggestions = suggest_semantic_dependencies(file_path, key_map, project_root, threshold)

    return _combine_suggestions(explicit_suggestions + semantic_suggestions)

def suggest_javascript_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float) -> List[Tuple[str, float]]:
    """
    Suggest dependencies for a JavaScript/TypeScript file.

    Args:
        file_path: Path to the JavaScript file (normalized)
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions
    Returns:
        List of (dependency_key, confidence) tuples
    """
    analysis = analyze_file(file_path)
    if "error" in analysis:
        logger.warning(f"Failed to analyze {file_path}: {analysis['error']}")
        return []

    explicit_deps = _identify_javascript_dependencies(file_path, analysis, {k: analyze_file(v) for k, v in key_map.items()}, project_root)
    explicit_suggestions = [(key_map.get(dep_path), 1.0) for dep_path, _ in explicit_deps if dep_path in key_map]

    semantic_suggestions = suggest_semantic_dependencies(file_path, key_map, project_root, threshold)

    return _combine_suggestions(explicit_suggestions + semantic_suggestions)

def suggest_documentation_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float) -> List[Tuple[str, float]]:
    """
    Suggest dependencies for a documentation file.

    Args:
        file_path: Path to the documentation file (normalized)
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions
    Returns:
        List of (dependency_key, confidence) tuples
    """
    analysis = analyze_file(file_path)
    if "error" in analysis:
        logger.warning(f"Failed to analyze {file_path}: {analysis['error']}")
        return []

    explicit_deps = _identify_markdown_dependencies(file_path, analysis, {k: analyze_file(v) for k, v in key_map.items()}, project_root)
    explicit_suggestions = [(key_map.get(dep_path), 1.0) for dep_path, _ in explicit_deps if dep_path in key_map]

    semantic_suggestions = suggest_semantic_dependencies(file_path, key_map, project_root, threshold)

    return _combine_suggestions(explicit_suggestions + semantic_suggestions)

def suggest_generic_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float) -> List[Tuple[str, float]]:
    """
    Suggest dependencies for a generic file.

    Args:
        file_path: Path to the file (normalized)
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions
    Returns:
        List of (dependency_key, confidence) tuples
    """
    return suggest_semantic_dependencies(file_path, key_map, project_root, threshold)

def suggest_semantic_dependencies(file_path: str, key_map: Dict[str, str], project_root: str, threshold: float) -> List[Tuple[str, float]]:
    """
    Suggest dependencies based on semantic similarity using embeddings.

    Args:
        file_path: Path to the file (normalized)
        key_map: Dictionary mapping keys to file paths
        project_root: Root directory of the project
        threshold: Confidence threshold for suggestions
    Returns:
        List of (dependency_key, confidence) tuples
    """
    config = ConfigManager()
    embeddings_dir = os.path.join(project_root, config.get_path("embeddings_dir", "embeddings"))

    if not os.path.exists(embeddings_dir):
        if config.config.get("auto_generate_embeddings", True):
            logger.info(f"Embeddings not found. Generating embeddings in {embeddings_dir}...")
            from cline_utils.dependency_system.analysis.embedding_manager import generate_embeddings
            generate_embeddings([project_root], project_root)
        else:
            logger.warning("Embeddings not found. Enable 'auto_generate_embeddings' or run generate-embeddings.")
            return []

    path_to_key = {normalize_path(path): key for key, path in key_map.items()}
    file_key = path_to_key.get(file_path)
    if not file_key:
        logger.debug(f"No key found for file: {file_path}")
        return []

    from cline_utils.dependency_system.analysis.embedding_manager import calculate_similarity
    similarities = []

    batch_size = 50
    keys = [k for k in key_map.keys() if k != file_key]

    for i in range(0, len(keys), batch_size):
        batch = keys[i:i + batch_size]
        for other_key in batch:
            similarity = calculate_similarity(file_key, other_key, embeddings_dir)
            confidence = calculate_suggestion_confidence(file_path, key_map[other_key], project_root, key_map)
            if confidence >= threshold:
                similarities.append((other_key, confidence))

    return sorted(similarities, key=lambda x: x[1], reverse=True)

def calculate_suggestion_confidence(source_path: str, target_path: str, project_root: str, key_map: Dict[str, str]) -> float:
    """
    Calculate confidence score for a dependency suggestion.

    Args:
        source_path: Path to the source file (normalized)
        target_path: Path to the target file (normalized)
        project_root: Root directory of the project
        key_map: Dictionary mapping keys to file paths
    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not (os.path.exists(source_path) and os.path.exists(target_path)):
        logger.debug(f"File does not exist: {source_path} or {target_path}")
        return 0.0

    config = ConfigManager()
    embeddings_dir = os.path.join(project_root, config.get_path("embeddings_dir", "embeddings"))
    if not os.path.exists(embeddings_dir):
        logger.debug("Embeddings directory not found")
        return 0.5

    path_to_key = {normalize_path(path): key for key, path in key_map.items()}
    source_key = path_to_key.get(source_path)
    target_key = path_to_key.get(target_path)
    if not (source_key and target_key):
        logger.debug(f"Keys not found: {source_path} -> {source_key}, {target_path} -> {target_key}")
        return 0.0

    from cline_utils.dependency_system.analysis.embedding_manager import calculate_similarity
    similarity = calculate_similarity(source_key, target_key, embeddings_dir)

    explicit_bonus = _check_explicit_dependency(source_path, target_path)
    subpath_bonus = 0.2 if is_subpath(target_path, source_path) or is_subpath(source_path, target_path) else 0.0

    confidence = min(1.0, similarity + explicit_bonus + subpath_bonus)
    logger.debug(f"Confidence for {source_path} -> {target_path}: {confidence} (sim={similarity}, explicit={explicit_bonus}, subpath={subpath_bonus})")
    return confidence

def _check_explicit_dependency(source_path: str, target_path: str) -> float:
    """
    Check for explicit dependencies (e.g., imports) and return a confidence bonus.

    Args:
        source_path: Path to the source file (normalized)
        target_path: Path to the target file (normalized)
    Returns:
        Bonus value (0.0 or 0.5)
    """
    source_ext = os.path.splitext(source_path)[1].lower()
    bonus = 0.0

    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if source_ext == '.py':
            import ast
            try:
                tree = ast.parse(content)
                target_module = os.path.splitext(os.path.basename(target_path))[0]
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        modules = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module] if node.module else []
                        if any(target_module in m for m in modules if m):
                            bonus = 0.5
                            break
            except SyntaxError:
                logger.debug(f"Syntax error in {source_path}")

        elif source_ext in ('.js', '.ts'):
            source_dir = os.path.dirname(source_path)
            import_patterns = [
                r'import\s+.*\s+from\s+[\'"](.+?)[\'"]',
                r'import\s+[\'"](.+?)[\'"]',
                r'require\s*\(\s*[\'"](.+?)[\'"]'
            ]
            for pattern in import_patterns:
                for match in re.finditer(pattern, content):
                    module_path = match.group(1)
                    resolved_path = resolve_relative_path(source_dir, module_path, '.js')
                    if normalize_path(resolved_path) == normalize_path(target_path):
                        bonus = 0.5
                        break
                if bonus > 0:
                    break

    except Exception as e:
        logger.debug(f"Error checking explicit dependency in {source_path}: {e}")

    return bonus

def _combine_suggestions(suggestions: List[Tuple[Optional[str], float]]) -> List[Tuple[str, float]]:
    """
    Combine and deduplicate suggestions, keeping highest confidence.

    Args:
        suggestions: List of (key, confidence) tuples, where key may be None
    Returns:
        Filtered and sorted list of (key, confidence) tuples
    """
    combined = {}
    for key, conf in suggestions:
        if key and (key not in combined or conf > combined[key]):
            combined[key] = conf
    return sorted([(k, v) for k, v in combined.items()], key=lambda x: x[1], reverse=True)

# Reusing dependency identification functions from dependency_analyzer.py
from cline_utils.dependency_system.analysis.dependency_analyzer import (
    _identify_python_dependencies,
    _identify_javascript_dependencies,
    _identify_markdown_dependencies
)
# End of file