"""
IO module for tracker file operations.
Handles reading, writing, merging and exporting tracker files.
"""

import datetime
import io
import json
import os
import re
import shutil
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import defaultdict

# Import only from utils and core layers
from cline_utils.dependency_system.core.key_manager import get_key_from_path, sort_keys
from cline_utils.dependency_system.utils.path_utils import normalize_path
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, check_file_modified, invalidate_dependent_entries, tracker_modified
from cline_utils.dependency_system.core.dependency_grid import compress, create_initial_grid, decompress, validate_grid

import logging
logger = logging.getLogger(__name__)

def get_tracker_path(project_dir: str, tracker_type: str = "main", module_path: Optional[str] = None) -> str:
    """
    Get the path to the appropriate tracker file based on type.

    Args:
        project_dir: Project directory
        tracker_type: Type of tracker ('main', 'doc', or 'mini')
        module_path: The module path (required for mini-trackers)
    Returns:
        Path to the tracker file
    """
    project_dir = normalize_path(project_dir)
    config_manager = ConfigManager()  # Instantiate ConfigManager

    if tracker_type == "main":
        # Main tracker is in the memory directory
        memory_dir = os.path.join(project_dir, config_manager.get_path("memory_dir"))
        return os.path.join(memory_dir, "dependencytracker.md")
    elif tracker_type == "doc":
        # Doc tracker is in the documentation directory
        doc_dir = os.path.join(project_dir, config_manager.get_path("doc_dir"))
        return os.path.join(doc_dir, "doctracker.md")
    elif tracker_type == "mini":
        # Mini trackers are in module directories
        if not module_path:
            raise ValueError("module_path must be provided for mini-trackers")
        return os.path.join(module_path, "mini_tracker.md")  # Mini-tracker is in the module dir
    else:
        raise ValueError(f"Unknown tracker type: {tracker_type}")


def read_tracker_file(tracker_path: str) -> Dict[str, Any]:
    """
    Read a tracker file and parse its contents.
    Args:
        tracker_path: Path to the tracker file
    Returns:
        Dictionary with keys, grid, and metadata
    """

    tracker_path = normalize_path(tracker_path)
    if not os.path.exists(tracker_path):
        logger.debug(f"Tracker file not found: {tracker_path}")
        return {"keys": {}, "grid": {}, "last_key_edit": "", "last_grid_edit": ""}

    try:
        with open(tracker_path, 'r', encoding='utf-8') as f:
            content = f.read()

        keys = {}
        grid = {}
        last_key_edit = ""
        last_grid_edit = ""

        # Parse key definitions
        key_section = re.search(r'---KEY_DEFINITIONS_START---\n(.*?)\n---KEY_DEFINITIONS_END---', content, re.DOTALL)
        if key_section:
            for line in key_section.group(1).splitlines():
                if line.startswith("Key Definitions:"):
                    continue
                if ": " in line:
                    k, v = line.strip().split(": ", 1)
                    keys[k] = normalize_path(v)

        # Parse grid
        grid_section = re.search(r'---GRID_START---\n(.*?)\n---GRID_END---', content, re.DOTALL)
        if grid_section:
            lines = grid_section.group(1).splitlines()
            if lines and lines[0].startswith("X "):
                x_axis = lines[0][2:].split()
                for line in lines[1:]:
                    if " = " in line:
                        k, v = line.strip().split(" = ", 1)
                        grid[k] = v

        # Parse metadata
        last_key_edit_match = re.search(r'last_KEY_edit:\s*(.+)', content)
        if last_key_edit_match:
            last_key_edit = last_key_edit_match.group(1)
        last_grid_edit_match = re.search(r'last_GRID_edit:\s*(.+)', content)
        if last_grid_edit_match:
            last_grid_edit = last_grid_edit_match.group(1)

        logger.debug(f"Read tracker: {len(keys)} keys, {len(grid)} grid entries")
        return {"keys": keys, "grid": grid, "last_key_edit": last_key_edit, "last_grid_edit": last_grid_edit}
    except Exception as e:
        logger.error(f"Error reading tracker file {tracker_path}: {e}")
        return {"keys": {}, "grid": {}, "last_key_edit": "", "last_grid_edit": ""}

