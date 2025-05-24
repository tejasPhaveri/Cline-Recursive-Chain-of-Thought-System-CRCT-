# analysis/dependency_analyzer.py

"""
Analysis module for dependency detection and code analysis.
Parses files to identify imports, function calls, and other dependency indicators.
"""

import os
import ast
import re
import logging
from typing import Dict, List, Tuple, Set, Optional, Any

# Import only from utils, core, and io layers
from cline_utils.dependency_system.utils.path_utils import normalize_path, is_subpath, get_file_type as util_get_file_type, get_project_root
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, cache_manager, invalidate_dependent_entries

logger = logging.getLogger(__name__)

# Regular expressions
PYTHON_IMPORT_PATTERN = re.compile(r'^\s*from\s+([.\w]+)\s+import\s+(?:\(|\*|\w+)', re.MULTILINE)
PYTHON_IMPORT_MODULE_PATTERN = re.compile(r'^\s*import\s+([.\w]+(?:\s*,\s*[.\w]+)*)', re.MULTILINE)
JAVASCRIPT_IMPORT_PATTERN = re.compile(r'import(?:["\'\s]*(?:[\w*{}\n\r\s,]+)from\s*)?["\']([^"\']+)["\']'r'|\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)'r'|import\s*\(\s*["\']([^"\']+)["\']\s*\)')
MARKDOWN_LINK_PATTERN = re.compile(r'\[(?:[^\]]+)\]\(([^)]+)\)')
HTML_A_HREF_PATTERN = re.compile(r'<a\s+(?:[^>]*?\s+)?href=(["\'])(?P<url>[^"\']+?)\1', re.IGNORECASE)
HTML_SCRIPT_SRC_PATTERN = re.compile(r'<script\s+(?:[^>]*?\s+)?src=(["\'])(?P<url>[^"\']+?)\1', re.IGNORECASE)
HTML_LINK_HREF_PATTERN = re.compile(r'<link\s+(?:[^>]*?\s+)?href=(["\'])(?P<url>[^"\']+?)\1', re.IGNORECASE) 
HTML_IMG_SRC_PATTERN = re.compile(r'<img\s+(?:[^>]*?\s+)?src=(["\'])(?P<url>[^"\']+?)\1', re.IGNORECASE)
CSS_IMPORT_PATTERN = re.compile(r'@import\s+(?:url\s*\(\s*)?["\']?([^"\')\s]+[^"\')]*?)["\']?(?:\s*\))?;', re.IGNORECASE)

# --- Main Analysis Function ---
@cached("file_analysis",
       key_func=lambda file_path, force=False: f"analyze_file:{normalize_path(file_path)}:{(os.path.getmtime(file_path) if os.path.exists(file_path) else 0)}:{force}")
