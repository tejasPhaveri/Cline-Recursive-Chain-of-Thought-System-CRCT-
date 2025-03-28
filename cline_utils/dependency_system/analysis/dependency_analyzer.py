"""
Analysis module for dependency detection and code analysis.
Parses files to identify imports, function calls, and other dependency indicators.
"""

import os
import ast
import re
import logging
from typing import Dict, List, Tuple, Set, Optional, Any
import importlib.util
import uuid

# Import only from utils, core, and io layers
from cline_utils.dependency_system.utils.path_utils import normalize_path, is_subpath
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, invalidate_dependent_entries
from cline_utils.dependency_system.core.key_manager import get_key_from_path
from cline_utils.dependency_system.io.tracker_io import read_tracker_file

logger = logging.getLogger(__name__)

# Regular expressions for dependency detection
PYTHON_IMPORT_PATTERN = re.compile(
    r'(?:from\s+([.\w]+(?:\s*\.\s*[.\w]+)*)\s+import)|(?:import\s+([.\w]+(?:\s*,\s*[.\w]+)*))',
    re.MULTILINE
)
JAVASCRIPT_IMPORT_PATTERN = re.compile(
    r'(?:import\s+.*\s+from\s+["\']([^"\']+)["\'])|(?:require\s*\(\s*["\']([^"\']+)["\']\s*\))|(?:import\s*\(\s*["\']([^"\']+)["\']\s*\))'
)
MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
HTML_LINK_PATTERN = re.compile(r'<a\s+(?:[^>]*?\s+)?href=(["\'])([^"\']+)\1')
CSS_IMPORT_PATTERN = re.compile(r'@import\s+(?:url\s*\(\s*)?["\']?([^"\')\s]+)["\']?(?:\s*\))?')

@cached('analysis', key_func=lambda file_path: f"file_type:{file_path}:{os.path.getmtime(file_path) if os.path.exists(file_path) else str(uuid.uuid4())}")
def get_file_type(file_path: str) -> str:
    """
    Determines the file type based on its extension.
    
    Args:
        file_path: The path to the file.
    Returns:
        The file type as a string (e.g., "py", "js", "md", "generic").
    """
    if not isinstance(file_path, str):
        logger.error(f"Invalid file_path type: {type(file_path)}")
        return "generic"
    _, ext = os.path.splitext(file_path)
    ext = ext.lower().lstrip('.')
    
    return {
        "py": "py",
        "js": "js", "ts": "js", "jsx": "js", "tsx": "js",
        "md": "md", "rst": "md",
        "html": "html", "htm": "html",
        "css": "css"
    }.get(ext, "generic")

@cached('analysis', 
        key_func=lambda file_path: f"analyze_file:{file_path}:{os.path.getmtime(file_path) if os.path.exists(file_path) else str(uuid.uuid4())}")
