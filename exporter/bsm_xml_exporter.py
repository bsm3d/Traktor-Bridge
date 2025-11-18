# -*- coding: utf-8 -*-
"""
Traktor Bridge - Rekordbox XML Export Module
Component: rekordbox_xml_exporter.py

Generates Rekordbox-compatible XML from Traktor NML data.
Fully compatible with BSM NML Parser output.
Fixed for complete Rekordbox conformity.
"""

import logging
import xml.etree.ElementTree as ET
import urllib.parse
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from parser.bsm_nml_parser import Track, Node, TraktorNMLParser

class RekordboxKeyMapper:
    """Musical key translator for Traktor -> Rekordbox"""
    
    # Traktor key index to Open Key notation
    TRAKTOR_TO_OPEN_KEY = {
        0: "8A", 1: "3A", 2: "10A", 3: "5A", 4: "12A", 5: "7A",
        6: "2A", 7: "9A", 8: "4A", 9: "11A", 10: "6A", 11: "1A",
        12: "8B", 13: "3B", 14: "10B", 15: "5B", 16: "12B", 17: "7B",
        18: "2B", 19: "9B", 20: "4B", 21: "11B", 22: "6B", 23: "1B"
    }
    
    @classmethod
    def convert_key(cls, musical_key: str) -> str:
        """Convert musical key to Open Key notation"""
        if not musical_key:
            return ""
        
        # If it's a numeric Traktor key
        if musical_key.isdigit():
            key_index = int(musical_key)
            return cls.TRAKTOR_TO_OPEN_KEY.get(key_index, "")
        
        # Return as-is if already in Open Key notation
        return musical_key

