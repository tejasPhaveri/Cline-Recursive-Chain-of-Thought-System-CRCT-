# cline_utils/dependency_system/utils/visualize_dependencies.py

"""
Handles the generation of Mermaid syntax for visualizing project dependencies.
"""

import os
import logging
import re
from collections import defaultdict
from typing import List, Optional, Dict, Tuple, Set

from cline_utils.dependency_system.utils.tracker_utils import aggregate_all_dependencies, get_key_global_instance_string, resolve_key_global_instance_to_ki

# Assuming these are the correct relative import paths based on the new file location
from ..core.key_manager import KeyInfo, sort_key_strings_hierarchically # Assuming global_path_to_key_info_type is Dict[str, KeyInfo]
from ..core.dependency_grid import DIAGONAL_CHAR # For skipping self-loops if necessary
from ..io import tracker_io # For aggregate_all_dependencies
from ..utils.path_utils import get_project_root, normalize_path # For path normalization
from ..utils.config_manager import ConfigManager # To get priorities etc.

logger = logging.getLogger(__name__)

PathMigrationInfo = Dict[str, Tuple[Optional[str], Optional[str]]]

def _is_direct_parent_child_key_relationship(
    key1_gi_str: str, # Now takes KEY#GI strings
    key2_gi_str: str, # Now takes KEY#GI strings
    global_path_to_key_info_map: Dict[str, KeyInfo]
) -> bool:
    """
    Checks if one key's path is the direct parent_path of the other key's path.
    """
    key1_info = resolve_key_global_instance_to_ki(key1_gi_str, global_path_to_key_info_map)
    key2_info = resolve_key_global_instance_to_ki(key2_gi_str, global_path_to_key_info_map)
    
    if not key1_info or not key2_info: return False
    # Paths should be normalized from KeyInfo itself
    if key2_info.parent_path and key1_info.norm_path == key2_info.parent_path: return True
    if key1_info.parent_path and key2_info.norm_path == key1_info.parent_path: return True
    return False


