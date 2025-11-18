"""
Path Validator Module for Traktor Bridge
Validates and sanitizes file paths to prevent security issues
"""

import logging
from pathlib import Path
from typing import Optional


class PathValidator:
    """Validates and sanitizes file paths to prevent errors and security issues."""
    
    @staticmethod
    def validate_path(path_str: str, must_exist: bool = True) -> Optional[Path]:
        """Validates and resolves a path string with security checks."""
        if not path_str:
            return None
            
        try:
            path = Path(path_str).resolve()
            
            # Security check: prevent path traversal attacks
            if '..' in str(path) or str(path).startswith('..'):
                raise ValueError("Invalid path format (path traversal detected)")
            
            # Check existence if required
            if must_exist and not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
                
            return path
            
        except Exception as e:
            logging.warning(f"Path validation failed for '{path_str}': {e}")
            return None
    
    @staticmethod
    def validate_file_path(path_str: str, extensions: Optional[list] = None) -> Optional[Path]:
        """Validate file path with optional extension checking."""
        path = PathValidator.validate_path(path_str, must_exist=True)
        if not path:
            return None
            
        if not path.is_file():
            logging.warning(f"Path is not a file: {path}")
            return None
            
        if extensions:
            if path.suffix.lower() not in [ext.lower() for ext in extensions]:
                logging.warning(f"Invalid file extension for {path}. Expected: {extensions}")
                return None
                
        return path
    
    @staticmethod
    def validate_directory_path(path_str: str, create_if_missing: bool = False) -> Optional[Path]:
        """Validate directory path with optional creation."""
        if not path_str:
            return None
            
        try:
            path = Path(path_str).resolve()
            
            # Security check
            if '..' in str(path) or str(path).startswith('..'):
                raise ValueError("Invalid path format (path traversal detected)")
            
            if not path.exists():
                if create_if_missing:
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    raise FileNotFoundError(f"Directory does not exist: {path}")
            
            if not path.is_dir():
                raise NotADirectoryError(f"Path is not a directory: {path}")
                
            return path
            
        except Exception as e:
            logging.warning(f"Directory validation failed for '{path_str}': {e}")
            return None
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to remove invalid characters."""
        if not filename:
            return "unnamed"
            
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = filename
        
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
            
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip(' .')
        
        # Ensure not empty
        if not sanitized:
            sanitized = "unnamed"
            
        return sanitized
    
    @staticmethod
    def is_safe_path(path_str: str, base_directory: Optional[str] = None) -> bool:
        """Check if path is safe (no traversal, within base directory if specified)."""
        try:
            path = Path(path_str).resolve()
            
            # Check for traversal
            if '..' in str(path):
                return False
                
            # Check if within base directory
            if base_directory:
                base = Path(base_directory).resolve()
                try:
                    path.relative_to(base)
                except ValueError:
                    return False
                    
            return True
            
        except Exception:
            return False