def analyze_file(file_path: str) -> Dict[str, Any]:
    """
    Analyzes a file to identify dependencies, imports, and other metadata.
    
    Args:
        file_path: Path to the file to analyze
    Returns:
        Dictionary containing analysis results
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        logger.warning(f"File not found or not a file: {file_path}")
        return {"error": "File not found or not a file"}
    
    try:
        file_type = get_file_type(file_path)
        
        analysis_result = {
            "file_path": file_path,
            "file_type": file_type,
            "imports": [],
            "functions": [],
            "classes": [],
            "references": [],
            "links": []
        }
        
        # Analyze based on file type
        if file_type == "py":
            _analyze_python_file(file_path, analysis_result)
        elif file_type == "js":
            _analyze_javascript_file(file_path, analysis_result)
        elif file_type == "md":
            _analyze_markdown_file(file_path, analysis_result)
        elif file_type == "html":
            _analyze_html_file(file_path, analysis_result)
        elif file_type == "css":
            _analyze_css_file(file_path, analysis_result)
        
        return analysis_result
    except FileNotFoundError:
        logger.warning(f"File not found during analysis: {file_path}")
        return {"error": "File not found"}
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
        return {"error": "Encoding error"}
    except Exception as e:
        logger.exception(f"Unexpected error analyzing {file_path}: {str(e)}")
        return {"error": str(e)}

def _analyze_python_file(file_path: str, result: Dict[str, Any]) -> None:
    """
    Analyzes a Python file for imports, functions, classes, and references.
    
    Args:
        file_path: Path to the Python file
        result: Dictionary to store analysis results (modified in-place)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract imports using regex
        import_matches = PYTHON_IMPORT_PATTERN.findall(content)
        result["imports"] = [match[0] or match[1] for match in import_matches if match[0] or match[1]]
        
        # Use AST for detailed analysis
        try:
            tree = ast.parse(content, filename=file_path)
            # Extract functions
            result["functions"] = [
                {"name": node.name, "args": [arg.arg for arg in node.args.args],
                 "line": node.lineno}
                for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            # Extract classes
            result["classes"] = [
                {"name": node.name, "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                 "line": node.lineno}
                for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            ]
            # Extract references (variables, attributes)
            result["references"] = [
                {"name": node.id, "line": node.lineno}
                for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            ]
        except SyntaxError:
            logger.warning(f"Syntax error in {file_path}, using regex only")
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing Python file {file_path}: {str(e)}")

def _analyze_javascript_file(file_path: str, result: Dict[str, Any]) -> None:
    """
    Analyzes a JavaScript file for imports and references.
    
    Args:
        file_path: Path to the JavaScript file
        result: Dictionary to store analysis results (modified in-place)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract imports
        import_matches = JAVASCRIPT_IMPORT_PATTERN.findall(content)
        result["imports"] = [match[0] or match[1] or match[2] for match in import_matches if any(match)]
        
        # Extract functions
        function_pattern = re.compile(r'(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)\s*\(([^)]*)\)')
        function_matches = function_pattern.findall(content)
        result["functions"] = [
            {"name": name, "args": [arg.strip() for arg in args.split(',') if arg.strip()],
             "line": content[:content.find(f"function {name}")].count('\n') + 1}
            for name, args in function_matches
        ]
        
        # Extract arrow functions
        arrow_pattern = re.compile(r'(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:\(([^)]*)\)|([a-zA-Z_$][\w$]*))\s*=>')
        arrow_matches = arrow_pattern.findall(content)
        for name, args1, args2 in arrow_matches:
            args = args1 or args2
            result["functions"].append({
                "name": name,
                "args": [arg.strip() for arg in args.split(',') if arg.strip()],
                "line": content[:content.find(name)].count('\n') + 1,
                "type": "arrow"
            })
        
        # Extract classes
        class_pattern = re.compile(r'class\s+([a-zA-Z_$][\w$]*)')
        class_matches = class_pattern.findall(content)
        result["classes"] = [
            {"name": name, "line": content[:content.find(f"class {name}")].count('\n') + 1}
            for name in class_matches
        ]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing JavaScript file {file_path}: {str(e)}")

def _analyze_markdown_file(file_path: str, result: Dict[str, Any]) -> None:
    """
    Analyzes a Markdown file for links and references.
    
    Args:
        file_path: Path to the Markdown file
        result: Dictionary to store analysis results (modified in-place)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract links
        link_matches = MARKDOWN_LINK_PATTERN.findall(content)
        result["links"] = [
            {"text": text, "url": url,
             "line": content[:content.find(f"[{text}]({url})")].count('\n') + 1}
            for text, url in link_matches
        ]
        
        # Extract code blocks
        code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
        code_blocks = code_block_pattern.findall(content)
        result["code_blocks"] = [
            {"language": lang or "unspecified", "content": block.strip(),
             "line": content[:content.find(f"```{lang or ''}")].count('\n') + 1}
            for lang, block in code_blocks
        ]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing Markdown file {file_path}: {str(e)}")

def _analyze_html_file(file_path: str, result: Dict[str, Any]) -> None:
    """
    Analyzes an HTML file for links, scripts, and stylesheet references.
    
    Args:
        file_path: Path to the HTML file
        result: Dictionary to store analysis results (modified in-place)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract links
        link_matches = HTML_LINK_PATTERN.findall(content)
        result["links"] = [
            {"url": url,
             "line": content[:content.find(f'href={quote}{url}{quote}')].count('\n') + 1 if content.find(f'href={quote}{url}{quote}') != -1 else 1}
            for quote, url in link_matches
        ]
        
        # Extract script tags
        script_pattern = re.compile(r'<script\s+(?:[^>]*?\s+)?src=(["\'])([^"\']+)\1')
        script_matches = script_pattern.findall(content)
        result["scripts"] = [
            {"src": src,
             "line": content[:content.find(f'src={quote}{src}{quote}')].count('\n') + 1 if content.find(f'src={quote}{src}{quote}') != -1 else 1}
            for quote, src in script_matches
        ]
        
        # Extract stylesheet links
        style_pattern = re.compile(r'<link\s+(?:[^>]*?\s+)?href=(["\'])([^"\']+)\1[^>]*?rel=(["\'])stylesheet\3')
        style_matches = style_pattern.findall(content)
        result["stylesheets"] = [
            {"href": href,
             "line": content[:content.find(f'href={quote1}{href}{quote1}')].count('\n') + 1 if content.find(f'href={quote1}{href}{quote1}') != -1 else 1}
            for quote1, href, quote2 in style_matches
        ]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing HTML file {file_path}: {str(e)}")

def _analyze_css_file(file_path: str, result: Dict[str, Any]) -> None:
    """
    Analyzes a CSS file for imports and references.
    
    Args:
        file_path: Path to the CSS file
        result: Dictionary to store analysis results (modified in-place)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract imports
        import_matches = CSS_IMPORT_PATTERN.findall(content)
        result["imports"] = [
            {"url": url,
             "line": content[:content.find(url)].count('\n') + 1 if content.find(url) != -1 else 1}
            for url in import_matches
        ]
        
        # Extract selectors
        selector_pattern = re.compile(r'([.#][\w-]+)\s*\{')
        selector_matches = selector_pattern.findall(content)
        result["selectors"] = [
            {"selector": selector,
             "line": content[:content.find(f'{selector} {{')].count('\n') + 1 if content.find(f'{selector} {{') != -1 else 1}
            for selector in selector_matches
        ]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing CSS file {file_path}: {str(e)}")

@cached('analysis', 
        key_func=lambda project_dir, tracker_file=None: 
        f"analyze_project:{project_dir}:{os.path.getmtime(tracker_file) if tracker_file and os.path.exists(tracker_file) else str(uuid.uuid4())}")
def analyze_project(project_dir: str, tracker_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyzes all files in a project to identify dependencies between them.
    
    Args:
        project_dir: Path to the project directory
        tracker_file: Optional path to a tracker file with existing key mappings
    Returns:
        Dictionary containing project-wide analysis results
    """
    logger.info(f"Analyzing project in directory: {project_dir}")
    
    if not os.path.isdir(project_dir):
        logger.error(f"Invalid project directory: {project_dir}")
        return {"error": "Invalid project directory"}
    
    config = ConfigManager()
    excluded_dirs = set(config.get_excluded_dirs())
    excluded_extensions = set(config.get_excluded_extensions())
    
    # Read key mapping from tracker if provided
    key_map = {}
    if tracker_file and os.path.exists(tracker_file):
        tracker_data = read_tracker_file(tracker_file)
        key_map = tracker_data.get("keys", {})
    
    # Collect all files
    all_files = []
    for root, dirs, files in os.walk(project_dir):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith('.')]
        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lstrip('.') not in excluded_extensions:
                all_files.append(os.path.join(root, file))
    
    # Analyze each file
    file_analyses = {}
    for file_path in all_files:
        rel_path = os.path.relpath(file_path, project_dir)
        logger.debug(f"Analyzing file: {rel_path}")
        analysis = analyze_file(file_path)
        if "error" not in analysis:
            file_analyses[file_path] = analysis
    
    # Identify dependencies between files
    dependencies = {}
    for source_path, source_analysis in file_analyses.items():
        source_key = get_key_from_path(source_path, key_map)
        if not source_key:
            continue
        
        deps = _identify_dependencies(source_path, source_analysis, file_analyses, project_dir)
        key_deps = [(get_key_from_path(dep_path, key_map), dep_type) 
                   for dep_path, dep_type in deps 
                   if get_key_from_path(dep_path, key_map) and get_key_from_path(dep_path, key_map) != source_key]
        if key_deps:
            dependencies[source_key] = key_deps
    
    return {
        "project_dir": project_dir,
        "file_count": len(file_analyses),
        "dependencies": dependencies
    }

def _identify_dependencies(source_path: str, source_analysis: Dict[str, Any],
                          file_analyses: Dict[str, Dict[str, Any]], 
                          project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from a source file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    file_type = source_analysis.get("file_type", "generic")
    
    if file_type == "py":
        dependencies.extend(_identify_python_dependencies(source_path, source_analysis, file_analyses, project_dir))
    elif file_type == "js":
        dependencies.extend(_identify_javascript_dependencies(source_path, source_analysis, file_analyses, project_dir))
    elif file_type == "md":
        dependencies.extend(_identify_markdown_dependencies(source_path, source_analysis, file_analyses, project_dir))
    elif file_type == "html":
        dependencies.extend(_identify_html_dependencies(source_path, source_analysis, file_analyses, project_dir))
    elif file_type == "css":
        dependencies.extend(_identify_css_dependencies(source_path, source_analysis, file_analyses, project_dir))
    
    # Optional directory-based dependencies (configurable)
    config = ConfigManager()
    if config.get("include_directory_dependencies", default=False):
        source_dir = os.path.dirname(source_path)
        for target_path in file_analyses:
            if source_path != target_path:
                target_dir = os.path.dirname(target_path)
                if source_dir == target_dir:
                    dependencies.append((target_path, "-"))  # Weak dependency
                elif is_subpath(target_dir, source_dir) and target_dir != source_dir:
                    dependencies.append((target_path, "<"))  # Strong parent dependency
                elif is_subpath(source_dir, target_dir) and target_dir != source_dir:
                    dependencies.append((target_path, ">"))  # Strong child dependency
    
    return list(set(dependencies))  # Remove duplicates

def _identify_python_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                file_analyses: Dict[str, Dict[str, Any]], 
                                project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from a Python file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    imports = source_analysis.get("imports", [])
    source_dir = os.path.dirname(source_path)
    
    for import_name in imports:
        # Convert import to possible file paths
        possible_paths = _convert_python_import_to_paths(import_name, source_dir, project_dir)
        # Check if any of the possible paths exist in the analyzed files
        for path in possible_paths:
            normalized_path = normalize_path(path)
            for target_path in file_analyses:
                if normalized_path == normalize_path(target_path):
                    dependencies.append((target_path, ">"))  # Strong dependency
                    break
    return dependencies

def _convert_python_import_to_paths(import_name: str, source_dir: str, project_dir: str) -> List[str]:
    """
    Converts a Python import statement to potential file paths.
    
    Args:
        import_name: The import name (e.g., 'os.path', 'module.submodule')
        source_dir: Directory of the source file
        project_dir: Root project directory
    Returns:
        List of potential file paths that could match the import
    """
    potential_paths = []
    import_parts = import_name.split('.')
    
    # Handle relative imports
    if import_name.startswith('.'):
        level = import_name.count('.') - 1
        import_path = import_name[level + 1:].replace('.', os.sep)
        current_dir = source_dir
        for _ in range(level):
            current_dir = os.path.dirname(current_dir)
            if not current_dir:  # Prevent going beyond root
                break
        potential_paths.append(os.path.join(current_dir, f"{import_path}.py"))
        potential_paths.append(os.path.join(current_dir, import_path, "__init__.py"))
    else:
        import_path = import_name.replace('.', os.sep)
        potential_paths.extend([
            os.path.join(source_dir, f"{import_path}.py"),
            os.path.join(source_dir, import_path, "__init__.py"),
            os.path.join(project_dir, f"{import_path}.py"),
            os.path.join(project_dir, import_path, "__init__.py")
        ])
    
    # Filter out external modules
    try:
        spec = importlib.util.find_spec(import_name)
        if spec and spec.origin and not spec.origin.startswith(project_dir):
            return []
    except (ImportError, AttributeError):
        pass
    
    return potential_paths

def _identify_javascript_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                    file_analyses: Dict[str, Dict[str, Any]], 
                                    project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from a JavaScript file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    imports = source_analysis.get("imports", [])
    source_dir = os.path.dirname(source_path)
    
    for import_name in imports:
        # Skip external modules
        if (import_name.startswith('http://') or import_name.startswith('https://') or 
            not (import_name.startswith('./') or import_name.startswith('../') or import_name.startswith('/'))):
            continue
        
        import_path = import_name
        if import_name.startswith('./'):
            import_path = import_name[2:]
        elif import_name.startswith('../'):
            level = import_name.count('../')
            import_path = import_name[level * 3:]
            current_dir = source_dir
            for _ in range(level):
                current_dir = os.path.dirname(current_dir)
            import_path = os.path.join(current_dir, import_path)
        elif import_name.startswith('/'):
            import_path = os.path.join(project_dir, import_name[1:])
        else:
            import_path = os.path.join(source_dir, import_name)
        
        if not os.path.splitext(import_path)[1]:
            for ext in ['.js', '.jsx', '.ts', '.tsx']:
                possible_path = f"{import_path}{ext}"
                for target_path in file_analyses:
                    if normalize_path(possible_path) == normalize_path(target_path):
                        dependencies.append((target_path, ">"))
                        break
                else:
                    index_path = os.path.join(import_path, f"index{ext}")
                    for target_path in file_analyses:
                        if normalize_path(index_path) == normalize_path(target_path):
                            dependencies.append((target_path, ">"))
                            break
        else:
            for target_path in file_analyses:
                if normalize_path(import_path) == normalize_path(target_path):
                    dependencies.append((target_path, ">"))
                    break
    
    return dependencies

def _identify_markdown_dependencies(source_path: str, source_analysis: Dict[str, Any],
                                  file_analyses: Dict[str, Dict[str, Any]], 
                                  project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from a Markdown file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    links = source_analysis.get("links", [])
    source_dir = os.path.dirname(source_path)
    
    for link in links:
        url = link.get("url", "")
        if (url.startswith('http://') or url.startswith('https://') or 
            url.startswith('#') or url.startswith('mailto:')):
            continue
        
        link_path = url[2:] if url.startswith('./') else url
        link_path = os.path.join(project_dir, link_path[1:]) if link_path.startswith('/') else os.path.join(source_dir, link_path)
        link_path = link_path.split('?')[0].split('#')[0]  # Remove query and fragment
        
        for target_path in file_analyses:
            if normalize_path(link_path) == normalize_path(target_path):
                dependencies.append((target_path, ">"))
                break
    
    return dependencies

def _identify_html_dependencies(source_path: str, source_analysis: Dict[str, Any],
                              file_analyses: Dict[str, Dict[str, Any]], 
                              project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from an HTML file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    links = source_analysis.get("links", [])
    scripts = source_analysis.get("scripts", [])
    stylesheets = source_analysis.get("stylesheets", [])
    source_dir = os.path.dirname(source_path)
    
    for link in links + [{"url": s["src"]} for s in scripts] + [{"url": s["href"]} for s in stylesheets]:
        url = link.get("url", "")
        if (url.startswith('http://') or url.startswith('https://') or 
            url.startswith('#') or url.startswith('mailto:')):
            continue
        
        link_path = _resolve_relative_path(url, source_dir, project_dir)
        for target_path in file_analyses:
            if normalize_path(link_path) == normalize_path(target_path):
                dependencies.append((target_path, ">"))
                break
    
    return dependencies

def _identify_css_dependencies(source_path: str, source_analysis: Dict[str, Any],
                             file_analyses: Dict[str, Dict[str, Any]], 
                             project_dir: str) -> List[Tuple[str, str]]:
    """
    Identifies dependencies from a CSS file to other files in the project.
    
    Args:
        source_path: Path to the source file
        source_analysis: Analysis results for the source file
        file_analyses: Dictionary of file paths to their analysis results
        project_dir: Root project directory path
    Returns:
        List of tuples (dependent_file_path, dependency_type)
    """
    dependencies = []
    imports = source_analysis.get("imports", [])
    source_dir = os.path.dirname(source_path)
    
    for import_item in imports:
        url = import_item.get("url", "")
        if url.startswith('http://') or url.startswith('https://'):
            continue
        
        import_path = _resolve_relative_path(url, source_dir, project_dir)
        for target_path in file_analyses:
            if normalize_path(import_path) == normalize_path(target_path):
                dependencies.append((target_path, ">"))
                break
    
    return dependencies

def _resolve_relative_path(path: str, source_dir: str, project_dir: str) -> str:
    """
    Resolves a relative path to an absolute path.
    
    Args:
        path: The relative path
        source_dir: Directory of the source file
        project_dir: Root project directory
    Returns:
        The resolved absolute path
    """
    if path.startswith('./'):
        path = path[2:]
    return os.path.join(project_dir, path[1:]) if path.startswith('/') else os.path.join(source_dir, path)

def extract_function_calls(source_content: str, source_type: str) -> List[str]:
    """
    Extracts function calls from source code.
    
    Args:
        source_content: Source code content
        source_type: Source file type (e.g., 'py', 'js')
    Returns:
        List of function names that are called
    """
    function_calls = []
    
    if source_type == "py":
        try:
            tree = ast.parse(source_content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        function_calls.append(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        function_calls.append(node.func.attr)
        except SyntaxError:
            logger.warning("Syntax error when extracting Python function calls")
    elif source_type == "js":
        func_call_pattern = re.compile(r'(?<!\.)([a-zA-Z_$][\w$]*)\s*\(')
        matches = func_call_pattern.findall(source_content)
        function_calls = [match for match in matches if match not in ('if', 'for', 'while', 'switch', 'catch')]
    
    return list(set(function_calls))

def register_parser(subparsers):
    """Register commands with the argument parser."""
    analyze_file_parser = subparsers.add_parser("analyze-file", help="Analyze a single file for dependencies")
    analyze_file_parser.add_argument("file_path", help="Path to the file to analyze")
    analyze_file_parser.add_argument("--output", help="Path to save the analysis results")
    analyze_file_parser.set_defaults(func=command_handler_analyze_file)
    
    analyze_project_parser = subparsers.add_parser("analyze-project", help="Analyze a project for dependencies")
    analyze_project_parser.add_argument("project_dir", help="Path to the project directory")
    analyze_project_parser.add_argument("--tracker-file", help="Path to the tracker file")
    analyze_project_parser.add_argument("--output", help="Path to save the analysis results")
    analyze_project_parser.set_defaults(func=command_handler_analyze_project)

def command_handler_analyze_file(args):
    """Handle the analyze-file command."""
    import json
    
    try:
        if not os.path.exists(args.file_path):
            print(f"Error: File not found: {args.file_path}")
            return 1
        
        results = analyze_file(args.file_path)
        
        if args.output:
            output_dir = os.path.dirname(args.output)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print(f"Analysis results saved to {args.output}")
        else:
            print(json.dumps(results, indent=2))
        return 0
    except Exception as e:
        print(f"Error analyzing file: {str(e)}")
        return 1

def command_handler_analyze_project(args):
    """Handle the analyze-project command."""
    import json
    
    try:
        if not os.path.exists(args.project_dir):
            print(f"Error: Project directory not found: {args.project_dir}")
            return 1
        
        if args.tracker_file and not os.path.exists(args.tracker_file):
            print(f"Warning: Tracker file not found: {args.tracker_file}")
        
        results = analyze_project(args.project_dir, args.tracker_file)
        
        if args.output:
            output_dir = os.path.dirname(args.output)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print(f"Analysis results saved to {args.output}")
        else:
            print(json.dumps(results, indent=2))
        return 0
    except Exception as e:
        print(f"Error analyzing project: {str(e)}")
        return 1

# End of file