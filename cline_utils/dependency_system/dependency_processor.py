# dependency_processor.py

"""
Main entry point for the dependency tracking system.
Processes command-line arguments and delegates to appropriate handlers.
"""

import argparse
from collections import defaultdict
import json
import logging
import os
import sys
import re
import glob
from typing import Dict

# <<< *** MODIFIED IMPORTS *** >>>
from cline_utils.dependency_system.analysis.project_analyzer import analyze_project
from cline_utils.dependency_system.core.dependency_grid import compress, decompress, get_char_at, set_char_at, add_dependency_to_grid, get_dependencies_from_grid
# Renamed function import
from cline_utils.dependency_system.io.tracker_io import remove_key_from_tracker, merge_trackers, read_tracker_file, write_tracker_file, export_tracker
# Removed KEY_PATTERN import
from cline_utils.dependency_system.utils.path_utils import get_project_root, normalize_path
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import clear_all_caches, file_modified, invalidate_dependent_entries # Added invalidate
from cline_utils.dependency_system.analysis.dependency_analyzer import analyze_file
# Added for show-dependencies
from cline_utils.dependency_system.core.key_manager import generate_keys, KeyInfo, KeyGenerationError, validate_key, sort_key_strings_hierarchically


# Configure logging (moved to main block)
logger = logging.getLogger(__name__) # Get logger for this module

# --- Command Handlers ---

# Constants for markers
KEY_DEFINITIONS_START_MARKER = "---KEY_DEFINITIONS_START---"
KEY_DEFINITIONS_END_MARKER = "---KEY_DEFINITIONS_END---"

def command_handler_analyze_file(args):
    """Handle the analyze-file command."""
    import json
    try:
        if not os.path.exists(args.file_path): print(f"Error: File not found: {args.file_path}"); return 1
        results = analyze_file(args.file_path)
        if args.output:
            output_dir = os.path.dirname(args.output); os.makedirs(output_dir, exist_ok=True) if output_dir else None
            with open(args.output, 'w', encoding='utf-8') as f: json.dump(results, f, indent=2)
            print(f"Analysis results saved to {args.output}")
        else: print(json.dumps(results, indent=2))
        return 0
    except Exception as e: print(f"Error analyzing file: {str(e)}"); return 1

def command_handler_analyze_project(args):
    """Handle the analyze-project command."""
    import json
    try:
        if not args.project_root: args.project_root = "."; logger.info(f"Defaulting project root to CWD: {os.path.abspath(args.project_root)}")
        abs_project_root = normalize_path(os.path.abspath(args.project_root))
        if not os.path.isdir(abs_project_root): print(f"Error: Project directory not found: {abs_project_root}"); return 1
        original_cwd = os.getcwd()
        if abs_project_root != normalize_path(original_cwd):
             logger.info(f"Changing CWD to: {abs_project_root}"); os.chdir(abs_project_root)
             # ConfigManager.initialize(force=True) # Re-init if CWD matters for config finding

        logger.debug(f"Analyzing project: {abs_project_root}, force_analysis={args.force_analysis}, force_embeddings={args.force_embeddings}")
        results = analyze_project(force_analysis=args.force_analysis, force_embeddings=args.force_embeddings)
        logger.debug(f"All Suggestions before Tracker Update: {results.get('dependency_suggestion', {}).get('suggestions')}")

        if args.output:
            output_path_abs = normalize_path(os.path.abspath(args.output))
            output_dir = os.path.dirname(output_path_abs); os.makedirs(output_dir, exist_ok=True) if output_dir else None
            with open(output_path_abs, 'w', encoding='utf-8') as f: json.dump(results, f, indent=2)
            print(f"Analysis results saved to {output_path_abs}")
        else: print("Analysis complete. Results not printed (use --output to save).")
        return 0
    except Exception as e:
        logger.error(f"Error analyzing project: {str(e)}", exc_info=True); print(f"Error analyzing project: {str(e)}"); return 1
    finally:
        if 'original_cwd' in locals() and normalize_path(os.getcwd()) != normalize_path(original_cwd):
             logger.info(f"Changing CWD back to: {original_cwd}"); os.chdir(original_cwd)
             # ConfigManager.initialize(force=True) # Re-init if needed

