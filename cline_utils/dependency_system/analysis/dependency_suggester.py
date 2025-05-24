# analysis/dependency_suggester.py

"""
Analysis module for dependency suggestion using contextual keys.
Suggests potential dependencies based on code analysis and embeddings.
Assigns specific characters based on the type of dependency found.
Outputs path-based dependencies: List[Tuple[target_norm_path, char]]
"""

from collections import defaultdict
import json
import re
import os
from typing import Dict, List, Tuple, Optional, Any
import ast

# Attempt to import jsonc-parser
try:
    from jsonc_parser.parser import JsoncParser
    from jsonc_parser.errors import FileError, ParserError, FunctionParameterError as JsoncFunctionParameterError
    JSONC_PARSER_AVAILABLE = True
except ImportError:
    JSONC_PARSER_AVAILABLE = False
    JsoncParser = None 
    FileError = ParserError = JsoncFunctionParameterError = Exception 

# Import only from lower-level modules
from cline_utils.dependency_system.core.key_manager import (
    KeyInfo, 
    get_key_from_path as get_key_string_from_path
)
from cline_utils.dependency_system.utils.path_utils import get_file_type, normalize_path, resolve_relative_path, is_subpath, get_project_root
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, clear_all_caches, cache_manager
# NOTE: Avoid importing analyze_file here to prevent circular dependency if analyzer calls suggester


import logging
logger = logging.getLogger(__name__)

# Character Definitions:
# <: Row depends on column.
# >: Column depends on row.
# x: Mutual dependency.
# d: Documentation dependency.
# o: Self dependency (diagonal only).
# n: Verified no dependency.
# p: Placeholder (unverified).
# s: Semantic dependency (weak .06-.07) - Adjusted based on .clinerules
# S: Semantic dependency (strong .07+) - Added based on .clinerules

_PROJECT_SYMBOL_MAP_FILENAME_LOCAL = "project_symbol_map.json"
# _OLD_PROJECT_SYMBOL_MAP_FILENAME_LOCAL = "project_symbol_map_old.json" # Not used by load, only by save
def clear_caches():
    clear_all_caches() 
    if hasattr(_find_and_parse_tsconfig, '_cache'): 
        _find_and_parse_tsconfig._cache.clear() # type: ignore 
    if hasattr(_identify_structural_dependencies, '_import_map_cache'):
         _identify_structural_dependencies._import_map_cache.clear() # type: ignore
    if hasattr(_identify_structural_dependencies, '_resolved_path_cache'):
         _identify_structural_dependencies._resolved_path_cache.clear() # type: ignore
    if hasattr(load_project_symbol_map, '_cache'):
        load_project_symbol_map._cache.clear() # type: ignore

def load_metadata(metadata_path: str) -> Dict[str, Any]:
    """
    Load metadata file with caching.

    Args:
        metadata_path: Path to the metadata file
    Returns:
        Dictionary containing metadata or empty dict on failure
    """
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f: metadata = json.load(f)
        return metadata
    except FileNotFoundError: logger.warning(f"Metadata file not found at {metadata_path}. Run generate-embeddings first."); return {}
    except json.JSONDecodeError as e: logger.error(f"Invalid JSON in metadata file {metadata_path}: {e}"); return {}
    except Exception as e: logger.exception(f"Unexpected error reading metadata {metadata_path}: {e}"); return {}

# --- TS/JS Config Helper ---
@cached("tsconfig_data", 
        key_func=lambda start_dir, project_root_val: f"tsconfig:{normalize_path(start_dir)}:{normalize_path(project_root_val)}")
