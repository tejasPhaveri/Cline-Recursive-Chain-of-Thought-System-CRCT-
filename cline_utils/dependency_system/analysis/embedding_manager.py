"""
Module for managing embeddings generation and similarity calculations.
Handles embedding creation from project files and cosine similarity between embeddings.
"""

import os
import json
from typing import List, Dict, Optional, Tuple, Any
import numpy as np

# Import only from lower-level modules
from cline_utils.dependency_system.utils.path_utils import normalize_path, is_valid_project_path
from cline_utils.dependency_system.utils.config_manager import ConfigManager
from cline_utils.dependency_system.utils.cache_manager import cached, invalidate_dependent_entries
from cline_utils.dependency_system.core.key_manager import generate_key, validate_key
from cline_utils.dependency_system.io.tracker_io import read_tracker_file, write_tracker_file

import logging
logger = logging.getLogger(__name__)

# Default model configuration
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def generate_embeddings(project_paths: List[str], output_dir: str, force: bool = False) -> Tuple[bool, Dict[str, str]]:
    """
    Generate embeddings for all files in the specified project paths.

    Args:
        project_paths: List of project directory paths
        output_dir: Directory to store embeddings and metadata
        force: If True, regenerate embeddings even if they exist
    Returns:
        Tuple of (success: bool, key_map: Dict[str, str]) where key_map maps keys to file paths
    """
    if not project_paths or not all(is_valid_project_path(p) for p in project_paths):
        logger.error(f"Invalid project paths: {project_paths}")
        return False, {}

    embeddings_dir = os.path.join(output_dir, "embeddings")
    metadata_file = os.path.join(embeddings_dir, "metadata.json")
    os.makedirs(embeddings_dir, exist_ok=True)

    # Check if embeddings exist and skip unless forced
    if not force and os.path.exists(metadata_file) and os.path.isdir(embeddings_dir):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if metadata.get("version") == "1.0" and all(os.path.exists(os.path.join(embeddings_dir, f"{k}.npy")) for k in metadata["keys"]):
                logger.info(f"Embeddings already exist in {embeddings_dir}. Use --force to regenerate.")
                return True, metadata["keys"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted metadata file {metadata_file}: {e}. Regenerating embeddings.")

    # Load model
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(DEFAULT_MODEL_NAME)
    except ImportError as e:
        logger.error(f"Failed to import SentenceTransformer. Install with 'pip install sentence-transformers': {e}")
        return False, {}
    except Exception as e:
        logger.error(f"Failed to load model {DEFAULT_MODEL_NAME}: {e}")
        return False, {}

    # Collect files and generate keys
    key_map = {}
    file_contents = {}
    for project_path in project_paths:
        for root, _, files in os.walk(project_path):
            for file in files:
                file_path = normalize_path(os.path.join(root, file))
                if _is_valid_file(file_path):
                    key = generate_key(file_path)
                    key_map[key] = file_path
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_contents[key] = f.read()
                    except UnicodeDecodeError:
                        logger.debug(f"Skipping non-text file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to read {file_path}: {e}")

    if not key_map:
        logger.warning("No valid files found to generate embeddings.")
        return False, {}

    # Generate embeddings
    embeddings = {}
    texts = []
    valid_keys = []
    for key, content in file_contents.items():
        if content.strip():
            texts.append(content)
            valid_keys.append(key)

    if not texts:
        logger.warning("No non-empty files found for embedding generation.")
        return False, key_map

    try:
        embeddings_array = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        for key, embedding in zip(valid_keys, embeddings_array):
            embeddings[key] = embedding
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return False, key_map

    # Save embeddings
    for key, embedding in embeddings.items():
        np.save(os.path.join(embeddings_dir, f"{key}.npy"), embedding)

    # Save metadata
    metadata = {
        "version": "1.0",
        "model": DEFAULT_MODEL_NAME,
        "keys": {k: v for k, v in key_map.items() if k in embeddings}
    }
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write metadata file {metadata_file}: {e}")
        return False, key_map

    # Update tracker if present
    tracker_file = os.path.join(output_dir, "tracker.json")
    if os.path.exists(tracker_file):
        tracker_data = read_tracker_file(tracker_file)
        if tracker_data:
            tracker_data["keys"].update(key_map)
            write_tracker_file(tracker_file, tracker_data["keys"], tracker_data["grid"], tracker_data.get("last_key_edit", ""))

    logger.info(f"Generated embeddings for {len(embeddings)} files in {embeddings_dir}")
    return True, key_map

@cached('similarity', key_func=lambda key1, key2, embeddings_dir: f"similarity:{key1}:{key2}:{normalize_path(embeddings_dir)}:{os.path.getmtime(embeddings_dir) if os.path.exists(embeddings_dir) else '0'}")
def calculate_similarity(key1: str, key2: str, embeddings_dir: str) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        key1: First key
        key2: Second key
        embeddings_dir: Directory containing .npy embedding files
    Returns:
        Cosine similarity score (0.0 to 1.0), or 0.0 on failure
    """
    if not (validate_key(key1) and validate_key(key2)):
        logger.warning(f"Invalid keys: {key1}, {key2}")
        return 0.0

    if key1 == key2:
        return 1.0

    file1 = os.path.join(embeddings_dir, f"{key1}.npy")
    file2 = os.path.join(embeddings_dir, f"{key2}.npy")

    if not (os.path.exists(file1) and os.path.exists(file2)):
        logger.debug(f"Embedding files missing: {file1}, {file2}")
        return 0.0

    try:
        emb1 = np.load(file1)
        emb2 = np.load(file2)
        similarity = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
    except Exception as e:
        logger.debug(f"Failed to calculate similarity for {key1} and {key2}: {e}")
        return 0.0

def _is_valid_file(file_path: str) -> bool:
    """
    Check if a file is valid for embedding generation.

    Args:
        file_path: Normalized path to the file
    Returns:
        True if the file should be processed, False otherwise
    """
    config = ConfigManager()
    exclude_dirs = config.get("exclude_dirs", ["node_modules", "__pycache__", ".git"])
    exclude_exts = config.get("exclude_extensions", [".pyc", ".log", ".bin"])

    file_name = os.path.basename(file_path)
    if file_name.startswith('.') or file_name in config.get("exclude_files", []):
        return False

    if any(ex_dir in file_path for ex_dir in exclude_dirs):
        return False

    ext = os.path.splitext(file_path)[1].lower()
    if ext in exclude_exts:
        return False

    return os.path.isfile(file_path) and os.path.getsize(file_path) < 10 * 1024 * 1024  # 10MB limit

def register_parser(subparsers):
    """Register command-line interface commands."""
    parser = subparsers.add_parser("generate-embeddings", help="Generate embeddings for project files")
    parser.add_argument("project_paths", nargs="+", help="Paths to project directories")
    parser.add_argument("--output-dir", default=".", help="Directory to store embeddings")
    parser.add_argument("--force", action="store_true", help="Force regeneration of embeddings")
    parser.set_defaults(func=command_handler)

def command_handler(args):
    """Handle the generate-embeddings command."""
    success, key_map = generate_embeddings(args.project_paths, args.output_dir, args.force)
    if success:
        print(f"Successfully generated embeddings for {len(key_map)} files in {args.output_dir}/embeddings")
        return 0
    else:
        print("Error: Failed to generate embeddings")
        return 1
    
# EoF