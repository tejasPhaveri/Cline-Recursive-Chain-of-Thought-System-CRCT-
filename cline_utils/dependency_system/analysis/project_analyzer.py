# analysis/project_analyzer.py

from collections import defaultdict
import fnmatch
import json
import os
from typing import Any, Dict, Optional, List, Tuple
from cline_utils.dependency_system.core.dependency_grid import decompress
from cline_utils.dependency_system.io.tracker_io import read_tracker_file, get_tracker_path, update_tracker
import uuid
import logging
from cline_utils.dependency_system.analysis.dependency_analyzer import analyze_file
from cline_utils.dependency_system.utils.batch_processor import BatchProcessor, process_items
from cline_utils.dependency_system.analysis.dependency_suggester import suggest_dependencies
from cline_utils.dependency_system.analysis.embedding_manager import generate_embeddings
from cline_utils.dependency_system.core.key_manager import get_key_from_path, generate_keys, validate_key, KeyInfo, KeyGenerationError, sort_keys
from cline_utils.dependency_system.utils.cache_manager import cached, file_modified, clear_all_caches
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.path_utils import is_subpath, normalize_path, get_project_root

logger = logging.getLogger(__name__)

# Caching for analyze_project (Consider if key_func needs more refinement)
# @cached("project_analysis",
#        key_func=lambda force_analysis=False, force_embeddings=False, **kwargs:
#        f"analyze_project:{normalize_path(get_project_root())}:{(os.path.getmtime(ConfigManager().config_path) if os.path.exists(ConfigManager().config_path) else 0)}:{force_analysis}:{force_embeddings}")
def analyze_project(force_analysis: bool = False, force_embeddings: bool = False) -> Dict[str, Any]:
    """
    Analyzes all files in a project to identify dependencies between them,
    initialize trackers, and suggest dependencies using the new contextual key system.

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
    # Clear relevant caches if forcing re-analysis (more targeted cache clearing might be needed)
    if force_analysis:
        logger.info("Force analysis requested. Clearing all caches.")
        clear_all_caches()

    results = {
        "status": "success",
        "message": "",
        "tracker_initialization": {},
        "embedding_generation": {},
        "dependency_suggestion": {},
        "tracker_update": {},
        "file_analysis": {} # Store results keyed by normalized absolute path
    }

    # --- Exclusion Setup ---
    excluded_dirs_rel = config.get_excluded_dirs()
    excluded_paths_rel = config.get_excluded_paths()
    excluded_extensions = set(config.get_excluded_extensions())
    excluded_file_patterns = config.config.get("excluded_file_patterns", [])
    
    excluded_dirs_abs = {normalize_path(os.path.join(project_root, p)) for p in excluded_dirs_rel}
    excluded_paths_abs = {normalize_path(os.path.join(project_root, p)) for p in excluded_paths_rel}
    all_excluded_paths_abs = excluded_dirs_abs.union(excluded_paths_abs)

    # Early exit if project root itself is excluded
    norm_project_root = normalize_path(project_root)
    if any(norm_project_root == excluded_path or norm_project_root.startswith(excluded_path + os.sep) # Use os.sep
           for excluded_path in all_excluded_paths_abs):
        logger.info(f"Skipping analysis of excluded project root: {project_root}")
        results["status"] = "skipped"; results["message"] = "Project root is excluded"; return results

    # --- Root Directories Setup ---
    code_root_directories_rel = config.get_code_root_directories()
    doc_directories_rel = config.get_doc_directories()
    # Combine unique roots
    all_roots_rel = list(set(code_root_directories_rel + doc_directories_rel)) # Use set for uniqueness

    # Sort the relative root paths alphabetically to ensure stable order
    all_roots_rel.sort()
    logger.debug(f"Processing root directories in stable order: {all_roots_rel}")

    if not code_root_directories_rel:
        logger.error("No code root directories configured.")
        results["status"] = "error"; results["message"] = "No code root directories configured."; return results
    if not doc_directories_rel:
        logger.warning("No documentation directories configured. Proceeding without doc analysis.")

    abs_code_roots = {normalize_path(os.path.join(project_root, r)) for r in code_root_directories_rel}
    abs_doc_roots = {normalize_path(os.path.join(project_root, r)) for r in doc_directories_rel}
    abs_all_roots = {normalize_path(os.path.join(project_root, r)) for r in all_roots_rel}


    # --- Key Generation ---
    logger.info("Generating keys...")
    path_to_key_info: Dict[str, KeyInfo] = {} # Initialize map
    newly_generated_keys: List[KeyInfo] = [] # Initialize list

    try:
        # <<< *** MODIFIED CALL *** >>>
        # Pass the SORTED relative roots and the precomputed absolute excluded paths
        path_to_key_info, newly_generated_keys = generate_keys(
            all_roots_rel, # Pass the sorted list
            # Pass exclusions directly if generate_keys handles fetching them internally,
            # otherwise pass the computed sets as before. Assuming generate_keys uses config:
            excluded_dirs=excluded_dirs_rel, # Pass rel paths/names
            excluded_extensions=excluded_extensions,
            precomputed_excluded_paths=all_excluded_paths_abs # Pass computed absolute paths
        )
        results["tracker_initialization"]["key_generation"] = "success"
        logger.info(f"Generated {len(path_to_key_info)} keys for {len(path_to_key_info)} files/dirs.")
        if newly_generated_keys:
            # Log count, maybe sample? Full list might be too long.
            logger.info(f"Assigned {len(newly_generated_keys)} new keys.")
            # Example: Log first 5 new key strings:
            # logger.debug(f"Sample new keys: {', '.join([k.key_string for k in newly_generated_keys[:5]])}")

    # <<< *** ADDED ERROR HANDLING *** >>>
    except KeyGenerationError as kge:
        results["status"] = "error"; results["message"] = f"Key generation failed: {kge}"; logger.critical(results["message"]); return results
    except Exception as e:
        results["status"] = "error"; results["message"] = f"Key generation failed unexpectedly: {e}"; logger.exception(results["message"]); return results

    # <<< *** REMOVED *** >>>
    # path_to_key = {v: k for k, v in key_map.items()} # No longer needed / possible directly

    # --- Create file_to_module mapping (Adapted for path_to_key_info) ---
    # Maps normalized absolute file path -> normalized absolute parent directory path (module path)
    # <<< *** NEW BLOCK *** >>>
    logger.info("Creating file-to-module mapping...")
    file_to_module: Dict[str, str] = {}
    for key_info in path_to_key_info.values():
        if not key_info.is_directory:
            if key_info.parent_path:
                file_path = key_info.norm_path
                module_path = key_info.parent_path
                file_to_module[file_path] = module_path
            else:
                logger.warning(f"File '{key_info.norm_path}' (Key: {key_info.key_string}) has no parent path. Cannot map to a module.")
    logger.info(f"File-to-module mapping created with {len(file_to_module)} entries.")

    # --- File Identification and Filtering ---
    config_manager_instance = ConfigManager()
    logger.info("Identifying files for analysis...")
    files_to_analyze_abs = []
    # Get excluded_file_patterns from config
    excluded_file_patterns = config_manager_instance.config.get("excluded_file_patterns", [])

    # Use abs_all_roots for finding files, order doesn't strictly matter here
    for abs_root_dir in abs_all_roots:
        if not os.path.isdir(abs_root_dir):
            logger.warning(f"Configured root directory not found: {abs_root_dir}")
            continue
        # Use os.walk - order within walk is OS-dependent but shouldn't affect analysis results
        for root, dirs, files in os.walk(abs_root_dir, topdown=True):
            norm_root = normalize_path(root)
            
            # Directory filtering
            dirs[:] = [
                d for d in dirs 
                if d not in excluded_dirs_rel
                and normalize_path(os.path.join(norm_root, d)) not in all_excluded_paths_abs
            ]

            # Check if the current directory itself is excluded by path/pattern
            is_root_excluded_by_path = False
            # Check against the comprehensive exclusion set
            if norm_root in all_excluded_paths_abs or \
               any(is_subpath(norm_root, excluded) for excluded in all_excluded_paths_abs):
                 is_root_excluded_by_path = True

            if is_root_excluded_by_path:
                logger.debug(f"Skipping files in excluded directory: {norm_root}")
                dirs[:] = [] # Prevent recursion into excluded directories
                continue

            # Process files in the current directory
            for file in files:
                file_path_abs = normalize_path(os.path.join(norm_root, file))
                file_basename = os.path.basename(file_path_abs)
                _, file_ext = os.path.splitext(file)
                file_ext = file_ext.lower()

                # Check all exclusion criteria
                is_excluded = (
                    file_path_abs in all_excluded_paths_abs
                    or any(is_subpath(file_path_abs, excluded) for excluded in all_excluded_paths_abs)
                    or file_ext in excluded_extensions
                    or any(fnmatch.fnmatch(file_basename, pattern) for pattern in excluded_file_patterns)
                )

                if is_excluded:
                    logger.debug(f"Skipping excluded file: {file_path_abs}")
                    continue

                if file_path_abs in path_to_key_info:
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

    results["file_analysis"] = file_analysis_results
    logger.info(f"File analysis complete. Analyzed: {analyzed_count}, Skipped: {skipped_count}, Errors: {error_count}")

        # --- Create file_to_module mapping (Adapted for path_to_key_info) ---
    # Maps normalized absolute file path -> normalized absolute parent directory path (module path)

    # Input: path_to_key_info: Dict[str, KeyInfo] from key_manager.generate_keys()
    # Output: file_to_module: Dict[str, str]

    file_to_module: Dict[str, str] = {}

    # Iterate through all the generated key information
    for key_info in path_to_key_info.values():
        # We only care about mapping files
        if not key_info.is_directory:
            # Ensure the file has a parent path recorded (should always be true for non-root files)
            if key_info.parent_path:
                # The file's path is key_info.norm_path
                # The module's path (containing directory) is key_info.parent_path
                file_path = key_info.norm_path
                module_path = key_info.parent_path # Direct parent directory path

                # Add the mapping
                file_to_module[file_path] = module_path
                # logger.debug(f"Mapped file '{file_path}' to module '{module_path}'") # Optional debug log
            else:
                # This case should be rare (files directly in filesystem root?), log if encountered.
                logger.warning(f"File '{key_info.norm_path}' has no parent path in KeyInfo. Cannot map to a module.")

    logger.info(f"File-to-module mapping created with {len(file_to_module)} entries.")

    # Note: The abs_code_roots and abs_doc_roots variables might still be needed elsewhere
    # (e.g., for determining which modules go into the main tracker), but they are
    # no longer needed for generating this specific file_to_module map.


    # --- Embedding generation ---
    logger.info("Starting embedding generation...")
    try:
        # <<< *** MODIFIED CALL *** >>>
        # Pass path_to_key_info instead of key_map
        success = generate_embeddings(all_roots_rel, path_to_key_info, force=force_embeddings)
        results["embedding_generation"]["status"] = "success" if success else "partial_failure"
        if not success: results["message"] += " Warning: Embedding generation failed for some paths."; logger.warning("Embedding generation failed or skipped for some paths.")
        else: logger.info("Embedding generation completed successfully.")
    except Exception as e:
        results["embedding_generation"]["status"] = "error"
        results["status"] = "error" # Upgrade status to error if embedding process fails critically
        results["message"] = f"Embedding generation process failed critically: {e}"
        logger.exception(results["message"]); return results


    # --- Dependency Suggestion ---
    logger.info("Starting dependency suggestion...")
    try:
        # Start with initial suggestions (e.g., from key generation if any)
        # Use defaultdict for easier merging
        all_suggestions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        # Merge initial suggestions if they exist
        # for src, targets in initial_suggestions.items():
        #    all_suggestions[src].extend(targets)

        # Add suggestions based on file analysis
        suggestion_count = 0
        # Use list of keys corresponding to analyzed files
        analyzed_file_paths = list(file_analysis_results.keys())
        for file_path_abs in analyzed_file_paths:
            # <<< *** MODIFIED key lookup *** >>>
            file_key_info = path_to_key_info.get(file_path_abs)
            if not file_key_info:
                logger.warning(f"No key info found for analyzed file {file_path_abs}, skipping suggestion.")
                continue
            file_key_string = file_key_info.key_string # Get the actual key string

            # <<< *** MODIFIED CALL *** >>>
            # Pass path_to_key_info instead of key_map
            suggestions_for_file = suggest_dependencies(
                file_path_abs,
                path_to_key_info, # Pass the main map
                project_root,
                file_analysis_results, # Pass the collected analysis results
                threshold=0.65 # This threshold is primarily for semantic fallback
            )

            if suggestions_for_file:
                # Suggestions are returned as (target_key_string, dep_char)
                all_suggestions[file_key_string].extend(suggestions_for_file)
                suggestion_count += len(suggestions_for_file)

        logger.info(f"Generated {suggestion_count} raw suggestions from file analysis.")

        # --- Combine suggestions within each source key using priority ---
        # This step is crucial before adding reciprocal ones
        logger.debug("Combining suggestions per source key using priorities...")
        combined_suggestions_per_source: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        # Import helper here to avoid potential circular dependencies at module level
        from cline_utils.dependency_system.analysis.dependency_suggester import _combine_suggestions_with_char_priority
        for source_key, suggestion_list in all_suggestions.items():
             combined_suggestions_per_source[source_key] = _combine_suggestions_with_char_priority(suggestion_list)
        all_suggestions = combined_suggestions_per_source # Replace raw with combined

        # # --- Add reciprocal '<'/'x' dependencies ---
        # logger.debug("Adding/Merging reciprocal dependencies ('<' or 'x')...")
        # get_priority = config.get_char_priority
        # keys_with_suggestions = list(all_suggestions.keys()) # Key strings
        # 
        # for source_key in keys_with_suggestions:
        #     # Use list() to avoid modifying dict during iteration if suggestion list changes
        #     current_source_suggestions = list(all_suggestions.get(source_key, []))
        # 
        #     for target_key, dep_char in current_source_suggestions:
        #          # <<< *** MODIFIED CHECK *** >>>
        #          # Check if target_key corresponds to a valid path in the map
        #          # This requires finding *a* path for the target key, which is ambiguous.
        #          # Assumption: suggest_dependencies returned valid target_key strings that exist in the map.
        #          # We need a way to confirm target_key represents a valid entity without needing its path here.
        #          # Let's rely on the suggestion function having done its job for now.
        #          # The check `target_key == source_key` is still valid.
        #          if target_key == source_key:
        #                continue
        # 
        #          target_suggestions = all_suggestions.setdefault(target_key, [])
        #          # Use a map for quick lookup of existing char from target back to source
        #          target_suggestion_map = {t: c for t, c in target_suggestions}
        #          existing_char_in_target = target_suggestion_map.get(source_key)
        #          existing_priority = get_priority(existing_char_in_target) if existing_char_in_target else -1
        # 
        #          reciprocal_char = None
        #          reciprocal_priority = -1
        # 
        #          if dep_char == '>':
        #               reciprocal_char = '<'
        #               reciprocal_priority = get_priority('<')
        #          elif dep_char == '<':
        #               reciprocal_char = '>'
        #               reciprocal_priority = get_priority('>')
        #          # Add other reciprocal pairs if needed (e.g., 'd'?)
        # 
        #          if reciprocal_char:
        #              if reciprocal_priority > existing_priority:
        #                   # Remove existing lower priority char if present
        #                   target_suggestions[:] = [(t, c) for t, c in target_suggestions if t != source_key]
        #                   # Add the new reciprocal dependency
        #                   logger.debug(f"Reciprocal: Adding {target_key} -> {source_key} ('{reciprocal_char}') based on {source_key}->{target_key} ('{dep_char}')")
        #                   target_suggestions.append((source_key, reciprocal_char))
        #              # MERGE to 'x' if mutual dependency (A->B='<' AND B->A='<') is found
        #              elif dep_char == '<' and existing_char_in_target == '<': # Check for matching '<' in both directions
        #                   if existing_char_in_target != 'x': # Avoid re-merging 'x'
        #                        # Update target -> source (B -> A) to 'x'
        #                        target_suggestions[:] = [(t, 'x' if t == source_key else c) for t, c in target_suggestions]
        #                        logger.debug(f"Mutual: Merging {target_key} -> {source_key} to 'x' due to matching '<' dependencies.") # Updated log
        # 
        #                        # Also update the original source -> target (A -> B) to 'x'
        #                        current_source_suggestions_for_update = all_suggestions.get(source_key, []) # Refetch
        #                        if current_source_suggestions_for_update: # Check if list exists before modifying
        #                           current_source_suggestions_for_update[:] = [(orig_t, 'x' if orig_t == target_key else orig_c) for orig_t, orig_c in current_source_suggestions_for_update]
        #                           logger.debug(f"Mutual: Merging {source_key} -> {target_key} to 'x' due to matching '<' dependencies.") # Updated log
        # 
        #                   # else: Keep existing for other equal priority conflicts

        results["dependency_suggestion"]["status"] = "success"
        logger.info("Dependency suggestion combining completed.")


        # --- Update Trackers ---
        logger.info("Updating trackers...")

        # --- Update Mini Trackers FIRST ---
        results["tracker_update"]["mini"] = {}
        mini_tracker_paths_updated = set() # Track paths to avoid duplicates if structure overlaps

        # <<< *** MAJOR CHANGE HERE *** >>>
        # We need the list of modules (directories) that should have mini-trackers.
        # This requires filtering path_to_key_info based on config (e.g., only dirs under code_roots)
        # Let's assume a simple filter for now: all directories directly under code roots.
        # This filtering logic might need refinement based on exact requirements.
        potential_mini_tracker_dirs: Dict[str, KeyInfo] = {}
        for code_root_abs in abs_code_roots:
             for path, key_info in path_to_key_info.items():
                  if key_info.is_directory and key_info.parent_path == code_root_abs:
                       potential_mini_tracker_dirs[path] = key_info
                  # Also consider the code root itself if it contains files directly
                  elif key_info.is_directory and path == code_root_abs:
                       potential_mini_tracker_dirs[path] = key_info

        logger.info(f"Identified {len(potential_mini_tracker_dirs)} potential directories for mini-trackers.")

        # Iterate through the identified module paths
        for norm_module_path, module_key_info in potential_mini_tracker_dirs.items():
            module_key_string = module_key_info.key_string # Get key string for logging if needed
            # Check if directory is NOT empty before trying to update/create tracker
            if os.path.isdir(norm_module_path) and not _is_empty_dir(norm_module_path):
                if norm_module_path in mini_tracker_paths_updated: continue # Skip if already processed

                mini_tracker_path = get_tracker_path(project_root, tracker_type="mini", module_path=norm_module_path)
                logger.info(f"Updating mini tracker for module '{norm_module_path}' (Key: {module_key_string}) at: {mini_tracker_path}")
                mini_tracker_paths_updated.add(norm_module_path)
                try:
                    # Update the mini-tracker. Suggestions are applied internally by update_tracker.
                    # Pass the GLOBAL suggestions here. update_tracker will filter them based on the module.
                    update_tracker(
                        mini_tracker_path,
                        path_to_key_info, # Pass the main map
                        tracker_type="mini",
                        suggestions=all_suggestions, # Pass combined & reciprocal suggestions (keyed by key strings)
                        file_to_module=file_to_module,
                        new_keys=newly_generated_keys # Pass list of KeyInfo objects
                    )
                    results["tracker_update"]["mini"][norm_module_path] = "success"
                except Exception as mini_err:
                     logger.error(f"Error updating mini tracker {mini_tracker_path}: {mini_err}", exc_info=True)
                     results["tracker_update"]["mini"][norm_module_path] = "failure"
                     results["status"] = "warning"
            elif os.path.isdir(norm_module_path):
                logger.debug(f"Skipping mini-tracker update for empty directory: {norm_module_path}")
            # else: logger.warning(...) # Path check happens implicitly

        # --- Update Doc Tracker ---
        # Assuming doc tracker logic remains similar, just pass path_to_key_info
        doc_tracker_path = get_tracker_path(project_root, tracker_type="doc") if doc_directories_rel else None
        if doc_tracker_path:
            logger.info(f"Updating doc tracker: {doc_tracker_path}")
            try:
                 # <<< *** MODIFIED CALL *** >>>
                update_tracker(
                    doc_tracker_path,
                    path_to_key_info, # Pass the main map
                    "doc",
                    suggestions=all_suggestions,
                    file_to_module=file_to_module,
                    new_keys=newly_generated_keys # Pass list of KeyInfo objects
                )
                results["tracker_update"]["doc"] = "success"
            except Exception as doc_err:
                logger.error(f"Error updating doc tracker {doc_tracker_path}: {doc_err}", exc_info=True)
                results["tracker_update"]["doc"] = "failure"; results["status"] = "warning"

        # --- Update Main Tracker LAST (using aggregation) ---
        main_tracker_path = get_tracker_path(project_root, tracker_type="main")
        logger.info(f"Updating main tracker (with aggregation): {main_tracker_path}")
        try:
            # update_tracker for "main" will call the aggregation function internally.
            # Aggregation needs path_to_key_info and file_to_module.
            update_tracker(
                main_tracker_path,
                path_to_key_info, # Pass the main map
                "main",
                suggestions=None, # Aggregation happens internally
                file_to_module=file_to_module, # Needed by aggregation
                new_keys=newly_generated_keys # Pass list of KeyInfo objects
            )
            results["tracker_update"]["main"] = "success"
        except Exception as main_err:
            logger.error(f"Error updating main tracker {main_tracker_path}: {main_err}", exc_info=True)
            results["tracker_update"]["main"] = "failure"; results["status"] = "warning"

    except Exception as e:
        results["status"] = "error" # Critical error during suggestions/updates
        results["message"] = f"Dependency suggestion or tracker update failed critically: {e}"
        logger.exception(results["message"]); return results

    # --- Final Status Check & Return ---
    if results["status"] == "success": print("Project analysis completed successfully."); results["message"] = "Project analysis completed successfully."
    elif results["status"] == "warning": print("Project analysis completed with warnings. Check logs."); results["message"] = results.get("message", "") + " Project analysis completed with warnings."
    return results

def _is_empty_dir(dir_path: str) -> bool:
    """
    Checks if a directory is empty (contains no files or subdirectories).
    Handles potential permission errors.
    """
    try: return not os.listdir(dir_path)
    except FileNotFoundError:
        logger.warning(f"Directory not found while checking if empty: {dir_path}")
        return True # Treat non-existent as empty for skipping purposes
    except NotADirectoryError:
         logger.warning(f"Path is not a directory while checking if empty: {dir_path}")
         return True # Treat non-directory as empty for skipping purposes
    except OSError as e:
        logger.error(f"OS error checking if directory is empty {dir_path}: {e}")
        return False # Assume not empty on permission error etc. to be safe

# --- End of project_analyzer.py ---