def _find_and_parse_tsconfig(start_dir: str, project_root_val: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Finds tsconfig.json or jsconfig.json by walking up from start_dir to project_root_val.
    Parses the first one found using jsonc-parser if available, otherwise standard json.
    Caches the result based on start_dir and project_root_val.

    Returns:
        Tuple of (config_file_path, parsed_data_dict) or None if not found/parsed.
    """
    current_dir = normalize_path(start_dir)
    project_root_norm = normalize_path(project_root_val)
    config_filenames = ["tsconfig.json", "jsconfig.json"]
    while True:
        for filename in config_filenames:
            config_path = os.path.join(current_dir, filename)
            if os.path.exists(config_path) and os.path.isfile(config_path):
                logger.debug(f"Found config file for JS/TS: {config_path}")
                try:
                    if JSONC_PARSER_AVAILABLE and JsoncParser: # Check JsoncParser is not None
                        # Ensure JsoncParser.parse_file is called correctly
                        data = JsoncParser.parse_file(config_path) # type: ignore
                        logger.debug(f"Successfully parsed {config_path} using jsonc-parser.")
                        return config_path, data
                    else:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        logger.debug(f"Successfully parsed {config_path} using standard json parser.")
                        return config_path, data
                except (FileError, ParserError, JsoncFunctionParameterError) as e_jsonc: # Catch specific jsonc-parser errors
                    logger.warning(f"Error parsing {config_path} with jsonc-parser: {e_jsonc}. Skipping this config.")
                    return None # Or try standard json as fallback? For now, skip on error.
                except json.JSONDecodeError as e_json:
                    logger.warning(f"JSONDecodeError parsing {config_path}: {e_json}. File might have comments and jsonc-parser is not available/failed.")
                    return None

        if current_dir == project_root_norm or not current_dir.startswith(project_root_norm):
            break 
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: 
            break
        current_dir = parent_dir
    logger.debug(f"No tsconfig.json or jsconfig.json found in hierarchy from {start_dir} up to {project_root_val}.")
    return None

# --- MODIFIED load_project_symbol_map ---
@cached("project_symbol_map_data",
        key_func=lambda: f"project_symbol_map:{os.path.getmtime(normalize_path(os.path.join(os.path.dirname(os.path.abspath(__import__('cline_utils.dependency_system.core.key_manager').__file__)), _PROJECT_SYMBOL_MAP_FILENAME_LOCAL))) if os.path.exists(normalize_path(os.path.join(os.path.dirname(os.path.abspath(__import__('cline_utils.dependency_system.core.key_manager').__file__)), _PROJECT_SYMBOL_MAP_FILENAME_LOCAL))) else 'missing'}")
def load_project_symbol_map() -> Dict[str, Dict[str, Any]]:
    """
    Loads the project_symbol_map.json file.
    The map contains information about functions, classes, globals, and exports for each file.
    Keys are normalized absolute file paths.
    It assumes the map is stored in the same directory as key_manager.py.
    """
    try:
        # Determine path relative to key_manager.py
        # Using __import__ and __file__ to robustly get key_manager's directory
        key_manager_module = __import__('cline_utils.dependency_system.core.key_manager', fromlist=[''])
        core_dir = os.path.dirname(os.path.abspath(key_manager_module.__file__))
        map_path = normalize_path(os.path.join(core_dir, _PROJECT_SYMBOL_MAP_FILENAME_LOCAL))

        if not os.path.exists(map_path):
            logger.warning(f"Project symbol map file not found at {map_path}. Symbol verification will be skipped.")
            return {}
        
        with open(map_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.debug(f"Successfully loaded project symbol map from: {map_path} ({len(data)} entries)")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from project symbol map file: {e}", exc_info=True)
        return {}
    except IOError as e:
        logger.error(f"I/O Error loading project symbol map file: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error loading project symbol map: {e}")
        return {}

# --- Main Dispatcher ---
def suggest_dependencies(file_path: str,
                         path_to_key_info: Dict[str, KeyInfo], 
                         project_root: str,
                         file_analysis_results: Dict[str, Any], 
                         threshold: float = 0.7
                         ) -> Tuple[List[Tuple[str, str]], List[Dict[str, str]]]: # MODIFIED return type
    """
    Suggest dependencies for a file, assigning appropriate characters, using contextual keys.

    Args:
        file_path: Path to the file to analyze
        path_to_key_info: Global map from normalized paths to KeyInfo objects.
        project_root: Root directory of the project
        file_analysis_results: Pre-computed analysis results for files
        threshold: Confidence threshold for *semantic* suggestions (0.0 to 1.0)
    Returns:
        List of (dependency_path, dependency_character) tuples
    """
    if not os.path.exists(file_path): 
        logger.warning(f"File not found: {file_path}")
        return [], [] # MODIFIED return

    norm_path = normalize_path(file_path)
    file_ext = os.path.splitext(norm_path)[1].lower()

    # --- Get the specific analysis result for the current file_path ---
    current_file_specific_analysis = file_analysis_results.get(norm_path)
    if current_file_specific_analysis is None or \
       "error" in current_file_specific_analysis or \
       "skipped" in current_file_specific_analysis:
        logger.debug(f"No valid analysis result for {norm_path} in file_analysis_results map. Skipping suggestions for this file.")
        return [], [] # MODIFIED return

    project_symbol_map = load_project_symbol_map()
    
    # Initialize collectors
    char_suggestions: List[Tuple[str, str]] = []
    raw_ast_links_collector: List[Dict[str, str]] = [] # NEW: For Python AST links

    if file_ext == '.py':
        # suggest_python_dependencies now returns two lists
        char_suggestions, py_ast_links = suggest_python_dependencies( # MODIFIED: Unpack two values
            norm_path,                         
            path_to_key_info,                  
            project_root,                      
            current_file_specific_analysis,    
            file_analysis_results,             
            project_symbol_map,                
            threshold                          
        )
        raw_ast_links_collector.extend(py_ast_links) # NEW: Collect AST links

    elif file_ext in ('.js', '.ts', '.tsx', '.mjs', '.cjs'):
        # These other language suggesters (as per your provided file) expect
        # file_analysis_results (the BIG map) and get the specific analysis internally.
        char_suggestions = suggest_javascript_dependencies(
            norm_path, 
            path_to_key_info, 
            project_root, 
            file_analysis_results, # Pass the BIG map
            project_symbol_map,    # It also takes project_symbol_map
            threshold
        )
        # No structured AST links from JS for now

    elif file_ext in ('.md', '.rst'):
        config = ConfigManager()
        embeddings_dir_rel = config.get_path("embeddings_dir", "cline_utils/dependency_system/analysis/embeddings")
        embeddings_dir = normalize_path(os.path.join(project_root, embeddings_dir_rel))
        metadata_path = os.path.join(embeddings_dir, "metadata.json")
        char_suggestions = suggest_documentation_dependencies(
            norm_path, 
            path_to_key_info, 
            project_root, 
            file_analysis_results, # Pass the BIG map
            threshold, 
            embeddings_dir, 
            metadata_path
        )
        # No AST links from Markdown

    elif file_ext in ('.html', '.htm'):
        char_suggestions = suggest_html_dependencies(
            norm_path, 
            path_to_key_info, 
            project_root, 
            file_analysis_results # Pass the BIG map
        )
        # No AST links from HTML

    elif file_ext == '.css':
        char_suggestions = suggest_css_dependencies(
            norm_path, 
            path_to_key_info, 
            project_root, 
            file_analysis_results # Pass the BIG map
        )
        # No AST links from CSS
        
    else: # Generic
        char_suggestions = suggest_generic_dependencies(
            norm_path, 
            path_to_key_info, 
            project_root, 
            threshold
        )
        # No AST links from generic
    
    return char_suggestions, raw_ast_links_collector # MODIFIED return
# --- Type-Specific Suggestion Functions ---
def _identify_structural_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                     path_to_key_info: Dict[str, KeyInfo], 
                                     project_root: str,
                                     project_symbol_map: Dict[str, Dict[str, Any]] 
                                     ) -> Tuple[List[Tuple[str, str]], List[Dict[str, str]]]:
    """
    Identifies Python structural dependencies (calls, attributes, inheritance) using contextual keys.
    Returns list of tuples (dependency_path, dependency_character).
    """
    suggestions_path_based: List[Tuple[str, str]] = []
    raw_ast_verified_links: List[Dict[str, str]] = [] # NEW: For collecting AST-derived links

    if not source_analysis: 
        return [], [] # MODIFIED return

    calls = source_analysis.get("calls", [])
    attributes = source_analysis.get("attribute_accesses", [])
    inheritance = source_analysis.get("inheritance", [])
    type_references = source_analysis.get("type_references", []) 
    decorators_used = source_analysis.get("decorators_used", [])       # NEW
    exceptions_handled = source_analysis.get("exceptions_handled", []) # NEW
    with_contexts_used = source_analysis.get("with_contexts_used", []) # NEW

    # Cache for _build_import_map results per source_path
    if not hasattr(_identify_structural_dependencies, '_import_map_cache'):
        _identify_structural_dependencies._import_map_cache = {} # type: ignore
    if not hasattr(_identify_structural_dependencies, '_resolved_path_cache'):
        _identify_structural_dependencies._resolved_path_cache = {} # type: ignore

    def _build_import_map(current_source_path: str) -> Dict[str, str]:
        """ 
        Builds a map of names available in the current scope to the absolute path 
        of the module file they were imported from or represent, using the AST
        retrieved from the dedicated 'ast_cache'.
        
        Example:
        - `import my_module.sub` -> map `{"my_module.sub": "/abs/path/to/my_module/sub.py"}`
        - `import my_module.sub as s` -> map `{"s": "/abs/path/to/my_module/sub.py"}`
        - `from my_package import specific_item` -> map `{"specific_item": "/abs/path/to/my_package/__init__.py"}`
        - `from my_package.another_module import specific_item as si` -> map `{"si": "/abs/path/to/my_package/another_module.py"}`
        """
        norm_source_path = normalize_path(current_source_path)
        if norm_source_path in _identify_structural_dependencies._import_map_cache: # type: ignore
            return _identify_structural_dependencies._import_map_cache[norm_source_path] # type: ignore
        
        local_import_map: Dict[str, str] = {} 

        ast_cache = cache_manager.get_cache("ast_cache")        
        tree = ast_cache.get(norm_source_path) # norm_source_path is the key
        
        if not tree:
            logger.error(f"ImportMap: AST tree not found in 'ast_cache' for {norm_source_path}. Cannot build import map accurately. This may indicate a parsing failure during the analysis phase or a cache miss/eviction.")
            _identify_structural_dependencies._import_map_cache[norm_source_path] = local_import_map 
            return local_import_map # Return empty map if AST is not available
            
        try:
            current_source_dir = os.path.dirname(norm_source_path)
            # project_root is available from the outer scope of _identify_structural_dependencies
            
            for node in ast.walk(tree): # Iterate through the provided AST tree
                if isinstance(node, ast.Import):
                    for alias_node in node.names:
                        imported_module_string = alias_node.name 
                        name_in_scope = alias_node.asname or alias_node.name

                        resolved_paths_info_list = _convert_python_import_to_paths(
                            import_name=imported_module_string, 
                            source_file_dir=current_source_dir, 
                            project_root=project_root, 
                            path_to_key_info=path_to_key_info,
                            project_symbol_map=project_symbol_map,
                            specific_item_name=None, 
                            relative_level=0 
                        )
                        
                        if resolved_paths_info_list:
                            resolved_module_file_path = normalize_path(resolved_paths_info_list[0][0])
                            item_verified = resolved_paths_info_list[0][1] 
                            local_import_map[name_in_scope] = resolved_module_file_path
                            logger.debug(f"ImportMap (ast.Import): Mapped '{name_in_scope}' to module path '{resolved_module_file_path}'. Item verified: {item_verified}")
                        else:
                            logger.debug(f"ImportMap (ast.Import): Could not resolve module string '{imported_module_string}' (imported as '{name_in_scope}') from '{current_source_path}'.")

                elif isinstance(node, ast.ImportFrom):
                    module_name_from_ast = node.module or "" 
                    level = node.level 
                    
                    base_dir_for_relative_resolve = current_source_dir
                    if level > 0: # Only adjust base_dir if it's a relative import
                        temp_base = current_source_dir
                        for _ in range(level): 
                            parent = os.path.dirname(temp_base)
                            if not parent or parent == temp_base or not parent.startswith(normalize_path(project_root)):
                                logger.warning(f"Relative import level {level} for '{module_name_from_ast}' in '{current_source_path}' went too high or out of project. Resolution base fallback to project root.")
                                temp_base = normalize_path(project_root) 
                            break
                        temp_base = parent
                        base_dir_for_relative_resolve = temp_base
                    
                    module_resolved_paths_info_list = _convert_python_import_to_paths(
                        import_name=module_name_from_ast, 
                        source_file_dir=base_dir_for_relative_resolve, # This is the directory from which relative pathing starts
                        project_root=project_root,
                        path_to_key_info=path_to_key_info,
                        project_symbol_map=project_symbol_map,
                        specific_item_name=None, 
                        relative_level=level 
                        )

                    if module_resolved_paths_info_list:
                        resolved_module_file_path = normalize_path(module_resolved_paths_info_list[0][0])
                        module_symbols = project_symbol_map.get(resolved_module_file_path, {})

                        for alias in node.names:
                            item_name_actually_imported = alias.name 
                            name_in_scope = alias.asname or alias.name 
                            
                            # Verify if item_name_actually_imported exists in resolved_module_file_path's symbols
                            is_defined_in_module_symbols = any(f.get('name') == item_name_actually_imported for f in module_symbols.get("functions", [])) or \
                                                         any(c.get('name') == item_name_actually_imported for c in module_symbols.get("classes", [])) or \
                                                         any(g.get('name') == item_name_actually_imported for g in module_symbols.get("globals_defined", []))
                            
                            is_submodule_or_package = False
                            if not is_defined_in_module_symbols: 
                                # If not a direct symbol, check if it's a submodule/package re-exported
                                # by an __init__.py, and if that submodule/package is tracked.
                                if os.path.basename(resolved_module_file_path) == "__init__.py":
                                    package_dir_for_submodule_check = os.path.dirname(resolved_module_file_path)
                                    potential_submodule_path_py = normalize_path(os.path.join(package_dir_for_submodule_check, item_name_actually_imported + ".py"))
                                    potential_subpackage_path_init = normalize_path(os.path.join(package_dir_for_submodule_check, item_name_actually_imported, "__init__.py"))
                                
                                    if potential_submodule_path_py in path_to_key_info or \
                                       potential_subpackage_path_init in path_to_key_info:
                                        is_submodule_or_package = True
                                        logger.debug(f"ImportMap: Item '{item_name_actually_imported}' (imported as '{name_in_scope}') from module '{module_name_from_ast}' appears to be a tracked submodule/package within '{package_dir_for_submodule_check}'.")

                            local_import_map[name_in_scope] = resolved_module_file_path
                            
                            if is_defined_in_module_symbols or is_submodule_or_package:
                                logger.debug(f"ImportMap (ast.ImportFrom): Mapped '{name_in_scope}' (item '{item_name_actually_imported}') to module '{resolved_module_file_path}' (verified in symbols or as tracked submodule).")
                            else:
                                logger.debug(f"ImportMap (ast.ImportFrom): Item '{item_name_actually_imported}' (imported as '{name_in_scope}') from module '{module_name_from_ast}' (path '{resolved_module_file_path}') not directly verified in its symbols or as a tracked submodule. Mapping to module path as fallback.")
                    else:
                        logger.debug(f"ImportMap: Module '{module_name_from_ast}' (level {level}) itself could not be resolved from '{current_source_path}'. Items like '{', '.join(a.name for a in node.names)}' not mapped.")
                                
        except Exception as e: 
            logger.error(f"Error building import map for {norm_source_path} using AST: {e}", exc_info=False)
        
        _identify_structural_dependencies._import_map_cache[norm_source_path] = local_import_map # type: ignore
        return local_import_map

    current_file_import_map = _build_import_map(source_path)

    def _resolve_name_to_path(name_to_resolve: Optional[str]) -> Optional[str]: 
        if not name_to_resolve: 
            return None
        
        # Use a cache specific to this run of _identify_structural_dependencies for this source_path
        # The cache key should remain the same as it's for the (source_path, name_to_resolve) pair.
        cache_key_res = (source_path, name_to_resolve) 
        if cache_key_res in _identify_structural_dependencies._resolved_path_cache: # type: ignore
            return _identify_structural_dependencies._resolved_path_cache[cache_key_res] # type: ignore
        
        parts = name_to_resolve.split('.')
        resolved_module_path_val: Optional[str] = None

        # Iterate from the longest possible prefix down to the shortest (first part)
        # e.g., for "foo.bar.baz.Item", try "foo.bar.baz", then "foo.bar", then "foo"
        for i in range(len(parts), 0, -1):
            current_prefix_to_check = ".".join(parts[:i])
            
            # Check if this prefix exists in our import map
            path_from_import_map = current_file_import_map.get(current_prefix_to_check)
            
            if path_from_import_map:
                # Ensure the path from the import map is a tracked file
                if path_from_import_map in path_to_key_info:
                    resolved_module_path_val = path_from_import_map
                    logger.debug(f"_resolve_name_to_path: Resolved prefix '{current_prefix_to_check}' (from '{name_to_resolve}') to module path '{resolved_module_path_val}' via import map.")
                    break # Found the longest matching prefix that's an imported module
                else:
                    # This case should be rare if _build_import_map only stores paths present in path_to_key_info
                    logger.warning(f"_resolve_name_to_path: Prefix '{current_prefix_to_check}' mapped to '{path_from_import_map}', but path not in path_to_key_info. Import map might be stale or contain unresolved external refs.")
        
        if not resolved_module_path_val:
            # If no prefix was found in the import map, it means the name_to_resolve
            # was not from an import statement (e.g., it's a local variable, global in current file, or built-in).
            # In this context, for finding *external module dependencies*, we return None.
            logger.debug(f"_resolve_name_to_path: Name '{name_to_resolve}' or its prefixes not found in import map for '{source_path}'. Assumed local or built-in.")

        _identify_structural_dependencies._resolved_path_cache[cache_key_res] = resolved_module_path_val # type: ignore
        return resolved_module_path_val
    
    # --- MODIFIED: Process Calls and Attributes with symbol verification ---
    for call_item in calls:
        potential_source_str = call_item.get("potential_source") # e.g., "my_module_alias" or "my_module_alias.class_name"
        target_name_str = call_item.get("target_name")           # e.g., "my_module_alias.method_name" or "ImportedClass()"
        
        target_path_val = _resolve_name_to_path(potential_source_str or target_name_str) # Try potential_source first

        if target_path_val and target_path_val != source_path:
            # Determine the actual item name being called/accessed on the target_path_val
            actual_item_name_to_check = ""
            if target_name_str: # "my_module_alias.method_name" -> "method_name"
                # If potential_source_str resolved, target_name_str is likely the full path to the method/function
                # We need the part of target_name_str that is relative to the resolved module (target_path_val)
                # This can be complex if target_name_str is like module.class.method
                # For now, simple split:
                parts = target_name_str.split('.')
                if len(parts) > 1 and ".".join(parts[:-1]) == potential_source_str : # my_alias.item -> item
                     actual_item_name_to_check = parts[-1]
                elif not potential_source_str : # direct call of an imported name
                     actual_item_name_to_check = target_name_str.split('.')[0] # if target_name_str itself is dotted
                else: # Fallback or if potential_source_str is the same as target_name_str (e.g. direct function call)
                     actual_item_name_to_check = target_name_str.split('.')[-1]


            if actual_item_name_to_check:
                # Remove "()" if it's a call representation from _get_full_name_str
                if actual_item_name_to_check.endswith("()"):
                    actual_item_name_to_check = actual_item_name_to_check[:-2]

                module_symbols = project_symbol_map.get(target_path_val, {})
                is_verified = any(s_item.get('name') == actual_item_name_to_check for s_list_key in ["functions", "classes", "globals_defined"] for s_item in module_symbols.get(s_list_key, []))
                
                # Heuristic: if it's a class method call like MyClass.method(), check if MyClass is in symbols,
                # but we don't have easy access to method names within classes in project_symbol_map yet.
                # For now, if potential_source (e.g., MyClass) is a class in target_path_val, assume method call is valid.
                if not is_verified and potential_source_str:
                    potential_class_name = potential_source_str.split('.')[-1]
                    if any(c.get('name') == potential_class_name for c in module_symbols.get("classes", [])):
                        is_verified = True # Assume valid method call if the class itself is verified
                        logger.debug(f"StructuralDep/Call: Assuming valid method call '{actual_item_name_to_check}' on verified class '{potential_class_name}' from {target_path_val}")


                if is_verified:
                    dep_char = "<"
                    suggestions_path_based.append((target_path_val, dep_char))
                    raw_ast_verified_links.append({
                        "source_path": source_path, "target_path": target_path_val,
                        "char": dep_char, "reason": f"Call/{target_name_str or potential_source_str}"
                    })
                    logger.debug(f"StructuralDep/Call: Verified {source_path} < uses '{target_name_str or potential_source_str}' from {target_path_val}")
                else:
                    logger.debug(f"StructuralDep/Call: Item '{actual_item_name_to_check}' (from call '{target_name_str}') not verified in symbols of '{target_path_val}'.")
            else:
                logger.debug(f"StructuralDep/Call: Could not determine specific item for call '{target_name_str}' with potential source '{potential_source_str}' resolved to '{target_path_val}'.")


    for attr_item in attributes:
        potential_source_str = attr_item.get("potential_source") # e.g., "my_module_alias" or "my_module_alias.instance"
        attribute_name_accessed = attr_item.get("target_name")   # e.g., "some_attribute"
        
        target_path_val = _resolve_name_to_path(potential_source_str)

        if target_path_val and target_path_val != source_path and attribute_name_accessed:
            module_symbols = project_symbol_map.get(target_path_val, {})
            
            # Check if the attribute_name_accessed is a global/function/class directly in the module
            is_verified = any(s_item.get('name') == attribute_name_accessed for s_list_key in ["functions", "classes", "globals_defined"] for s_item in module_symbols.get(s_list_key, []))
            
            # Heuristic: if potential_source_str (e.g., MyClass or my_instance_of_MyClass) resolves to a class,
            # we assume the attribute access is valid for now (we don't have instance/class attributes in project_symbol_map easily).
            if not is_verified and potential_source_str:
                potential_class_name_from_source = potential_source_str.split('.')[-1]
                if any(c.get('name') == potential_class_name_from_source for c in module_symbols.get("classes", [])):
                    is_verified = True # Assume valid attribute access if the base object is a known class
                    logger.debug(f"StructuralDep/Attribute: Assuming valid attribute '{attribute_name_accessed}' access on object/class '{potential_source_str}' (resolved to class in {target_path_val})")

            if is_verified:
                dep_char = "<"
                suggestions_path_based.append((target_path_val, dep_char))
                raw_ast_verified_links.append({
                    "source_path": source_path, "target_path": target_path_val,
                    "char": dep_char, "reason": f"Attribute/{potential_source_str}.{attribute_name_accessed}"
                })
                logger.debug(f"StructuralDep/Attribute: Verified {source_path} < uses attribute '{attribute_name_accessed}' from source '{potential_source_str}' (module: {target_path_val})")
            else:
                logger.debug(f"StructuralDep/Attribute: Attribute '{attribute_name_accessed}' from source '{potential_source_str}' not directly verified as defined symbol in '{target_path_val}'.")
    # --- END OF MODIFIED Process Calls and Attributes ---

    # Process Inheritance (from your last provided snippet, with raw_ast_links addition)
    for inh_item in inheritance: 
        base_class_name_str = inh_item.get("base_class_name") 
        target_path_val = _resolve_name_to_path(base_class_name_str) 
        if target_path_val and target_path_val != source_path:
            # Verify "Base" is in target_path_val's symbols
            module_symbols = project_symbol_map.get(target_path_val, {})
            actual_class_name = base_class_name_str.split('.')[-1] if '.' in base_class_name_str else base_class_name_str
            if any(c['name'] == actual_class_name for c in module_symbols.get("classes", [])):
                dep_char = "<"
                suggestions_path_based.append((target_path_val, dep_char))
                raw_ast_verified_links.append({
                    "source_path": source_path, "target_path": target_path_val,
                    "char": dep_char, "reason": f"Inheritance/{actual_class_name}"
                })
                logger.debug(f"StructuralDep/Inheritance: Verified {source_path} < inherits '{actual_class_name}' from {target_path_val}")
            else:
                logger.debug(f"StructuralDep/Inheritance: Base class '{actual_class_name}' (from '{base_class_name_str}') not found in symbols of resolved module '{target_path_val}'. Skipping dep suggestion for this inheritance.")

    # --- MODIFIED: Process Type References with symbol map verification ---
    for type_ref_item in type_references:
        type_name_str = type_ref_item.get("type_name_str") # e.g., "MyType" or "other_module.TheirType"
        target_path_val = _resolve_name_to_path(type_name_str) # Resolves "other_module" part if present
        
        if target_path_val and target_path_val != source_path:
            # Verify the actual type (e.g., "TheirType") is defined in the resolved module
            module_symbols = project_symbol_map.get(target_path_val, {})
            actual_type_to_check = type_name_str.split('.')[-1] if '.' in type_name_str else type_name_str
            is_defined_type = any(c['name'] == actual_type_to_check for c in module_symbols.get("classes", [])) or \
                              any(f['name'] == actual_type_to_check for f in module_symbols.get("functions", [])) or \
                              any(g['name'] == actual_type_to_check for g in module_symbols.get("globals_defined", []))
            if is_defined_type: 
                if any(c['name'] == actual_type_to_check for c in module_symbols.get("classes", [])): # Prioritize classes for type hints
                    dep_char = "<"
                    suggestions_path_based.append((target_path_val, dep_char))
                    raw_ast_verified_links.append({
                        "source_path": source_path, "target_path": target_path_val,
                        "char": dep_char, "reason": f"TypeHint/{actual_type_to_check}"
                    })
                    logger.debug(f"StructuralDep/TypeHint: Verified {source_path} < uses type '{actual_type_to_check}' from {target_path_val}")
            else:
                logger.debug(f"StructuralDep/TypeHint: Type '{actual_type_to_check}' (from '{type_name_str}') not found in symbols of resolved module '{target_path_val}'. Skipping dep suggestion.")

    # --- Process Decorators, Exceptions, With-Contexts with symbol map verification ---
    item_categories_to_process = [
        (decorators_used, "Decorator", "<"),       # Using a decorator from another module means current file depends on it.
        (exceptions_handled, "Exception", "<"),    # Handling an exception from another module.
        (with_contexts_used, "WithContext", "<")   # Using a context manager from another module.
    ]
    for item_list, item_type_log_name, dep_char in item_categories_to_process:
        for item_entry in item_list:
            # 'name' for decorators, 'type_name_str' for exceptions, 'context_expr_str' for with
            item_name_str = item_entry.get("name") or item_entry.get("type_name_str") or item_entry.get("context_expr_str")
            if not item_name_str: continue
            target_path_val = _resolve_name_to_path(item_name_str)
            if target_path_val and target_path_val != source_path:
                module_symbols = project_symbol_map.get(target_path_val, {})
                actual_item_to_check = item_name_str.split('.')[-1] if '.' in item_name_str else item_name_str

                # Check if the item exists as any kind of defined symbol in the target module
                is_defined_symbol = any(c['name'] == actual_item_to_check for c in module_symbols.get("classes", [])) or \
                                    any(f['name'] == actual_item_to_check for f in module_symbols.get("functions", [])) or \
                                    any(g['name'] == actual_item_to_check for g in module_symbols.get("globals_defined", []))
                if is_defined_symbol:
                    suggestions_path_based.append((target_path_val, dep_char))
                    raw_ast_verified_links.append({
                        "source_path": source_path, "target_path": target_path_val,
                        "char": dep_char, "reason": f"{item_type_log_name}/{actual_item_to_check}"
                    })
                    logger.debug(f"StructuralDep/{item_type_log_name}: Verified {source_path} {dep_char} uses '{actual_item_to_check}' from {target_path_val}")
                else:
                    logger.debug(f"StructuralDep/{item_type_log_name}: Item '{actual_item_to_check}' (from '{item_name_str}') not found in symbols of resolved module '{target_path_val}'. Skipping dep suggestion.")

    return list(set(suggestions_path_based)), raw_ast_verified_links

def suggest_python_dependencies(
    file_path: str, 
    path_to_key_info: Dict[str, KeyInfo], 
    project_root: str, 
    source_analysis: Dict[str, Any],             # MODIFIED: This is now the specific analysis for file_path
    _all_file_analyses_map: Dict[str, Any],      # MODIFIED: This is the full map of all file analyses
    project_symbol_map: Dict[str, Dict[str, Any]], 
    threshold: float
) -> Tuple[List[Tuple[str, str]], List[Dict[str, str]]]: # MODIFIED return type
    norm_file_path = normalize_path(file_path)
    # source_analysis is already the specific analysis for norm_file_path
    if source_analysis is None or "error" in source_analysis or "skipped" in source_analysis: 
        logger.debug(f"No valid analysis for {norm_file_path}, skipping Python suggestions.")
        return [], [] # MODIFIED return

    explicit_deps_paths, explicit_raw_ast_links = _identify_python_dependencies(
        norm_file_path, 
        source_analysis, 
        _all_file_analyses_map, 
        project_root, 
        path_to_key_info, 
        project_symbol_map
    )
    structural_suggestions_paths, structural_raw_ast_links = _identify_structural_dependencies(
        norm_file_path, 
        source_analysis, 
        path_to_key_info, 
        project_root, 
        project_symbol_map
    )
    semantic_suggestions_paths = suggest_semantic_dependencies_path_based(norm_file_path, path_to_key_info, project_root, threshold)

    all_suggestions_paths = explicit_deps_paths + structural_suggestions_paths + semantic_suggestions_paths
    
    # Combine all raw AST links
    all_raw_ast_links = explicit_raw_ast_links + structural_raw_ast_links # NEW

    # Apply priority to character-based suggestions
    combined_suggestions = _combine_suggestions_path_based_with_char_priority(all_suggestions_paths, norm_file_path)

    if combined_suggestions:
        logger.debug(f"Final Combined Dependencies for {norm_file_path}:")
        for target_path, char_code in combined_suggestions:
            logger.debug(f"  -> {target_path} ({char_code})")
    else:
        logger.debug(f"No combined dependencies found for {norm_file_path}.")

    if all_raw_ast_links:
        logger.debug(f"Raw AST-Verified Links Collected for {norm_file_path}: {len(all_raw_ast_links)} links")
    
    return combined_suggestions, all_raw_ast_links

def suggest_javascript_dependencies(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                                    project_root: str, file_analysis_results: Dict[str, Any],
                                    project_symbol_map: Dict[str, Dict[str, Any]], # NEW PARAMETER
                                    threshold: float) -> List[Tuple[str, str]]: 
    norm_file_path = normalize_path(file_path)
    analysis = file_analysis_results.get(norm_file_path)
    if analysis is None or "error" in analysis or "skipped" in analysis: return []

    source_file_dir = os.path.dirname(norm_file_path)
    tsconfig_info = _find_and_parse_tsconfig(source_file_dir, project_root)
    # tsconfig_info is Tuple[str, Dict[str, Any]] or None
    # ---

    # Pass tsconfig_info to _identify_javascript_dependencies
    explicit_deps_paths = _identify_javascript_dependencies(
        norm_file_path, 
        analysis, 
        file_analysis_results, 
        project_root, 
        path_to_key_info,
        project_symbol_map, # Pass the map
        tsconfig_info 
    )
    semantic_suggestions_paths = suggest_semantic_dependencies_path_based(norm_file_path, path_to_key_info, project_root, threshold)
    
    all_suggestions_paths = explicit_deps_paths + semantic_suggestions_paths
    return _combine_suggestions_path_based_with_char_priority(all_suggestions_paths, norm_file_path)

def suggest_documentation_dependencies(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                                       project_root: str, file_analysis_results: Dict[str, Any],
                                       threshold: float, _embeddings_dir: str, 
                                       _metadata_path: str) -> List[Tuple[str, str]]: 
    norm_file_path = normalize_path(file_path)
    analysis = file_analysis_results.get(norm_file_path)
    if analysis is None or "error" in analysis or "skipped" in analysis: return []

    explicit_deps_paths = _identify_markdown_dependencies(norm_file_path, analysis, file_analysis_results, project_root, path_to_key_info)
    semantic_suggestions_paths = suggest_semantic_dependencies_path_based(norm_file_path, path_to_key_info, project_root, threshold)

    all_suggestions_paths = explicit_deps_paths + semantic_suggestions_paths
    return _combine_suggestions_path_based_with_char_priority(all_suggestions_paths, norm_file_path)

def suggest_html_dependencies(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                              project_root: str, file_analysis_results: Dict[str, Any]
                              ) -> List[Tuple[str, str]]: # Output: List[(target_norm_path, char)]
    norm_file_path = normalize_path(file_path)
    analysis = file_analysis_results.get(norm_file_path)
    if analysis is None or "error" in analysis or "skipped" in analysis: return []
    
    explicit_deps_paths = _identify_html_dependencies(norm_file_path, analysis, file_analysis_results, project_root, path_to_key_info)
    # Optionally add semantic for HTML if meaningful:
    # semantic_suggestions_paths = suggest_semantic_dependencies_path_based(norm_file_path, path_to_key_info, project_root, some_html_threshold)
    # all_suggestions_paths = explicit_deps_paths + semantic_suggestions_paths
    return _combine_suggestions_path_based_with_char_priority(explicit_deps_paths, norm_file_path)

def suggest_css_dependencies(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                             project_root: str, file_analysis_results: Dict[str, Any]
                             ) -> List[Tuple[str, str]]: # Output: List[(target_norm_path, char)]
    norm_file_path = normalize_path(file_path)
    analysis = file_analysis_results.get(norm_file_path)
    if analysis is None or "error" in analysis or "skipped" in analysis: return []

    explicit_deps_paths = _identify_css_dependencies(norm_file_path, analysis, file_analysis_results, project_root, path_to_key_info)
    return _combine_suggestions_path_based_with_char_priority(explicit_deps_paths, norm_file_path)

def suggest_generic_dependencies(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                                 project_root: str, threshold: float) -> List[Tuple[str, str]]: # Output: List[(target_norm_path, char)]
    norm_file_path = normalize_path(file_path)
    semantic_suggestions_paths = suggest_semantic_dependencies_path_based(norm_file_path, path_to_key_info, project_root, threshold)
    return _combine_suggestions_path_based_with_char_priority(semantic_suggestions_paths, norm_file_path)

# --- Semantic Suggestion (Adapted to return paths) ---
def suggest_semantic_dependencies_path_based(file_path: str, path_to_key_info: Dict[str, KeyInfo], 
                                             project_root: str, threshold: float) -> List[Tuple[str, str]]: # Output: List[(target_norm_path, char)]
    config = ConfigManager()
    embeddings_dir_rel = config.get_path("embeddings_dir", "cline_utils/dependency_system/analysis/embeddings")
    embeddings_dir_abs = normalize_path(os.path.join(project_root, embeddings_dir_rel))
    if not os.path.exists(embeddings_dir_abs): 
        logger.debug(f"Embeddings dir {embeddings_dir_abs} not found. No semantic suggestions for {file_path}.")
        return []

    source_key_info = path_to_key_info.get(file_path) 
    if not source_key_info or source_key_info.is_directory: return [] # Only for files
    
    suggested_deps_path_based: List[Tuple[str, str]] = []
    target_key_infos_list = [
        info for info in path_to_key_info.values() 
        if not info.is_directory and info.norm_path != file_path # Must be a file and not self
    ]

    if not target_key_infos_list: return [] 

    # For calculate_similarity, it needs code_roots and doc_roots (relative to project_root)
    code_roots_rel_list = config.get_code_root_directories()
    doc_roots_rel_list = config.get_doc_directories()
    
    try: 
        from .embedding_manager import calculate_similarity # Local import to avoid top-level circularity
    except ImportError: 
        logger.error("embedding_manager.calculate_similarity could not be imported. Semantic suggestions disabled.")
        return []

    for target_ki in target_key_infos_list:
        try:
            # calculate_similarity expects key strings (canonical global ones)
            confidence = calculate_similarity(
                source_key_info.key_string, target_ki.key_string,
                embeddings_dir_abs, path_to_key_info, project_root,
                code_roots_rel_list, doc_roots_rel_list
            )
        except Exception as e_sim_calc: 
            confidence = 0.0
            logger.warning(f"Similarity calculation error between '{source_key_info.key_string}' and '{target_ki.key_string}': {e_sim_calc}", exc_info=False)

        threshold_S_strong_semantic = config.get_threshold("code_similarity") 
        threshold_s_weak_semantic = threshold 

        assigned_char_semantic: Optional[str] = None
        if confidence >= threshold_S_strong_semantic: assigned_char_semantic = 'S'
        elif confidence >= threshold_s_weak_semantic: assigned_char_semantic = 's'

        if assigned_char_semantic:
            suggested_deps_path_based.append((target_ki.norm_path, assigned_char_semantic))
            # logger.debug(f"Semantic: {source_key_info.norm_path} -> {target_ki.norm_path} ('{assigned_char_semantic}') conf: {confidence:.3f}")

    return suggested_deps_path_based


# --- Helper Functions ---
def _combine_suggestions_path_based_with_char_priority(
    suggestions_path_based: List[Tuple[str, str]], # List[(target_norm_path, char)]
    source_path_for_log: str 
    ) -> List[Tuple[str, str]]: # Output: List[(target_norm_path, char)]
    combined_by_path: Dict[str, str] = {} # target_norm_path -> char
    config = ConfigManager()
    get_priority = config.get_char_priority

    for target_path, char_val in suggestions_path_based:
        if not target_path or target_path == source_path_for_log: continue 

        current_char_for_path = combined_by_path.get(target_path)
        current_priority_val = get_priority(current_char_for_path) if current_char_for_path else -1
        new_priority_val = get_priority(char_val)

        if new_priority_val > current_priority_val:
            combined_by_path[target_path] = char_val
        elif new_priority_val == current_priority_val and char_val != current_char_for_path and current_char_for_path is not None:
            # Handle specific merge cases like < and > to x
            if {char_val, current_char_for_path} == {'<', '>'}: 
                if combined_by_path.get(target_path) != 'x': 
                    combined_by_path[target_path] = 'x'
    return list(combined_by_path.items())

# --- Dependency Identification Helpers ---

def _convert_python_import_to_paths(
    import_name: str,           # The module part, e.g., "foo" in "from .foo import X", or "os.path"
    source_file_dir: str,       # Absolute, normalized dir of the file containing the import
    project_root: str,          # Absolute, normalized project root
    path_to_key_info: Dict[str, KeyInfo], # The global map of tracked files
    project_symbol_map: Dict[str, Dict[str, Any]], # For verifying specific_item_name
    specific_item_name: Optional[str] = None,    # e.g., "X" in "from .foo import X"
    _is_from_import: bool = False, # Kept for signature, could be used for nuanced logic
    relative_level: int = 0       # 0 for absolute, 1 for '.', 2 for '..'
) -> List[Tuple[str, bool]]: # Returns List[(resolved_module_path, item_verified_in_module_symbols)]
    
    potential_paths_abs_info: List[Tuple[str, bool]] = [] # (path, item_verified_flag)
    normalized_project_root = normalize_path(project_root)
    
    candidate_module_file_paths_to_check_in_map: List[str] = []

    if relative_level > 0: 
        current_search_base = normalize_path(source_file_dir)
        for _ in range(relative_level - 1): 
            parent_dir = os.path.dirname(current_search_base)
            if not parent_dir or parent_dir == current_search_base or \
               (not parent_dir.startswith(normalized_project_root) and parent_dir != normalized_project_root):
                current_search_base = None; break
            current_search_base = parent_dir
        
        if current_search_base:
            module_path_part_rel = import_name.replace('.', os.sep) if import_name else ""
            base_path_for_relative_import = normalize_path(os.path.join(current_search_base, module_path_part_rel))
            candidate_module_file_paths_to_check_in_map.append(f"{base_path_for_relative_import}.py")
            candidate_module_file_paths_to_check_in_map.append(normalize_path(os.path.join(base_path_for_relative_import, "__init__.py")))

    elif import_name: # Absolute import (relative_level == 0)
        fs_like_import_path = import_name.replace('.', os.sep)
        
        # 1. Try relative to project_root
        base_abs_from_proj_root = normalize_path(os.path.join(normalized_project_root, fs_like_import_path))
        candidate_module_file_paths_to_check_in_map.append(f"{base_abs_from_proj_root}.py")
        candidate_module_file_paths_to_check_in_map.append(normalize_path(os.path.join(base_abs_from_proj_root, "__init__.py")))

        # 2. Try relative to each configured code_root
        try:
            configured_code_roots_rel = ConfigManager().get_code_root_directories()
            for cr_rel in configured_code_roots_rel:
                abs_code_root = normalize_path(os.path.join(normalized_project_root, cr_rel))
                # Check if import_name starts with the code_root's relative name (e.g., "src.")
                # If import_name = "src.module.foo" and cr_rel = "src"
                if import_name.startswith(cr_rel + '.'):
                    # The "project_root" case above already handles this correctly because
                    # fs_like_import_path would be "src/module/foo".
                    # os.path.join(project_root, "src/module/foo") is the correct base.
                    # No special action needed here to avoid double prefixing "src/src/...".
                    pass
                else:
                    # Handles imports like "my_module" when "src" is a code root,
                    # looking for "project_root/src/my_module.py"
                    base_abs_from_code_root = normalize_path(os.path.join(abs_code_root, fs_like_import_path))
                    candidate_module_file_paths_to_check_in_map.append(f"{base_abs_from_code_root}.py")
                    candidate_module_file_paths_to_check_in_map.append(normalize_path(os.path.join(base_abs_from_code_root, "__init__.py")))
        except Exception as e_cfg:
             logger.warning(f"Error getting code_root_directories for absolute import fallback: {e_cfg}")
        
        candidate_module_file_paths_to_check_in_map = list(set(candidate_module_file_paths_to_check_in_map)) # Deduplicate
        logger.debug(f"Absolute import '{import_name}': Candidate file paths to check: {candidate_module_file_paths_to_check_in_map}")

    # --- Check generated candidates against path_to_key_info and verify specific_item_name ---
    seen_paths = set()
    for p_candidate_str in candidate_module_file_paths_to_check_in_map:
        # p_candidate_str is already a normalized absolute path from the generation logic
        if p_candidate_str in path_to_key_info: # Direct check against tracked files
            if p_candidate_str not in seen_paths:
                item_verified_in_symbols = True # Default to true if no specific item to check
                if specific_item_name:
                    module_symbols = project_symbol_map.get(p_candidate_str, {})
                    is_defined = any(f.get('name') == specific_item_name for f in module_symbols.get("functions", [])) or \
                                 any(c.get('name') == specific_item_name for c in module_symbols.get("classes", [])) or \
                                 any(g.get('name') == specific_item_name for g in module_symbols.get("globals_defined", []))
                    
                    if not is_defined and os.path.basename(p_candidate_str) == "__init__.py":
                        # Check for re-exported submodule/subpackage if the resolved module is an __init__.py
                        package_dir_of_init = os.path.dirname(p_candidate_str)
                        potential_submodule_file = normalize_path(os.path.join(package_dir_of_init, specific_item_name + ".py"))
                        potential_subpackage_init = normalize_path(os.path.join(package_dir_of_init, specific_item_name, "__init__.py"))
                        
                        # Crucially, check if these potential submodule paths are ALSO tracked
                        if potential_submodule_file in path_to_key_info or \
                           potential_subpackage_init in path_to_key_info:
                            is_defined = True 
                            logger.debug(f"Import Check: Item '{specific_item_name}' imported from '{import_name}' (via package '{p_candidate_str}') appears to be a tracked re-exported submodule/package.")
                            
                    if not is_defined:
                        item_verified_in_symbols = False
                        logger.debug(f"Import Check: Item '{specific_item_name}' imported from '{import_name}' (resolved to module '{p_candidate_str}') not found in its defined symbols or as a tracked submodule/package.")
                
                potential_paths_abs_info.append((p_candidate_str, item_verified_in_symbols))
                seen_paths.add(p_candidate_str)
                
                # For absolute imports, Python's import machinery typically stops at the first match.
                # We replicate this behavior by returning after the first successful resolution.
                if relative_level == 0 and potential_paths_abs_info: 
                    logger.debug(f"Absolute import '{import_name}' resolved to '{p_candidate_str}'. Taking first match.")
                    return potential_paths_abs_info # Return immediately
                
    if not potential_paths_abs_info and import_name: 
        logger.debug(f"Could not resolve import '{import_name}' (item: {specific_item_name}, level:{relative_level}) from source '{source_file_dir}' to any *tracked* project files. Candidates checked (sample): {candidate_module_file_paths_to_check_in_map[:3]}")
    return potential_paths_abs_info
# ---

def _identify_python_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                 _file_analysis_results: Dict[str, Dict[str, Any]], 
                                 project_root: str,
                                 path_to_key_info: Dict[str, KeyInfo],
                                 project_symbol_map: Dict[str, Dict[str, Any]] 
                                 ) -> Tuple[List[Tuple[str, str]], List[Dict[str, str]]]: # MODIFIED return type
    dependencies_paths: List[Tuple[str, str]] = []
    raw_ast_links: List[Dict[str, str]] = [] # NEW: For collecting AST-derived links

    imports_in_source = source_analysis.get("imports", []) 
    source_dir_norm = os.path.dirname(source_path)
    tracked_paths_globally = set(path_to_key_info.keys())

    for import_name_str_from_ast in imports_in_source: # This is like "module" or ".module" or "..module.sub"
         temp_import_name = import_name_str_from_ast
         level_for_convert = 0
         while temp_import_name.startswith('.'):
             level_for_convert +=1
             temp_import_name = temp_import_name[1:]
         module_to_resolve_for_convert = temp_import_name

         resolved_path_infos = _convert_python_import_to_paths(
             import_name=module_to_resolve_for_convert, 
             source_file_dir=source_dir_norm, 
             project_root=project_root,
             path_to_key_info=path_to_key_info,
             project_symbol_map=project_symbol_map, 
             specific_item_name=None, 
             _is_from_import=True, 
             relative_level=level_for_convert
         )
         for path_abs_val, item_verified_flag in resolved_path_infos:
             if path_abs_val in tracked_paths_globally and path_abs_val != source_path: 
                 dep_char = "<" # Explicit imports are a direct dependency
                 dependencies_paths.append((path_abs_val, dep_char))
                 
                 # NEW: Collect this resolved import as an AST-verified link
                 raw_ast_links.append({
                     "source_path": source_path,
                     "target_path": path_abs_val,
                     "char": dep_char,
                     "reason": f"ExplicitImport/{import_name_str_from_ast}"
                 })
                 # ---
                 
                 if not item_verified_flag and module_to_resolve_for_convert: 
                     logger.debug(f"PythonDep: Import of '{module_to_resolve_for_convert}' from '{source_path}' resolved to module '{path_abs_val}', but specific item verification status: {item_verified_flag}.")
                 break 
    return list(set(dependencies_paths)), list(raw_ast_links)

def _identify_javascript_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                    _file_analyses: Dict[str, Dict[str, Any]], 
                                    project_root: str, 
                                    path_to_key_info: Dict[str, KeyInfo],
                                    project_symbol_map: Dict[str, Dict[str, Any]], 
                                    tsconfig_info: Optional[Tuple[str, Dict[str, Any]]] = None 
                                    ) -> List[Tuple[str, str]]:
    logger.debug(f"JS Deps: project_symbol_map received but specific item verification from JS imports is currently limited by analyzer's output for JS.")
    dependencies_paths: List[Tuple[str, str]] = []
    # raw_imports_in_source is List[str] like "./utils" or "@alias/component"
    raw_imports_in_source = source_analysis.get("imports", []) 
    source_dir_norm = os.path.dirname(source_path)
    tracked_paths_globally = set(path_to_key_info.keys())
    js_extensions_check = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'] 

    # Extract baseUrl and paths from tsconfig_info if available
    base_url_from_config: Optional[str] = None
    paths_from_config: Optional[Dict[str, List[str]]] = None
    tsconfig_dir_path: Optional[str] = None

    if tsconfig_info:
        tsconfig_dir_path = normalize_path(os.path.dirname(tsconfig_info[0]))
        config_data = tsconfig_info[1]
        compiler_options = config_data.get("compilerOptions", {})
        raw_base_url = compiler_options.get("baseUrl")
        if raw_base_url and tsconfig_dir_path: # baseUrl is relative to tsconfig_dir_path
            base_url_from_config = normalize_path(os.path.join(tsconfig_dir_path, raw_base_url))
            logger.debug(f"JS Resolve: Using baseUrl '{base_url_from_config}' (from {tsconfig_info[0]})")
        raw_paths = compiler_options.get("paths")
        if isinstance(raw_paths, dict):
            paths_from_config = raw_paths
            logger.debug(f"JS Resolve: Using paths configuration: {paths_from_config} (from {tsconfig_info[0]})")
    for import_path_str_val in raw_imports_in_source:
        if not import_path_str_val or \
           import_path_str_val.startswith(('http:', 'https:', '//', 'data:')): 
            continue
        resolved_target_path_abs: Optional[str] = None
        potential_alias_resolved_paths: List[str] = []
        if not import_path_str_val.startswith('.') and paths_from_config and tsconfig_dir_path:
            # Try to match import_path_str_val against keys in paths_from_config
            for alias, target_path_patterns in paths_from_config.items():
                # Handle wildcard matching (e.g., "@components/*": ["src/components/*"])
                if alias.endswith('/*'):
                    alias_prefix = alias[:-2] # e.g., "@components"
                    if import_path_str_val.startswith(alias_prefix):
                        wildcard_part = import_path_str_val[len(alias_prefix):] # e.g., "/Button" or "/ui/Card"
                        for pattern in target_path_patterns:
                            if pattern.endswith('/*'):
                                resolved_alias_base = pattern[:-2] + wildcard_part
                                # This resolved_alias_base is relative to tsconfig_dir_path or baseUrl
                                resolution_base_dir = base_url_from_config if base_url_from_config else tsconfig_dir_path
                                potential_alias_resolved_paths.append(normalize_path(os.path.join(resolution_base_dir, resolved_alias_base)))
                        if potential_alias_resolved_paths: break # Found a matching alias pattern
                elif import_path_str_val == alias: # Exact match
                    for pattern in target_path_patterns:
                        resolution_base_dir = base_url_from_config if base_url_from_config else tsconfig_dir_path
                        potential_alias_resolved_paths.append(normalize_path(os.path.join(resolution_base_dir, pattern)))
                    if potential_alias_resolved_paths: break # Found an exact alias match
            
            for alias_res_path_attempt in potential_alias_resolved_paths:
                has_known_ext_alias = any(alias_res_path_attempt.lower().endswith(ext) for ext in js_extensions_check)
                if has_known_ext_alias and os.path.isfile(alias_res_path_attempt):
                    if alias_res_path_attempt.startswith(normalize_path(project_root)): 
                        resolved_target_path_abs = alias_res_path_attempt; break
                else:
                    for ext_try in js_extensions_check:
                        if os.path.isfile(f"{alias_res_path_attempt}{ext_try}") and \
                           (f"{alias_res_path_attempt}{ext_try}").startswith(normalize_path(project_root)):
                            resolved_target_path_abs = f"{alias_res_path_attempt}{ext_try}"; break
                    if resolved_target_path_abs: break
                    for ext_try in js_extensions_check: 
                        idx_path = normalize_path(os.path.join(alias_res_path_attempt, f"index{ext_try}"))
                        if os.path.isfile(idx_path) and idx_path.startswith(normalize_path(project_root)):
                            resolved_target_path_abs = idx_path; break
                    if resolved_target_path_abs: break
            if resolved_target_path_abs:
                 logger.debug(f"JS Resolve: Alias '{import_path_str_val}' resolved to '{resolved_target_path_abs}' via tsconfig.")
        if not resolved_target_path_abs and import_path_str_val.startswith('.'): 
            base_resolved_path = normalize_path(os.path.abspath(os.path.join(source_dir_norm, import_path_str_val))) 
            if not base_resolved_path.startswith(normalize_path(project_root)):
                logger.debug(f"JS relative import '{import_path_str_val}' in '{source_path}' resolved to '{base_resolved_path}' outside project. Skipping.")
                continue
            has_known_ext = any(base_resolved_path.lower().endswith(ext) for ext in js_extensions_check)
            if has_known_ext and os.path.isfile(base_resolved_path):
                resolved_target_path_abs = base_resolved_path
            else: 
                for ext_try in js_extensions_check:
                    if os.path.isfile(f"{base_resolved_path}{ext_try}"):
                        resolved_target_path_abs = f"{base_resolved_path}{ext_try}"; break
                if not resolved_target_path_abs: 
                    for ext_try in js_extensions_check:
                        idx_path = normalize_path(os.path.join(base_resolved_path, f"index{ext_try}"))
                        if os.path.isfile(idx_path):
                            resolved_target_path_abs = idx_path; break
            if resolved_target_path_abs:
                 logger.debug(f"JS Resolve: Relative import '{import_path_str_val}' resolved to '{resolved_target_path_abs}'.")
        if not resolved_target_path_abs and not import_path_str_val.startswith('.') and base_url_from_config:
            # This path is not an alias, and not relative. Try resolving from baseUrl.
            path_from_base_url = normalize_path(os.path.join(base_url_from_config, import_path_str_val))
            # Apply extension/index checks again for this path_from_base_url
            has_known_ext_base = any(path_from_base_url.lower().endswith(ext) for ext in js_extensions_check)
            if has_known_ext_base and os.path.isfile(path_from_base_url):
                if path_from_base_url.startswith(normalize_path(project_root)):
                    resolved_target_path_abs = path_from_base_url
            else:
                for ext_try in js_extensions_check:
                    if os.path.isfile(f"{path_from_base_url}{ext_try}") and \
                       (f"{path_from_base_url}{ext_try}").startswith(normalize_path(project_root)):
                        resolved_target_path_abs = f"{path_from_base_url}{ext_try}"; break
                if not resolved_target_path_abs:
                    for ext_try in js_extensions_check:
                        idx_path = normalize_path(os.path.join(path_from_base_url, f"index{ext_try}"))
                        if os.path.isfile(idx_path) and idx_path.startswith(normalize_path(project_root)):
                            resolved_target_path_abs = idx_path; break
            if resolved_target_path_abs:
                 logger.debug(f"JS Resolve: Non-relative import '{import_path_str_val}' resolved to '{resolved_target_path_abs}' via baseUrl.")
        if resolved_target_path_abs and resolved_target_path_abs in tracked_paths_globally and resolved_target_path_abs != source_path:
            # At this point, resolved_target_path_abs is the path to the imported module file.
            # We don't have the specific named imports from the simple regex in dependency_analyzer.
            # So, we assume a dependency on the module file itself.
            # If we had specific named imports, e.g., `imported_item_name`, we could check:
            #   module_symbols = project_symbol_map.get(resolved_target_path_abs, {})
            #   if any(exp['name'] == imported_item_name for exp in module_symbols.get("exports", [])):
            #       dependencies_paths.append((resolved_target_path_abs, "<"))
            #   else:
            #       logger.debug(f"JS Import Check: Item '{imported_item_name}' from '{import_path_str_val}' (resolved to '{resolved_target_path_abs}') not found in its exports.")
            # For now, a simpler approach:
            dependencies_paths.append((resolved_target_path_abs, "<")) 
        elif not resolved_target_path_abs and not import_path_str_val.startswith('.'):
             logger.debug(f"JS non-relative import '{import_path_str_val}' in '{source_path}' could not be resolved within the project (checked tsconfig aliases/baseUrl). Might be an external package or unresolved.")
    return list(set(dependencies_paths))


def _identify_markdown_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                  _file_analyses: Dict[str, Dict[str, Any]], 
                                  project_root: str, 
                                  path_to_key_info: Dict[str, KeyInfo]
                                  ) -> List[Tuple[str, str]]:
    dependencies_paths: List[Tuple[str, str]] = []
    links_in_source = source_analysis.get("links", []) 
    source_dir_norm = os.path.dirname(source_path)
    tracked_paths_globally = set(path_to_key_info.keys())
    norm_project_root = normalize_path(project_root)
    for link_item in links_in_source:
        url_val = link_item.get("url", "")
        if not url_val or url_val.startswith(('#', 'mailto:', 'tel:', 'http:', 'https:', '//', 'data:')): continue
        url_cleaned_val = url_val.split('#')[0].split('?')[0] 
        if not url_cleaned_val: continue
        if os.path.isabs(url_cleaned_val): 
            logger.debug(f"MD Link: Skipping absolute-looking URL '{url_cleaned_val}' in '{source_path}'.")
            continue
        resolved_base_path_abs = normalize_path(os.path.abspath(os.path.join(source_dir_norm, url_cleaned_val)))
        
        # Ensure resolved path is within the project
        if not resolved_base_path_abs.startswith(norm_project_root):
            logger.debug(f"MD Link: Resolved path '{resolved_base_path_abs}' for link '{url_cleaned_val}' in '{source_path}' is outside project. Skipping.")
            continue
        possible_target_paths_check = [resolved_base_path_abs]
        _base_name_md, base_ext_md = os.path.splitext(resolved_base_path_abs)
        if not base_ext_md or os.path.isdir(resolved_base_path_abs): 
            possible_target_paths_check.extend([
                f"{resolved_base_path_abs}.md", f"{resolved_base_path_abs}.rst",
                normalize_path(os.path.join(resolved_base_path_abs, "index.md")),
                normalize_path(os.path.join(resolved_base_path_abs, "README.md"))
            ])
        found_target_path_md: Optional[str] = None
        for target_path_try in possible_target_paths_check:
            if os.path.isfile(target_path_try) and target_path_try in tracked_paths_globally:
                found_target_path_md = target_path_try; break
        if found_target_path_md and found_target_path_md != source_path:
            dependencies_paths.append((found_target_path_md, "d")) 
    return list(set(dependencies_paths))

def _identify_html_dependencies(source_path: str, source_analysis: Dict[str, Any],
                              _file_analyses: Dict[str, Dict[str, Any]], 
                              project_root: str, 
                              path_to_key_info: Dict[str, KeyInfo]
                              ) -> List[Tuple[str, str]]:
    dependencies_paths: List[Tuple[str, str]] = []
    source_dir_norm = os.path.dirname(source_path)
    tracked_paths_globally = set(path_to_key_info.keys())
    norm_project_root = normalize_path(project_root)

    # --- ADDED: Get doc_roots from ConfigManager ---
    config = ConfigManager()
    # get_doc_directories returns relative paths, convert them to absolute
    abs_doc_roots = [normalize_path(os.path.join(norm_project_root, dr)) for dr in config.get_doc_directories()]
    if not abs_doc_roots: # Fallback to project_root if no doc_roots are configured
        abs_doc_roots = [norm_project_root]
    urls_to_check_html: List[Tuple[Optional[str], str]] = [] 
    for link_item in source_analysis.get("links", []): urls_to_check_html.append((link_item.get("url"), "link")) 
    for script_item in source_analysis.get("scripts", []): urls_to_check_html.append((script_item.get("url"), "script")) 
    for style_item in source_analysis.get("stylesheets", []): urls_to_check_html.append((style_item.get("url"), "style")) 
    for img_item in source_analysis.get("images", []): urls_to_check_html.append((img_item.get("url"), "image")) 
    for url_val_html, resource_type_hint_html in urls_to_check_html:
        if not url_val_html or url_val_html.startswith(('#', 'mailto:', 'tel:', 'http:', 'https:', '//', 'data:')): continue
        url_cleaned_html = url_val_html.split('#')[0].split('?')[0]
        if not url_cleaned_html: continue
        resolved_path_abs_html: Optional[str] = None
        if url_cleaned_html.startswith('/'):
            # --- MODIFIED: Try resolving against each doc_root ---
            path_relative_to_root = url_cleaned_html.lstrip('/')
            for doc_root_abs in abs_doc_roots:
                potential_path = normalize_path(os.path.abspath(os.path.join(doc_root_abs, path_relative_to_root)))
                if potential_path.startswith(norm_project_root) and os.path.isfile(potential_path): 
                    resolved_path_abs_html = potential_path
                    logger.debug(f"HTML Link: Root-relative '{url_cleaned_html}' resolved to '{resolved_path_abs_html}' via doc_root '{doc_root_abs}'.")
                    break 
            if not resolved_path_abs_html:
                 logger.debug(f"HTML Link: Root-relative '{url_cleaned_html}' in '{source_path}' could not be resolved against configured doc_roots: {abs_doc_roots}.")
        else: 
            # Relative to the current HTML file's directory
            potential_path_rel = normalize_path(os.path.abspath(os.path.join(source_dir_norm, url_cleaned_html)))
            if potential_path_rel.startswith(norm_project_root) and os.path.isfile(potential_path_rel): # Ensure within project
                resolved_path_abs_html = potential_path_rel
            else:
                logger.debug(f"HTML Link: Relative '{url_cleaned_html}' in '{source_path}' resolved to '{potential_path_rel}' which is outside project or not a file.")
        if not resolved_path_abs_html: 
            logger.debug(f"HTML Link: Path for link '{url_val_html}' in '{source_path}' could not be resolved to an existing project file.")
            continue

        # Ensure it's not outside the project root (double check, though resolution logic should handle it)
        if not resolved_path_abs_html.startswith(norm_project_root): 
            logger.debug(f"HTML Link: Resolved path '{resolved_path_abs_html}' for link '{url_val_html}' in '{source_path}' is outside project. Skipping.")
            continue
        if resolved_path_abs_html in tracked_paths_globally and resolved_path_abs_html != source_path:
            dep_char_html = "d" 
            target_ext_html = os.path.splitext(resolved_path_abs_html)[1].lower()
            if resource_type_hint_html == "style" or target_ext_html == '.css': dep_char_html = 'd' 
            elif resource_type_hint_html == "script" or target_ext_html in ['.js', '.ts', '.tsx', '.mjs', '.cjs']: dep_char_html = 'd' 
            elif resource_type_hint_html == "link" and target_ext_html in ['.html', '.htm', '.md', '.rst']: dep_char_html = 'd' 
            elif resource_type_hint_html == "image" and target_ext_html in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']: dep_char_html = 'd' 
            dependencies_paths.append((resolved_path_abs_html, dep_char_html))
    return list(set(dependencies_paths))

def _identify_css_dependencies(source_path: str, source_analysis: Dict[str, Any],
                             _file_analyses: Dict[str, Dict[str, Any]], 
                             project_root: str, 
                             path_to_key_info: Dict[str, KeyInfo]
                             ) -> List[Tuple[str, str]]:
    dependencies_paths: List[Tuple[str, str]] = []
    imports_in_css = source_analysis.get("imports", []) 
    source_dir_norm = os.path.dirname(source_path)
    tracked_paths_globally = set(path_to_key_info.keys())
    norm_project_root = normalize_path(project_root)
    for import_item_css in imports_in_css:
        url_val_css = import_item_css.get("url", "") # CSS @import url(...)
        if not url_val_css or url_val_css.startswith(('#', 'http:', 'https:', '//', 'data:')): continue
        url_val_css = url_val_css.strip('\'"') 
        url_cleaned_css = url_val_css.split('#')[0].split('?')[0]
        if not url_cleaned_css: continue
        resolved_path_abs_css = normalize_path(os.path.abspath(os.path.join(source_dir_norm, url_cleaned_css)))
        if not resolved_path_abs_css.startswith(norm_project_root):
            logger.debug(f"CSS Import: Resolved path '{resolved_path_abs_css}' for import '{url_val_css}' in '{source_path}' is outside project. Skipping.")
            continue
        if os.path.isfile(resolved_path_abs_css) and resolved_path_abs_css in tracked_paths_globally and resolved_path_abs_css != source_path:
            dependencies_paths.append((resolved_path_abs_css, "<")) 
    return list(set(dependencies_paths))

# --- END OF FILE dependency_suggester.py ---