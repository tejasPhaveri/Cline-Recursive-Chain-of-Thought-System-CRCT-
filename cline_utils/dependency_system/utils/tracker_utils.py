# utils/tracker_utils.py

import os
import glob
import logging
import re
from typing import Any, Dict, Set, Tuple, List, Optional
from collections import defaultdict

from .cache_manager import cached
from .config_manager import ConfigManager
from .path_utils import normalize_path, get_project_root
from cline_utils.dependency_system.core.key_manager import KeyInfo, sort_key_strings_hierarchically, validate_key
from cline_utils.dependency_system.core.dependency_grid import PLACEHOLDER_CHAR, decompress, DIAGONAL_CHAR, EMPTY_CHAR

logger = logging.getLogger(__name__)

PathMigrationInfo = Dict[str, Tuple[Optional[str], Optional[str]]] 

# --- GLOBAL INSTANCE RESOLUTION HELPERS (Centralized Here) ---
def resolve_key_global_instance_to_ki( 
    key_hash_instance_str: str, 
    current_global_path_to_key_info: Dict[str, KeyInfo] 
) -> Optional[KeyInfo]:
    """
    Resolves a KEY#global_instance string to a specific KeyInfo object
    from the provided current_global_path_to_key_info.
    """
    parts = key_hash_instance_str.split('#')
    base_key = parts[0]
    instance_num = 1 
    if len(parts) > 1:
        try: 
            instance_num = int(parts[1])
            if instance_num <= 0: 
                logger.warning(f"TrackerUtils.ResolveKI: Invalid instance num {instance_num} in '{key_hash_instance_str}'.")
                return None
        except ValueError: 
            logger.warning(f"TrackerUtils.ResolveKI: Invalid instance format in '{key_hash_instance_str}'.")
            return None
    
    matches = [ki for ki in current_global_path_to_key_info.values() if ki.key_string == base_key]
    if not matches:
        logger.warning(f"TrackerUtils.ResolveKI: Base key '{base_key}' (from '{key_hash_instance_str}') has no KeyInfo entries in global map.")
        return None
    
    matches.sort(key=lambda k_sort: k_sort.norm_path) 
            
    if 0 < instance_num <= len(matches):
        return matches[instance_num - 1]
    
    logger.warning(f"TrackerUtils.ResolveKI: Global instance {key_hash_instance_str} out of bounds (max {len(matches)} for key '{base_key}').")
    return None

# (This was moved from project_analyzer.py and made more generic)
# It's placed here because tracker_io will also need it.

# Module-level cache for get_key_global_instance_string to persist across calls within a run
_module_level_base_key_to_sorted_KIs_cache: Dict[str, List[KeyInfo]] = defaultdict(list)

def clear_global_instance_resolution_cache(): # Helper to clear if needed, e.g. for testing or between runs
    """Clears the module-level cache for GI string resolution."""
    _module_level_base_key_to_sorted_KIs_cache.clear()
    logger.debug("TrackerUtils: Cleared module-level GI resolution cache.")