def handle_compress(args: argparse.Namespace) -> int:
    """Handle the compress command. (No changes needed)"""
    try: result = compress(args.string); print(f"Compressed string: {result}"); return 0
    except Exception as e: logger.error(f"Error compressing: {e}"); print(f"Error: {e}"); return 1

def handle_decompress(args: argparse.Namespace) -> int:
    """Handle the decompress command. (No changes needed)"""
    try: result = decompress(args.string); print(f"Decompressed string: {result}"); return 0
    except Exception as e: logger.error(f"Error decompressing: {e}"); print(f"Error: {e}"); return 1

def handle_get_char(args: argparse.Namespace) -> int:
    """Handle the get_char command. (No changes needed)"""
    try: result = get_char_at(args.string, args.index); print(f"Character at index {args.index}: {result}"); return 0
    except IndexError: logger.error("Index out of range"); print("Error: Index out of range"); return 1
    except Exception as e: logger.error(f"Error get_char: {e}"); print(f"Error: {e}"); return 1

def handle_set_char(args: argparse.Namespace) -> int:
    """Handle the set_char command."""
    try:
        tracker_data = read_tracker_file(args.tracker_file)
        if not tracker_data or not tracker_data.get("keys"): print(f"Error: Could not read tracker: {args.tracker_file}"); return 1
        if args.key not in tracker_data["keys"]: print(f"Error: Key {args.key} not found"); return 1
        sorted_keys = sort_key_strings_hierarchically(list(tracker_data["keys"].keys())) # Use hierarchical sort
        # Check index validity against sorted list length
        if not (0 <= args.index < len(sorted_keys)): print(f"Error: Index {args.index} out of range for {len(sorted_keys)} keys."); return 1
        # Check char validity (optional, could rely on set_char_at)
        # if len(args.char) != 1: print("Error: Character must be a single character."); return 1

        row_str = tracker_data["grid"].get(args.key, "")
        if not row_str: logger.warning(f"Row for key '{args.key}' missing. Initializing."); row_str = compress('p' * len(sorted_keys))

        updated_compressed_row = set_char_at(row_str, args.index, args.char)
        tracker_data["grid"][args.key] = updated_compressed_row
        tracker_data["last_grid_edit"] = f"Set {args.key}[{args.index}] to {args.char}"
        success = write_tracker_file(args.tracker_file, tracker_data["keys"], tracker_data["grid"], tracker_data.get("last_key_edit", ""), tracker_data["last_grid_edit"])
        if success: print(f"Set char at index {args.index} to '{args.char}' for key {args.key} in {args.tracker_file}"); return 0
        else: print(f"Error: Failed write to {args.tracker_file}"); return 1
    except IndexError: print(f"Error: Index {args.index} out of range."); return 1
    except ValueError as e: print(f"Error: {e}"); return 1
    except Exception as e: logger.error(f"Error set_char: {e}", exc_info=True); print(f"Error: {e}"); return 1

# <<< *** MODIFIED COMMAND HANDLER *** >>>
def handle_remove_key(args: argparse.Namespace) -> int: # Renamed handler
    """Handle the remove-key command."""
    try:
        # Call the updated tracker_io function
        remove_key_from_tracker(args.tracker_file, args.key)
        print(f"Removed key '{args.key}' from tracker '{args.tracker_file}'")
        # Invalidate cache for the modified tracker
        invalidate_dependent_entries('tracker_data', f"tracker_data:{normalize_path(args.tracker_file)}:.*")
        # Broader invalidation might be needed if other caches depend on grid structure
        invalidate_dependent_entries('grid_decompress', '.*'); invalidate_dependent_entries('grid_validation', '.*'); invalidate_dependent_entries('grid_dependencies', '.*')
        return 0
    except FileNotFoundError as e: print(f"Error: {e}"); return 1
    except ValueError as e: print(f"Error: {e}"); return 1 # e.g., key not found in tracker
    except Exception as e:
        logger.error(f"Failed to remove key: {str(e)}", exc_info=True); print(f"Error: {e}"); return 1

