"""
Audio Manager Module for Traktor Bridge
Handles thread-safe audio playback using pygame
"""

import logging
import os
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available. Audio playback disabled.")


class AudioManager:
    """Thread-safe audio playback manager using pygame."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        self._current_file = None
        self._playing_item_id = None
        self._root_ref = None
        
    def initialize(self, root_widget=None) -> bool:
        """Initialize pygame mixer in thread-safe manner."""
        if not PYGAME_AVAILABLE:
            return False
            
        with self._lock:
            if not self._initialized:
                try:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
                    self._initialized = True
                    self._root_ref = root_widget
                    return True
                except pygame.error as e:
                    logging.error(f"Failed to initialize pygame mixer: {e}")
                    return False
            return True
    
    def play_file(self, file_path: str, item_id: str) -> bool:
        """Play audio file in thread-safe manner."""
        if not PYGAME_AVAILABLE or not self._initialized:
            return False
            
        with self._lock:
            # Stop previous file
            self._stop_internal()
            
            try:
                # Validate file
                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    return False
                
                # Load and play
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                
                self._current_file = file_path
                self._playing_item_id = item_id
                
                return True
                
            except (pygame.error, OSError) as e:
                logging.error(f"Failed to play {file_path}: {e}")
                return False
    
    def stop(self):
        """Stop playback in thread-safe manner."""
        with self._lock:
            self._stop_internal()
    
    def _stop_internal(self):
        """Internal stop method (already in thread-safe context)."""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except:
            pass
        
        self._current_file = None
        self._playing_item_id = None
    
    def get_current_state(self) -> Dict[str, Any]:
        """Return current state in thread-safe manner."""
        with self._lock:
            return {
                'file': self._current_file,
                'item_id': self._playing_item_id,
                'is_playing': pygame.mixer.music.get_busy() if self._initialized else False
            }
    
    def is_available(self) -> bool:
        """Check if audio functionality is available."""
        return PYGAME_AVAILABLE and self._initialized
    
    def cleanup(self):
        """Clean up audio resources."""
        with self._lock:
            self._stop_internal()
            if self._initialized:
                try:
                    pygame.mixer.quit()
                except:
                    pass
                self._initialized = False