def get_key_global_instance_string(
    ki_obj_to_format: KeyInfo, 
    current_global_path_to_key_info: Dict[str, KeyInfo],
    # Optional cache can be passed for specific contexts, otherwise uses module-level
    base_key_to_sorted_KIs_cache: Optional[Dict[str, List[KeyInfo]]] = None 
) -> Optional[str]:
    """
    Determines the KEY#global_instance string for a given KeyInfo object
    based on its order within all KeyInfos sharing the same base key string
    in the provided current_global_path_to_key_info.
    Uses a provided cache or a module-level cache.
    """
    if not ki_obj_to_format:
        logger.warning("TrackerUtils.GetGlobalInstanceString: Received None for ki_obj_to_format.")
        return None

    # Use the provided cache if available, otherwise the module-level one
    cache_to_use = base_key_to_sorted_KIs_cache if base_key_to_sorted_KIs_cache is not None \
                   else _module_level_base_key_to_sorted_KIs_cache

    base_key = ki_obj_to_format.key_string
    if base_key not in cache_to_use: # Populate cache if miss
        matches = [ki for ki in current_global_path_to_key_info.values() if ki.key_string == base_key]
        if not matches: 
            logger.error(f"TrackerUtils.GetGlobalInstanceString: Base key '{base_key}' for KI '{ki_obj_to_format.norm_path}' not found in global map. Cannot generate GI string.")
            return None # Cannot proceed if base_key has no matches
        matches.sort(key=lambda k_sort: k_sort.norm_path)
        cache_to_use[base_key] = matches
    
    sorted_matches = cache_to_use.get(base_key) # Use .get() for safety, though it should be populated
    if not sorted_matches: 
        # This case should ideally not be hit if the above logic is correct
        logger.error(f"TrackerUtils.GetGlobalInstanceString: Base key '{base_key}' for KI '{ki_obj_to_format.norm_path}' not found in cache after attempting population.")
        return None
        
    try:
        # Find the index of the specific KeyInfo object by its unique normalized path
        instance_num = -1
        for i, match_ki in enumerate(sorted_matches):
            if match_ki.norm_path == ki_obj_to_format.norm_path:
                instance_num = i + 1
                break
        
        if instance_num == -1: # Should not happen if ki_obj_to_format is valid and from current_global_path_to_key_info
            logger.error(f"TrackerUtils.GetGlobalInstanceString: Could not find KI {ki_obj_to_format.norm_path} (Key: {base_key}) in its own sorted list of global matches. List: {[m.norm_path for m in sorted_matches]}")
            return None
        return f"{base_key}#{instance_num}"
    except Exception as e: # Catch any unexpected errors during list processing
        logger.error(f"TrackerUtils.GetGlobalInstanceString: Unexpected error finding instance for KI {ki_obj_to_format.norm_path} (Key: {base_key}) in its own sorted list of global matches. Matches found: {[m.norm_path for m in matches]}", exc_info=True)
        return None

def get_globally_resolved_key_info_for_cli( 
    base_key_str: str, 
    user_instance_num: Optional[int], 
    global_map: Dict[str, KeyInfo], 
    key_role: str 
) -> Optional[KeyInfo]:
    matching_global_infos = [info for info in global_map.values() if info.key_string == base_key_str]
    if not matching_global_infos:
        print(f"Error: Base {key_role} key '{base_key_str}' not found in global key map.")
        return None
    matching_global_infos.sort(key=lambda ki: ki.norm_path) 
    if user_instance_num is not None: 
        if 0 < user_instance_num <= len(matching_global_infos):
            return matching_global_infos[user_instance_num - 1]
        else:
            print(f"Error: {key_role.capitalize()} key '{base_key_str}#{user_instance_num}' specifies an invalid global instance number. Max is {len(matching_global_infos)}.")
    if len(matching_global_infos) > 1:
        print(f"Error: {key_role.capitalize()} key '{base_key_str}' is globally ambiguous. Please specify which instance you mean using '#<num>':")
        for i, ki in enumerate(matching_global_infos):
            print(f"  [{i+1}] {ki.key_string} (Path: {ki.norm_path})  (Use as '{base_key_str}#{i+1}')")
        return None
    return matching_global_infos[0]
# --- END OF GLOBAL INSTANCE RESOLUTION HELPERS ---

# --- PARSING HELPERS (Updated for KEY#GI) ---
KEY_GI_PATTERN_PART = r"[a-zA-Z0-9]+(?:#[0-9]+)?" # Capture KEY or KEY#num

def read_key_definitions_from_lines(lines: List[str]) -> List[Tuple[str, str]]:
    """Reads key definitions from lines. Returns a list of (key_string, path_string) tuples."""
    key_path_pairs: List[Tuple[str, str]] = []
    in_section = False
    key_def_start_pattern = re.compile(r'^---KEY_DEFINITIONS_START---$', re.IGNORECASE)
    key_def_end_pattern = re.compile(r'^---KEY_DEFINITIONS_END---$', re.IGNORECASE)
    # Regex now includes optional #instance part
    definition_pattern = re.compile(fr"^({KEY_GI_PATTERN_PART})\s*:\s*(.*)$")

    for line in lines:
        if key_def_end_pattern.match(line.strip()): break
        if in_section:
            line_content = line.strip()
            if not line_content or line_content.lower().startswith("key definitions:"): continue
            match = definition_pattern.match(line_content) # Use updated pattern
            if match:
                k_gi, v_path = match.groups() # k_gi is now the full KEY#GI or KEY
                # validate_key already handles KEY#GI format
                if validate_key(k_gi): 
                    key_path_pairs.append((k_gi, normalize_path(v_path.strip())))
                else: # Should be caught by regex, but as fallback
                    logger.warning(f"TrackerUtils.ReadDefinitions: Skipping invalid key format '{k_gi}'.") 
            # else: logger.debug(f"ReadDefs: Line did not match key def pattern: '{line_content}'")
        elif key_def_start_pattern.match(line.strip()): in_section = True
    return key_path_pairs