def analyze_file(file_path: str, force: bool = False) -> Dict[str, Any]:
    """
    Analyzes a file to identify dependencies, imports, and other metadata.
    Uses caching based on file path, modification time, and force flag.
    Skips binary files before attempting text-based analysis.
    Python ASTs are stored separately in "ast_cache".

    Args:
        file_path: Path to the file to analyze
        force: If True, bypass the cache for this specific file analysis.
    Returns:
        Dictionary containing analysis results (without AST for Python files) or error/skipped status.
    """
    norm_file_path = normalize_path(file_path)
    if not os.path.exists(norm_file_path) or not os.path.isfile(norm_file_path): 
        return {"error": "File not found or not a file", "file_path": norm_file_path}

    config_manager = ConfigManager(); project_root = get_project_root()
    excluded_dirs_rel = config_manager.get_excluded_dirs()
    # get_excluded_paths() from config_manager now returns a list of absolute normalized paths
    # including resolved file patterns.
    all_excluded_paths_abs = set(config_manager.get_excluded_paths()) # Fetch once
    excluded_extensions = set(config_manager.get_excluded_extensions())
    
    # Check against pre-normalized absolute excluded paths
    if norm_file_path in all_excluded_paths_abs or \
       any(is_subpath(norm_file_path, excluded_dir_abs) for excluded_dir_abs in {normalize_path(os.path.join(project_root, p)) for p in excluded_dirs_rel}) or \
       os.path.splitext(norm_file_path)[1].lower() in excluded_extensions or \
       os.path.basename(norm_file_path).endswith("_module.md"): # Check tracker file name pattern
        logger.debug(f"Skipping analysis of excluded/tracker file: {norm_file_path}"); 
        return {"skipped": True, "reason": "Excluded path, extension, or tracker file", "file_path": norm_file_path}

    # --- Binary File Check ---
    try:
        with open(norm_file_path, 'rb') as f_check_binary:
            # Read a small chunk to check for null bytes, common in many binary files
            # This is a heuristic, not a perfect binary detector.
            if b'\0' in f_check_binary.read(1024):
                logger.debug(f"Skipping analysis of binary file: {norm_file_path}")
                return {"skipped": True, "reason": "Binary file detected", "file_path": norm_file_path, "size": os.path.getsize(norm_file_path)}
    except FileNotFoundError: return {"error": "File disappeared before binary check", "file_path": norm_file_path}
    except Exception as e_bin_check:
        logger.warning(f"Error during binary check for {norm_file_path}: {e_bin_check}. Proceeding with text analysis attempt.")

    try:
        file_type = util_get_file_type(norm_file_path)
        # Initialize with all potential keys to ensure consistent structure
        analysis_result: Dict[str, Any] = {
            "file_path": norm_file_path, "file_type": file_type, "imports": [], 
            "links": [], "functions": [], "classes": [], "calls": [],     
            "attribute_accesses": [], "inheritance": [], "type_references": [], 
            "globals_defined": [], "exports": [], "code_blocks": [], "scripts": [], 
            "stylesheets": [], "images": [], "decorators_used": [],
            "exceptions_handled": [], "with_contexts_used": []
        }
        try:
            with open(norm_file_path, 'r', encoding='utf-8') as f: content = f.read()
        except FileNotFoundError: return {"error": "File disappeared during analysis", "file_path": norm_file_path}
        except UnicodeDecodeError as e: 
            logger.warning(f"Encoding error reading {norm_file_path} as UTF-8: {e}. File might be non-text or use different encoding.")
            return {"error": "Encoding error", "details": str(e), "file_path": norm_file_path}
        except Exception as e: 
            logger.error(f"Error reading file {norm_file_path}: {e}", exc_info=True)
            return {"error": "File read error", "details": str(e), "file_path": norm_file_path}

        if file_type == "py": 
            _analyze_python_file(norm_file_path, content, analysis_result)
            # --- MODIFICATION: Handle AST storage after _analyze_python_file ---
            ast_object = analysis_result.pop("_ast_tree", None) # Remove from result
            ast_cache = cache_manager.get_cache("ast_cache") # Get/create the ast_cache

            if ast_object and not analysis_result.get("error"): # Only cache valid ASTs from successful full analysis
                logger.debug(f"Caching AST for {norm_file_path} in 'ast_cache'.")
                ast_cache.set(norm_file_path, ast_object) # Default TTL from cache_manager applies
            elif ast_object and analysis_result.get("error"):
                logger.warning(f"AST parsed for {norm_file_path} but analysis had error: {analysis_result.get('error')}. AST not cached.")
                # Optionally, explicitly store None or invalidate if an error occurred AFTER parsing
                ast_cache.set(norm_file_path, None) # Store None to indicate parsing happened but analysis failed later
            elif not ast_object: # Parsing itself failed (e.g. SyntaxError)
                logger.warning(f"No AST object produced for {norm_file_path} (likely parsing error). 'ast_cache' will not be populated for this file or will store None.")
                ast_cache.set(norm_file_path, None) # Store None to indicate parsing failed
            # --- END OF MODIFICATION ---
        elif file_type == "js": _analyze_javascript_file(norm_file_path, content, analysis_result)
        elif file_type == "md": _analyze_markdown_file(norm_file_path, content, analysis_result)
        elif file_type == "html": _analyze_html_file(norm_file_path, content, analysis_result)
        elif file_type == "css": _analyze_css_file(norm_file_path, content, analysis_result)
        
        try: analysis_result["size"] = os.path.getsize(norm_file_path)
        except FileNotFoundError: analysis_result["size"] = -1 
        except OSError: analysis_result["size"] = -2 
            
        return analysis_result # This result no longer contains _ast_tree for Python files
    except Exception as e:
        logger.exception(f"Unexpected error analyzing {norm_file_path}: {e}")
        return {"error": "Unexpected analysis error", "details": str(e), "file_path": norm_file_path}