def write_tracker_file(tracker_path: str, keys: Dict[str, str], grid: Dict[str, str], last_key_edit: str, last_grid_edit: str = "") -> bool:
    """
    Write tracker data to a file in markdown format with embedded JSON.
    Args:
        tracker_path: Path to the tracker file
        keys: Dictionary of keys to paths
        grid: Dictionary of grid rows
        last_key_edit: Last key edit identifier
        last_grid_edit: Last grid edit identifier
    Returns:
        True if successful, False otherwise
    """
    tracker_path = normalize_path(tracker_path)
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(tracker_path), exist_ok=True)

    try:
        sorted_keys = sort_keys(list(keys.keys()))
        with open(tracker_path, 'w', encoding='utf-8') as f:
            # Write key definitions
            f.write("---KEY_DEFINITIONS_START---\n")
            f.write("Key Definitions:\n")
            for key in sorted_keys:
                f.write(f"{key}: {keys[key]}\n")
            f.write("---KEY_DEFINITIONS_END---\n")

            # Write metadata
            f.write(f"last_KEY_edit: {last_key_edit}\n")
            f.write(f"last_GRID_edit: {last_grid_edit}\n")

            # Write grid
            f.write("---GRID_START---\n")
            f.write(f"X {' '.join(sorted_keys)}\n")
            for key in sorted_keys:
                grid_row = grid.get(key, "." * len(sorted_keys))
                f.write(f"{key} = {grid_row}\n")
            f.write("---GRID_END---\n")

        logger.info(f"Wrote tracker file: {tracker_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing tracker file {tracker_path}: {e}")
        return False

def update_tracker(tracker_path: str, key_map: Dict[str, str], tracker_type: str, sort_keys: bool = True, file_to_module: Dict[str, str] = None) -> bool:
    """
    Update an existing tracker with new keys and adjust the grid.

    Args:
        tracker_path: Path to the tracker file
        key_map: New key-to-path mappings
        tracker_type: Type of tracker ('main', 'doc', 'mini')
        sort_keys: Whether to sort keys in the output
        file_to_module: Mapping of file paths to module paths (for mini-trackers)
    Returns:
        True if successful, False otherwise
    """
    tracker_data = read_tracker_file(tracker_path)
    existing_keys = tracker_data["keys"]
    existing_grid = tracker_data["grid"]
    last_key_edit = tracker_data["last_key_edit"]
    last_grid_edit = tracker_data["last_grid_edit"] or datetime.datetime.now().isoformat()

    # Merge new keys
    updated_keys = {**existing_keys, **key_map}
    sorted_key_list = sort_keys(list(updated_keys.keys())) if sort_keys else list(updated_keys.keys())
    key_count = len(sorted_key_list)

    # Update grid
    updated_grid = {}
    for key in sorted_key_list:
        if key in existing_grid and len(existing_grid[key]) == len(existing_keys):
            # Extend existing row with dots for new keys
            existing_row = existing_grid[key]
            new_length = key_count - len(existing_keys)
            updated_grid[key] = existing_row + "." * new_length
        else:
            # New key, create a full row of dots
            updated_grid[key] = "." * key_count

    success = write_tracker_file(tracker_path, updated_keys, updated_grid, last_key_edit, last_grid_edit)
    if success:
        invalidate_dependent_entries('tracker', f"{tracker_path}:{tracker_type}")
    return success

