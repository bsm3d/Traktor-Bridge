#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U Export Inspector - Analyze exported M3U files and validate format compliance
Tests M3U export functionality and checks standard compliance
"""

import sys
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse
from collections import Counter

# Import your NML parser and M3U exporter
from parser.bsm_nml_parser import create_traktor_parser, Track, Node

class M3UInspector:
    """Inspector for M3U files and export validation."""
    
    def __init__(self):
        self.m3u_standards = {
            'basic': ['#EXTM3U'],
            'extended': ['#EXTM3U', '#EXTINF'],
            'vlc': ['#EXTM3U', '#EXTINF', '#EXTVLCOPT'],
            'winamp': ['#EXTM3U', '#EXTINF', '#EXTGENRE', '#EXTALBUM']
        }
    
    def test_m3u_export(self, nml_path: str, output_dir: str, music_root: str = None) -> Dict:
        """Test M3U export functionality and analyze results."""
        print(f"Testing M3U export from: {nml_path}")
        print(f"Output directory: {output_dir}")
        print("=" * 60)
        
        try:
            # Parse NML
            parser = create_traktor_parser(nml_path, music_root)
            structure = parser.get_playlists_with_structure()
            
            # Extract exportable data
            export_data = self._extract_export_data(structure)
            
            # Simulate M3U export (you would call your actual M3U exporter here)
            results = self._simulate_m3u_export(export_data, output_dir)
            
            # Analyze generated files
            analysis = self._analyze_m3u_files(output_dir)
            
            return {
                'success': True,
                'export_data': export_data,
                'export_results': results,
                'analysis': analysis
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _extract_export_data(self, structure: List[Node]) -> Dict:
        """Extract data that would be exported to M3U."""
        playlists = []
        all_tracks = []
        track_ids = set()
        
        def process_nodes(nodes: List[Node], path: str = ""):
            for node in nodes:
                if node.type == 'playlist':
                    playlist_data = {
                        'name': node.name,
                        'path': path,
                        'track_count': len(node.tracks),
                        'tracks': []
                    }
                    
                    for track in node.tracks:
                        track_data = self._extract_track_data(track)
                        playlist_data['tracks'].append(track_data)
                        
                        # Collect unique tracks
                        track_key = track.audio_id or track.file_path
                        if track_key and track_key not in track_ids:
                            all_tracks.append(track_data)
                            track_ids.add(track_key)
                    
                    playlists.append(playlist_data)
                
                elif node.type == 'folder':
                    folder_path = f"{path}/{node.name}" if path else node.name
                    process_nodes(node.children, folder_path)
        
        process_nodes(structure)
        
        return {
            'playlists': playlists,
            'all_tracks': all_tracks,
            'total_playlists': len(playlists),
            'total_tracks': len(all_tracks)
        }
    
    def _extract_track_data(self, track: Track) -> Dict:
        """Extract all available track data for M3U export."""
        # Get all track attributes
        track_data = {}
        
        # Standard attributes
        standard_attrs = [
            'title', 'artist', 'album', 'genre', 'year', 'bpm', 
            'musical_key', 'playtime', 'bitrate', 'file_path',
            'audio_id', 'ranking', 'comment'
        ]
        
        for attr in standard_attrs:
            value = getattr(track, attr, None)
            track_data[attr] = value
        
        # Additional metadata
        track_data['file_exists'] = bool(track.file_path and Path(track.file_path).exists())
        track_data['file_extension'] = Path(track.file_path).suffix.lower() if track.file_path else None
        track_data['duration_formatted'] = self._format_duration(track.playtime) if track.playtime else None
        
        # Cue points
        track_data['cue_points'] = len(track.cue_points) if hasattr(track, 'cue_points') else 0
        
        # M3U specific fields
        track_data['m3u_extinf'] = self._generate_extinf(track)
        track_data['m3u_path'] = self._normalize_path(track.file_path) if track.file_path else None
        
        return track_data
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration for M3U EXTINF."""
        if not seconds:
            return "0"
        return str(int(seconds))
    
    def _generate_extinf(self, track: Track) -> str:
        """Generate EXTINF line for track."""
        duration = int(track.playtime) if track.playtime else -1
        artist = track.artist or "Unknown Artist"
        title = track.title or "Unknown Title"
        return f"#EXTINF:{duration},{artist} - {title}"
    
    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path for M3U format."""
        if not file_path:
            return ""
        
        # Convert to forward slashes
        normalized = file_path.replace('\\', '/')
        
        # Check if absolute or relative
        if Path(file_path).is_absolute():
            return f"file:///{normalized}"
        else:
            return normalized
    
    def _simulate_m3u_export(self, export_data: Dict, output_dir: str) -> Dict:
        """Simulate M3U file generation and return results."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results = {
            'files_created': [],
            'tracks_exported': 0,
            'issues': []
        }
        
        for playlist in export_data['playlists']:
            # Generate M3U filename
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', playlist['name'])
            m3u_file = output_path / f"{safe_name}.m3u"
            
            try:
                # Generate M3U content
                content = self._generate_m3u_content(playlist)
                
                # Write file
                with open(m3u_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                results['files_created'].append(str(m3u_file))
                results['tracks_exported'] += len(playlist['tracks'])
                
            except Exception as e:
                results['issues'].append(f"Failed to create {m3u_file}: {e}")
        
        return results
    
    def _generate_m3u_content(self, playlist: Dict) -> str:
        """Generate M3U file content."""
        lines = ['#EXTM3U']
        lines.append(f'# Playlist: {playlist["name"]}')
        lines.append(f'# Tracks: {playlist["track_count"]}')
        lines.append('')
        
        for track in playlist['tracks']:
            # Add EXTINF line
            lines.append(track['m3u_extinf'])
            
            # Add file path
            if track['m3u_path']:
                lines.append(track['m3u_path'])
            else:
                lines.append('# Missing file path')
            
            lines.append('')
        
        return '\n'.join(lines)
    
    def _analyze_m3u_files(self, directory: str) -> Dict:
        """Analyze generated M3U files for compliance."""
        analysis = {
            'files_found': [],
            'total_files': 0,
            'compliance': {},
            'issues': [],
            'statistics': {}
        }
        
        m3u_files = list(Path(directory).glob('*.m3u'))
        analysis['total_files'] = len(m3u_files)
        
        for m3u_file in m3u_files:
            file_analysis = self._analyze_single_m3u(m3u_file)
            analysis['files_found'].append(file_analysis)
        
        # Aggregate statistics
        analysis['statistics'] = self._calculate_statistics(analysis['files_found'])
        
        return analysis
    
    def _analyze_single_m3u(self, file_path: Path) -> Dict:
        """Analyze a single M3U file."""
        analysis = {
            'filename': file_path.name,
            'size_bytes': file_path.stat().st_size,
            'line_count': 0,
            'track_count': 0,
            'has_header': False,
            'has_extinf': False,
            'compliance_level': 'invalid',
            'issues': [],
            'track_info': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            analysis['line_count'] = len(lines)
            
            # Check compliance
            content = ''.join(lines)
            
            if '#EXTM3U' in content:
                analysis['has_header'] = True
                analysis['compliance_level'] = 'basic'
            
            if '#EXTINF' in content:
                analysis['has_extinf'] = True
                analysis['compliance_level'] = 'extended'
            
            # Count tracks and analyze
            track_count = 0
            current_extinf = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                if line.startswith('#EXTINF:'):
                    current_extinf = line
                    track_count += 1
                elif line and not line.startswith('#') and current_extinf:
                    # This is a file path
                    track_info = {
                        'extinf': current_extinf,
                        'path': line,
                        'line_number': i + 1,
                        'file_exists': Path(line).exists() if not line.startswith(('http', 'file://')) else None
                    }
                    analysis['track_info'].append(track_info)
                    current_extinf = None
            
            analysis['track_count'] = track_count
            
            # Check for issues
            if not analysis['has_header']:
                analysis['issues'].append('Missing #EXTM3U header')
            
            if analysis['track_count'] == 0:
                analysis['issues'].append('No tracks found')
            
            # Check file paths
            missing_files = sum(1 for t in analysis['track_info'] 
                              if t['file_exists'] is False)
            if missing_files > 0:
                analysis['issues'].append(f'{missing_files} missing audio files')
            
        except Exception as e:
            analysis['issues'].append(f'Failed to read file: {e}')
        
        return analysis
    
    def _calculate_statistics(self, file_analyses: List[Dict]) -> Dict:
        """Calculate aggregate statistics."""
        if not file_analyses:
            return {}
        
        total_tracks = sum(f['track_count'] for f in file_analyses)
        total_size = sum(f['size_bytes'] for f in file_analyses)
        
        compliance_levels = Counter(f['compliance_level'] for f in file_analyses)
        
        return {
            'total_tracks': total_tracks,
            'total_size_bytes': total_size,
            'avg_tracks_per_playlist': total_tracks / len(file_analyses) if file_analyses else 0,
            'compliance_distribution': dict(compliance_levels),
            'files_with_issues': sum(1 for f in file_analyses if f['issues'])
        }

def print_export_data_analysis(export_data: Dict):
    """Print analysis of export data."""
    print("EXPORT DATA ANALYSIS")
    print("-" * 40)
    print(f"Total playlists: {export_data['total_playlists']}")
    print(f"Total unique tracks: {export_data['total_tracks']}")
    print()
    
    print("TRACK VARIABLES EXPORTED TO M3U:")
    print("-" * 40)
    if export_data['all_tracks']:
        sample_track = export_data['all_tracks'][0]
        for key, value in sample_track.items():
            value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            print(f"  {key}: {value_str} ({type(value).__name__})")
    print()
    
    print("PLAYLIST STRUCTURE:")
    print("-" * 40)
    for playlist in export_data['playlists'][:5]:  # Show first 5
        print(f"  {playlist['name']}: {playlist['track_count']} tracks")
        if playlist['path']:
            print(f"    Path: {playlist['path']}")
    
    if len(export_data['playlists']) > 5:
        print(f"  ... and {len(export_data['playlists']) - 5} more playlists")
    print()

def print_compliance_analysis(analysis: Dict):
    """Print M3U compliance analysis."""
    print("M3U COMPLIANCE ANALYSIS")
    print("-" * 40)
    
    stats = analysis['statistics']
    print(f"Files analyzed: {analysis['total_files']}")
    print(f"Total tracks: {stats.get('total_tracks', 0)}")
    print(f"Total size: {stats.get('total_size_bytes', 0)} bytes")
    print(f"Files with issues: {stats.get('files_with_issues', 0)}")
    print()
    
    print("COMPLIANCE LEVELS:")
    compliance = stats.get('compliance_distribution', {})
    for level, count in compliance.items():
        print(f"  {level}: {count} files")
    print()
    
    print("DETAILED FILE ANALYSIS:")
    print("-" * 40)
    for file_info in analysis['files_found']:
        print(f"File: {file_info['filename']}")
        print(f"  Tracks: {file_info['track_count']}")
        print(f"  Compliance: {file_info['compliance_level']}")
        print(f"  Size: {file_info['size_bytes']} bytes")
        
        if file_info['issues']:
            print(f"  Issues: {', '.join(file_info['issues'])}")
        else:
            print(f"  Status: OK")
        print()

def main():
    """Main function."""
    if len(sys.argv) < 3:
        print("Usage: python m3u_inspector.py <nml_file> <output_dir> [music_root]")
        print("Example: python m3u_inspector.py collection.nml ./m3u_export")
        sys.exit(1)
    
    nml_path = sys.argv[1]
    output_dir = sys.argv[2] 
    music_root = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not Path(nml_path).exists():
        print(f"NML file not found: {nml_path}")
        sys.exit(1)
    
    inspector = M3UInspector()
    result = inspector.test_m3u_export(nml_path, output_dir, music_root)
    
    if not result['success']:
        print(f"Export test failed: {result['error']}")
        sys.exit(1)
    
    # Print results
    print_export_data_analysis(result['export_data'])
    
    print("EXPORT RESULTS")
    print("-" * 40)
    export_results = result['export_results']
    print(f"Files created: {len(export_results['files_created'])}")
    print(f"Tracks exported: {export_results['tracks_exported']}")
    
    if export_results['issues']:
        print("Issues during export:")
        for issue in export_results['issues']:
            print(f"  - {issue}")
    print()
    
    print_compliance_analysis(result['analysis'])
    
    # Show sample M3U content
    if result['analysis']['files_found']:
        sample_file = Path(output_dir) / result['analysis']['files_found'][0]['filename']
        if sample_file.exists():
            print("SAMPLE M3U CONTENT:")
            print("-" * 40)
            with open(sample_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')[:20]  # First 20 lines
                for i, line in enumerate(lines, 1):
                    print(f"{i:2d}: {line}")
                if len(content.split('\n')) > 20:
                    print("... (truncated)")

if __name__ == "__main__":
    main()