def read_grid_from_lines(lines: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Reads grid from lines. Returns: (grid_column_header_key_strings, list_of_grid_rows)
    where list_of_grid_rows is List[(row_key_string_label, compressed_row_data_string)]
    """
    grid_column_header_keys_gi: List[str] = [] # Will store KEY or KEY#GI
    grid_rows_data_gi: List[Tuple[str, str]] = [] # (KEY or KEY#GI, compressed_data) 
    in_section = False
    grid_start_pattern = re.compile(r'^---GRID_START---$', re.IGNORECASE)
    grid_end_pattern = re.compile(r'^---GRID_END---$', re.IGNORECASE)
    # Regex for row labels now includes optional #instance part
    row_label_pattern = re.compile(fr"^({KEY_GI_PATTERN_PART})\s*=\s*(.*)$")

    for line in lines:
        if grid_end_pattern.match(line.strip()): break
        if in_section:
            line_content = line.strip()
            if line_content.upper().startswith("X "):
                # Split header, keys can now be KEY or KEY#GI
                potential_keys = line_content.split()[1:]
                grid_column_header_keys_gi = [k for k in potential_keys if validate_key(k)]
                if len(grid_column_header_keys_gi) != len(potential_keys):
                    logger.warning(f"TrackerUtils.ReadGrid: Some X-header keys are invalid and were skipped.")
                continue
            if not line_content or line_content == "X": continue
            
            match = row_label_pattern.match(line_content) # Use updated pattern
            if match:
                k_label_gi, v_data = match.groups() # k_label_gi is KEY or KEY#GI
                if validate_key(k_label_gi):
                    grid_rows_data_gi.append((k_label_gi, v_data.strip()))
                else: # Should be caught by regex
                    logger.warning(f"TrackerUtils.ReadGrid: Skipping row with invalid key label format '{k_label_gi}'.")
            # else: logger.debug(f"ReadGrid: Line did not match row data pattern: '{line_content}'")
        elif grid_start_pattern.match(line.strip()): in_section = True
    
    # Consistency check in read_tracker_file_structured will compare with definitions count
    return grid_column_header_keys_gi, grid_rows_data_gi
# --- END OF PARSING HELPERS ---

@cached("tracker_data_structured",
        key_func=lambda tracker_path:
        f"tracker_data_structured:{normalize_path(tracker_path)}:{(os.path.getmtime(tracker_path) if os.path.exists(tracker_path) else 0)}")
def read_tracker_file_structured(tracker_path: str) -> Dict[str, Any]:
    """
    Read a tracker file and parse its contents into list-based structures
    compatible with the new format (handles duplicate key strings).
    Args:
        tracker_path: Path to the tracker file
    Returns:
        Dictionary with "definitions_ordered": List[Tuple[str,str]], 
                         "grid_headers_ordered": List[str],
                         "grid_rows_ordered": List[Tuple[str,str]], (row_label, compressed_data)
                         "last_key_edit": str, "last_grid_edit": str
        or empty structure on failure.
    """
    tracker_path = normalize_path(tracker_path)
    # Initialize with empty lists for the new structure
    empty_result = {
        "definitions_ordered": [], 
        "grid_headers_ordered": [], 
        "grid_rows_ordered": [], 
        "last_key_edit": "", 
        "last_grid_edit": ""
    }
    if not os.path.exists(tracker_path):
        logger.debug(f"Tracker file not found: {tracker_path}. Returning empty structured data.")
        return empty_result
    try:
        with open(tracker_path, 'r', encoding='utf-8') as f: lines = f.readlines()
        # Use the helpers now defined in this file
        definitions = read_key_definitions_from_lines(lines) 
        grid_headers, grid_rows = read_grid_from_lines(lines)
        content_str = "".join(lines)
        last_key_edit_match = re.search(r'^last_KEY_edit\s*:\s*(.*)$', content_str, re.MULTILINE | re.IGNORECASE)
        last_key_edit = last_key_edit_match.group(1).strip() if last_key_edit_match else ""
        last_grid_edit_match = re.search(r'^last_GRID_edit\s*:\s*(.*)$', content_str, re.MULTILINE | re.IGNORECASE)
        last_grid_edit = last_grid_edit_match.group(1).strip() if last_grid_edit_match else ""
        
        # Basic consistency check based on what was read from file directly
        if definitions and grid_headers and grid_rows and not (len(definitions) == len(grid_headers) == len(grid_rows)):
            logger.warning(f"ReadStructured: Inconsistent counts in '{os.path.basename(tracker_path)}'. Defs: {len(definitions)}, Headers: {len(grid_headers)}, Rows: {len(grid_rows)}. Data might be misaligned.")
        elif definitions and grid_rows and not grid_headers and len(definitions) == len(grid_rows):
            logger.debug(f"ReadStructured: Grid headers missing but defs and rows match for '{os.path.basename(tracker_path)}'. Imputing headers from defs.")
            grid_headers = [d[0] for d in definitions]
        
        logger.debug(f"Read structured tracker '{os.path.basename(tracker_path)}': "
                     f"{len(definitions)} defs, {len(grid_headers)} grid headers, {len(grid_rows)} grid rows.")
        
        return {
            "definitions_ordered": definitions,
            "grid_headers_ordered": grid_headers,
            "grid_rows_ordered": grid_rows,
            "last_key_edit": last_key_edit,
            "last_grid_edit": last_grid_edit
        }
    except Exception as e:
        logger.exception(f"Error reading structured tracker file {tracker_path}: {e}")
        return empty_result

def find_all_tracker_paths(config: ConfigManager, project_root: str) -> Set[str]:
    """Finds all main, doc, and mini tracker files in the project."""
    all_tracker_paths = set()
    memory_dir_rel = config.get_path('memory_dir')
    if not memory_dir_rel:
        logger.warning("memory_dir not configured. Cannot find main/doc trackers.")
        memory_dir_abs = None
    else:
        memory_dir_abs = normalize_path(os.path.join(project_root, memory_dir_rel))
        logger.debug(f"Path Components: project_root='{project_root}', memory_dir_rel='{memory_dir_rel}', calculated memory_dir_abs='{memory_dir_abs}'")

        # Main Tracker
        main_tracker_abs = config.get_path("main_tracker_filename", os.path.join(memory_dir_abs, "module_relationship_tracker.md"))
        logger.debug(f"Using main_tracker_abs from config (or default): '{main_tracker_abs}'")
        if os.path.exists(main_tracker_abs): all_tracker_paths.add(main_tracker_abs)
        else: logger.debug(f"Main tracker not found at: {main_tracker_abs}")

        # Doc Tracker
        doc_tracker_abs = config.get_path("doc_tracker_filename", os.path.join(memory_dir_abs, "doc_tracker.md"))
        logger.debug(f"Using doc_tracker_abs from config (or default): '{doc_tracker_abs}'")
        if os.path.exists(doc_tracker_abs): all_tracker_paths.add(doc_tracker_abs)
        else: logger.debug(f"Doc tracker not found at: {doc_tracker_abs}")

    # Mini Trackers
    code_roots_rel = config.get_code_root_directories()
    if not code_roots_rel:
         logger.warning("No code_root_directories configured. Cannot find mini trackers.")
    else:
        for code_root_rel in code_roots_rel:
            code_root_abs = normalize_path(os.path.join(project_root, code_root_rel))
            mini_tracker_pattern = os.path.join(code_root_abs, '**', '*_module.md')
            try:
                found_mini_trackers = glob.glob(mini_tracker_pattern, recursive=True)
                normalized_mini_paths = {normalize_path(mt_path) for mt_path in found_mini_trackers}
                all_tracker_paths.update(normalized_mini_paths)
                logger.debug(f"Found {len(normalized_mini_paths)} mini trackers under '{code_root_rel}'.")
            except Exception as e:
                 logger.error(f"Error during glob search for mini trackers under '{code_root_abs}': {e}")
    logger.info(f"Found {len(all_tracker_paths)} total tracker files.")
    return all_tracker_paths

# --- MODIFIED AGGREGATION FUNCTION (Uses KEY#global_instance) ---
@cached("aggregation_v2_gi",
        key_func=lambda paths, pmi, cgptki: f"agg_v2_gi:{':'.join(sorted(list(paths)))}:{hash(tuple(sorted(pmi.items())))}:{hash(tuple(sorted(cgptki.items())))}", 
        ttl=300)
def aggregate_all_dependencies(
    tracker_paths: Set[str],
    path_migration_info: PathMigrationInfo,
    current_global_path_to_key_info: Dict[str, KeyInfo] # NEW PARAMETER
) -> Dict[Tuple[str, str], Tuple[str, Set[str]]]: # Output keys are Tuple[src_KEY#GI, tgt_KEY#GI]
    """
    Aggregates dependencies from tracker files, resolving paths to current global KeyInfo objects
    and then to their KEY#global_instance strings for instance-specific aggregation.
    """
    aggregated_links: Dict[Tuple[str, str], Tuple[str, Set[str]]] = {} # Key: (src_KEY#GI, tgt_KEY#GI)
    config = ConfigManager() 
    get_priority_from_char = config.get_char_priority

    logger.info(f"Aggregating dependencies (outputting KEY#global_instance) from {len(tracker_paths)} trackers...")

    for tracker_file_path in tracker_paths:
        logger.debug(f"Aggregation: Processing tracker {os.path.basename(tracker_file_path)}")
        tracker_data = read_tracker_file_structured(tracker_file_path) 
        
        definitions_ordered_from_file = tracker_data["definitions_ordered"] # List[Tuple[key_str_in_file, path_str_in_file]]
        grid_headers_from_file = tracker_data["grid_headers_ordered"]       # List[key_str_in_file]
        grid_rows_from_file = tracker_data["grid_rows_ordered"]             # List[Tuple[row_label_str_in_file, compressed_data_str]]

        if not definitions_ordered_from_file or not grid_rows_from_file:
            logger.debug(f"Aggregation: Skipping empty/incomplete data in: {os.path.basename(tracker_file_path)}")
            continue
        
        # Build an ordered list of current global KeyInfo objects corresponding to the tracker's definitions
        # This list defines the structure of the grid being processed for *this* tracker.
        effective_ki_list_for_this_tracker: List[Optional[KeyInfo]] = []
        for _key_in_file, path_in_file in definitions_ordered_from_file:
            mig_info = path_migration_info.get(path_in_file)
            resolved_ki_for_this_def_entry: Optional[KeyInfo] = None
            if mig_info and mig_info[1]: # Path is stable and has a current global base key
                new_global_base_key = mig_info[1]
                # Find the KeyInfo object in current_global_path_to_key_info. Prefer exact path match if key string is same.
                resolved_ki_for_this_def_entry = next((ki for ki in current_global_path_to_key_info.values() if ki.key_string == new_global_base_key and ki.norm_path == path_in_file), None) \
                                               or next((ki for ki in current_global_path_to_key_info.values() if ki.key_string == new_global_base_key), None) # Fallback to any path for this key
            effective_ki_list_for_this_tracker.append(resolved_ki_for_this_def_entry)

        # Validate consistency after global resolution
        if not (len(effective_ki_list_for_this_tracker) == len(grid_headers_from_file) and \
                len(effective_ki_list_for_this_tracker) == len(grid_rows_from_file)):
            logger.warning(f"Aggregation: Tracker '{os.path.basename(tracker_file_path)}' has inconsistent structure after global validation. "
                           f"Effective KIs: {len(effective_ki_list_for_this_tracker)}, File Headers: {len(grid_headers_from_file)}, File Rows: {len(grid_rows_from_file)}. "
                           "Skipping this tracker.")
            continue
        
        for row_idx, (_row_label_in_file, compressed_row_str) in enumerate(grid_rows_from_file):
            source_ki_global = effective_ki_list_for_this_tracker[row_idx]
            if not source_ki_global: # Path for this row wasn't globally stable/valid or KI not found
                continue 
            
            # Use the helper now in this file
            source_key_gi_str = get_key_global_instance_string(source_ki_global, current_global_path_to_key_info)
            if not source_key_gi_str:
                logger.warning(f"Aggregation: Could not get global instance for source path {source_ki_global.norm_path} from {os.path.basename(tracker_file_path)}. Skipping row.")
                continue

            try:
                decompressed_row_chars = decompress(compressed_row_str)
                if len(decompressed_row_chars) != len(effective_ki_list_for_this_tracker):
                     logger.warning(f"Aggregation: Row {row_idx} (source KI: {source_key_gi_str}) in {os.path.basename(tracker_file_path)} "
                                    f"has decompressed length {len(decompressed_row_chars)}, expected {len(effective_ki_list_for_this_tracker)}. Skipping row.")
                     continue

                for col_idx, dep_char_val in enumerate(decompressed_row_chars):
                    if dep_char_val in (DIAGONAL_CHAR, EMPTY_CHAR, PLACEHOLDER_CHAR): continue
                    
                    target_ki_global = effective_ki_list_for_this_tracker[col_idx]
                    if not target_ki_global: # Path for this col wasn't globally stable/valid
                        continue
                    
                    # Critical check: ensure we are not creating self-loops for the *same actual item*
                    if source_ki_global.norm_path == target_ki_global.norm_path: 
                        # This should ideally be caught by DIAGONAL_CHAR, but direct path check is safer
                        # if keys might be duplicated for the same path (which shouldn't happen for global KIs).
                        continue

                    target_key_gi_str = get_key_global_instance_string(target_ki_global, current_global_path_to_key_info)
                    if not target_key_gi_str:
                        logger.warning(f"Aggregation: Could not get global instance for target path {target_ki_global.norm_path} from {os.path.basename(tracker_file_path)}. Skipping cell.")
                        continue
                    
                    current_link_gi = (source_key_gi_str, target_key_gi_str) # Now a KEY#GI to KEY#GI link
                    existing_char, existing_origins = aggregated_links.get(current_link_gi, (None, set()))

                    try:
                        current_priority = get_priority_from_char(dep_char_val)
                        existing_priority = get_priority_from_char(existing_char) if existing_char else -1
                    except KeyError: 
                        logger.warning(f"Aggregation: Invalid dep char '{dep_char_val}' in {os.path.basename(tracker_file_path)}. Skipping cell for link {source_key_gi_str} -> {target_key_gi_str}."); 
                        continue

                    if current_priority > existing_priority:
                        aggregated_links[current_link_gi] = (dep_char_val, {tracker_file_path})
                    elif current_priority == existing_priority:
                        if dep_char_val == existing_char: 
                            existing_origins.add(tracker_file_path) # No need to reassign tuple if set is mutable
                        elif existing_char == 'n': 
                            pass # Keep 'n' if new char has same priority but isn't 'n'
                        elif dep_char_val == 'n': # New char is 'n' and has same priority as existing non-'n'
                            aggregated_links[current_link_gi] = (dep_char_val, {tracker_file_path}) # 'n' overwrites
                        else: # Different chars, same priority, neither is 'n' - current tracker file "wins"
                            aggregated_links[current_link_gi] = (dep_char_val, {tracker_file_path})
                            logger.debug(f"Aggregation conflict (same priority): {current_link_gi} was '{existing_char}', overwritten by '{dep_char_val}' from {os.path.basename(tracker_file_path)}.")
            except Exception as e_agg_row:
                logger.warning(f"Aggregation: Error processing row {row_idx} for source KI {source_key_gi_str} in {os.path.basename(tracker_file_path)}: {e_agg_row}", exc_info=False) # Less verbose exc_info

    logger.info(f"Aggregation complete. Found {len(aggregated_links)} unique KEY#global_instance directed links.")
    return aggregated_links

# --- End of tracker_utils.py ---