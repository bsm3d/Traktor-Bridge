"""
Key Translator Module for Traktor Bridge - Updated for CDJ compatibility
Handles translation between different musical key formats and display
Includes proper Rekordbox key ID mapping for PDB export
"""

from typing import Dict, Optional, Tuple, List


class KeyTranslator:
    """Translates between Traktor, Rekordbox, and standard musical key formats."""
    
    def __init__(self):
        # Traktor internal key index to musical notations (0-23)
        self.open_key_map = [
            "8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B",
            "5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"
        ]
        
        self.classical_map = [
            "F#", "A#", "D#", "G#", "C#", "F", "A", "D", "G", "C", "E", "B",
            "D#m", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m"
        ]
        
        # Alternative notation styles
        self.flat_classical_map = [
            "Gb", "Bb", "Eb", "Ab", "Db", "F", "A", "D", "G", "C", "E", "B",
            "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "Gbm", "Dbm", "Abm"
        ]
        
        # Pioneer/Rekordbox key mapping (different from Traktor!)
        self.pioneer_key_map = [
            "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A", "5A", "12A",
            "4B", "11B", "6B", "1B", "8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B"
        ]
        
        # Rekordbox database key ID mapping (for PDB export)
        # This maps Open Key notation to Rekordbox database IDs
        self.rekordbox_key_id_map = {
            '1A': 21, '1B': 12, '2A': 16, '2B': 7, '3A': 23, '3B': 2,
            '4A': 18, '4B': 9, '5A': 13, '5B': 4, '6A': 20, '6B': 11,
            '7A': 15, '7B': 6, '8A': 22, '8B': 1, '9A': 17, '9B': 8,
            '10A': 24, '10B': 3, '11A': 19, '11B': 10, '12A': 14, '12B': 5
        }
        
        # Reverse Rekordbox ID mapping
        self.rekordbox_id_to_key_map = {v: k for k, v in self.rekordbox_key_id_map.items()}
        
        # Translation cache for performance
        self._translation_cache = {}
        
        # Reverse lookup dictionaries
        self._reverse_maps = self._build_reverse_maps()
    
    def _build_reverse_maps(self) -> Dict[str, Dict[str, int]]:
        """Build reverse lookup maps for efficient conversion."""
        return {
            'open_key': {key: idx for idx, key in enumerate(self.open_key_map)},
            'classical': {key: idx for idx, key in enumerate(self.classical_map)},
            'flat_classical': {key: idx for idx, key in enumerate(self.flat_classical_map)},
            'pioneer': {key: idx for idx, key in enumerate(self.pioneer_key_map)}
        }
    
    def translate(self, traktor_key: str, target_format: str = "Open Key") -> str:
        """Translate Traktor key index to specified format with caching."""
        if not traktor_key:
            return ""
        
        # Si déjà au format Open Key, convertir d'abord en index
        if isinstance(traktor_key, str) and any(traktor_key.endswith(suffix) for suffix in ['A', 'B']):
            traktor_index = self.reverse_translate(traktor_key, "Open Key")
            if traktor_index is None:
                return ""
            traktor_key = str(traktor_index)
        
        if not str(traktor_key).isdigit():
            return ""
            
        # Check cache first
        cache_key = f"{traktor_key}:{target_format}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
            
        try:
            key_index = int(traktor_key)
            if not 0 <= key_index < len(self.open_key_map):
                return ""
            
            # Select appropriate mapping
            if target_format == "Classical":
                result = self.classical_map[key_index]
            elif target_format == "Flat Classical":
                result = self.flat_classical_map[key_index]
            elif target_format == "Pioneer":
                result = self.pioneer_key_map[key_index]
            else:  # Default to Open Key
                result = self.open_key_map[key_index]
                
            # Cache and return
            self._translation_cache[cache_key] = result
            return result
            
        except (IndexError, ValueError):
            return ""
    
    def reverse_translate(self, key_notation: str, source_format: str = "Open Key") -> Optional[int]:
        """Convert key notation back to Traktor index."""
        if not key_notation:
            return None
            
        format_map = {
            "Open Key": "open_key",
            "Classical": "classical", 
            "Flat Classical": "flat_classical",
            "Pioneer": "pioneer"
        }
        
        map_name = format_map.get(source_format, "open_key")
        reverse_map = self._reverse_maps.get(map_name, {})
        
        return reverse_map.get(key_notation)
    
    def get_rekordbox_key_id(self, traktor_key: str) -> int:
        """Convert Traktor key to Rekordbox database key ID for PDB export."""
        if not traktor_key:
            return 1  # Default key ID
        
        # Convert to Open Key first if needed
        open_key = self.translate(traktor_key, "Open Key")
        if not open_key:
            return 1
        
        return self.rekordbox_key_id_map.get(open_key, 1)
    
    def get_key_from_rekordbox_id(self, rekordbox_id: int) -> str:
        """Convert Rekordbox key ID back to Open Key notation."""
        return self.rekordbox_id_to_key_map.get(rekordbox_id, "")
    
    def convert_traktor_to_rekordbox_key(self, traktor_key: str) -> Tuple[int, str]:
        """Convert Traktor key to both Rekordbox ID and Open Key notation.
        
        Returns:
            Tuple of (rekordbox_id, open_key_notation)
        """
        open_key = self.translate(traktor_key, "Open Key")
        rekordbox_id = self.get_rekordbox_key_id(traktor_key)
        return rekordbox_id, open_key
    
    def get_compatible_keys(self, traktor_key: str, format_type: str = "Open Key") -> List[str]:
        """Get harmonically compatible keys (same number, different letter)."""
        if not traktor_key or not str(traktor_key).isdigit():
            return []
            
        try:
            key_index = int(traktor_key)
            if not 0 <= key_index < len(self.open_key_map):
                return []
            
            current_key = self.translate(traktor_key, format_type)
            if not current_key:
                return []
            
            compatible = []
            
            # For Open Key format
            if format_type == "Open Key":
                if current_key.endswith('A'):
                    # Find corresponding B key (relative minor/major)
                    number = current_key[:-1]
                    compatible.append(f"{number}B")
                elif current_key.endswith('B'):
                    # Find corresponding A key
                    number = current_key[:-1] 
                    compatible.append(f"{number}A")
                    
                # Add perfect fourth and fifth
                try:
                    num = int(current_key[:-1])
                    letter = current_key[-1]
                    
                    # Perfect fourth (+1 or -11)
                    fourth = ((num % 12) + 1) if (num % 12) != 0 else 1
                    compatible.append(f"{fourth}{letter}")
                    
                    # Perfect fifth (-1 or +11) 
                    fifth = ((num - 2) % 12) + 1
                    compatible.append(f"{fifth}{letter}")
                    
                except ValueError:
                    pass
            
            # For Classical format - relative major/minor
            elif format_type == "Classical":
                if 'm' in current_key:  # Minor key
                    # Find relative major (3 semitones up)
                    major_idx = (key_index + 3) % 12
                    if major_idx < len(self.classical_map):
                        major_key = self.classical_map[major_idx]
                        if 'm' not in major_key:
                            compatible.append(major_key)
                else:  # Major key
                    # Find relative minor (3 semitones down)
                    minor_idx = (key_index - 3) % 24
                    if minor_idx >= 12 and minor_idx < len(self.classical_map):
                        minor_key = self.classical_map[minor_idx] 
                        if 'm' in minor_key:
                            compatible.append(minor_key)
            
            return compatible
            
        except (ValueError, IndexError):
            return []
    
    def get_key_color(self, traktor_key: str, format_type: str = "Open Key") -> Optional[str]:
        """Get display color for key based on harmonic wheel."""
        key_notation = self.translate(traktor_key, format_type)
        if not key_notation:
            return None
            
        # Open Key color mapping (Camelot wheel colors)
        if format_type == "Open Key":
            # Color wheel based on Camelot system
            camelot_colors = {
                '1A': '#FF0000', '1B': '#FF4444',  # Red
                '2A': '#FF8000', '2B': '#FF9944',  # Orange
                '3A': '#FFFF00', '3B': '#FFFF44',  # Yellow
                '4A': '#80FF00', '4B': '#99FF44',  # Yellow-Green
                '5A': '#00FF00', '5B': '#44FF44',  # Green
                '6A': '#00FF80', '6B': '#44FF99',  # Green-Cyan
                '7A': '#00FFFF', '7B': '#44FFFF',  # Cyan
                '8A': '#0080FF', '8B': '#4499FF',  # Cyan-Blue
                '9A': '#0000FF', '9B': '#4444FF',  # Blue
                '10A': '#8000FF', '10B': '#9944FF', # Blue-Purple
                '11A': '#FF00FF', '11B': '#FF44FF', # Magenta
                '12A': '#FF0080', '12B': '#FF4499'  # Red-Magenta
            }
            return camelot_colors.get(key_notation)
        
        # Classical color mapping
        elif format_type == "Classical":
            classical_colors = {
                # Major keys - brighter colors
                'C': '#FF4444', 'G': '#44FF44', 'D': '#4444FF', 'A': '#FFFF44',
                'E': '#FF44FF', 'B': '#44FFFF', 'F#': '#FF8844', 'Gb': '#FF8844',
                'C#': '#88FF44', 'Db': '#88FF44', 'G#': '#4488FF', 'Ab': '#4488FF',
                'D#': '#FF4488', 'Eb': '#FF4488', 'A#': '#FFAA44', 'Bb': '#FFAA44',
                'F': '#AA44FF',
                
                # Minor keys - darker variants
                'Am': '#CC2222', 'Em': '#CC22CC', 'Bm': '#22CCCC', 'F#m': '#CC6622',
                'Gbm': '#CC6622', 'C#m': '#66CC22', 'Dbm': '#66CC22', 'G#m': '#2266CC',
                'Abm': '#2266CC', 'D#m': '#CC2266', 'Ebm': '#CC2266', 'Bbm': '#CC8822',
                'Fm': '#8822CC', 'Cm': '#2222CC', 'Gm': '#22CC22', 'Dm': '#CC2222'
            }
            return classical_colors.get(key_notation)
        
        return None
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported key formats."""
        return ["Open Key", "Classical", "Flat Classical", "Pioneer"]
    
    def validate_key_notation(self, key_notation: str, format_type: str = "Open Key") -> bool:
        """Validate if key notation is valid for given format."""
        if not key_notation:
            return False
            
        format_maps = {
            "Open Key": self.open_key_map,
            "Classical": self.classical_map,
            "Flat Classical": self.flat_classical_map, 
            "Pioneer": self.pioneer_key_map
        }
        
        valid_keys = format_maps.get(format_type, self.open_key_map)
        return key_notation in valid_keys
    
    def convert_between_formats(self, key_notation: str, 
                               source_format: str, target_format: str) -> str:
        """Convert key notation from one format to another."""
        if source_format == target_format:
            return key_notation
            
        # First convert to Traktor index
        traktor_index = self.reverse_translate(key_notation, source_format)
        if traktor_index is None:
            return ""
            
        # Then convert to target format
        return self.translate(str(traktor_index), target_format)
    
    def get_key_info(self, traktor_key: str) -> Dict[str, any]:
        """Get comprehensive key information including Rekordbox mapping."""
        if not traktor_key or not str(traktor_key).isdigit():
            return {}
            
        try:
            key_index = int(traktor_key)
            if not 0 <= key_index < len(self.open_key_map):
                return {}
            
            open_key = self.translate(traktor_key, "Open Key")
            rekordbox_id = self.get_rekordbox_key_id(traktor_key)
            
            info = {
                'traktor_index': key_index,
                'open_key': open_key,
                'classical': self.translate(traktor_key, "Classical"),
                'flat_classical': self.translate(traktor_key, "Flat Classical"),
                'pioneer': self.translate(traktor_key, "Pioneer"),
                'rekordbox_id': rekordbox_id,
                'is_major': key_index < 12,
                'is_minor': key_index >= 12
            }
            
            # Add compatible keys
            info['compatible_open_key'] = self.get_compatible_keys(traktor_key, "Open Key")
            info['compatible_classical'] = self.get_compatible_keys(traktor_key, "Classical")
            
            # Add colors
            info['open_key_color'] = self.get_key_color(traktor_key, "Open Key")
            info['classical_color'] = self.get_key_color(traktor_key, "Classical")
            
            return info
            
        except (ValueError, IndexError):
            return {}
    
    def get_harmonic_mixing_info(self, traktor_key: str) -> Dict[str, List[str]]:
        """Get detailed harmonic mixing information for DJs."""
        open_key = self.translate(traktor_key, "Open Key")
        if not open_key:
            return {}
        
        try:
            number = int(open_key[:-1])
            letter = open_key[-1]
            
            mixing_info = {
                'perfect_matches': [f"{number}{'B' if letter == 'A' else 'A'}"],  # Relative major/minor
                'energy_up': [f"{(number % 12) + 1}{letter}"],     # +1 semitone
                'energy_down': [f"{((number - 2) % 12) + 1}{letter}"],  # -1 semitone
                'harmonic_matches': [],
                'cautions': []
            }
            
            # Add harmonic matches (perfect 4th and 5th)
            fourth = ((number + 6) % 12) + 1  # Perfect 4th
            fifth = ((number + 4) % 12) + 1   # Perfect 5th
            mixing_info['harmonic_matches'] = [f"{fourth}{letter}", f"{fifth}{letter}"]
            
            # Add caution keys (dissonant intervals)
            tritone = ((number + 5) % 12) + 1  # Tritone (most dissonant)
            mixing_info['cautions'] = [f"{tritone}{letter}"]
            
            return mixing_info
            
        except (ValueError, IndexError):
            return {}
    
    def suggest_key_progression(self, current_key: str, direction: str = "up") -> List[str]:
        """Suggest key progression for DJ sets."""
        open_key = self.translate(current_key, "Open Key")
        if not open_key:
            return []
        
        try:
            number = int(open_key[:-1])
            letter = open_key[-1]
            
            if direction == "up":
                # Energy building progression
                progression = [
                    f"{number}{letter}",  # Current
                    f"{number}{'B' if letter == 'A' else 'A'}",  # Relative
                    f"{(number % 12) + 1}{'B' if letter == 'A' else 'A'}",  # +1 relative
                    f"{(number % 12) + 1}{letter}",  # +1 same mode
                    f"{((number + 1) % 12) + 1}{letter}"  # +2 same mode
                ]
            else:
                # Energy reducing progression
                progression = [
                    f"{number}{letter}",  # Current
                    f"{number}{'B' if letter == 'A' else 'A'}",  # Relative
                    f"{((number - 2) % 12) + 1}{'B' if letter == 'A' else 'A'}",  # -1 relative
                    f"{((number - 2) % 12) + 1}{letter}",  # -1 same mode
                    f"{((number - 3) % 12) + 1}{letter}"  # -2 same mode
                ]
            
            return progression
            
        except (ValueError, IndexError):
            return []
    
    def clear_cache(self):
        """Clear translation cache."""
        self._translation_cache.clear()
    
    def get_rekordbox_export_data(self, traktor_key: str) -> Dict[str, any]:
        """Get all data needed for Rekordbox PDB export."""
        return {
            'rekordbox_id': self.get_rekordbox_key_id(traktor_key),
            'open_key': self.translate(traktor_key, "Open Key"),
            'classical': self.translate(traktor_key, "Classical"),
            'scale_name': self.translate(traktor_key, "Open Key")  # For djmdKey.ScaleName
        }