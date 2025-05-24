# analysis/project_analyzer.py

from collections import defaultdict
import fnmatch
import json
import os
import shutil # For managing _old.json file
from typing import Any, Dict, Optional, List, Tuple

from cline_utils.dependency_system.io import tracker_io
from cline_utils.dependency_system.core import key_manager

import logging
from cline_utils.dependency_system.analysis.dependency_analyzer import analyze_file
from cline_utils.dependency_system.utils.batch_processor import BatchProcessor, process_items
from cline_utils.dependency_system.analysis.dependency_suggester import suggest_dependencies
from cline_utils.dependency_system.analysis.embedding_manager import generate_embeddings
from cline_utils.dependency_system.utils.cache_manager import cached, file_modified, clear_all_caches, cache_manager
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.path_utils import is_subpath, normalize_path, get_project_root
from cline_utils.dependency_system.utils.template_generator import generate_final_review_checklist
from cline_utils.dependency_system.utils.visualize_dependencies import generate_mermaid_diagram
from cline_utils.dependency_system.utils.tracker_utils import get_key_global_instance_string

logger = logging.getLogger(__name__)

# Type alias from tracker_io
PathMigrationInfo = Dict[str, Tuple[Optional[str], Optional[str]]]

# --- ADDED: Constants for the new symbol map ---
PROJECT_SYMBOL_MAP_FILENAME = "project_symbol_map.json"
OLD_PROJECT_SYMBOL_MAP_FILENAME = "project_symbol_map_old.json"

# --- Constants for the AST verified links file ---
AST_VERIFIED_LINKS_FILENAME = "ast_verified_links.json"
OLD_AST_VERIFIED_LINKS_FILENAME = "ast_verified_links_old.json"