def generate_mermaid_diagram(
    focus_keys_list_input: List[str], # User input, could be "KEY" or "KEY#GI"
    global_path_to_key_info_map: Dict[str, KeyInfo], # Current global map
    path_migration_info: PathMigrationInfo, 
    all_tracker_paths_list: List[str],
    config_manager_instance: ConfigManager
) -> Optional[str]:
    """
    Core logic to generate a Mermaid string for given focus keys or overall project.

    Args:
        focus_keys_list: List of key strings to focus on. If empty, attempts to visualize all.
        global_path_to_key_info_map: Maps normalized paths to KeyInfo objects (CURRENT state).
        path_migration_info: The authoritative map linking paths to their old/new keys.
        all_tracker_paths_list: List of paths to all tracker files.
        config_manager_instance: Instance of ConfigManager.

    Returns:
        The Mermaid diagram string or None on critical failure.
        Returns a simple "no data" Mermaid string if no relevant items are found.
    """
    logger.info(f"Generating Mermaid diagram. Focus Keys Input: {focus_keys_list_input or 'Project Overview'}")

    # --- Resolve focus_keys_list_input to specific KEY#GI strings ---
    resolved_focus_keys_gi: List[str] = []
    if focus_keys_list_input:
        from .tracker_utils import get_globally_resolved_key_info_for_cli # For CLI-style ambiguity resolution
        for key_input_str in focus_keys_list_input:
            parts = key_input_str.split('#')
            base_key = parts[0]
            instance_num_str = parts[1] if len(parts) > 1 else None
            instance_num = int(instance_num_str) if instance_num_str and instance_num_str.isdigit() else None
            
            # Use the CLI helper to resolve ambiguity if instance not provided
            # Note: This prints to console if ambiguous. For non-CLI use, direct resolution might be better.
            resolved_ki = get_globally_resolved_key_info_for_cli(base_key, instance_num, global_path_to_key_info_map, "focus")
            if resolved_ki:
                gi_str = get_key_global_instance_string(resolved_ki, global_path_to_key_info_map)
                if gi_str:
                    resolved_focus_keys_gi.append(gi_str)
                else:
                    logger.warning(f"Mermaid: Could not get GI string for resolved focus KI: {resolved_ki.norm_path}")
            # If get_globally_resolved_key_info_for_cli returns None, error was printed.
    logger.info(f"Mermaid: Resolved Focus KEY#GIs: {resolved_focus_keys_gi or 'Project Overview (no specific focus)'}")


    try:
        # --- CORRECTED CALL to aggregate_all_dependencies ---
        aggregated_links_with_origins = aggregate_all_dependencies( # From tracker_utils
            set(all_tracker_paths_list), 
            path_migration_info,
            global_path_to_key_info_map # Pass the current global map
        )
        # Keys are now Tuple[src_KEY#GI, tgt_KEY#GI]
    except ValueError as ve: # Catch potential errors from aggregation (e.g. if called with bad map by mistake)
        logger.error(f"Mermaid generation failed: Error during dependency aggregation: {ve}")
        return f"flowchart TB\n\n// Error: Could not aggregate dependencies: {ve}"
    except Exception as e:
        logger.error(f"Mermaid generation failed: Unexpected error during aggregation: {e}", exc_info=True)
        return f"flowchart TB\n\n// Error: Unexpected error aggregating: {e}"

    # consolidated_directed_links now has KEY#GI keys
    consolidated_directed_links_gi: Dict[Tuple[str, str], str] = {
        link_gi_tuple: char_and_origins[0]
        for link_gi_tuple, char_and_origins in aggregated_links_with_origins.items()
    }
    logger.debug(f"Aggregated {len(consolidated_directed_links_gi)} consolidated KEY#GI directed links.")

    # --- Scope Determination (using KEY#GI strings) ---
    # focus_keys_valid now stores KEY#GI strings
    focus_keys_valid_gi = set(resolved_focus_keys_gi) 
    keys_in_module_scope_gi = set() # Stores KEY#GI strings
    is_module_view = False
    module_path_prefix_for_scope = "" # Used if is_module_view

    if len(resolved_focus_keys_gi) == 1:
        focus_key_gi_str = resolved_focus_keys_gi[0]
        # Resolve the focus KEY#GI string back to its KeyInfo
        focus_info = resolve_key_global_instance_to_ki(focus_key_gi_str, global_path_to_key_info_map)
        
        if focus_info and focus_info.is_directory:
            is_module_view = True
            module_path_prefix_for_scope = focus_info.norm_path + ("/" if not focus_info.norm_path.endswith('/') else "")
            
            # Find all KIs under this module and get their KEY#GI strings
            for ki_val in global_path_to_key_info_map.values():
                if ki_val.norm_path == focus_info.norm_path or \
                   (ki_val.parent_path and normalize_path(ki_val.parent_path) == focus_info.norm_path) or \
                   (module_path_prefix_for_scope and ki_val.norm_path.startswith(module_path_prefix_for_scope)): # General subpath check
                    gi_str_module_item = get_key_global_instance_string(ki_val, global_path_to_key_info_map)
                    if gi_str_module_item:
                        keys_in_module_scope_gi.add(gi_str_module_item)
            logger.info(f"Module view for {focus_key_gi_str}: {len(keys_in_module_scope_gi)} items in scope.")
        elif not focus_info: # Should not happen if resolved_focus_keys_gi is populated correctly
             logger.warning(f"Focus KEY#GI '{focus_key_gi_str}' could not be resolved to KeyInfo. Defaulting to overview."); focus_keys_valid_gi.clear()

    # --- Edge Preparation (using KEY#GI strings) ---
    intermediate_edges_gi = []; processed_pairs_for_intermediate_gi = set()
    non_n_links_gi = {(s_gi, t_gi): char for (s_gi, t_gi), char in consolidated_directed_links_gi.items() if char != 'n'}
    
    # Sort by the KEY#GI strings for consistent processing
    for (source_gi, target_gi), forward_char in sorted(non_n_links_gi.items()):
        pair_tuple_gi = tuple(sorted((source_gi, target_gi)))
        if pair_tuple_gi in processed_pairs_for_intermediate_gi: continue
        
        reverse_char = non_n_links_gi.get((target_gi, source_gi))
        
        # Logic for determining edge type based on forward and reverse chars
        if forward_char == 'x' or reverse_char == 'x': 
            intermediate_edges_gi.append((source_gi, target_gi, 'x'))
        elif forward_char == '<' and reverse_char == '>': # A relies on B, B is relied on by A == A --> B
            intermediate_edges_gi.append((source_gi, target_gi, '<')) # Source relies on Target
        elif forward_char == '>' and reverse_char == '<': # A is relied on by B, B relies on A == B --> A
            intermediate_edges_gi.append((target_gi, source_gi, '<')) # Target relies on Source (swap for consistent '<' meaning)
        elif forward_char == '>' : # A is relied on by B (B --> A)
             intermediate_edges_gi.append((target_gi, source_gi, '<')) # Target relies on source
        elif forward_char == '<': # A relies on B (A --> B)
             intermediate_edges_gi.append((source_gi, target_gi, '<'))
        elif forward_char: # Other non-directional like 'd', 's', 'S'
            intermediate_edges_gi.append((source_gi, target_gi, forward_char))
        
        processed_pairs_for_intermediate_gi.add(pair_tuple_gi)

    # --- Edge Filtering by Scope (using KEY#GI strings) ---
    edges_within_scope_gi = []; relevant_keys_for_nodes_gi = set()
    if is_module_view:
        relevant_keys_for_nodes_gi.update(keys_in_module_scope_gi)
        for k1_gi, k2_gi, char_val in intermediate_edges_gi:
            k1_is_internal = k1_gi in keys_in_module_scope_gi
            k2_is_internal = k2_gi in keys_in_module_scope_gi
            if (k1_is_internal and k2_is_internal) or (k1_is_internal != k2_is_internal): # Link within module or crossing boundary
                edges_within_scope_gi.append((k1_gi, k2_gi, char_val))
                relevant_keys_for_nodes_gi.add(k1_gi)
                relevant_keys_for_nodes_gi.add(k2_gi)
    elif focus_keys_valid_gi:
        relevant_keys_for_nodes_gi.update(focus_keys_valid_gi)
        for k1_gi, k2_gi, char_val in intermediate_edges_gi:
            if k1_gi in focus_keys_valid_gi or k2_gi in focus_keys_valid_gi:
                edges_within_scope_gi.append((k1_gi, k2_gi, char_val))
                relevant_keys_for_nodes_gi.add(k1_gi)
                relevant_keys_for_nodes_gi.add(k2_gi)
    else: # Overview
        edges_within_scope_gi = intermediate_edges_gi
        relevant_keys_for_nodes_gi = {k_gi for edge_tuple_gi in edges_within_scope_gi for k_gi in edge_tuple_gi[:2]}

    # --- Final Edge Filtering (using KEY#GI strings) ---
    final_edges_to_draw_gi = []
    for k1_gi, k2_gi, char_val in edges_within_scope_gi:
        if char_val == 'p': continue # Skip placeholder links

        info1 = resolve_key_global_instance_to_ki(k1_gi, global_path_to_key_info_map)
        info2 = resolve_key_global_instance_to_ki(k2_gi, global_path_to_key_info_map)
        if not info1 or not info2: continue

        # Skip drawing 'x' if it's a direct parent-child structural link (handled by subgraphs)
        if char_val == 'x' and _is_direct_parent_child_key_relationship(k1_gi, k2_gi, global_path_to_key_info_map):
            continue
        
        # Filter: if not a doc link ('d'), only show links between items of the same type (file-file or dir-dir)
        # This helps declutter by not showing, e.g., a code file directly linking to a parent directory via non-'d' link.
        if char_val != 'd' and info1.is_directory != info2.is_directory:
            continue
        final_edges_to_draw_gi.append((k1_gi, k2_gi, char_val))
    logger.info(f"Final count of KEY#GI edges to draw: {len(final_edges_to_draw_gi)}")

    # Nodes to render are those involved in final edges, plus any explicitly focused keys
    nodes_to_render_gi = {k_gi for edge_tuple_gi in final_edges_to_draw_gi for k_gi in edge_tuple_gi[:2]}
    if focus_keys_valid_gi: nodes_to_render_gi.update(focus_keys_valid_gi)

    if not nodes_to_render_gi: return "flowchart TB\n\n// No relevant data to visualize."
    logger.info(f"Final count of distinct KEY#GI nodes to render: {len(nodes_to_render_gi)}")

    # --- Hierarchical Structure for Subgraphs (using KeyInfo from resolved KEY#GI) ---
    parent_norm_path_to_child_key_infos: Dict[Optional[str], List[KeyInfo]] = defaultdict(list)
    all_kis_for_hierarchy: Dict[str, KeyInfo] = {} # Map KEY#GI to KeyInfo for items in hierarchy

    # Populate all_kis_for_hierarchy for nodes that will be rendered or are parents of rendered nodes
    queue_for_hierarchy_build = list(nodes_to_render_gi)
    visited_for_hierarchy_build = set()

    while queue_for_hierarchy_build:
        key_gi_q = queue_for_hierarchy_build.pop(0)
        if key_gi_q in visited_for_hierarchy_build: continue
        visited_for_hierarchy_build.add(key_gi_q)

        ki_q = resolve_key_global_instance_to_ki(key_gi_q, global_path_to_key_info_map)
        if not ki_q: continue
        all_kis_for_hierarchy[key_gi_q] = ki_q

        if ki_q.parent_path:
            parent_ki = global_path_to_key_info_map.get(ki_q.parent_path)
            if parent_ki:
                parent_gi_str = get_key_global_instance_string(parent_ki, global_path_to_key_info_map)
                if parent_gi_str and parent_gi_str not in visited_for_hierarchy_build:
                    queue_for_hierarchy_build.append(parent_gi_str)
    
    # Build parent_to_children map using resolved KeyInfo objects
    for ki_hier in all_kis_for_hierarchy.values():
        parent_norm_path_to_child_key_infos[ki_hier.parent_path].append(ki_hier)


    # --- Generate Mermaid String (Nodes and Subgraphs, using KEY#GI as node IDs) ---
    mermaid_string_parts = ["flowchart TB"]
    # classDef module - for subgraph titles (text color, font-weight) and fallback directory nodes
    mermaid_string_parts.append("  classDef module fill:#f9f,stroke:#333,stroke-width:2px,color:#333,font-weight:bold;") 
    
    # MODIFIED: 'file' classDef for code files - new purple fill
    mermaid_string_parts.append("  classDef file fill:#D1C4E9,stroke:#666,stroke-width:1px,color:#333;") # Mild purple fill
    
    # 'doc' classDef remains for documentation files
    mermaid_string_parts.append("  classDef doc fill:#D1C4E9,stroke:#666,stroke-width:1px,color:#333;")
    
    mermaid_string_parts.append("  classDef focusNode stroke:#007bff,stroke-width:3px;")

    mermaid_string_parts.append("  linkStyle default stroke:#CCCCCC,stroke-width:1px") # Light gray links
    
    # --- Node Styling Helper ---
    project_root_viz = get_project_root() # For _get_item_type if used in _get_node_class_viz
    try: from .template_generator import _get_item_type as get_item_type_for_diagram_style_viz
    except ImportError:
        def get_item_type_for_diagram_style_viz(p, c, pr): return "doc" if any(p.endswith(e) for e in ['.md','.rst']) else "file"

    def _get_node_class_viz(key_info_obj: KeyInfo) -> str:
        if key_info_obj.is_directory: return "module"
        item_type = get_item_type_for_diagram_style_viz(key_info_obj.norm_path, config_manager_instance, project_root_viz)
        return "doc" if item_type == "doc" else "file"

    mermaid_rendered_node_ids = set()
    dir_gi_to_mermaid_subgraph_id: Dict[str, str] = {}
    subgraph_id_counter = 0 

    # Pre-calculate global counts for display formatting of node labels
    global_key_string_counts = defaultdict(int)
    for ki_count in global_path_to_key_info_map.values():
        global_key_string_counts[ki_count.key_string] += 1

    mermaid_string_parts.append("\n  %% -- Nodes and Subgraphs --")
    def _generate_mermaid_structure_recursive_gi(parent_norm_path_rec: Optional[str], depth_indent_str_rec: str):
        nonlocal mermaid_rendered_node_ids, subgraph_id_counter, dir_gi_to_mermaid_subgraph_id
        
        child_key_infos_rec = sorted(
            parent_norm_path_to_child_key_infos.get(parent_norm_path_rec, []),
            # Sort by base key string then instance number for consistent visual output
            key=lambda ki_rec: (
                sort_key_strings_hierarchically([ki_rec.key_string])[0],
                int(get_key_global_instance_string(ki_rec, global_path_to_key_info_map).split('#')[1])
                    if get_key_global_instance_string(ki_rec, global_path_to_key_info_map) and '#' in get_key_global_instance_string(ki_rec, global_path_to_key_info_map) else 0
            )
        )

        for child_ki_rec in child_key_infos_rec:
            child_key_gi_str = get_key_global_instance_string(child_ki_rec, global_path_to_key_info_map)
            if not child_key_gi_str or child_key_gi_str not in all_kis_for_hierarchy: # Must be part of the overall hierarchy to draw
                continue

            item_basename_rec = os.path.basename(child_ki_rec.norm_path)
            mermaid_node_id = child_key_gi_str # Use KEY#GI directly as ID, unquoted

            # Determine label: Show full KEY#GI only if base key is globally duplicated
            node_display_key = child_ki_rec.key_string
            if global_key_string_counts.get(child_ki_rec.key_string, 0) > 1:
                node_display_key = child_key_gi_str # Use full KEY#GI for display

            if child_ki_rec.is_directory:
                # Ensure unique subgraph ID, especially if base keys are duplicated
                subgraph_id_counter += 1
                mermaid_subgraph_id = f"sg_{re.sub(r'[^a-zA-Z0-9_]', '_', child_ki_rec.key_string)}_{subgraph_id_counter}"
                dir_gi_to_mermaid_subgraph_id[child_key_gi_str] = mermaid_subgraph_id
                
                # Display base key and basename for subgraph title
                subgraph_text_color = "#D1C4E9"
                subgraph_title = f"<font color='{subgraph_text_color}'>{child_ki_rec.key_string}<br>{item_basename_rec}" # Use <br> for newline
                mermaid_string_parts.append(f'{depth_indent_str_rec}subgraph {mermaid_subgraph_id} ["{subgraph_title}"]')
                mermaid_rendered_node_ids.add(child_key_gi_str) 
                
                mermaid_string_parts.append(f'{depth_indent_str_rec}  style {mermaid_subgraph_id} fill:#282828,stroke:#39FF14,stroke-width:4px')
                if child_key_gi_str in resolved_focus_keys_gi: # If a focused item is a directory
                     mermaid_string_parts.append(f'{depth_indent_str_rec}  style {mermaid_subgraph_id} stroke-width:5px,stroke:#00FF00') # Example: thicker/brighter focus
                
                _generate_mermaid_structure_recursive_gi(child_ki_rec.norm_path, depth_indent_str_rec + "  ")
                mermaid_string_parts.append(f'{depth_indent_str_rec}end')
            
            elif child_key_gi_str in nodes_to_render_gi: # It's a file to be rendered explicitly
                if child_key_gi_str not in mermaid_rendered_node_ids:
                    node_label_text = f"{node_display_key}<br>{item_basename_rec}"
                    node_definition = f'{mermaid_node_id}["{node_label_text}"]' # ID["Label Text"]
                    mermaid_string_parts.append(f'{depth_indent_str_rec}{node_definition}')
                    
                    node_class = _get_node_class_viz(child_ki_rec)
                    mermaid_string_parts.append(f'{depth_indent_str_rec}class {mermaid_node_id} {node_class}')
                    if child_key_gi_str in focus_keys_valid_gi: # focus_keys_valid_gi contains KEY#GI
                        mermaid_string_parts.append(f'{depth_indent_str_rec}class {mermaid_node_id} focusNode')
                    mermaid_rendered_node_ids.add(child_key_gi_str)

    _generate_mermaid_structure_recursive_gi(None, "  ") # Start recursion from roots (parent_norm_path is None)

    # Fallback for any nodes in nodes_to_render_gi not yet drawn (e.g., if not part of main hierarchy)
    mermaid_string_parts.append("\n  %% -- Fallback Node Definitions (Orphaned/Not in Main Hierarchy) --")
    for key_gi_fb in nodes_to_render_gi:
        if key_gi_fb not in mermaid_rendered_node_ids:
            info_fb = resolve_key_global_instance_to_ki(key_gi_fb, global_path_to_key_info_map) # Resolve KEY#GI
            if info_fb:
                item_basename_fb = os.path.basename(info_fb.norm_path)
                mermaid_node_id_fb = key_gi_fb # Use KEY#GI directly
                node_display_key_fb = info_fb.key_string
                if global_key_string_counts.get(info_fb.key_string, 0) > 1:
                    node_display_key_fb = key_gi_fb
                
                node_label_text_fb = f"{node_display_key_fb}<br>{item_basename_fb}"
                node_definition_fb = f'{mermaid_node_id_fb}["{node_label_text_fb}"]'
                mermaid_string_parts.append(f'  {node_definition_fb}')
                node_class_fb = _get_node_class_viz(info_fb) 
                mermaid_string_parts.append(f'  class {mermaid_node_id_fb} {node_class_fb}')
                if key_gi_fb in focus_keys_valid_gi:
                    mermaid_string_parts.append(f'  class {mermaid_node_id_fb} focusNode')
                mermaid_rendered_node_ids.add(key_gi_fb) 
            else: logger.warning(f"Mermaid Fallback: KeyInfo missing for KEY#GI '{key_gi_fb}'.")

    # Dependencies Edge Drawing (using KEY#GI strings as node IDs)
    mermaid_string_parts.append("\n  %% -- Dependencies --")
    dep_char_to_style = {
        '<': ('-->', "relies on"), '>': ('-->', "required by"), # Note: '>' is converted to target<--source
        'x': ('<-->', "mutual"), 'd': ('-.->', "docs"),
        's': ('-.->', "semantic (weak)"), 'S': ('==>', "semantic (strong)"),
    }
    # Sort edges for consistent output
    sorted_final_edges_gi = sorted(final_edges_to_draw_gi, key=lambda x: (x[0], x[1], x[2]))

    for k1_gi, k2_gi, dep_char in sorted_final_edges_gi:
        # Get KeyInfo for source and target to check if they are directories/subgraphs
        ki1 = all_kis_for_hierarchy.get(k1_gi) # Use the map built for hierarchy
        ki2 = all_kis_for_hierarchy.get(k2_gi)

        if not ki1 or not ki2: # If for some reason KIs not found, skip edge
            logger.warning(f"Mermaid Edges: KI not found for {k1_gi} or {k2_gi}. Skipping edge.")
            continue

        if k1_gi not in mermaid_rendered_node_ids or k2_gi not in mermaid_rendered_node_ids:
            continue # Skip edges if nodes aren't rendered

        node1_mermaid_id = dir_gi_to_mermaid_subgraph_id.get(k1_gi, k1_gi)
        node2_mermaid_id = dir_gi_to_mermaid_subgraph_id.get(k2_gi, k2_gi)
        
        arrow_style, label_text = dep_char_to_style.get(dep_char, ('-->', dep_char)) # Default style
        
        source_node_id_draw, target_node_id_draw = node1_mermaid_id, node2_mermaid_id
        # If dep_char is '>', reverse the arrow direction for display (B --> A becomes A <-- B)
        # But the label "required by" still implies original source requires target.
        # For '<', it's "relies on", so source --> target is correct.
        mermaid_string_parts.append(f'  {source_node_id_draw} {arrow_style}|"{label_text}"| {target_node_id_draw}')

    return "\n".join(mermaid_string_parts)

# --- End of visualize_dependencies.py ---