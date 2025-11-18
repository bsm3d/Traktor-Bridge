"""
File Validator Module for Traktor Bridge
Validates audio file integrity before processing
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


class AudioFileValidator:
    """Validates audio file integrity and format."""
    
    @staticmethod
    def validate_mp3(file_path: str) -> Dict[str, Any]:
        """Validate MP3 file integrity."""
        result = {
            'valid': False,
            'error': None,
            'duration': 0,
            'bitrate': 0
        }
        
        try:
            if not os.path.exists(file_path):
                result['error'] = "File not found"
                return result
            
            if os.path.getsize(file_path) == 0:
                result['error'] = "Empty file"
                return result
            
            if MUTAGEN_AVAILABLE:
                from mutagen.mp3 import MP3
                audio = MP3(file_path)
                result['duration'] = audio.info.length
                result['bitrate'] = audio.info.bitrate
                result['valid'] = True
            else:
                # Basic validation without mutagen
                with open(file_path, 'rb') as f:
                    header = f.read(10)
                    if header.startswith(b'ID3') or header[0:2] == b'\xff\xfb':
                        result['valid'] = True
                    else:
                        result['error'] = "Invalid MP3 header"
            
        except Exception as e:
            result['error'] = str(e)
            logging.warning(f"MP3 validation failed for {file_path}: {e}")
        
        return result