def backup_tracker_file(tracker_path: str) -> str:
    """
    Create a backup of a tracker file.

    Args:
        tracker_path: Path to the tracker file
    Returns:
        Path to the backup file or empty string on failure
    """
    tracker_path = normalize_path(tracker_path)
    if not os.path.exists(tracker_path):
        logger.warning(f"Tracker file not found for backup: {tracker_path}")
        return ""

    try:
        backup_dir = os.path.join(os.path.dirname(tracker_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        # Create backup filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{os.path.basename(tracker_path)}.{timestamp}.bak"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Copy the file
        shutil.copy2(tracker_path, backup_path)
        logger.info(f"Backed up tracker to: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Error backing up tracker file {tracker_path}: {e}")
        return ""

def merge_trackers(primary_tracker_path: str, secondary_tracker_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Merge two tracker files, with the primary taking precedence.  Invalidates tracker cache after merge.
    Args:
        primary_tracker_path: Path to the primary tracker file
        secondary_tracker_path: Path to the secondary tracker file
        output_path: Optional path to write the merged tracker (if None, returns dict only)
    Returns:
        Merged tracker data as a dictionary
    """
    check_file_modified(primary_tracker_path)
    check_file_modified(secondary_tracker_path)

    primary_tracker_path = normalize_path(primary_tracker_path)
    secondary_tracker_path = normalize_path(secondary_tracker_path)
    if output_path:
        output_path = normalize_path(output_path)

    # Read both trackers
    primary_data = read_tracker_file(primary_tracker_path)
    secondary_data = read_tracker_file(secondary_tracker_path)

    if not primary_data:
        return secondary_data if not output_path else write_tracker_file(output_path, secondary_data["keys"], secondary_data["grid"], secondary_data["last_key_edit"], secondary_data["last_grid_edit"]) and secondary_data
    if not secondary_data:
        return primary_data if not output_path else write_tracker_file(output_path, primary_data["keys"], primary_data["grid"], primary_data["last_key_edit"], primary_data["last_grid_edit"]) and primary_data

    # Merge keys (union with primary precedence)
    merged_keys = {**secondary_data.get("keys", {}), **primary_data.get("keys", {})}  # Primary overrides secondary
    merged_key_list = list(merged_keys.keys())  # Ordered list for grid indexing

    # Create new grid with merged keys
    merged_grid = create_initial_grid(merged_key_list)

    # Decompress existing grids
    primary_grid = {k: decompress(v) for k, v in primary_data.get("grid", {}).items()}
    secondary_grid = {k: decompress(v) for k, v in secondary_data.get("grid", {}).items()}

    # Create key index mappings
    key_indices = {key: i for i, key in enumerate(merged_key_list)}

    # Copy primary grid data
    for row_key, row in primary_grid.items():
        if row_key in key_indices:
            row_idx = key_indices[row_key]
            for col_key, val in zip(primary_data["keys"].keys(), row):
                if col_key in key_indices:
                    col_idx = key_indices[col_key]
                    merged_grid[row_idx][col_idx] = val

    # Fill gaps from secondary grid (only if empty in merged grid)
    for row_key, row in secondary_grid.items():
        if row_key in key_indices:
            row_idx = key_indices[row_key]
            for col_key, val in zip(secondary_data["keys"].keys(), row):
                if col_key in key_indices:
                    col_idx = key_indices[col_key]
                    if merged_grid[row_idx][col_idx] == "p":  # Only overwrite default 'p'
                        merged_grid[row_idx][col_idx] = val

    # Compress the merged grid
    compressed_merged_grid = {key: compress(''.join(merged_grid[i])) for i, key in enumerate(merged_key_list)}

    # Merge metadata (primary takes precedence)
    merged_metadata = {
        "last_key_edit": primary_data.get("last_key_edit", secondary_data.get("last_key_edit", "")),
        "last_grid_edit": primary_data.get("last_grid_edit", secondary_data.get("last_grid_edit", "")),
        "merged_from": [
            os.path.basename(primary_tracker_path),
            os.path.basename(secondary_tracker_path)
        ],
        "merge_date": datetime.datetime.now().isoformat(),
        "file_count": len(merged_keys)
    }

    # Construct merged tracker
    merged_tracker = {
        "keys": merged_keys,
        "grid": compressed_merged_grid,
        "last_key_edit": merged_metadata["last_key_edit"],
        "last_grid_edit": merged_metadata["last_grid_edit"],
        "metadata": merged_metadata
    }

    # Optionally write to file
    if output_path:
        success = write_tracker_file(
            output_path,
            merged_keys,
            compressed_merged_grid,
            merged_metadata["last_key_edit"],
            merged_metadata["last_grid_edit"]
        )
        if not success:
            print(f"Warning: Failed to write merged tracker to {output_path}")

    # Invalidate the entire tracker cache after merging
    invalidate_dependent_entries('tracker', '.*')  # Invalidate all tracker entries
    return merged_tracker

def _read_existing_keys(lines: List[str]) -> Dict[str, str]:
    """Reads existing key definitions."""
    key_def_start = "---KEY_DEFINITIONS_START---"
    key_def_end = "---KEY_DEFINITIONS_END---"
    try:
        start = lines.index(key_def_start + "\n") + 2
        end = lines.index(key_def_end + "\n")
        return {
            k: v
            for line in lines[start:end]
            if ": " in line
            for k, v in [line.strip().split(": ", 1)]
        }
    except ValueError:
        return {}

def _read_existing_grid(lines: List[str]) -> Dict[str, str]:
    """Reads the existing grid data."""
    grid_start = "---GRID_START---"
    grid_end = "---GRID_END---"
    try:
        start = lines.index(grid_start + "\n") + 1
        end = lines.index(grid_end + "\n")
        return {
            match.group(1): match.group(2)
            for line in lines[start:end]
            if (match := re.match(r"(\w+) = (.*)", line))
        }
    except ValueError:
        return {}

def _write_key_definitions(file_obj: io.StringIO, key_map: Dict[str, str], sort_keys: bool = True):
    """Writes the key definitions section to the file object."""
    key_def_start = "---KEY_DEFINITIONS_START---"
    key_def_end = "---KEY_DEFINITIONS_END---"
    file_obj.write(f"{key_def_start}\nKey Definitions:\n")
    if sort_keys:
        def sort_key(key):
            parts = re.findall(r'\d+|\D+', key)
            return [int(p) if p.isdigit() else p for p in parts]
        for k, v in sorted(key_map.items(), key=lambda item: sort_key(item[0])):
            file_obj.write(f"{k}: {v}\n")
    else:
        for k, v in key_map.items():
            file_obj.write(f"{k}: {v}\n")
    file_obj.write(f"{key_def_end}\n")

def _write_grid(file_obj: io.StringIO, sorted_keys: List[str], existing_grid: Dict[str, str]):
    """Writes the grid section to the provided file object."""
    grid_start = "---GRID_START---"
    grid_end = "---GRID_END---"

    file_obj.write(f"{grid_start}\n")
    file_obj.write(f"X {' '.join(sorted_keys)}\n")

    for row_key in sorted_keys:
        row = ["o" if row_key == col_key else "p" for col_key in sorted_keys]
        initial_string = compress(''.join(row))
        file_obj.write(f"{row_key} = {existing_grid.get(row_key, initial_string)}\n")

    file_obj.write(f"{grid_end}\n")

def update_tracker(output_file: str, key_map: Dict[str, str], tracker_type: str = "mini", suggestions: Optional[Dict[str, List[Tuple[str, str]]]] = None, sort_keys: bool = True, file_to_module: Optional[Dict[str, str]] = None):
    """
    Updates or creates a tracker file. Invalidates cache on changes.

    Now with granular invalidation.  Handles mini-trackers correctly.
    """
    check_file_modified(output_file)

    def sort_key(key):
        parts = re.findall(r'\d+|\D+', key)
        return [int(p) if p.isdigit() else p for p in parts]
    # Determine the correct output file based on tracker_type
    if tracker_type == "mini":
        # For mini-trackers, we need to find the correct file based on the keys.
        # We use the file_to_module mapping for this.  We assume all keys in
        # key_map belong to the same module for a mini-tracker update.
        if not file_to_module:
            raise ValueError("file_to_module must be provided for mini-tracker updates")
        if not key_map:
            output_file = "" # Handle the case where key_map is empty.
        else:
            first_key = list(key_map.keys())[0]
            first_file = key_map[first_key]
            module_path = file_to_module.get(first_file)
            if not module_path:
                raise ValueError(f"Could not determine module path for key {first_key} and file {first_file}")
            output_file = get_tracker_path("", "mini", module_path=module_path) # Get correct mini-tracker path
            check_file_modified(output_file) # Check the correct file.

    if tracker_type == "main":
        filtered_keys = {
            k: v for k, v in key_map.items()
            if (k.startswith("1") and len(k) == 2) or
               (k[0] == '2' and len(k) > 2 and k[2].islower() and not any(char.isdigit() for char in k[2:]))
        }
    else:
        filtered_keys = key_map

    sorted_keys = sorted(filtered_keys.keys(), key=sort_key) if sort_keys else list(filtered_keys.keys())

    if not os.path.exists(output_file) and output_file != "":
        with open(output_file, "w", encoding="utf-8") as f:
            _write_key_definitions(f, filtered_keys, sort_keys=sort_keys)
            f.write(f"last_KEY_edit: {sorted_keys[-1] if sorted_keys else ''}\n")
            f.write("last_GRID_edit: \n")
            _write_grid(f, sorted_keys, {})
        # Invalidate tracker cache after initial creation
        invalidate_dependent_entries('tracker', '.*')
    elif output_file != "":
        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        existing_key_defs = _read_existing_keys(lines)
        existing_grid = _read_existing_grid(lines)
        last_key_edit_line = next((line for line in lines if line.startswith("last_KEY_edit")), None)
        last_grid_edit_line = next((line for line in lines if line.startswith("last_GRID_edit")), None)

        last_key_edit = last_key_edit_line.split(":", 1)[1].strip() if last_key_edit_line else ""
        last_grid_edit = last_grid_edit_line.split(":", 1)[1].strip() if last_grid_edit_line else ""

        # Determine added and removed keys
        added_keys = set(filtered_keys.keys()) - set(existing_key_defs.keys())
        removed_keys = set(existing_key_defs.keys()) - set(filtered_keys.keys())

        merged_key_defs = existing_key_defs.copy()
        merged_key_defs.update(filtered_keys)  # Add new keys and update existing ones
        sorted_merged_keys = sorted(merged_key_defs.keys(), key=sort_key) if sort_keys else list(merged_key_defs.keys())

        updated_content = io.StringIO()
        _write_key_definitions(updated_content, merged_key_defs, sort_keys=sort_keys)
        updated_content.write(f"last_KEY_edit: {last_key_edit}\n")
        updated_content.write(f"last_GRID_edit: {last_grid_edit}\n")
        _write_grid(updated_content, sorted_merged_keys, existing_grid)


        if suggestions:
            last_grid_edit = list(suggestions.keys())[-1] if suggestions else last_grid_edit
            updated_grid = existing_grid.copy()
            for row_key, deps in suggestions.items():
                if row_key not in sorted_merged_keys:
                    print(f"Warning: Row key '{row_key}' not in tracker; skipping.")
                    continue
                current_row_str = updated_grid.get(row_key, compress(''.join(["o" if row_key == col_key else "p" for col_key in sorted_merged_keys])))
                decompressed = decompress(current_row_str)
                for col_key, dep_char in deps:
                    if col_key not in sorted_merged_keys:
                        print(f"Warning: Column key '{col_key}' not in tracker; skipping.")
                        continue
                    index = sorted_merged_keys.index(col_key)
                    if index >= len(decompressed):
                        print(f"Error: Index {index} out of bounds for row '{row_key}'; skipping.")
                        continue
                    if decompressed[index] == 'p':
                        decompressed = decompressed[:index] + dep_char + decompressed[index + 1:]
                    else:
                        print(f"Warning: Skipping update at index {index} for row '{row_key}'; already set to '{decompressed[index]}'.")
                updated_grid[row_key] = compress(decompressed)


            updated_content.seek(0)  # Rewind to the beginning
            _write_key_definitions(updated_content, merged_key_defs, sort_keys=sort_keys)
            updated_content.write(f"last_KEY_edit: {last_key_edit}\n") # Added last_KEY_edit
            updated_content.write(f"last_GRID_edit: {last_grid_edit}\n")
            _write_grid(updated_content, sorted_merged_keys, updated_grid)

        if output_file != "":
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(updated_content.getvalue())
            updated_content.close()

        # Granular invalidation based on added/removed keys
        for key in added_keys:
            invalidate_dependent_entries('tracker', f'.*:{key}')  # Invalidate entries related to added key
        for key in removed_keys:
            invalidate_dependent_entries('tracker', f'.*:{key}')  # Invalidate entries related to removed key
        if suggestions:
            invalidate_dependent_entries('tracker', '.*') # Need to do this for now.

def export_tracker(tracker_path: str, output_format: str = "json", output_path: Optional[str] = None) -> str:
    """
    Export a tracker file to various formats.
    Args:
        tracker_path: Path to the tracker file
        output_format: Format to export to ('md', 'json', 'csv', 'dot')
        output_path: Optional path to save the exported file
    Returns:
        Path to the exported file or error message
    """
    check_file_modified(tracker_path)

    tracker_path = normalize_path(tracker_path)

    # Read the tracker
    tracker_data = read_tracker_file(tracker_path)
    if not tracker_data or not tracker_data["keys"]:
        return "Error: Empty tracker or tracker not found"

    # Determine output path if not provided
    if output_path is None:
        base_name = os.path.splitext(tracker_path)[0]
        output_path = f"{base_name}_export.{output_format}"

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if output_format == "md":
            shutil.copy2(tracker_path, output_path)
        elif output_format == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(tracker_data, f, indent=2)
        elif output_format == "csv":
            # Export as CSV
            from cline_utils.dependency_system.core.dependency_grid import decompress

            grid = tracker_data.get("grid", {})
            keys = tracker_data.get("keys", {})
            with open(output_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("Source,Target,Dependency Type\n")
                keys = sort_keys(list(tracker_data["keys"].keys()))
                for source_key in keys:
                    row = tracker_data["grid"].get(source_key, "." * len(keys))
                    for target_key, dep_type in zip(keys, row):
                        if dep_type not in (".", "o"):
                            f.write(f"{source_key},{target_key},{dep_type}\n")
        elif output_format == "dot":
            # Export as GraphViz DOT format
            from cline_utils.dependency_system.core.dependency_grid import decompress

            grid = tracker_data.get("grid", {})
            keys = tracker_data.get("keys", {})
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("digraph Dependencies {\n")
                f.write("  rankdir=LR;\n")
                f.write("  node [shape=box];\n")
                keys = sort_keys(list(tracker_data["keys"].keys()))
                for key in keys:
                    f.write(f'  "{key}" [label="{key}"];\n')
                for source_key in keys:
                    row = tracker_data["grid"].get(source_key, "." * len(keys))
                    for target_key, dep_type in zip(keys, row):
                        if dep_type not in (".", "o"):
                            f.write(f'  "{source_key}" -> "{target_key}" [label="{dep_type}"];\n')

                # Write edges
                for i, source_key in enumerate(keys):
                    for j, target_key in enumerate(keys):
                        if source_key in grid and isinstance(grid[source_key], str):
                            decompressed_row = decompress(grid[source_key])
                            if j < len(decompressed_row) and decompressed_row[j] not in [".", "o"]:
                                f.write(f' "{source_key}" -> "{target_key}" [label="{decompressed_row[j]}"];\n')
                f.write("}\n")
        else:
            return f"Error: Unsupported output format '{output_format}'"

        logger.info(f"Exported tracker to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error exporting tracker: {e}")
        return f"Error exporting tracker: {str(e)}"

def remove_file_from_tracker(output_file: str, file_to_remove: str):
    """Removes a file's key and row/column from the tracker.  Invalidates cache."""
    check_file_modified(output_file)

    key_def_start = "---KEY_DEFINITIONS_START---"
    key_def_end = "---KEY_DEFINITIONS_END---"
    grid_start = "---GRID_START---"
    grid_end = "---GRID_END---"
    last_grid_edit = "last_GRID_edit"
    last_key_edit = "last_KEY_edit"

    if not os.path.exists(output_file):
        raise FileNotFoundError(f"Tracker file '{output_file}' not found.")

    with open(output_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # --- Key Removal ---
    try:
        key_def_start_index = lines.index(key_def_start + "\n") + 2
        key_def_end_index = lines.index(key_def_end + "\n")

        # Efficiently find the key to remove using get_key_from_path
        existing_keys = {}
        for line in lines[key_def_start_index:key_def_end_index]:
            if ": " in line:
                k, v = line.strip().split(": ", 1)
                existing_keys[k] = v
        key_to_remove = get_key_from_path(file_to_remove, existing_keys)


    except ValueError as e:
        raise ValueError("Key Definitions section not found.") from e

    if key_to_remove is None:
        raise ValueError(f"File '{file_to_remove}' not found in tracker.")


    updated_lines = [key_def_start + "\n", "Key Definitions:\n"]
    for line in lines[key_def_start_index:key_def_end_index]:  # Iterate through original lines
        if ": " in line and not line.startswith(key_to_remove + ":"):
             updated_lines.append(line)
    updated_lines.append(key_def_end + "\n")

    # --- Keep last_KEY_edit and update last_GRID_edit ---
    last_key_edit_line = next((line for line in lines if line.startswith(last_key_edit)), None)
    if last_key_edit_line:
        updated_lines.append(last_key_edit_line)
    updated_lines.append(f"{last_grid_edit}: {key_to_remove}\n")
    updated_lines.append(grid_start + "\n")

    # --- Grid Removal ---
    try:
        grid_start_index = lines.index(grid_start + "\n") + 1
        grid_end_index = lines.index(grid_end + "\n")
        x_axis_line = lines[grid_start_index]
        x_axis_keys = x_axis_line.strip().split(" ", 1)[1].split()

        if key_to_remove not in x_axis_keys:
            raise ValueError(f"Key '{key_to_remove}' not found on X-axis.")

        updated_x_axis_keys = [k for k in x_axis_keys if k != key_to_remove]
        updated_lines.append(f"X {' '.join(updated_x_axis_keys)}\n")

        index_to_remove = x_axis_keys.index(key_to_remove)
        for line in lines[grid_start_index + 1:grid_end_index]:
            match = re.match(r"(\w+) = (.*)", line)
            if match and match.group(1) != key_to_remove:
                row_key = match.group(1)
                dependency_string = match.group(2)
                decompressed = decompress(dependency_string)
                updated_decompressed = (decompressed[:index_to_remove] +
                                        decompressed[index_to_remove + 1:])
                updated_lines.append(f"{row_key} = {compress(updated_decompressed)}\n")

    except ValueError as e:
        raise ValueError(f"Grid section error: {e}") from e

    updated_lines.append(grid_end + "\n")
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    # Invalidate the entire tracker cache after removing a file
    invalidate_dependent_entries('tracker', '.*')
    tracker_modified(file_to_remove, os.path.dirname(output_file))

# EoF