# <<< *** MODIFIED COMMAND HANDLER *** >>>
def handle_add_dependency(args: argparse.Namespace) -> int:
    """Handle the add-dependency command."""
    try:
        tracker_data = read_tracker_file(args.tracker)
        if not tracker_data or not tracker_data.get("keys"): print(f"Error: Could not read tracker: {args.tracker}"); return 1
        # Dependency type validation
        ALLOWED_DEP_TYPES = {'<', '>', 'x', 'd', 'o', 'n', 'p', 's', 'S'};
        if args.dep_type not in ALLOWED_DEP_TYPES: print(f"Error: Invalid dep type '{args.dep_type}'. Allowed: {', '.join(sorted(list(ALLOWED_DEP_TYPES)))}"); return 1

        keys = sort_key_strings_hierarchically(list(tracker_data["keys"].keys())) # Use hierarchical sort

        # Validate source and ALL target keys
        missing_keys = [tk for tk in args.target_key if tk not in keys]
        if args.source_key not in keys or missing_keys:
            error_msg = f"Error: Source key '{args.source_key}' not found." if args.source_key not in keys else ""
            if missing_keys:
                error_msg += f" Target key(s) not found: {', '.join(missing_keys)}"
            print(error_msg.strip())
            return 1

        grid_changed = False # Track if any change was made
        for target_key in args.target_key: # Iterate through each target key
            try:
                # Add dependency from source to current target
                new_grid = add_dependency_to_grid(tracker_data["grid"], args.source_key, target_key, keys, args.dep_type)
                if new_grid != tracker_data["grid"]: # Check if the grid actually changed
                    tracker_data["grid"] = new_grid
                    grid_changed = True

                # Add reciprocal dependency if type is '<' or '>'
                reciprocal_char = None
                if args.dep_type == '>':
                    reciprocal_char = '<'
                    new_grid = add_dependency_to_grid(tracker_data["grid"], target_key, args.source_key, keys, reciprocal_char)
                    if new_grid != tracker_data["grid"]: tracker_data["grid"] = new_grid; grid_changed = True
                elif args.dep_type == '<':
                    reciprocal_char = '>'
                    new_grid = add_dependency_to_grid(tracker_data["grid"], target_key, args.source_key, keys, reciprocal_char)
                    if new_grid != tracker_data["grid"]: tracker_data["grid"] = new_grid; grid_changed = True

            except ValueError as ve:
                # Catch errors from add_dependency_to_grid (e.g., invalid keys within the function)
                print(f"Error processing {args.source_key} -> {target_key}: {ve}")
                return 1 # Exit on first error during processing

        if not grid_changed:
            print("No changes made to the grid.")
            return 0 # Exit successfully if no changes were needed

        # Update last edit message for batch operation
        target_keys_str = ', '.join(args.target_key)
        tracker_data["last_grid_edit"] = f"Batch add dependency {args.source_key} -> [{target_keys_str}] ({args.dep_type})"

        success = write_tracker_file(args.tracker, tracker_data["keys"], tracker_data["grid"], tracker_data.get("last_key_edit", ""), tracker_data["last_grid_edit"])
        if success: print(f"Added dependencies from {args.source_key} -> {target_keys_str} ({args.dep_type}) in {args.tracker}"); return 0
        else: print(f"Error: Failed write to {args.tracker}"); return 1
    except ValueError as e: print(f"Error: {e}"); return 1 # Catch errors like key not found during initial checks
    except Exception as e: logger.error(f"Error add_dependency: {e}", exc_info=True); print(f"Error: {e}"); return 1