# --- Analysis Helper Functions ---

def _analyze_python_file(file_path: str, content: str, result: Dict[str, Any]) -> None:
    # Ensure lists are initialized (caller already does this, but good for safety)
    result.setdefault("imports", [])
    result.setdefault("functions", []) 
    result.setdefault("classes", [])   
    result.setdefault("calls", [])
    result.setdefault("attribute_accesses", [])
    result.setdefault("inheritance", [])
    result.setdefault("type_references", [])
    result.setdefault("globals_defined", [])
    result.setdefault("decorators_used", [])      
    result.setdefault("exceptions_handled", [])   
    result.setdefault("with_contexts_used", [])   
    # --- ADDED: Key for storing the AST tree ---
    result.setdefault("_ast_tree", None) 
    # ---

    # _get_full_name_str and _extract_type_names_from_annotation helpers
    def _get_full_name_str(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name): return node.id
        if isinstance(node, ast.Attribute):
            # Recursively get the base part
            base = _get_full_name_str(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Subscript):
            base = _get_full_name_str(node.value)
            index_repr = "..."
            slice_node = node.slice
            if isinstance(slice_node, ast.Constant): index_repr = repr(slice_node.value)
            elif isinstance(slice_node, ast.Name): index_repr = slice_node.id
            elif isinstance(slice_node, ast.Tuple): 
                elts_str = ", ".join([_get_full_name_str(e) or "..." for e in slice_node.elts])
                index_repr = f"Tuple[{elts_str}]"
            elif isinstance(slice_node, ast.Slice): 
                 lower = _get_full_name_str(slice_node.lower) if slice_node.lower else ""
                 upper = _get_full_name_str(slice_node.upper) if slice_node.upper else ""
                 step = _get_full_name_str(slice_node.step) if slice_node.step else ""
                 index_repr = f"{lower}:{upper}:{step}".rstrip(":")
            # Fallback for ast.Index which wraps the actual slice value in older Python versions
            elif hasattr(slice_node, 'value'): 
                index_value_node = getattr(slice_node, 'value')
                if isinstance(index_value_node, ast.Constant): index_repr = repr(index_value_node.value)
                elif isinstance(index_value_node, ast.Name): index_repr = index_value_node.id
                # Could add more complex slice representations here if needed
            return f"{base}[{index_repr}]" if base else f"[{index_repr}]"
        if isinstance(node, ast.Call):
             base = _get_full_name_str(node.func)
             return f"{base}()" if base else "()" 
        if isinstance(node, ast.Constant): return repr(node.value)
        return None 
    def _get_source_object_str(node: ast.AST) -> Optional[str]: # Included for completeness
        if isinstance(node, ast.Attribute): return _get_full_name_str(node.value)
        if isinstance(node, ast.Call): return _get_full_name_str(node.func) 
        if isinstance(node, ast.Subscript): return _get_full_name_str(node.value)
        return None
    def _extract_type_names_from_annotation(annotation_node: Optional[ast.AST]) -> Set[str]: # Included for completeness
        names: Set[str] = set()
        if not annotation_node:
            return names
        nodes_to_visit = [annotation_node]
        while nodes_to_visit:
            node = nodes_to_visit.pop(0)
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                full_name = _get_full_name_str(node) 
                if full_name:
                    names.add(full_name)
            elif isinstance(node, ast.Subscript): 
                if node.value: 
                    nodes_to_visit.append(node.value)
                current_slice = node.slice
                # For Python < 3.9, slice is often ast.Index(value=actual_slice_node)
                if hasattr(current_slice, 'value') and not isinstance(current_slice, (ast.Name, ast.Attribute, ast.Tuple, ast.Constant, ast.BinOp)):
                    current_slice = getattr(current_slice, 'value')
                if isinstance(current_slice, (ast.Name, ast.Attribute, ast.Constant, ast.BinOp)): 
                    nodes_to_visit.append(current_slice)
                elif isinstance(current_slice, ast.Tuple): # e.g., (str, int) in Dict[str, int]
                    for elt in current_slice.elts:
                        nodes_to_visit.append(elt)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str): # Forward reference: 'MyClass'
                names.add(node.value)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr): # For X | Y syntax (Python 3.10+)
                nodes_to_visit.append(node.left)
                nodes_to_visit.append(node.right)
        return names

    result.setdefault("_ast_tree", None) # Initialize key in result
    tree_obj_for_debug: Optional[ast.AST] = None 

    try:
        tree = ast.parse(content, filename=file_path)
        result["_ast_tree"] = tree
        tree_obj_for_debug = tree 
        
        logger.debug(f"DEBUG DA: Parsed {file_path}. AST tree assigned to result['_ast_tree']. Type: {type(result['_ast_tree'])}")
        
        for node_with_parent in ast.walk(tree):
            for child in ast.iter_child_nodes(node_with_parent):
                setattr(child, '_parent', node_with_parent)
        logger.debug(f"DEBUG DA: Parent pointers added for {file_path}.")
        
        # Pass 1: Populate top-level definitions
        for node in tree.body: 
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                 module_name = node.module or ""
                 relative_prefix = "." * node.level
                 full_import_source = f"{relative_prefix}{module_name}"
                 result["imports"].append(full_import_source)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_data = {"name": node.name, "line": node.lineno}
                if isinstance(node, ast.AsyncFunctionDef): func_data["async"] = True
                # Avoid duplicates if somehow processed differently (though tree.body is one pass)
                if not any(f["name"] == node.name and f["line"] == node.lineno for f in result["functions"]):
                    result["functions"].append(func_data)
            elif isinstance(node, ast.ClassDef):
                # Add TOP-LEVEL classes to result["classes"]
                if not any(c["name"] == node.name and c["line"] == node.lineno for c in result["classes"]):
                    result["classes"].append({ "name": node.name, "line": node.lineno })
                # Top-level class decorators captured in ast.walk pass
            elif isinstance(node, ast.Assign): 
                for target in node.targets:
                    if isinstance(target, ast.Name): # Simple assignment: MY_VAR = 1
                        result["globals_defined"].append({"name": target.id, "line": node.lineno})
            elif isinstance(node, ast.AnnAssign): 
                if isinstance(node.target, ast.Name): # MY_VAR: int = 1
                    result["globals_defined"].append({"name": node.target.id, "line": node.lineno, "annotated": True})

        logger.debug(f"DEBUG DA: tree.body processed for {file_path}.")
        
        # Pass 2: ast.walk for detailed analysis
        for node in ast.walk(tree):
            # Decorators (for all functions/classes, top-level or nested)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parent = getattr(node, '_parent', None)
                target_type = "unknown"
                is_top_level = parent is tree
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    target_type = "function" if is_top_level else ("method" if isinstance(parent, ast.ClassDef) else "nested_function")
                elif isinstance(node, ast.ClassDef):
                    target_type = "class" if is_top_level else "nested_class"
                for dec_node in node.decorator_list:
                    dec_name = _get_full_name_str(dec_node)
                    if dec_name:
                        result["decorators_used"].append({
                            "name": dec_name, "target_type": target_type,
                            "target_name": node.name, "line": dec_node.lineno
                        })
            # Type References
            if isinstance(node, ast.AnnAssign): 
                if node.annotation:
                    target_name_val = _get_full_name_str(node.target) 
                    context = "variable_annotation" 
                    parent = getattr(node, '_parent', None)
                    if parent is tree: context = "global_variable_annotation"
                    elif isinstance(parent, ast.ClassDef): context = "class_variable_annotation"
                    elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)): context = "local_variable_annotation"
                    for type_name_str in _extract_type_names_from_annotation(node.annotation):
                        result["type_references"].append({
                            "type_name_str": type_name_str, "context": context,
                            "target_name": target_name_val if target_name_val else "_unknown_target_",
                            "line": node.lineno
                        })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_top_level_func = any(item is node for item in tree.body)
                if not is_top_level_func: 
                    for dec_node in node.decorator_list:
                        dec_name = _get_full_name_str(dec_node)
                        if dec_name:
                            result["decorators_used"].append({
                                "name": dec_name, "target_type": "method" if isinstance(getattr(node, '_parent', None), ast.ClassDef) else "nested_function",
                                "target_name": node.name, "line": dec_node.lineno
                            })
                for arg_node_type in [node.args.args, node.args.posonlyargs, node.args.kwonlyargs]:
                    for arg in arg_node_type:
                        if arg.annotation:
                            for type_name_str in _extract_type_names_from_annotation(arg.annotation):
                                result["type_references"].append({
                                    "type_name_str": type_name_str, "context": "arg_annotation",
                                    "function_name": node.name, "target_name": arg.arg, 
                                    "line": getattr(arg.annotation, 'lineno', node.lineno) 
                                })
                if node.args.vararg and node.args.vararg.annotation: 
                     for type_name_str in _extract_type_names_from_annotation(node.args.vararg.annotation):
                        result["type_references"].append({
                            "type_name_str": type_name_str, "context": "vararg_annotation",
                            "function_name": node.name, "target_name": node.args.vararg.arg,
                            "line": getattr(node.args.vararg.annotation, 'lineno', node.lineno)
                        })
                if node.args.kwarg and node.args.kwarg.annotation: 
                     for type_name_str in _extract_type_names_from_annotation(node.args.kwarg.annotation):
                        result["type_references"].append({
                            "type_name_str": type_name_str, "context": "kwarg_annotation",
                            "function_name": node.name, "target_name": node.args.kwarg.arg,
                            "line": getattr(node.args.kwarg.annotation, 'lineno', node.lineno)
                        })
                if node.returns:
                    for type_name_str in _extract_type_names_from_annotation(node.returns):
                        result["type_references"].append({
                            "type_name_str": type_name_str, "context": "return_annotation",
                            "function_name": node.name,
                            "line": getattr(node.returns, 'lineno', node.lineno)
                        })
            # Inheritance
            elif isinstance(node, ast.ClassDef):
                is_top_level_class = any(item is node for item in tree.body)
                if not is_top_level_class: 
                    for dec_node in node.decorator_list:
                        dec_name = _get_full_name_str(dec_node)
                        if dec_name:
                            result["decorators_used"].append({
                                "name": dec_name, "target_type": "nested_class",
                                "target_name": node.name, "line": dec_node.lineno
                            })
                for base in node.bases:
                    base_full_name = _get_full_name_str(base)
                    if base_full_name: 
                        # Avoid duplicates if inheritance was somehow processed differently before
                        if not any(inh['class_name'] == node.name and inh['base_class_name'] == base_full_name for inh in result["inheritance"]):
                            result["inheritance"].append({"class_name": node.name, "base_class_name": base_full_name, "potential_source": base_full_name, "line": getattr(base, 'lineno', node.lineno)})
            # Calls
            elif isinstance(node, ast.Call):
                target_full_name = _get_full_name_str(node.func)
                potential_source = _get_source_object_str(node.func)
                if target_full_name: 
                    result["calls"].append({"target_name": target_full_name, "potential_source": potential_source, "line": node.lineno})
            # Attribute Accesses
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                 attribute_name = node.attr
                 potential_source = _get_full_name_str(node.value)
                 if potential_source: 
                     result["attribute_accesses"].append({"target_name": attribute_name, "potential_source": potential_source, "line": node.lineno})
            # Exceptions Handled
            elif isinstance(node, ast.ExceptHandler):
                if node.type: # node.type can be None for a bare except
                    exception_type_name = _get_full_name_str(node.type)
                    if exception_type_name:
                        result["exceptions_handled"].append({
                            "type_name_str": exception_type_name,
                            "line": node.lineno
                        })
            # With Contexts
            elif isinstance(node, ast.With):
                for item in node.items:
                    context_expr_name = _get_full_name_str(item.context_expr)
                    if context_expr_name:
                        result["with_contexts_used"].append({
                            "context_expr_str": context_expr_name,
                            "line": item.context_expr.lineno
                        })
        
        logger.debug(f"DEBUG DA: Second ast.walk completed for {file_path}.")
            
    except SyntaxError as e: 
        logger.warning(f"AST Syntax Error in {file_path}: {e}. Analysis may be incomplete.")
        result["error"] = f"AST Syntax Error: {e}"
        # result["_ast_tree"] remains None if parsing failed, or holds tree if parsing succeeded but later step failed
    except Exception as e: 
        # Log with full traceback for unexpected errors during AST processing
        logger.exception(f"Unexpected AST analysis error IN TRY BLOCK for {file_path}: {e}")
        result["error"] = f"Unexpected AST analysis error: {e}"
    
    is_tree_none_at_end = result.get("_ast_tree") is None
    logger.debug(f"DEBUG DA: End of _analyze_python_file for {file_path}. result['_ast_tree'] is None: {is_tree_none_at_end}. tree_obj_for_debug type: {type(tree_obj_for_debug)}. Keys: {list(result.keys())}")