class RekordboxXMLExporter:
    """Exports Traktor data to Rekordbox XML format with full conformity"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.key_mapper = RekordboxKeyMapper()
        self.track_id_counter = 1
        
        # Export statistics
        self.stats = {
            'tracks_exported': 0,
            'playlists_exported': 0,
            'cues_converted': 0,
            'errors': 0
        }
    
    def export_collection(self, tracks: List[Track], 
                         playlist_structure: List[Node],
                         output_path: Optional[Path] = None) -> str:
        """Export collection to Rekordbox XML format"""
        self._reset_stats()
        
        # Create XML structure
        root = self._create_xml_root()
        
        # Build track ID mapping
        track_mapping = self._build_track_mapping(tracks)
        
        # Add collection section
        self._create_collection_section(root, tracks, track_mapping)
        
        # Add playlists section
        self._create_playlists_section(root, playlist_structure, track_mapping)
        
        # Generate formatted XML
        xml_string = self._format_xml_output(root)
        
        # Save if path specified
        if output_path:
            self._save_xml_file(xml_string, output_path)
        
        self.logger.info(f"Rekordbox XML export: {self.stats['tracks_exported']} tracks, "
                        f"{self.stats['playlists_exported']} playlists")
        
        return xml_string
    
    def _reset_stats(self):
        """Reset export statistics"""
        self.stats = {k: 0 for k in self.stats}
        self.track_id_counter = 1
    
    def _build_track_mapping(self, tracks: List[Track]) -> Dict[str, int]:
        """Build mapping from track identifiers to XML TrackIDs"""
        mapping = {}
        
        for track in tracks:
            # Use audio_id as primary key, fallback to file path
            key = track.audio_id or track.file_path
            if key:
                mapping[key] = self.track_id_counter
                self.track_id_counter += 1
        
        return mapping
    
    def _create_xml_root(self) -> ET.Element:
        """Create XML root structure"""
        root = ET.Element('DJ_PLAYLISTS', Version="1.0.0")
        
        # Add PRODUCT element
        ET.SubElement(root, 'PRODUCT',
                     Name="rekordbox",
                     Version="6.8.5",
                     Company="Pioneer DJ")
        
        return root
    
    def _create_collection_section(self, root: ET.Element, tracks: List[Track], 
                                  track_mapping: Dict[str, int]):
        """Create COLLECTION section with all tracks"""
        collection = ET.SubElement(root, 'COLLECTION', Entries=str(len(tracks)))
        
        for track in tracks:
            try:
                self._add_rekordbox_track(collection, track, track_mapping)
                self.stats['tracks_exported'] += 1
            except Exception as e:
                self.logger.error(f"Error exporting track {track.title}: {e}")
                self.stats['errors'] += 1
    
    def _add_rekordbox_track(self, collection: ET.Element, track: Track, 
                            track_mapping: Dict[str, int]):
        """Add single track to collection"""
        # Get TrackID from mapping
        key = track.audio_id or track.file_path
        track_id = track_mapping.get(key, 0)
        
        if track_id == 0:
            raise ValueError(f"No TrackID mapping for track: {track.title}")
        
        # Create TRACK element with all required attributes
        track_elem = ET.SubElement(collection, 'TRACK',
                                  TrackID=str(track_id),
                                  Name=track.title,
                                  Artist=track.artist,
                                  Composer="",  # Keep empty for compatibility
                                  Album=track.album,
                                  Grouping="",
                                  Genre=track.genre,
                                  Kind=self._get_file_kind(track.file_path),
                                  Size=str(track.file_size),
                                  TotalTime=str(int(track.playtime)),
                                  DiscNumber="0",
                                  TrackNumber="1",
                                  Year="",
                                  AverageBpm=f"{track.bpm:.2f}",
                                  DateAdded=self._format_date(track.date_added),
                                  BitRate=str(int(track.bitrate / 1000)) if track.bitrate > 0 else "320",
                                  SampleRate="44100",
                                  Comments=track.comment,
                                  PlayCount=str(track.play_count),
                                  Rating=str(self._convert_rating(track.ranking)),
                                  Location=self._format_file_location(track.file_path),
                                  Remixer=track.remixer,
                                  Tonality=self.key_mapper.convert_key(track.musical_key),
                                  Label=track.label,
                                  Mix="")
        
        # Add TEMPO element (REQUIRED for beat sync)
        ET.SubElement(track_elem, 'TEMPO',
                     Inizio="0.000",
                     Bpm=f"{track.bpm:.2f}",
                     Metro="4/4",
                     Battito="1")
        
        # Add cue points as POSITION_MARK elements
        self._add_position_marks(track_elem, track)
    
    def _get_file_kind(self, file_path: str) -> str:
        """Determine file kind from extension"""
        if not file_path:
            return "MP3 File"
        
        ext = Path(file_path).suffix.lower()
        
        kind_mapping = {
            '.mp3': 'MP3 File',
            '.m4a': 'M4A File',
            '.flac': 'FLAC File',
            '.wav': 'WAV File',
            '.aiff': 'AIFF File',
            '.aif': 'AIFF File'
        }
        
        return kind_mapping.get(ext, 'MP3 File')
    
    def _format_date(self, date_string: str) -> str:
        """Format date for Rekordbox (YYYY-MM-DD)"""
        if not date_string:
            return datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Handle different Traktor date formats
            if '/' in date_string:  # YYYY/M/D format
                parts = date_string.split('/')
                if len(parts) == 3:
                    year, month, day = parts
                    return f"{year:0>4}-{month:0>2}-{day:0>2}"
            
            # ISO format
            if 'T' in date_string:
                dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d")
            
            return date_string
            
        except (ValueError, IndexError):
            return datetime.now().strftime("%Y-%m-%d")
    
    def _convert_rating(self, ranking: int) -> int:
        """Convert Traktor ranking (0-255) to Rekordbox rating (0-5)"""
        if ranking <= 0:
            return 0
        return min(5, int((ranking / 255.0) * 5))
    
    def _format_file_location(self, file_path: str) -> str:
        """Format file path as Rekordbox file:// URL"""
        if not file_path:
            return ""
        
        # Normalize path separators to forward slashes
        normalized_path = file_path.replace('\\', '/')
        
        # Remove Traktor-specific path prefixes
        if normalized_path.startswith('/:'):
            normalized_path = normalized_path[2:]
        
        # Ensure absolute path format
        if not normalized_path.startswith('/') and ':' not in normalized_path:
            normalized_path = '/' + normalized_path
        
        # URL encode the path components
        path_parts = normalized_path.split('/')
        encoded_parts = [urllib.parse.quote(part, safe='') for part in path_parts]
        encoded_path = '/'.join(encoded_parts)
        
        # Create proper file:// URL
        return f"file://localhost{encoded_path}"
    
    def _add_position_marks(self, track_elem: ET.Element, track: Track):
        """Add cue points as POSITION_MARK elements"""
        cue_counter = 0
        
        for cue in track.cue_points:
            try:
                # Skip grid markers - they're not cues in Rekordbox
                if cue.get('type') == 4:  # Grid marker
                    continue
                
                # Convert milliseconds to seconds with proper precision
                start_seconds = cue['start'] / 1000.0
                
                # Determine cue name
                cue_name = cue.get('name', '')
                
                # Determine cue type (0 = memory cue, 4 = loop)
                cue_type = 4 if cue.get('len', 0) > 0 else 0
                
                # Create POSITION_MARK element
                mark_elem = ET.SubElement(track_elem, 'POSITION_MARK',
                                        Name=cue_name,
                                        Type=str(cue_type),
                                        Start=f"{start_seconds:.3f}",
                                        Num=str(cue_counter))
                
                # Add loop end if it's a loop cue
                if cue.get('len', 0) > 0:
                    end_seconds = (cue['start'] + cue['len']) / 1000.0
                    mark_elem.set('End', f"{end_seconds:.3f}")
                
                cue_counter += 1
                self.stats['cues_converted'] += 1
                
            except Exception as e:
                self.logger.warning(f"Error converting cue point: {e}")
    
    def _create_playlists_section(self, root: ET.Element, playlist_structure: List[Node],
                                 track_mapping: Dict[str, int]):
        """Create PLAYLISTS section"""
        playlists = ET.SubElement(root, 'PLAYLISTS')
        
        # Create ROOT node
        root_node = ET.SubElement(playlists, 'NODE',
                                 Type="0",
                                 Name="ROOT",
                                 Count=str(len(playlist_structure)))
        
        # Add playlist nodes
        for node in playlist_structure:
            self._add_playlist_node(root_node, node, track_mapping)
    
    def _add_playlist_node(self, parent: ET.Element, node: Node, 
                          track_mapping: Dict[str, int]):
        """Add playlist or folder node recursively"""
        if node.type == 'folder':
            # Create folder node
            folder_node = ET.SubElement(parent, 'NODE',
                                       Type="0",
                                       Name=node.name,
                                       Count=str(len(node.children)))
            
            # Add children recursively
            for child in node.children:
                self._add_playlist_node(folder_node, child, track_mapping)
                
        elif node.type in ['playlist', 'smartlist']:
            # Create playlist node
            playlist_node = ET.SubElement(parent, 'NODE',
                                         Type="1", 
                                         Name=node.name,
                                         Entries=str(len(node.tracks)))
            
            # Add track references
            for track in node.tracks:
                key = track.audio_id or track.file_path
                track_id = track_mapping.get(key)
                
                if track_id:
                    ET.SubElement(playlist_node, 'TRACK', Key=str(track_id))
            
            self.stats['playlists_exported'] += 1
    
    def _format_xml_output(self, root: ET.Element) -> str:
        """Format XML with proper indentation"""
        self._indent_xml(root)
        
        # XML declaration
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_content = ET.tostring(root, encoding='unicode')
        
        return xml_declaration + xml_content
    
    def _indent_xml(self, elem: ET.Element, level: int = 0):
        """Add XML indentation for readability"""
        indent = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent
    
    def _save_xml_file(self, xml_content: str, output_path: Path):
        """Save XML to file"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            self.logger.info(f"Rekordbox XML saved: {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving XML: {e}")
            raise
    
    def get_export_stats(self) -> Dict:
        """Get export statistics"""
        return self.stats.copy()


# Factory and utility functions
def export_nml_to_rekordbox_xml(nml_path: str, output_path: str, 
                                music_root: Optional[str] = None) -> bool:
    """Convert Traktor NML to Rekordbox XML"""
    try:
        # Parse NML
        from parser.bsm_nml_parser import create_traktor_parser
        parser = create_traktor_parser(nml_path, music_root)
        playlist_structure = parser.get_playlists_with_structure()
        
        # Collect all tracks from playlists
        all_tracks = []
        track_seen = set()
        
        def collect_tracks(nodes: List[Node]):
            for node in nodes:
                if node.type in ['playlist', 'smartlist']:
                    for track in node.tracks:
                        track_key = track.audio_id or track.file_path
                        if track_key and track_key not in track_seen:
                            all_tracks.append(track)
                            track_seen.add(track_key)
                elif node.type == 'folder':
                    collect_tracks(node.children)
        
        collect_tracks(playlist_structure)
        
        # Export to XML
        exporter = RekordboxXMLExporter()
        exporter.export_collection(all_tracks, playlist_structure, Path(output_path))
        
        return True
        
    except Exception as e:
        logging.error(f"NML to Rekordbox XML export failed: {e}")
        return False


# Example usage
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 3:
        print("Usage: python bsm_xml_exporter.py <nml_file> <output_xml> [music_root]")
        sys.exit(1)
    
    nml_file = sys.argv[1]
    output_xml = sys.argv[2]
    music_root = sys.argv[3] if len(sys.argv) > 3 else None
    
    success = export_nml_to_rekordbox_xml(nml_file, output_xml, music_root)
    
    if success:
        print(f"✓ Rekordbox XML export completed: {output_xml}")
    else:
        print("✗ Export failed")
        sys.exit(1)