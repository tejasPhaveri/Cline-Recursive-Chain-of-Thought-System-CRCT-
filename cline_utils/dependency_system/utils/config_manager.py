"""
Configuration module for dependency tracking system.
Handles reading and writing configuration settings.
"""

import os
import json
from typing import Dict, List, Any, Optional, Union
import logging

from cline_utils.dependency_system.utils.path_utils import normalize_path, get_project_root

# Configure logging
logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_CONFIG = {
    "excluded_dirs": [
        "__pycache__",
        "embeddings",
        ".git",
        ".idea",
        "__MACOSX",
        "node_modules",
        "venv",
        "env",
        ".venv",
        "dist",
        "build"
    ],
    "excluded_extensions": [
        ".embedding",
        ".pyc",
        ".pyo",
        ".pyd",
        ".DS_Store",
        ".o",
        ".so",
        ".dll",
        ".exe"
    ],
    "thresholds": {
        "doc_similarity": 0.7,
        "code_similarity": 0.8
    },
    "models": {
        "doc_model_name": "all-MiniLM-L6-v2",
        "code_model_name": "all-mpnet-base-v2"
    },
    "paths": {
        "doc_dir": "docs",
        "memory_dir": "clinedocs",
        "embeddings_dir": "embeddings",
        "backups_dir": "backups"
    }
}

class ConfigManager:
    """
    Configuration manager for dependency tracking system.
    Handles reading and writing configuration settings.
    """

    _instance = None

    def __new__(cls):
        """
        Singleton pattern implementation to ensure only one config instance.
        
        Returns:
            ConfigManager instance
        """
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the configuration manager."""
        self._initialized = False # Initialize _initialized at the beginning
        if self._initialized:
            return

        self._config = None
        self._config_path = None

    @property
    def config(self) -> Dict[str, Any]:
        """
        Get the configuration dictionary.
        
        Returns:
            Configuration dictionary
        """
        if self._config is None:
            self._load_config()
        return self._config

    @property
    def config_path(self) -> str:
        """
        Get the path to the configuration file.
        
        Returns:
            Path to the configuration file
        """
        if self._config_path is None:
            project_root = get_project_root()
            self._config_path = normalize_path(os.path.join(project_root, ".clinerules.config.json"))
        return self._config_path

    def _load_config(self) -> None:
        """Load configuration from file or create default."""
        try:
            if os.path.exists(normalize_path(self.config_path)):
                with open(normalize_path(self.config_path), 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            else:
                self._config = DEFAULT_CONFIG.copy()
                self._save_config()
        except Exception as e:
            logger.error(f"Error loading configuration from {self.config_path}: {e}")
            self._config = DEFAULT_CONFIG.copy()

    def _save_config(self) -> bool:
        """
        Save configuration to file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(normalize_path(self.config_path)), exist_ok=True)
            with open(normalize_path(self.config_path), 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
            return True
        except OSError as e:
            logger.error(f"Error writing configuration file {self.config_path}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error saving configuration to {self.config_path}: {e}")
            return False
    
    def get_excluded_dirs(self) -> List[str]:
        """
        Get list of excluded directories.
        
        Returns:
            List of excluded directory names
        """
        return self.config.get("excluded_dirs", DEFAULT_CONFIG["excluded_dirs"])
    
    def get_excluded_extensions(self) -> List[str]:
        """
        Get list of excluded file extensions.
        
        Returns:
            List of excluded file extensions
        """
        return self.config.get("excluded_extensions", DEFAULT_CONFIG["excluded_extensions"])
    
    def get_threshold(self, threshold_type: str) -> float:
        """
        Get threshold value.
        
        Args:
            threshold_type: Type of threshold ('doc_similarity' or 'code_similarity')
            
        Returns:
            Threshold value
        """
        thresholds = self.config.get("thresholds", DEFAULT_CONFIG["thresholds"])
        return thresholds.get(threshold_type, 0.7)
    
    def get_model_name(self, model_type: str) -> str:
        """
        Get model name.
        
        Args:
            model_type: Type of model ('doc_model_name' or 'code_model_name')
            
        Returns:
            Model name
        """
        models = self.config.get("models", DEFAULT_CONFIG["models"])
        return models.get(model_type, "all-MiniLM-L6-v2")

    def get_path(self, path_type: str, default_path: Optional[str] = None) -> str:
        """
        Get path from configuration.
        
        Args:
            path_type: Type of path ('doc_dir', 'memory_dir', or 'embeddings_dir')
            default_path: Default path to use if not found in configuration
            
        Returns:
            Path from configuration or default
        """
        paths = self.config.get("paths", DEFAULT_CONFIG["paths"])
        path = paths.get(path_type, default_path if default_path else DEFAULT_CONFIG["paths"].get(path_type, ""))
        return normalize_path(path) # Normalize the returned path

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of configuration updates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Deep update of nested dictionaries
            self._deep_update(self.config, updates)
            return self._save_config()
        except Exception as e:
            logger.error(f"Error updating configuration: {str(e)}")
            return False

    def _deep_update(self, d: Dict[str, Any], u: Dict[str, Any]) -> None:
        """
        Recursively update a dictionary.
        
        Args:
            d: Dictionary to update
            u: Dictionary with updates
        """
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v

    def reset_to_defaults(self) -> bool:
        """
        Reset configuration to default values.
        
        Returns:
            True if successful, False otherwise
        """
        self._config = DEFAULT_CONFIG.copy()
        return self._save_config()