def _analyze_javascript_file(file_path: str, content: str, result: Dict[str, Any]) -> None:
    # Initialize/ensure keys exist
    result.setdefault("imports", [])
    result.setdefault("functions", [])
    result.setdefault("classes", [])
    result.setdefault("exports", []) 

    import_matches = JAVASCRIPT_IMPORT_PATTERN.finditer(content)
    result["imports"] = [m.group(1) or m.group(2) or m.group(3) for m in import_matches if m and (m.group(1) or m.group(2) or m.group(3))]
    
    try: 
        # Basic function and class detection (already present)
        func_pattern = re.compile(r'(?:async\s+)?function\s*\*?\s*([a-zA-Z_$][\w$]*)\s*\([^)]*\)')
        arrow_pattern = re.compile(r'(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>')
        class_pattern = re.compile(r'class\s+([a-zA-Z_$][\w$]*)')
        for match in func_pattern.finditer(content): 
            result["functions"].append({"name": match.group(1), "line": content[:match.start()].count('\n') + 1})
        for match in arrow_pattern.finditer(content): 
            result["functions"].append({"name": match.group(1), "line": content[:match.start()].count('\n') + 1, "type": "arrow"})
        for match in class_pattern.finditer(content): 
            result["classes"].append({"name": match.group(1), "line": content[:match.start()].count('\n') + 1})

        # NEW: Basic regex for exports (can be improved with more specific patterns)
        # export function foo() {}  OR export async function foo() {}
        export_func_pattern = re.compile(r'export\s+(?:async\s+)?function\s*\*?\s*([a-zA-Z_$][\w$]*)')
        # export class Foo {}
        export_class_pattern = re.compile(r'export\s+class\s+([a-zA-Z_$][\w$]*)')
        # export const foo = ..., export let foo = ..., export var foo = ...
        export_var_pattern = re.compile(r'export\s+(?:const|let|var)\s+([a-zA-Z_$][\w$]*)')
        # export default function foo() {} OR export default function() {}
        export_default_func_pattern = re.compile(r'export\s+default\s+(?:async\s+)?function\s*\*?\s*([a-zA-Z_$][\w$]*)?')
        # export default class Foo {} OR export default class {}
        export_default_class_pattern = re.compile(r'export\s+default\s+class\s+([a-zA-Z_$][\w$]*)?')
        # export default foo; (where foo is already defined)
        export_default_identifier_pattern = re.compile(r'export\s+default\s+([a-zA-Z_$][\w$]*);')
        # --- ADDED: Regex for export { name1, name2 as alias } ---
        export_named_block_pattern = re.compile(r'export\s*{\s*([^}]+)\s*}')
        # ---

        for match in export_func_pattern.finditer(content):
            result["exports"].append({"name": match.group(1), "type": "function", "line": content[:match.start()].count('\n') + 1})
        for match in export_class_pattern.finditer(content):
            result["exports"].append({"name": match.group(1), "type": "class", "line": content[:match.start()].count('\n') + 1})
        for match in export_var_pattern.finditer(content):
            result["exports"].append({"name": match.group(1), "type": "variable", "line": content[:match.start()].count('\n') + 1})
        for match in export_default_func_pattern.finditer(content):
            name = match.group(1) or "_default_function" # Handle anonymous default function
            result["exports"].append({"name": name, "type": "function", "is_default": True, "line": content[:match.start()].count('\n') + 1})
        for match in export_default_class_pattern.finditer(content):
            name = match.group(1) or "_default_class" # Handle anonymous default class
            result["exports"].append({"name": name, "type": "class", "is_default": True, "line": content[:match.start()].count('\n') + 1})
        for match in export_default_identifier_pattern.finditer(content):
            result["exports"].append({"name": match.group(1), "type": "identifier", "is_default": True, "line": content[:match.start()].count('\n') + 1})
        
        # --- ADDED: Processing for export_named_block_pattern ---
        for match in export_named_block_pattern.finditer(content):
            items_str = match.group(1) # Content inside {}
            line_num = content[:match.start()].count('\n') + 1
            # Split by comma, then process each item for potential "as" alias
            individual_exports = [item.strip() for item in items_str.split(',')]
            for export_item_str in individual_exports:
                if not export_item_str: continue
                name_parts = [p.strip() for p in export_item_str.split(' as ')]
                original_name = name_parts[0]
                exported_name = name_parts[-1] # If "as" is used, this is the alias; otherwise, same as original_name
                result["exports"].append({
                    "name": exported_name, 
                    "original_name": original_name if len(name_parts) > 1 else None,
                    "type": "named_block_item", 
                    "line": line_num
                })
        # ---
    except Exception as e: logger.warning(f"Regex error during JS analysis in {file_path}: {e}")

