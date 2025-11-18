# -*- coding: utf-8 -*-
"""
Traktor Bridge - M3U Export Module
Component: bsm_m3u_exporter.py

Standard M3U playlist export compatible with all DJ software.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from parser.bsm_nml_parser import Node, Track

class M3UExporter:
    """Exports playlists to standard M3U format."""
    
    def __init__(self, output_path: str):
        self.output_path = Path(output_path)
        self.logger = logging.getLogger(__name__)
    
    def export_playlists(self, playlist_structure: List[Node], 
                        relative_paths: bool = False,
                        copy_music: bool = False) -> Path:
        """Export playlist structure to M3U format."""
        try:
            self.output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Cannot create output directory: {e}")
            raise
        
        music_dir = None
        if copy_music:
            music_dir = self.output_path / "Music"
            music_dir.mkdir(exist_ok=True)
        
        self._process_playlist_structure(
            playlist_structure, 
            self.output_path, 
            relative_paths,
            music_dir
        )
        
        return self.output_path
    
    def _process_playlist_structure(self, nodes: List[Node], current_dir: Path, 
                                   relative_paths: bool, music_dir: Optional[Path]):
        """Process playlist structure recursively."""
        for node in nodes:
            if node.type == 'folder':
                folder_dir = current_dir / self._sanitize_filename(node.name)
                folder_dir.mkdir(exist_ok=True)
                self._process_playlist_structure(
                    node.children, folder_dir, relative_paths, music_dir
                )
            elif node.type in ['playlist', 'smartlist']:
                self._export_single_playlist(node, current_dir, relative_paths, music_dir)
    
    def _export_single_playlist(self, playlist: Node, dir_path: Path, 
                               relative_paths: bool, music_dir: Optional[Path]):
        """Export single playlist to standard M3U format."""
        playlist_path = dir_path / f"{self._sanitize_filename(playlist.name)}.m3u"
        
        try:
            with open(playlist_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                
                copied_count = 0
                error_count = 0
                
                for track in playlist.tracks:
                    if track.file_path:
                        try:
                            # Normalize Traktor path
                            normalized_path = self._normalize_traktor_path(track.file_path)
                            
                            final_path = normalized_path
                            if music_dir and os.path.exists(normalized_path):
                                final_path = self._copy_music_file(track, music_dir, normalized_path)
                                copied_count += 1
                            
                            # Standard EXTINF: duration,artist - title
                            duration_sec = int(track.playtime) if track.playtime > 0 else -1
                            f.write(f"#EXTINF:{duration_sec},{track.artist} - {track.title}\n")
                            
                            # File path
                            if relative_paths and music_dir:
                                file_path = f"Music/{os.path.basename(final_path)}"
                            elif relative_paths:
                                file_path = os.path.basename(final_path)
                            else:
                                file_path = final_path
                            
                            f.write(f"{file_path}\n")
                            
                        except Exception as e:
                            self.logger.warning(f"Error processing {track.title}: {e}")
                            error_count += 1
            
            self.logger.info(f"Exported: {playlist.name} ({len(playlist.tracks)} tracks, {copied_count} copied)")
            return playlist_path
            
        except Exception as e:
            self.logger.error(f"Error exporting {playlist.name}: {e}")
            return None
    
    def _normalize_traktor_path(self, traktor_path: str) -> str:
        """Convert Traktor path format to standard path."""
        if not traktor_path:
            return ""
        
        # Remove Traktor-specific prefixes
        path = traktor_path
        if path.startswith('file://localhost/'):
            path = path[17:]
        elif path.startswith('file:///'):
            path = path[8:]
        elif path.startswith('file://'):
            path = path[7:]
        
        # Handle Traktor format /:folder/:
        if path.startswith('/:') and path.endswith('/:'):
            path = path[2:-2].replace('/:', '/')
        elif path.startswith('/:'):
            path = path[2:].replace('/:', '/')
        
        # URL decode
        path = unquote(path)
        
        # Convert to OS-specific path
        return os.path.normpath(path)
    
    def _copy_music_file(self, track: Track, music_dir: Path, source_path: str) -> str:
        """Copy music file to output directory."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        
        # Generate unique filename
        dest_filename = source.name
        dest_path = music_dir / dest_filename
        
        counter = 1
        while dest_path.exists():
            stem = source.stem
            suffix = source.suffix
            dest_filename = f"{stem}_{counter}{suffix}"
            dest_path = music_dir / dest_filename
            counter += 1
        
        shutil.copy2(source, dest_path)
        return str(dest_path)
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename for filesystem."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        name = name.strip(' .')
        return name[:100] or "Untitled"


# Factory function
def export_nml_to_m3u(nml_path: str, output_dir: str, 
                     music_root: Optional[str] = None,
                     copy_music: bool = False,
                     relative_paths: bool = True) -> bool:
    """Convert Traktor NML to M3U playlists."""
    try:
        from parser.bsm_nml_parser import create_traktor_parser
        
        parser = create_traktor_parser(nml_path, music_root)
        playlists = parser.get_playlists_with_structure()
        
        exporter = M3UExporter(output_dir)
        exporter.export_playlists(playlists, relative_paths, copy_music)
        
        return True
        
    except Exception as e:
        logging.error(f"M3U export failed: {e}")
        return False