def handle_merge_trackers(args: argparse.Namespace) -> int:
    """Handle the merge-trackers command."""
    try:
        primary_tracker_path = normalize_path(args.primary_tracker_path); secondary_tracker_path = normalize_path(args.secondary_tracker_path)
        output_path = normalize_path(args.output) if args.output else primary_tracker_path
        merged_data = merge_trackers(primary_tracker_path, secondary_tracker_path, output_path)
        if merged_data: print(f"Merged trackers: ... into {output_path}. Total keys: {len(merged_data.get('keys', {}))}"); return 0
        else: print("Error merging trackers."); return 1 # merge_trackers logs errors
    except Exception as e: logger.exception(f"Failed merge: {e}"); print(f"Error: {e}"); return 1

def handle_clear_caches(args: argparse.Namespace) -> int:
    """Handle the clear-caches command."""
    try:
        clear_all_caches()
        print("All caches cleared.")
        return 0
    except Exception as e:
        logger.exception(f"Error clearing caches: {e}")
        print(f"Error clearing caches: {e}")
        return 1

def handle_export_tracker(args: argparse.Namespace) -> int:
    """Handle the export-tracker command."""
    try:
        output_path = args.output or os.path.splitext(args.tracker_file)[0] + '.' + args.format
        result = export_tracker(args.tracker_file, args.format, output_path)
        if "Error:" in result: print(result); return 1
        print(f"Tracker exported to {output_path}"); return 0
    except Exception as e: logger.exception(f"Error export_tracker: {e}"); print(f"Error: {e}"); return 1

def handle_update_config(args: argparse.Namespace) -> int:
    """Handle the update-config command."""
    config_manager = ConfigManager()
    try:
        # Attempt to parse value as JSON (allows lists/dicts), fall back to string
        try: value = json.loads(args.value)
        except json.JSONDecodeError: value = args.value
        success = config_manager.update_config_setting(args.key, value)
        if success: print(f"Updated config: {args.key} = {value}"); return 0
        else: print(f"Error: Failed update config (key '{args.key}' invalid?)."); return 1
    except Exception as e: logger.exception(f"Error update_config: {e}"); print(f"Error: {e}"); return 1

def handle_reset_config(args: argparse.Namespace) -> int:
    """Handle the reset-config command. (No changes needed)"""
    config_manager = ConfigManager()
    try:
        success = config_manager.reset_to_defaults()
        if success: print("Config reset to defaults."); return 0
        else: print("Error: Failed reset config."); return 1
    except Exception as e: logger.exception(f"Error reset_config: {e}"); print(f"Error: {e}"); return 1

