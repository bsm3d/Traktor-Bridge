#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NML Data Inspector - Analyze Traktor NML Files
Uses the BSM NML Parser to display collection statistics and data
"""

import sys
import logging
from pathlib import Path
from collections import Counter
from typing import Dict, List

# Import your NML parser
from parser.bsm_nml_parser import create_traktor_parser, Track, Node

def analyze_nml_file(nml_path: str, music_root: str = None) -> Dict:
    """Analyze NML file and return statistics."""
    print(f"🔍 Analyzing NML file: {nml_path}")
    print("=" * 60)
    
    try:
        # Create parser
        parser = create_traktor_parser(nml_path, music_root)
        
        # Get structure
        structure = parser.get_playlists_with_structure()
        
        # Collect all tracks
        all_tracks = []
        track_ids = set()
        
        def collect_tracks(nodes: List[Node]):
            for node in nodes:
                if node.type in ['playlist', 'smartlist']:
                    for track in node.tracks:
                        track_key = track.audio_id or track.file_path
                        if track_key and track_key not in track_ids:
                            all_tracks.append(track)
                            track_ids.add(track_key)
                elif node.type == 'folder':
                    collect_tracks(node.children)
        
        collect_tracks(structure)
        
        # Analyze data
        stats = {
            'total_playlists': count_playlists(structure),
            'total_folders': count_folders(structure),
            'total_unique_tracks': len(all_tracks),
            'tracks_with_files': sum(1 for t in all_tracks if t.file_path and Path(t.file_path).exists()),
            'missing_files': sum(1 for t in all_tracks if t.file_path and not Path(t.file_path).exists()),
            'tracks_without_path': sum(1 for t in all_tracks if not t.file_path),
            'artists': Counter(t.artist for t in all_tracks if t.artist),
            'genres': Counter(t.genre for t in all_tracks if t.genre),
            'years': Counter(getattr(t, 'year', 'Unknown') for t in all_tracks),
            'keys': Counter(t.musical_key for t in all_tracks if t.musical_key),
            'bpm_ranges': categorize_bpm(all_tracks),
            'file_formats': Counter(Path(t.file_path).suffix.lower() for t in all_tracks if t.file_path),
            'cue_points': sum(len(t.cue_points) for t in all_tracks),
            'tracks_with_cues': sum(1 for t in all_tracks if t.cue_points),
            'bitrates': Counter(t.bitrate for t in all_tracks if t.bitrate),
            'duration_stats': calculate_duration_stats(all_tracks)
        }
        
        return {
            'success': True,
            'stats': stats,
            'structure': structure,
            'tracks': all_tracks
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def count_playlists(nodes: List[Node]) -> int:
    """Count total playlists recursively."""
    count = 0
    for node in nodes:
        if node.type == 'playlist':
            count += 1
        elif node.type == 'folder':
            count += count_playlists(node.children)
    return count

def count_folders(nodes: List[Node]) -> int:
    """Count total folders recursively."""
    count = 0
    for node in nodes:
        if node.type == 'folder':
            count += 1 + count_folders(node.children)
    return count

def categorize_bpm(tracks: List[Track]) -> Dict[str, int]:
    """Categorize tracks by BPM ranges."""
    categories = {
        'Unknown': 0,
        '0-70 (Slow)': 0,
        '70-90 (Downtempo)': 0,
        '90-110 (Hip-Hop)': 0,
        '110-130 (House)': 0,
        '130-150 (Techno)': 0,
        '150-180 (Drum & Bass)': 0,
        '180+ (Hardcore)': 0
    }
    
    for track in tracks:
        bpm = track.bpm
        if not bpm or bpm == 0:
            categories['Unknown'] += 1
        elif bpm < 70:
            categories['0-70 (Slow)'] += 1
        elif bpm < 90:
            categories['70-90 (Downtempo)'] += 1
        elif bpm < 110:
            categories['90-110 (Hip-Hop)'] += 1
        elif bpm < 130:
            categories['110-130 (House)'] += 1
        elif bpm < 150:
            categories['130-150 (Techno)'] += 1
        elif bpm < 180:
            categories['150-180 (Drum & Bass)'] += 1
        else:
            categories['180+ (Hardcore)'] += 1
    
    return categories

def calculate_duration_stats(tracks: List[Track]) -> Dict[str, float]:
    """Calculate duration statistics."""
    durations = [t.playtime for t in tracks if t.playtime and t.playtime > 0]
    
    if not durations:
        return {'total_hours': 0, 'avg_minutes': 0, 'shortest': 0, 'longest': 0}
    
    total_seconds = sum(durations)
    return {
        'total_hours': round(total_seconds / 3600, 2),
        'avg_minutes': round(sum(durations) / len(durations) / 60, 2),
        'shortest': round(min(durations) / 60, 2),
        'longest': round(max(durations) / 60, 2)
    }

def print_results(result: Dict):
    """Print analysis results in a formatted way."""
    if not result['success']:
        print(f"❌ Error analyzing NML: {result['error']}")
        return
    
    stats = result['stats']
    
    print("📊 COLLECTION OVERVIEW")
    print("-" * 30)
    print(f"Playlists: {stats['total_playlists']}")
    print(f"Folders: {stats['total_folders']}")
    print(f"Unique tracks: {stats['total_unique_tracks']}")
    print()
    
    print("📁 FILE STATUS")
    print("-" * 30)
    print(f"Files found: {stats['tracks_with_files']}")
    print(f"Missing files: {stats['missing_files']}")
    print(f"No file path: {stats['tracks_without_path']}")
    if stats['missing_files'] > 0:
        print(f"⚠️  {stats['missing_files']} tracks have missing audio files!")
    print()
    
    print("🎵 AUDIO DETAILS")
    print("-" * 30)
    duration = stats['duration_stats']
    print(f"Total duration: {duration['total_hours']} hours")
    print(f"Average track: {duration['avg_minutes']} minutes")
    print(f"Shortest: {duration['shortest']} min | Longest: {duration['longest']} min")
    print()
    
    print("🎚️  BPM DISTRIBUTION")
    print("-" * 30)
    for bpm_range, count in stats['bpm_ranges'].items():
        if count > 0:
            print(f"{bmp_range}: {count}")
    print()
    
    print("🔑 MUSICAL KEYS")
    print("-" * 30)
    top_keys = stats['keys'].most_common(10)
    for key, count in top_keys:
        print(f"{key}: {count}")
    print()
    
    print("🎤 TOP ARTISTS")
    print("-" * 30)
    top_artists = stats['artists'].most_common(10)
    for artist, count in top_artists:
        print(f"{artist}: {count} tracks")
    print()
    
    print("🎼 GENRES")
    print("-" * 30)
    top_genres = stats['genres'].most_common(10)
    for genre, count in top_genres:
        print(f"{genre}: {count}")
    print()
    
    print("💿 FILE FORMATS")
    print("-" * 30)
    for fmt, count in stats['file_formats'].most_common():
        print(f"{fmt.upper()}: {count}")
    print()
    
    print("🎯 CUE POINTS")
    print("-" * 30)
    print(f"Total cue points: {stats['cue_points']}")
    print(f"Tracks with cues: {stats['tracks_with_cues']}")
    if stats['tracks_with_cues'] > 0:
        avg_cues = stats['cue_points'] / stats['tracks_with_cues']
        print(f"Average cues per track: {avg_cues:.1f}")
    print()
    
    print("🔊 AUDIO QUALITY")
    print("-" * 30)
    top_bitrates = stats['bitrates'].most_common(5)
    for bitrate, count in top_bitrates:
        if bitrate:
            print(f"{bitrate} kbps: {count}")
    print()

def print_structure_tree(nodes: List[Node], indent: int = 0):
    """Print playlist structure as a tree."""
    for node in nodes:
        prefix = "  " * indent
        if node.type == 'folder':
            print(f"{prefix}📁 {node.name}")
            print_structure_tree(node.children, indent + 1)
        elif node.type == 'playlist':
            print(f"{prefix}🎵 {node.name} ({len(node.tracks)} tracks)")

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python nml_inspector.py <path_to_nml> [music_root_folder]")
        sys.exit(1)
    
    nml_path = sys.argv[1]
    music_root = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(nml_path).exists():
        print(f"❌ NML file not found: {nml_path}")
        sys.exit(1)
    
    # Set up logging
    logging.basicConfig(level=logging.WARNING)
    
    # Analyze
    result = analyze_nml_file(nml_path, music_root)
    
    # Print results
    print_results(result)
    
    if result['success']:
        print("\n" + "=" * 60)
        print("📂 PLAYLIST STRUCTURE")
        print("=" * 60)
        print_structure_tree(result['structure'])
        
        # Ask for detailed track info
        response = input("\n🔍 Show detailed track information? (y/N): ")
        if response.lower() == 'y':
            print("\n" + "=" * 60)
            print("📋 DETAILED TRACK LIST")
            print("=" * 60)
            for i, track in enumerate(result['tracks'][:20], 1):  # Show first 20
                status = "✅" if track.file_path and Path(track.file_path).exists() else "❌"
                print(f"{i:3d}. {status} {track.artist} - {track.title}")
                print(f"     🎵 {track.bpm} BPM | {track.musical_key or 'No key'} | {track.genre or 'No genre'}")
                print(f"     📁 {track.file_path or 'No file path'}")
                print()
            
            if len(result['tracks']) > 20:
                print(f"... and {len(result['tracks']) - 20} more tracks")

if __name__ == "__main__":
    main()