def _analyze_markdown_file(file_path: str, content: str, result: Dict[str, Any]) -> None:
    """Analyzes Markdown file content using regex."""
    result["links"] = []; result["code_blocks"] = []
    try: 
        for match in MARKDOWN_LINK_PATTERN.finditer(content):
            url = match.group(1);
            if url and not url.startswith(('#', 'http:', 'https:', 'mailto:', 'tel:')): result["links"].append({"url": url, "line": content[:match.start()].count('\n') + 1})
    except Exception as e: logger.warning(f"Regex error during MD link analysis in {file_path}: {e}")
    try: 
        code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
        for match in code_block_pattern.finditer(content):
             lang = match.group(1) or "text"; 
             result["code_blocks"].append({"language": lang.lower(), "line": content[:match.start()].count('\n') + 1})
    except Exception as e: logger.warning(f"Regex error during MD code block analysis in {file_path}: {e}")

def _analyze_html_file(file_path: str, content: str, result: Dict[str, Any]) -> None:
    """Analyzes HTML file content using regex."""
    result["links"] = [] # For <a> tags
    result["scripts"] = [] # For <script src="...">
    result["stylesheets"] = [] # For <link rel="stylesheet" href="...">
    result["images"] = [] # For <img src="...">

    def find_resources(pattern, type_list_name): # Pass name of list in result
        type_list = result[type_list_name]
        try:
            for match in pattern.finditer(content):
                url = match.group("url")
                if url and not url.startswith(('#', 'http:', 'https:', 'mailto:', 'tel:', 'data:')): type_list.append({"url": url, "line": content[:match.start()].count('\n') + 1})
        except Exception as e: logger.warning(f"Regex error during HTML {type_list_name} analysis in {file_path}: {e}")
    find_resources(HTML_A_HREF_PATTERN, "links"); find_resources(HTML_SCRIPT_SRC_PATTERN, "scripts"); find_resources(HTML_IMG_SRC_PATTERN, "images")
    try: 
        link_tag_pattern = re.compile(r'<link([^>]+)>', re.IGNORECASE); href_pattern = re.compile(r'href=(["\'])(?P<url>[^"\']+?)\1', re.IGNORECASE); rel_pattern = re.compile(r'rel=(["\'])stylesheet\1', re.IGNORECASE)
        for link_match in link_tag_pattern.finditer(content):
            tag_content = link_match.group(1); href_match = href_pattern.search(tag_content); rel_match = rel_pattern.search(tag_content)
            if href_match and rel_match:
                url = href_match.group("url")
                if url and not url.startswith(('#', 'http:', 'https:', 'mailto:', 'tel:', 'data:')): result["stylesheets"].append({"url": url, "line": content[:link_match.start()].count('\n') + 1})
    except Exception as e: logger.warning(f"Regex error during HTML stylesheet analysis in {file_path}: {e}")

def _analyze_css_file(file_path: str, content: str, result: Dict[str, Any]) -> None:
    """Analyzes CSS file content using regex."""
    result["imports"] = [] # For @import rules

    try:
        for match in CSS_IMPORT_PATTERN.finditer(content):
             url = match.group(1)
             if url and not url.startswith(('#', 'http:', 'https:', 'data:')): result["imports"].append({"url": url.strip(), "line": content[:match.start()].count('\n') + 1})
    except Exception as e: logger.warning(f"Regex error during CSS import analysis in {file_path}: {e}")

# --- End of dependency_analyzer.py ---