# <<< *** MODIFIED COMMAND HANDLER *** >>>
def handle_show_dependencies(args: argparse.Namespace) -> int:
    """Handle the show-dependencies command using the contextual key system."""
    target_key_str = args.key
    logger.info(f"Showing dependencies for key string: {target_key_str}")

    # 1. Generate the global path_to_key_info map
    config = ConfigManager()
    project_root = get_project_root()
    path_to_key_info: Dict[str, KeyInfo] = {}
    try:
        logger.info("Generating global key map for context...")
        # Use settings from config for generation
        code_roots_rel = config.get_code_root_directories()
        doc_roots_rel = config.get_doc_directories()
        all_roots_rel = sorted(list(set(code_roots_rel + doc_roots_rel)))
        excluded_paths_abs = set(config.get_excluded_paths()) # get_excluded_paths returns absolute paths now
        excluded_dirs_rel = config.get_excluded_dirs()
        excluded_extensions = set(config.get_excluded_extensions())

        path_to_key_info, _ = generate_keys(
            all_roots_rel,
            excluded_dirs=excluded_dirs_rel,
            excluded_extensions=excluded_extensions,
            precomputed_excluded_paths=excluded_paths_abs
        )
        if not path_to_key_info:
             print("Error: Key generation resulted in an empty map. Cannot show dependencies.")
             return 1
        logger.info("Global key map generated.")
    except KeyGenerationError as kge:
        print(f"Error generating keys: {kge}"); logger.error(f"Key generation failed: {kge}"); return 1
    except Exception as e:
        print(f"Error during key generation: {e}"); logger.exception("Key generation failed"); return 1

    # 2. Find path(s) for the target key string
    matching_infos = [info for info in path_to_key_info.values() if info.key_string == target_key_str]

    if not matching_infos:
        print(f"Error: Key string '{target_key_str}' not found in the project.")
        return 1

    target_info: KeyInfo
    if len(matching_infos) > 1:
        print(f"Warning: Key string '{target_key_str}' is ambiguous and matches multiple paths:")
        for i, info in enumerate(matching_infos):
            print(f"  [{i+1}] {info.norm_path}")
        # Simple approach: Use the first match for now, or prompt user?
        # For CLI, let's use the first one found and mention it.
        target_info = matching_infos[0]
        print(f"Using the first match: {target_info.norm_path}")
    else:
        target_info = matching_infos[0]

    target_norm_path = target_info.norm_path
    print(f"\n--- Dependencies for Key: {target_key_str} (Path: {target_norm_path}) ---")

    # 3. Aggregate dependencies by reading trackers and using the global map
    all_dependencies_by_type = defaultdict(set) # Store sets of (key_string, path_string) tuples
    all_tracker_paths = set() # Find all trackers again (logic as before)
    memory_dir_rel = config.get_path('memory_dir')
    if not memory_dir_rel: print("Error: memory_dir not configured."); return 1
    memory_dir_abs = normalize_path(os.path.join(project_root, memory_dir_rel))
    # <<< Add detailed logging for path construction >>>
    logger.debug(f"Path Components: project_root='{project_root}', memory_dir_rel='{memory_dir_rel}', calculated memory_dir_abs='{memory_dir_abs}'")
    # Directly use the absolute path returned by ConfigManager
    main_tracker_abs = config.get_path("main_tracker_filename", os.path.join(memory_dir_abs, "module_relationship_tracker.md")) # Provide default path construction if key missing
    logger.debug(f"Using main_tracker_abs from config (or default): '{main_tracker_abs}'")
    # Directly use the absolute path returned by ConfigManager
    doc_tracker_abs = config.get_path("doc_tracker_filename", os.path.join(memory_dir_abs, "doc_tracker.md")) # Provide default path construction if key missing
    logger.debug(f"Using doc_tracker_abs from config (or default): '{doc_tracker_abs}'")
    logger.debug(f"Checking existence of main tracker: '{main_tracker_abs}' -> {os.path.exists(main_tracker_abs)}")
    if os.path.exists(main_tracker_abs): all_tracker_paths.add(main_tracker_abs)
    logger.debug(f"Checking existence of doc tracker: '{doc_tracker_abs}' -> {os.path.exists(doc_tracker_abs)}")
    if os.path.exists(doc_tracker_abs): all_tracker_paths.add(doc_tracker_abs)
    code_roots_rel = config.get_code_root_directories()
    for code_root_rel in code_roots_rel:
        code_root_abs = normalize_path(os.path.join(project_root, code_root_rel))
        mini_tracker_pattern = os.path.join(code_root_abs, '**', '*_module.md')
        found_mini_trackers = glob.glob(mini_tracker_pattern, recursive=True)
        for mt_path in found_mini_trackers: all_tracker_paths.add(normalize_path(mt_path))

    if not all_tracker_paths: print("Warning: No tracker files found."); # Proceed, might have only target key info

    for tracker_path in all_tracker_paths:
        try:
            tracker_data = read_tracker_file(tracker_path)
            if not tracker_data or not tracker_data.get("keys") or not tracker_data.get("grid"): continue

            local_keys_map = tracker_data["keys"] # Key string -> Path string (local defs)
            grid = tracker_data["grid"]
            sorted_keys_local = sort_key_strings_hierarchically(list(local_keys_map.keys())) # Use hierarchical sort

            if target_key_str in local_keys_map:
                logger.debug(f"Analyzing dependencies for '{target_key_str}' in {os.path.basename(tracker_path)}...")
                # Use the standard grid function, passing locally sorted keys
                deps_from_this_grid = get_dependencies_from_grid(grid, target_key_str, sorted_keys_local)

                # Merge results, looking up paths in the GLOBAL map
                for dep_type, key_list in deps_from_this_grid.items():
                    for dep_key_str in key_list:
                         # Find the KeyInfo for this dependency key string globally
                         dep_info = next((info for info in path_to_key_info.values() if info.key_string == dep_key_str), None)
                         dep_path_str = dep_info.norm_path if dep_info else "PATH_NOT_FOUND_GLOBALLY"
                         all_dependencies_by_type[dep_type].add((dep_key_str, dep_path_str))

        except Exception as e:
            logger.error(f"Failed to read or process tracker {tracker_path} during dependency aggregation: {e}", exc_info=True)
            print(f"Warning: Error processing {tracker_path}. See debug.txt for details.")

    # --- Print results ---
    output_sections = [
        ("Mutual ('x')", 'x'), ("Documentation ('d')", 'd'), ("Semantic (Strong) ('S')", 'S'),
        ("Semantic (Weak) ('s')", 's'), ("Depends On ('<')", '<'), ("Depended On By ('>')", '>'),
        ("Placeholders ('p')", 'p')
    ]
    for section_title, dep_char in output_sections:
        print(f"\n{section_title}:")
        dep_set = all_dependencies_by_type.get(dep_char)
        if dep_set:
            # Define helper for hierarchical sorting within the print loop
            def _hierarchical_sort_key_func(key_str: str):
                import re # Import re locally if not globally available
                KEY_PATTERN = r'\d+|\D+' # Pattern from key_manager
                if not key_str or not isinstance(key_str, str): return []
                parts = re.findall(KEY_PATTERN, key_str)
                try:
                    return [(int(p) if p.isdigit() else p) for p in parts]
                except (ValueError, TypeError): # Fallback
                    logger.warning(f"Could not convert parts for sorting display key '{key_str}'")
                    return parts

            # Sort by key string using hierarchical sort helper
            sorted_deps = sorted(list(dep_set), key=lambda item: _hierarchical_sort_key_func(item[0]))
            for dep_key, dep_path in sorted_deps: print(f"  - {dep_key}: {dep_path}")
        else: print("  None")
    print("\n------------------------------------------")
    return 0