# Caching for analyze_project (Consider if key_func needs more refinement)
# @cached("project_analysis",
#        key_func=lambda force_analysis=False, force_embeddings=False, **kwargs:
#        f"analyze_project:{normalize_path(get_project_root())}:{(os.path.getmtime(ConfigManager().config_path) if os.path.exists(ConfigManager().config_path) else 0)}:{force_analysis}:{force_embeddings}")
def analyze_project(force_analysis: bool = False, force_embeddings: bool = False) -> Dict[str, Any]:
    """
    Analyzes all files in a project to identify dependencies between them,
    initialize trackers, suggest dependencies using the new contextual key system,
    and generate relevant project templates like the final review checklist.
    Also auto-generates dependency diagrams if enabled.

    Args:
        force_analysis: Bypass cache and force reanalysis of files
        force_embeddings: Force regeneration of embeddings
    Returns:
        Dictionary containing project-wide analysis results and status
    """
    # --- Initial Setup ---
    config = ConfigManager()
    project_root = get_project_root()
    logger.info(f"Starting project analysis in directory: {project_root}")

    analyzer_batch_processor = BatchProcessor() 
    if force_analysis:
        logger.info("Force analysis requested. Clearing all caches.")
        clear_all_caches()
    analysis_results: Dict[str, Any] = { 
        "status": "success", 
        "message": "Analysis initiated.", 
        "warnings": [],
        "key_generation": {}, 
        "embedding_generation": {},
        "dependency_suggestion": {},
        "tracker_updates": {}, # MUST BE INITIALIZED AS A DICT
        "file_analysis": {},
        "template_generation": {},
        "auto_visualization": {},
        "symbol_map_generation": {} # NEW entry for symbol map status
    }
    # --- Exclusion Setup ---
    excluded_dirs_rel = config.get_excluded_dirs()
    excluded_paths_config = config.config.get("excluded_paths", []) # Get raw "excluded_paths" list from config
    excluded_paths_rel = [p for p in excluded_paths_config if not os.path.isabs(p)] # Filter for relative
    all_excluded_paths_abs_set = set(config.get_excluded_paths()) 
    excluded_extensions = set(config.get_excluded_extensions())
    excluded_file_patterns_config = config.config.get("excluded_file_patterns", [])

    norm_project_root = normalize_path(project_root)
    if any(norm_project_root == excluded_path or norm_project_root.startswith(excluded_path + os.sep if not excluded_path.endswith(os.sep) else excluded_path) # Ensure trailing sep for startswith
           for excluded_path in all_excluded_paths_abs_set if excluded_path): # check if excluded_path is not empty
        logger.info(f"Skipping analysis of excluded project root: {project_root}"); analysis_results["status"] = "skipped"; analysis_results["message"] = "Project root is excluded"; return analysis_results

    # --- Root Directories Setup ---
    code_root_directories_rel = config.get_code_root_directories()
    doc_directories_rel = config.get_doc_directories()
    all_roots_rel = sorted(list(set(code_root_directories_rel + doc_directories_rel)))
    abs_code_roots = {normalize_path(os.path.join(project_root, r)) for r in code_root_directories_rel}
    abs_all_roots = {normalize_path(os.path.join(project_root, r)) for r in all_roots_rel}
    logger.debug(f"Absolute code roots for mini-tracker consideration: {abs_code_roots}")
    
    # old_map_existed_before_gen logic block
    old_map_existed_before_gen = False
    try:
        # Determine the expected path for the old map file RELATIVE to key_manager.py
        # Use the imported key_manager module to find its location
        key_manager_dir = os.path.dirname(os.path.abspath(key_manager.__file__))
        old_map_path = normalize_path(os.path.join(key_manager_dir, key_manager.OLD_GLOBAL_KEY_MAP_FILENAME))
        old_map_existed_before_gen = os.path.exists(old_map_path)
        if old_map_existed_before_gen:
            logger.info(f"Found existing '{key_manager.OLD_GLOBAL_KEY_MAP_FILENAME}' before key generation. Grid migration will prioritize it.")
        else:
            logger.info(f"'{key_manager.OLD_GLOBAL_KEY_MAP_FILENAME}' not found before key generation. Grid migration will use tracker definitions as fallback.")
    except Exception as path_err:
        logger.error(f"Error determining path or checking existence of old key map file: {path_err}. Assuming it didn't exist.")
        old_map_existed_before_gen = False

    # --- Key Generation ---
    logger.info("Generating/Regenerating keys...")
    path_to_key_info: Dict[str, key_manager.KeyInfo] = {}
    newly_generated_keys: List[key_manager.KeyInfo] = []
    try:
        # Call generate_keys using the module reference
        path_to_key_info, newly_generated_keys = key_manager.generate_keys(
            all_roots_rel, # Use this variable name
            excluded_dirs=excluded_dirs_rel, # Pass specific lists from config
            excluded_extensions=list(excluded_extensions), # Pass specific lists from config (ensure list for type hint if generate_keys expects List)
            precomputed_excluded_paths=all_excluded_paths_abs_set
        )
        analysis_results["key_generation"]["count"] = len(path_to_key_info)
        analysis_results["key_generation"]["new_count"] = len(newly_generated_keys)
        logger.info(f"Generated {len(path_to_key_info)} keys for {len(path_to_key_info)} files/dirs.")
        if newly_generated_keys: logger.info(f"Assigned {len(newly_generated_keys)} new keys.")
    except key_manager.KeyGenerationError as kge:
        analysis_results["status"] = "error"; analysis_results["message"] = f"Key generation failed: {kge}"; logger.critical(analysis_results["message"]); return analysis_results
    except Exception as e:
        analysis_results["status"] = "error"; analysis_results["message"] = f"Key generation failed unexpectedly: {e}"; logger.exception(analysis_results["message"]); return analysis_results

    # --- Build Path Migration Map (Early, after new keys are generated) ---
    logger.info("Building path migration map for analysis and updates...")
    old_global_map = key_manager.load_old_global_key_map() # Load old map (can be None)
    path_migration_info: PathMigrationInfo
    try:
        path_migration_info = tracker_io._build_path_migration_map(old_global_map, path_to_key_info)
    except ValueError as ve:
         logger.critical(f"Failed to build migration map during analysis: {ve}. Downstream functions may fail.")
         analysis_results["status"] = "error"; analysis_results["message"] = f"Migration map build failed: {ve}"; return analysis_results
    except Exception as e:
         logger.critical(f"Unexpected error building migration map during analysis: {e}. Downstream functions may fail.", exc_info=True)
         analysis_results["status"] = "error"; analysis_results["message"] = f"Migration map build error: {e}"; return analysis_results


    # --- File Identification and Filtering ---
    logger.info("Identifying files for analysis...")
    files_to_analyze_abs = []
    for abs_root_dir in abs_all_roots:
        if not os.path.isdir(abs_root_dir):
            logger.warning(f"Configured root directory not found: {abs_root_dir}")
            continue
        # Use os.walk - order within walk is OS-dependent but shouldn't affect analysis analysis_results
        for root, dirs, files in os.walk(abs_root_dir, topdown=True):
            norm_root = normalize_path(root)
            dirs[:] = [d for d in dirs if d not in excluded_dirs_rel and normalize_path(os.path.join(norm_root, d)) not in all_excluded_paths_abs_set]
            is_root_excluded_by_path = False
            if norm_root in all_excluded_paths_abs_set or \
               any(is_subpath(norm_root, excluded) for excluded in all_excluded_paths_abs_set if os.path.isdir(excluded)): # Check against dirs in exclusion set
                 is_root_excluded_by_path = True
            if is_root_excluded_by_path:
                dirs[:] = []; continue
            for file_name in files:
                file_path_abs = normalize_path(os.path.join(norm_root, file_name))
                file_basename = os.path.basename(file_path_abs) 
                _, file_ext_tuple = os.path.splitext(file_name) 
                file_ext = file_ext_tuple.lower()
                
                is_excluded = (
                    file_path_abs in all_excluded_paths_abs_set or
                    any(is_subpath(file_path_abs, excluded_path_iter) for excluded_path_iter in all_excluded_paths_abs_set if os.path.isdir(excluded_path_iter)) or
                    file_ext in excluded_extensions or
                    any(fnmatch.fnmatch(file_basename, pattern) for pattern in excluded_file_patterns_config) # Use original pattern list from config
                )
                if is_excluded:
                    logger.debug(f"Skipping excluded file: {file_path_abs}")
                    continue
                if file_path_abs in path_to_key_info: # Check against the generated map
                    files_to_analyze_abs.append(file_path_abs)
                else:
                    logger.warning(f"File found but no key generated: {file_path_abs}")
    logger.info(f"Found {len(files_to_analyze_abs)} files to analyze.")

    # --- File Analysis ---
    logger.info("Starting file analysis...")
    # Use process_items for potential parallelization
    # Pass force_analysis flag down to analyze_file if caching is implemented there
    analysis_results_list = process_items(
        files_to_analyze_abs,
        analyze_file,
        force=force_analysis
    )
    file_analysis_results: Dict[str, Any] = {}
    analyzed_count, skipped_count, error_count = 0, 0, 0
    for file_path_abs, analysis_result in zip(files_to_analyze_abs, analysis_results_list):
        if analysis_result:
            if "error" in analysis_result: logger.warning(f"Analysis error for {file_path_abs}: {analysis_result['error']}"); error_count += 1
            elif "skipped" in analysis_result: skipped_count += 1
            else: file_analysis_results[file_path_abs] = analysis_result; analyzed_count += 1
        else: logger.warning(f"Analysis returned no result for {file_path_abs}"); error_count += 1
    analysis_results["file_analysis"] = file_analysis_results
    logger.info(f"File analysis complete. Analyzed: {analyzed_count}, Skipped: {skipped_count}, Errors: {error_count}")

    # --- NEW: Generate and Save Project Symbol Map ---
    logger.info("Generating project symbol map...")
    project_symbol_data: Dict[str, Dict[str, Any]] = {}
    for path_abs, single_file_analysis_result in file_analysis_results.items():
        if single_file_analysis_result and "error" not in single_file_analysis_result and "skipped" not in single_file_analysis_result:
            symbols_for_file: Dict[str, Any] = {
                "file_type": single_file_analysis_result.get("file_type", "unknown")
            }
            # Add specific symbol lists if they exist in the analysis result
            for symbol_key in ["functions", "classes", "globals_defined", "exports", "type_references"]:
                if symbol_key in single_file_analysis_result:
                    symbols_for_file[symbol_key] = single_file_analysis_result[symbol_key]
            project_symbol_data[path_abs] = symbols_for_file
    
    if project_symbol_data:
        try:
            # Save to the same directory as key_manager.py (core metadata location)
            core_dir = os.path.dirname(os.path.abspath(key_manager.__file__))
            current_symbol_map_path = normalize_path(os.path.join(core_dir, PROJECT_SYMBOL_MAP_FILENAME))
            old_symbol_map_path = normalize_path(os.path.join(core_dir, OLD_PROJECT_SYMBOL_MAP_FILENAME))
            os.makedirs(core_dir, exist_ok=True)

            if os.path.exists(current_symbol_map_path):
                try: shutil.move(current_symbol_map_path, old_symbol_map_path)
                except OSError as rename_err: logger.error(f"Failed to rename current symbol map to old: {rename_err}")
            
            with open(current_symbol_map_path, 'w', encoding='utf-8') as f_sym:
                json.dump(project_symbol_data, f_sym, indent=2)
            logger.info(f"Successfully saved project symbol map to: {current_symbol_map_path} ({len(project_symbol_data)} files)")
            analysis_results["symbol_map_generation"]["status"] = "success"
            analysis_results["symbol_map_generation"]["path"] = current_symbol_map_path
            analysis_results["symbol_map_generation"]["count"] = len(project_symbol_data)
        except Exception as e_sym_save:
            logger.error(f"Failed to save project symbol map: {e_sym_save}", exc_info=True)
            analysis_results["symbol_map_generation"]["status"] = "error"
            analysis_results["symbol_map_generation"]["error_message"] = str(e_sym_save)
    else:
        logger.warning("No symbol data generated from file analysis. Symbol map will be empty or not saved.")
        analysis_results["symbol_map_generation"]["status"] = "no_data"
    # --- END OF NEW SYMBOL MAP GENERATION ---

    # --- Create file_to_module mapping (Adapted for path_to_key_info) ---
    # Maps normalized absolute file path -> normalized absolute parent directory path (module path)
    logger.info("Creating file-to-module mapping...")
    file_to_module: Dict[str, str] = {}
    # Iterate through all the generated key information from path_to_key_info
    for key_info_obj in path_to_key_info.values(): # Iterate over KeyInfo objects
        # We only care about mapping files
        if not key_info_obj.is_directory:
            # Ensure the file has a parent path recorded
            if key_info_obj.parent_path:
                file_path = key_info_obj.norm_path
                module_path = key_info_obj.parent_path # Direct parent directory path
                file_to_module[file_path] = module_path
                logger.debug(f"Mapped file '{file_path}' to module '{module_path}'") # Optional debug log

            else:
                logger.warning(f"File '{key_info_obj.norm_path}' (Key: {key_info_obj.key_string}) has no parent path in KeyInfo. Cannot map to a module.")
    logger.info(f"File-to-module mapping created with {len(file_to_module)} entries.")

    # --- Embedding generation ---
    logger.info("Starting embedding generation...")
    try:
        # Pass path_to_key_info instead of key_map
        success = generate_embeddings(all_roots_rel, path_to_key_info, force=force_embeddings)
        analysis_results["embedding_generation"]["status"] = "success" if success else "partial_failure"
        if not success: analysis_results["warnings"].append("Embedding generation failed for some paths."); logger.warning("Embedding generation failed or skipped for some paths.")
        else: logger.info("Embedding generation completed successfully.")
    except Exception as e:
        analysis_results["embedding_generation"]["status"] = "error"
        analysis_results["status"] = "error" # Upgrade status to error if embedding process fails critically
        analysis_results["message"] = f"Embedding generation process failed critically: {e}"
        logger.exception(analysis_results["message"]); return analysis_results

    # --- Dependency Suggestion (Adapted for Path-Based Output) ---
    logger.info("Starting dependency suggestion (path-based)...") 
    analysis_results["dependency_suggestion"] = {"status": "pending", "suggestion_count": 0, "ast_link_count": 0} # Added ast_link_count
    
    # --- >>> INITIALIZE all_suggestions HERE <<< ---
    all_path_based_suggestions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    # --- Initialize list to collect all AST-verified links from the project ---
    all_project_ast_links: List[Dict[str, str]] = []

    analyzed_file_paths = list(file_analysis_results.keys())
    # Use configured threshold for doc_similarity
    doc_similarity_threshold = config.get_threshold("doc_similarity")

    # --- Store the length of the last printed progress line ---
    _last_progress_message_length = 0

    for i, file_path_abs in enumerate(analyzed_file_paths):
        file_key_info = path_to_key_info.get(file_path_abs)
        if not file_key_info:
            logger.warning(f"No key info found for analyzed file {file_path_abs}, skipping suggestion.")
            continue
        
        # --- MODIFICATION: Unpack two return values from suggest_dependencies ---
        suggestions_for_file, ast_links_for_file = suggest_dependencies(
            file_path_abs, 
            path_to_key_info, 
            project_root,
            file_analysis_results, 
            threshold=doc_similarity_threshold
        )
        if suggestions_for_file:
            all_path_based_suggestions[file_path_abs].extend(suggestions_for_file) # Use the initialized variable
            analysis_results["dependency_suggestion"]["suggestion_count"] += len(suggestions_for_file)

        # --- NEW: Collect AST links ---
        if ast_links_for_file:
            all_project_ast_links.extend(ast_links_for_file)
            analysis_results["dependency_suggestion"]["ast_link_count"] += len(ast_links_for_file)
        
        # --- UPDATED LOGGING FOR PROGRESS (More Robust Line Clearing) ---
        progress_percent = ((i + 1) / len(analyzed_file_paths)) * 100
        current_suggestion_count = analysis_results["dependency_suggestion"]["suggestion_count"]
        current_ast_link_count = analysis_results["dependency_suggestion"]["ast_link_count"] # Get current count
        progress_message = (
            f"Dependency Suggestion: Processed {i+1}/{len(analyzed_file_paths)} files ({progress_percent:.1f}%) - "
            f"Found {current_suggestion_count} char suggestions, {current_ast_link_count} AST links..."
        )        
        # 1. Move cursor to beginning of the line
        print(end='\r') 
        # 2. Print spaces to overwrite the PREVIOUS message
        print(" " * _last_progress_message_length, end='\r') 
        # 3. Print the NEW message (cursor is already at the beginning)
        print(progress_message, end='', flush=True) # Use flush=True for immediate output
        
        # 4. Update the length for the next iteration
        _last_progress_message_length = len(progress_message)
        # --- END OF UPDATED LOGGING ---

    # After the loop:
    # 1. Clear the last progress line
    print(end='\r')
    print(" " * _last_progress_message_length, end='\r') 
    
    # 2. Print the final summary message using the standard logger (which adds a newline)
    final_suggestion_count = analysis_results["dependency_suggestion"]["suggestion_count"]
    final_ast_link_count = analysis_results["dependency_suggestion"]["ast_link_count"] # Get final count
    logger.info(
        f"Dependency suggestion complete. Generated {final_suggestion_count} total raw suggestions "
        f"and {final_ast_link_count} AST-verified links from file analysis."
    )


    # --- NEW: Save all_project_ast_links to ast_verified_links.json ---
    analysis_results["ast_verified_links_generation"] = {} # Initialize status dict
    if all_project_ast_links:
        try:
            core_dir = os.path.dirname(os.path.abspath(key_manager.__file__)) # Assuming key_manager is imported
            current_ast_links_path = normalize_path(os.path.join(core_dir, AST_VERIFIED_LINKS_FILENAME))
            old_ast_links_path = normalize_path(os.path.join(core_dir, OLD_AST_VERIFIED_LINKS_FILENAME))
            os.makedirs(core_dir, exist_ok=True)

            if os.path.exists(current_ast_links_path):
                try: 
                    shutil.move(current_ast_links_path, old_ast_links_path)
                    logger.info(f"Renamed existing '{AST_VERIFIED_LINKS_FILENAME}' to '{OLD_AST_VERIFIED_LINKS_FILENAME}'.")
                except OSError as rename_err: 
                    logger.error(f"Failed to rename current AST verified links file to old: {rename_err}")
            
            with open(current_ast_links_path, 'w', encoding='utf-8') as f_ast_links:
                json.dump(all_project_ast_links, f_ast_links, indent=2)
            logger.info(f"Successfully saved AST verified links to: {current_ast_links_path} ({len(all_project_ast_links)} links)")
            analysis_results["ast_verified_links_generation"]["status"] = "success"
            analysis_results["ast_verified_links_generation"]["path"] = current_ast_links_path
            analysis_results["ast_verified_links_generation"]["count"] = len(all_project_ast_links)
        except Exception as e_ast_links_save:
            logger.error(f"Failed to save AST verified links: {e_ast_links_save}", exc_info=True)
            analysis_results["ast_verified_links_generation"]["status"] = "error"
            analysis_results["ast_verified_links_generation"]["error_message"] = str(e_ast_links_save)
    else:
        logger.info("No AST-verified links collected. 'ast_verified_links.json' will not be created or will be empty if it previously existed and was moved.")
        analysis_results["ast_verified_links_generation"]["status"] = "no_data"
        # Optionally, ensure an empty file or remove old if no data
        core_dir = os.path.dirname(os.path.abspath(key_manager.__file__))
        current_ast_links_path = normalize_path(os.path.join(core_dir, AST_VERIFIED_LINKS_FILENAME))
        if not os.path.exists(current_ast_links_path): # If it wasn't created because no data
             with open(current_ast_links_path, 'w', encoding='utf-8') as f_empty: json.dump([], f_empty) # Create empty
    

    # --- Combine suggestions within each source key using priority ---
    # This step is crucial before adding reciprocal ones
    # Import helper here to avoid potential circular dependencies at module level
    from cline_utils.dependency_system.analysis.dependency_suggester import _combine_suggestions_path_based_with_char_priority # Needs import
    combined_path_suggestions_for_conversion = defaultdict(list)
    for source_path, path_sugg_list in all_path_based_suggestions.items():
            combined_path_suggestions_for_conversion[source_path] = _combine_suggestions_path_based_with_char_priority(path_sugg_list, source_path)
    logger.debug(f"Combined path-based suggestions by priority. Count remains: {sum(len(v) for v in combined_path_suggestions_for_conversion.values())}")

    # --- CONVERT Path-Based Suggestions to KEY#global_instance Format ---
    logger.info("Converting path-based suggestions to KEY#global_instance format for tracker updates...")
    all_global_instance_suggestions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    
    # --- MODIFICATION: Use a local cache for this specific conversion loop if desired, 
    # or rely on the module-level cache in tracker_utils.
    # For clarity, let's show passing a local cache instance.
    # If the module-level cache in tracker_utils is sufficient, this can be omitted.
    _base_key_to_sorted_KIs_cache_for_conversion: Dict[str, List[key_manager.KeyInfo]] = defaultdict(list) 
    # ---

    # Ensure path_to_key_info is the current global map
    current_global_map = path_to_key_info 

    for src_path, path_deps_list in combined_path_suggestions_for_conversion.items(): # Assuming combined_path_suggestions_for_conversion is populated
        src_ki = current_global_map.get(src_path)
        if not src_ki: 
            logger.warning(f"ProjectAnalyzerConversion: Source path '{src_path}' from suggestions not in global map. Skipping.")
            continue
        
        # --- MODIFICATION: Call the utility function from tracker_utils ---
        src_key_global_instance_str = get_key_global_instance_string(
            src_ki, 
            current_global_map, 
            _base_key_to_sorted_KIs_cache_for_conversion # Pass the local cache
        )
        # ---
        if not src_key_global_instance_str:
            logger.warning(f"ProjectAnalyzerConversion: Could not get global instance string for source KI '{src_ki.norm_path}'. Skipping suggestions from it.")
            continue
            
        processed_target_deps = []
        for tgt_path, char_val in path_deps_list:
            tgt_ki = current_global_map.get(tgt_path)
            if not tgt_ki:
                logger.warning(f"ProjectAnalyzerConversion: Target path '{tgt_path}' not in global map. Skipping for source '{src_path}'.")
                continue
            
            # --- MODIFICATION: Call the utility function from tracker_utils ---
            tgt_key_global_instance_str = get_key_global_instance_string(
                tgt_ki, 
                current_global_map, 
                _base_key_to_sorted_KIs_cache_for_conversion # Pass the local cache
            )
            # ---
            if not tgt_key_global_instance_str:
                logger.warning(f"ProjectAnalyzerConversion: Could not get global instance for target KI '{tgt_ki.norm_path}'. Skipping for source '{src_path}'.")
                continue
            processed_target_deps.append((tgt_key_global_instance_str, char_val))
            
        if processed_target_deps:
            all_global_instance_suggestions[src_key_global_instance_str].extend(processed_target_deps)
            
    logger.info(f"Converted to {sum(len(v) for v in all_global_instance_suggestions.values())} KEY#global_instance formatted suggestions.")

    # --- Update Trackers ---
    logger.info("Updating trackers...")
    analysis_results["tracker_updates"]["mini"] = {} 
    analysis_results["tracker_updates"]["doc"] = "pending"
    analysis_results["tracker_updates"]["main"] = "pending"

    # --- Update Mini Trackers FIRST ---
    mini_tracker_paths_updated = set() # Keep track of updated module paths to avoid redundant processing if paths overlap
    potential_mini_tracker_dirs: List[key_manager.KeyInfo] = []
    for ki_obj in path_to_key_info.values(): 
        if ki_obj.is_directory:
            if not ki_obj.norm_path or ki_obj.norm_path == ".":
                logger.warning(f"Skipping KeyInfo with invalid norm_path for module consideration: {ki_obj}")
                continue
            is_mod_dir = False
            # A directory is a potential module dir if it IS a code root OR if it is a SUBDIRECTORY of any code root.
            for code_r_abs in abs_code_roots:
                if ki_obj.norm_path == code_r_abs or is_subpath(ki_obj.norm_path, code_r_abs):
                    if ki_obj.norm_path not in all_excluded_paths_abs_set: 
                        is_mod_dir = True; break 
            if is_mod_dir:
                potential_mini_tracker_dirs.append(ki_obj)
    unique_potential_module_dirs_map: Dict[str, key_manager.KeyInfo] = {}
    for ki_dir in potential_mini_tracker_dirs:
        if ki_dir.norm_path not in unique_potential_module_dirs_map:
            unique_potential_module_dirs_map[ki_dir.norm_path] = ki_dir
    potential_mini_tracker_dirs = list(unique_potential_module_dirs_map.values())
    # Optional: Sort them by path for consistent processing order, e.g., parent dirs first.
    potential_mini_tracker_dirs.sort(key=lambda ki: ki.norm_path)
    logger.info(f"Identified {len(potential_mini_tracker_dirs)} potential directories for mini-trackers:")
    for ki_dir_log in potential_mini_tracker_dirs:
        logger.debug(f"  - Potential Module Dir: {ki_dir_log.norm_path} (Key: {ki_dir_log.key_string})")

    for module_key_info_obj in potential_mini_tracker_dirs:
        norm_module_path = module_key_info_obj.norm_path
        if not norm_module_path: 
            logger.error(f"Encountered module KeyInfo with empty norm_path: {module_key_info_obj}. Skipping mini-tracker update.")
            analysis_results["tracker_updates"]["mini"][f"ERROR_EMPTY_MODULE_PATH_FOR_{module_key_info_obj.key_string}"] = "failure_empty_path"
            continue
        if norm_module_path in mini_tracker_paths_updated: continue
        expected_mini_tracker_filename = os.path.basename(
            tracker_io.get_tracker_path(project_root=project_root, tracker_type="mini", module_path=norm_module_path)
        )
        if os.path.isdir(norm_module_path) and not _is_empty_dir(norm_module_path, expected_mini_tracker_filename):
            mini_tracker_path_val = tracker_io.get_tracker_path(
                project_root=project_root, tracker_type="mini", module_path=norm_module_path
            )
            logger.info(f"Updating mini tracker for module '{norm_module_path}' (Key: {module_key_info_obj.key_string}) at: {mini_tracker_path_val}") 
            mini_tracker_paths_updated.add(norm_module_path)
            try:
                tracker_io.update_tracker(
                    output_file_suggestion=mini_tracker_path_val,
                    path_to_key_info=path_to_key_info,
                    tracker_type="mini",
                    suggestions_external=all_global_instance_suggestions, 
                    file_to_module=file_to_module,
                    new_keys=newly_generated_keys,
                    force_apply_suggestions=False, 
                    use_old_map_for_migration=old_map_existed_before_gen 
                )
                analysis_results["tracker_updates"]["mini"][norm_module_path] = "success"
            except Exception as mini_err:
                logger.error(f"Error updating mini tracker {mini_tracker_path_val}: {mini_err}", exc_info=True) 
                analysis_results["tracker_updates"]["mini"][norm_module_path] = "failure"
                analysis_results["status"] = "warning"
        elif os.path.isdir(norm_module_path): 
            logger.debug(f"Skipping mini-tracker update for empty module directory: {norm_module_path}")

    # --- Update Doc Tracker ---
    doc_directories_rel = config.get_doc_directories() # Ensure this is fetched correctly
    doc_tracker_path = tracker_io.get_tracker_path(project_root, tracker_type="doc") if doc_directories_rel else None
    if doc_tracker_path:
        logger.info(f"Updating doc tracker: {doc_tracker_path}")
        try:
            tracker_io.update_tracker(
                output_file_suggestion=doc_tracker_path, 
                path_to_key_info=path_to_key_info, 
                tracker_type="doc", 
                suggestions_external=all_global_instance_suggestions, 
                file_to_module=file_to_module, 
                new_keys=newly_generated_keys, 
                force_apply_suggestions=False,
                use_old_map_for_migration=old_map_existed_before_gen
            )
            analysis_results["tracker_updates"]["doc"] = "success"
        except Exception as doc_err:
            logger.error(f"Error updating doc tracker {doc_tracker_path}: {doc_err}", exc_info=True)
            # This part is reached if update_tracker itself raises an exception
            analysis_results["tracker_updates"]["doc"] = "failure"
            analysis_results["status"] = "warning" 
            # If the error from update_tracker is critical, consider setting status to "error"
            # analysis_results["message"] = f"Doc tracker update failed: {doc_err}"
    else:
        logger.info("Doc tracker update skipped: No doc directories configured or path determination failed.")
        analysis_results["tracker_updates"]["doc"] = "skipped_no_config"

    # --- Update Main Tracker LAST (using aggregation) ---
    main_tracker_path = tracker_io.get_tracker_path(project_root, tracker_type="main")
    logger.info(f"Updating main tracker (with internal aggregation): {main_tracker_path}")
    try:
        tracker_io.update_tracker(
            output_file_suggestion=main_tracker_path, path_to_key_info=path_to_key_info,
            tracker_type="main", 
            suggestions_external=all_global_instance_suggestions, 
            file_to_module=file_to_module,
            new_keys=newly_generated_keys, force_apply_suggestions=False,
            use_old_map_for_migration=old_map_existed_before_gen
        )
        analysis_results["tracker_updates"]["main"] = "success"
    except Exception as main_err:
        logger.error(f"Error updating main tracker {main_tracker_path}: {main_err}", exc_info=True)
        analysis_results["tracker_updates"]["main"] = "failure"; analysis_results["status"] = "warning"

    # --- Template Generation ---
    logger.info("Starting template generation (e.g., final review checklist)...")
    try:
        # Pass the pre-computed current global map and path migration map
        checklist_generated_successfully = generate_final_review_checklist(
            global_key_map_param=path_to_key_info,
            path_migration_info_param=path_migration_info
        )
        if checklist_generated_successfully:
            analysis_results["template_generation"]["final_review_checklist"] = "success"
            logger.info("Final review checklist generated successfully.")
        else:
            analysis_results["template_generation"]["final_review_checklist"] = "failure"
            logger.warning("Final review checklist generation failed. Check logs for details.")
            if analysis_results["status"] == "success":
                 analysis_results["status"] = "warning"; analysis_results["message"] += " Warning: Failed to generate final review checklist."
    except Exception as template_err:
        analysis_results["template_generation"]["final_review_checklist"] = "error"
        logger.error(f"Critical error during template generation: {template_err}", exc_info=True)
        if analysis_results["status"] == "success": analysis_results["status"] = "warning"
        analysis_results["message"] += f" Critical error during template generation: {template_err}."

    # --- Auto Diagram Generation ---
    auto_generate_enabled = config.config.get("visualization", {}).get("auto_generate_on_analyze", True)
    if auto_generate_enabled:
        logger.info("Starting automatic diagram generation...")
        analysis_results["auto_visualization"] = {"overview": "skipped", "modules": {}}
        memory_dir_rel_analyzer = config.get_path('memory_dir', 'cline_docs')
        default_diagram_subdir = "dependency_diagrams"
        default_auto_diagram_dir_abs = normalize_path(os.path.join(project_root, memory_dir_rel_analyzer, default_diagram_subdir))
        auto_diagram_output_dir_config_rel = config.config.get("visualization", {}).get("auto_diagram_output_dir") 
        if auto_diagram_output_dir_config_rel:
            auto_diagram_output_dir_abs = normalize_path(os.path.join(project_root, auto_diagram_output_dir_config_rel))
            logger.info(f"Using configured auto diagram output directory: {auto_diagram_output_dir_abs}")
        else:
            auto_diagram_output_dir_abs = default_auto_diagram_dir_abs
            logger.info(f"Using default auto diagram output directory: {auto_diagram_output_dir_abs}")
        try:
            if not os.path.exists(auto_diagram_output_dir_abs):
                os.makedirs(auto_diagram_output_dir_abs, exist_ok=True)

            # Find all tracker paths *again* here, as they might have just been created/updated
            current_tracker_paths = tracker_io.find_all_tracker_paths(config, project_root)

            # --- Generate Project Overview Diagram ---
            logger.info("Generating project overview diagram...")
            overview_filename = "project_overview_dependencies.mermaid"
            overview_path = os.path.join(auto_diagram_output_dir_abs, overview_filename)
            # Pass path_migration_info to generate_mermaid_diagram
            overview_mermaid_code = generate_mermaid_diagram(
                focus_keys_list_input=[], 
                global_path_to_key_info_map=path_to_key_info,
                path_migration_info=path_migration_info, 
                all_tracker_paths_list=list(current_tracker_paths), config_manager_instance=config
            )
            if overview_mermaid_code and "// No relevant data" not in overview_mermaid_code and not overview_mermaid_code.strip().startswith("Error:"): 
                with open(overview_path, 'w', encoding='utf-8') as f: f.write(overview_mermaid_code)
                logger.info(f"Project overview diagram saved to {overview_path}")
                analysis_results["auto_visualization"]["overview"] = "success"
            else:
                logger.warning(f"Skipping save for project overview diagram (no data or failed generation). Error: {overview_mermaid_code if overview_mermaid_code and 'Error:' in overview_mermaid_code[:20] else 'No data'}")
                analysis_results["auto_visualization"]["overview"] = "nodata_or_failed"

            # --- Generate Per-Module Diagrams ---
            module_keys_to_visualize = []
            for key_info_obj_analyzer in path_to_key_info.values():
                if key_info_obj_analyzer.is_directory:
                    is_top_level_module_dir_analyzer = any(key_info_obj_analyzer.norm_path == acr_path_analyzer or key_info_obj_analyzer.parent_path == acr_path_analyzer for acr_path_analyzer in abs_code_roots) 
                    if is_top_level_module_dir_analyzer:
                         module_keys_to_visualize.append(key_info_obj_analyzer.key_string)
            module_keys_unique = sorted(list(set(module_keys_to_visualize)))
            logger.info(f"Identified module keys for auto-visualization: {module_keys_unique}")
            analysis_results["auto_visualization"]["modules"] = {mk: "skipped" for mk in module_keys_unique} 
            for module_key_str in module_keys_unique:
                logger.info(f"Generating diagram for module: {module_key_str}...")
                module_diagram_filename = f"module_{module_key_str}_dependencies.mermaid".replace("/", "_").replace("\\", "_")
                module_diagram_path = os.path.join(auto_diagram_output_dir_abs, module_diagram_filename)
                module_mermaid_code = generate_mermaid_diagram(
                    focus_keys_list_input=[module_key_str], 
                    global_path_to_key_info_map=path_to_key_info,
                    path_migration_info=path_migration_info, 
                    all_tracker_paths_list=list(current_tracker_paths), config_manager_instance=config
                )
                if module_mermaid_code and "// No relevant data" not in module_mermaid_code and "Error:" not in module_mermaid_code[:20]:
                    with open(module_diagram_path, 'w', encoding='utf-8') as f: f.write(module_mermaid_code)
                    logger.info(f"Module {module_key_str} diagram saved to {module_diagram_path}")
                    analysis_results["auto_visualization"]["modules"][module_key_str] = "success"
                else:
                    logger.warning(f"Skipping save for module {module_key_str} diagram (no data or failed generation). Error: {module_mermaid_code if module_mermaid_code and 'Error:' in module_mermaid_code[:20] else 'No data'}")
                    analysis_results["auto_visualization"]["modules"][module_key_str] = "nodata_or_failed"
        except Exception as viz_err:
            logger.error(f"Error during automatic diagram generation: {viz_err}", exc_info=True)
            analysis_results["auto_visualization"]["status"] = "error"
            if analysis_results["status"] == "success": analysis_results["status"] = "warning"
            analysis_results["message"] += f" Warning: Automatic diagram generation failed: {viz_err}."
    else:
        logger.info("Automatic diagram generation is disabled in config.")
        analysis_results["auto_visualization"]["status"] = "disabled"

    if analysis_results["status"] == "success" and not analysis_results["warnings"]: final_message = "Project analysis completed successfully."
    elif analysis_results["status"] == "success" and analysis_results["warnings"]: final_message = f"Project analysis completed with warnings: {'; '.join(analysis_results['warnings'])}. Check logs."; analysis_results["status"] = "warning"
    elif analysis_results["status"] == "warning": final_message = f"Project analysis completed with warnings: {analysis_results.get('message', '')} {'; '.join(analysis_results['warnings'])}. Check logs."
    else: final_message = f"Project analysis failed: {analysis_results.get('message', '')}. Check logs."
    analysis_results["message"] = final_message
    logger.info(final_message)

    # --- MODIFICATION: Clear the dedicated AST cache at the end of the project analysis ---
    try:
        ast_cache_instance = cache_manager.get_cache("ast_cache")
        # More robustly clear the cache data if Cache class has such a method or clear dicts directly
        if hasattr(ast_cache_instance, 'data') and isinstance(ast_cache_instance.data, dict):
            ast_cache_instance.data.clear()
        if hasattr(ast_cache_instance, 'dependencies') and isinstance(ast_cache_instance.dependencies, dict):
            ast_cache_instance.dependencies.clear()
        if hasattr(ast_cache_instance, 'reverse_deps') and isinstance(ast_cache_instance.reverse_deps, dict):
            ast_cache_instance.reverse_deps.clear()
        # Reset hits/misses if desired, or let them accumulate if CacheManager instance is long-lived
        ast_cache_instance.hits = 0
        ast_cache_instance.misses = 0
        logger.info("Cleared in-memory AST cache ('ast_cache') after project analysis.")
    except Exception as e_clear_ast:
        # Catch any exception during cache clearing to prevent analyze_project from failing here
        logger.warning(f"Could not explicitly clear 'ast_cache' at the end of project analysis: {e_clear_ast}")
    # --- END OF MODIFICATION ---

    return analysis_results