def handle_show_keys(args: argparse.Namespace) -> int:
    """Handle the show-keys command."""
    tracker_path = normalize_path(args.tracker)
    logger.info(f"Attempting to show keys from tracker: {tracker_path}")

    if not os.path.exists(tracker_path):
        print(f"Error: Tracker file not found: {tracker_path}", file=sys.stderr)
        logger.error(f"Tracker file not found: {tracker_path}")
        return 1

    in_definitions_section = False
    start_marker_found = False
    end_marker_found = False

    try:
        with open(tracker_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if stripped_line == KEY_DEFINITIONS_START_MARKER:
                    in_definitions_section = True
                    start_marker_found = True
                    continue # Don't print the marker itself
                elif stripped_line == KEY_DEFINITIONS_END_MARKER:
                    in_definitions_section = False
                    end_marker_found = True
                    break # Stop processing after end marker

                if in_definitions_section:
                    print(line, end='') # Print the line including original newline

        if not start_marker_found:
            print(f"Warning: Start marker '{KEY_DEFINITIONS_START_MARKER}' not found in {tracker_path}", file=sys.stderr)
            logger.warning(f"Start marker not found in {tracker_path}")
        # Only warn about missing end marker if start marker was found
        elif not end_marker_found:
            print(f"Warning: End marker '{KEY_DEFINITIONS_END_MARKER}' not found after start marker in {tracker_path}. Output may be incomplete.", file=sys.stderr)
            logger.warning(f"End marker not found after start marker in {tracker_path}")

        # Success is 0 even if markers missing (warnings printed)
        return 0

    except IOError as e:
        print(f"Error reading tracker file {tracker_path}: {e}", file=sys.stderr)
        logger.error(f"IOError reading {tracker_path}: {e}", exc_info=True)
        return 1
    except Exception as e:
        print(f"An unexpected error occurred while processing {tracker_path}: {e}", file=sys.stderr)
        logger.error(f"Unexpected error processing {tracker_path}: {e}", exc_info=True)
        return 1


def main():
    """Parse arguments and dispatch to handlers."""
    parser = argparse.ArgumentParser(description="Dependency tracking system CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # --- Analysis Commands ---
    analyze_file_parser = subparsers.add_parser("analyze-file", help="Analyze a single file")
    analyze_file_parser.add_argument("file_path", help="Path to the file")
    analyze_file_parser.add_argument("--output", help="Save results to JSON file")
    analyze_file_parser.set_defaults(func=command_handler_analyze_file)

    analyze_project_parser = subparsers.add_parser("analyze-project", help="Analyze project, generate keys/embeddings, update trackers")
    analyze_project_parser.add_argument("project_root", nargs='?', default='.', help="Project directory path (default: CWD)")
    analyze_project_parser.add_argument("--output", help="Save analysis summary to JSON file")
    analyze_project_parser.add_argument("--force-embeddings", action="store_true", help="Force regeneration of embeddings")
    analyze_project_parser.add_argument("--force-analysis", action="store_true", help="Force re-analysis and bypass cache")
    analyze_project_parser.set_defaults(func=command_handler_analyze_project)

    # --- Grid Manipulation Commands ---
    compress_parser = subparsers.add_parser("compress", help="Compress RLE string")
    compress_parser.add_argument("string", help="String to compress")
    compress_parser.set_defaults(func=handle_compress)

    decompress_parser = subparsers.add_parser("decompress", help="Decompress RLE string")
    decompress_parser.add_argument("string", help="String to decompress")
    decompress_parser.set_defaults(func=handle_decompress)

    get_char_parser = subparsers.add_parser("get_char", help="Get char at logical index in compressed string")
    get_char_parser.add_argument("string", help="Compressed string")
    get_char_parser.add_argument("index", type=int, help="Logical index")
    get_char_parser.set_defaults(func=handle_get_char)

    set_char_parser = subparsers.add_parser("set_char", help="Set char at logical index in a tracker file")
    set_char_parser.add_argument("tracker_file", help="Path to tracker file")
    set_char_parser.add_argument("key", type=str, help="Row key")
    set_char_parser.add_argument("index", type=int, help="Logical index")
    set_char_parser.add_argument("char", type=str, help="New character")
    set_char_parser.set_defaults(func=handle_set_char)

    add_dep_parser = subparsers.add_parser("add-dependency", help="Add dependency between keys")
    add_dep_parser.add_argument("--tracker", required=True, help="Path to tracker file")
    add_dep_parser.add_argument("--source-key", required=True, help="Source key")
    add_dep_parser.add_argument("--target-key", required=True, nargs='+', help="One or more target keys (space-separated)")
    add_dep_parser.add_argument("--dep-type", default=">", help="Dependency type (e.g., '>', '<', 'x')")
    add_dep_parser.set_defaults(func=handle_add_dependency)

    # --- Tracker File Management ---
    # <<< *** MODIFIED COMMAND *** >>>
    remove_key_parser = subparsers.add_parser("remove-key", help="Remove a key and its row/column from a specific tracker") # Renamed
    remove_key_parser.add_argument("tracker_file", help="Path to the tracker file (.md)")
    remove_key_parser.add_argument("key", type=str, help="The key string to remove from this tracker") # Changed from file path
    remove_key_parser.set_defaults(func=handle_remove_key) # Use renamed handler

    merge_parser = subparsers.add_parser("merge-trackers", help="Merge two tracker files")
    merge_parser.add_argument("primary_tracker_path", help="Primary tracker")
    merge_parser.add_argument("secondary_tracker_path", help="Secondary tracker")
    merge_parser.add_argument("--output", "-o", help="Output path (defaults to primary)")
    merge_parser.set_defaults(func=handle_merge_trackers)

    export_parser = subparsers.add_parser("export-tracker", help="Export tracker data")
    export_parser.add_argument("tracker_file", help="Path to tracker file")
    export_parser.add_argument("--format", choices=["json", "csv", "dot"], default="json", help="Export format")
    export_parser.add_argument("--output", "-o", help="Output file path")
    export_parser.set_defaults(func=handle_export_tracker)

    # --- Utility Commands ---
    clear_caches_parser = subparsers.add_parser("clear-caches", help="Clear all internal caches")
    clear_caches_parser.set_defaults(func=handle_clear_caches)

    reset_config_parser = subparsers.add_parser("reset-config", help="Reset config to defaults")
    reset_config_parser.set_defaults(func=handle_reset_config)

    update_config_parser = subparsers.add_parser("update-config", help="Update a config setting")
    update_config_parser.add_argument("key", help="Config key path (e.g., 'paths.doc_dir')")
    update_config_parser.add_argument("value", help="New value (JSON parse attempted)")
    update_config_parser.set_defaults(func=handle_update_config)

    show_deps_parser = subparsers.add_parser("show-dependencies", help="Show aggregated dependencies for a key")
    show_deps_parser.add_argument("--key", required=True, help="Key string to show dependencies for")
    show_deps_parser.set_defaults(func=handle_show_dependencies)

    # --- Show Keys Command ---
    show_keys_parser = subparsers.add_parser("show-keys", help="Show only the key definitions from a tracker file")
    show_keys_parser.add_argument("--tracker", required=True, help="Path to the tracker file (.md)")
    show_keys_parser.set_defaults(func=handle_show_keys)

    args = parser.parse_args()

    # --- Setup Logging ---
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger(); root_logger.setLevel(logging.DEBUG)
    log_file_path = 'debug.txt'; suggestions_log_path = 'suggestions.log'
    try: # File Handler
        file_handler = logging.FileHandler(log_file_path, mode='w'); file_handler.setLevel(logging.DEBUG); file_handler.setFormatter(log_formatter); root_logger.addHandler(file_handler)
    except Exception as e: print(f"Error setting up file logger {log_file_path}: {e}", file=sys.stderr)
    try: # Suggestions Handler
        suggestion_handler = logging.FileHandler(suggestions_log_path, mode='w'); suggestion_handler.setLevel(logging.DEBUG); suggestion_handler.setFormatter(log_formatter)
        class SuggestionLogFilter(logging.Filter):
            def filter(self, record): return record.name.startswith('cline_utils.dependency_system.analysis') # Broaden slightly
        suggestion_handler.addFilter(SuggestionLogFilter()); root_logger.addHandler(suggestion_handler)
    except Exception as e: print(f"Error setting up suggestions logger {suggestions_log_path}: {e}", file=sys.stderr)
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout); console_handler.setLevel(logging.INFO); console_handler.setFormatter(log_formatter); root_logger.addHandler(console_handler)

    # Execute command
    if hasattr(args, 'func'):
        exit_code = args.func(args)
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main() # Call main function if script is executed