def _is_empty_dir(dir_path: str, tracker_filename_to_ignore: Optional[str] = None) -> bool:
    """
    Checks if a directory is effectively empty for tracker creation purposes.
    It's empty if it contains no files or subdirectories, OR if it only contains
    the tracker file that would be associated with it (if provided).
    """
    try:
        items_in_dir = os.listdir(dir_path)
        if not items_in_dir: 
            return True 
        if tracker_filename_to_ignore:
            # Check if only the tracker file itself is present
            if len(items_in_dir) == 1 and items_in_dir[0].lower() == tracker_filename_to_ignore.lower():
                logger.debug(f"Directory '{dir_path}' considered empty for tracker creation as it only contains '{tracker_filename_to_ignore}'.")
                return True
            # Check if it contains more than just the tracker file
            elif tracker_filename_to_ignore.lower() in [item.lower() for item in items_in_dir] and len(items_in_dir) > 1:
                return False 
            elif tracker_filename_to_ignore.lower() not in [item.lower() for item in items_in_dir] and items_in_dir:
                return False 
        return False if items_in_dir else True
    except FileNotFoundError: 
        logger.debug(f"Directory not found '{dir_path}' while checking if empty (for tracker creation). Treating as empty.")
        return True 
    except NotADirectoryError: 
        logger.debug(f"Path '{dir_path}' is not a directory (for tracker creation). Treating as empty.")
        return True 
    except OSError as e: 
        logger.error(f"OS error checking dir '{dir_path}' (for tracker creation): {e}. Assuming not empty for safety.")
        return False # Assume not empty on permission error etc. to be safe

# --- End of project_analyzer.py ---