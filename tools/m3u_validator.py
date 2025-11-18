#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U File Validator - Load and validate M3U/M3U8 playlist files
Checks format compliance, file integrity, and standard conformity
"""

import sys
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse, unquote
from collections import Counter
import mimetypes

class M3UValidator:
    """Validator for M3U playlist files."""
    
    def __init__(self):
        self.m3u_standards = {
            'basic': {
                'required': ['#EXTM3U'],
                'optional': [],
                'description': 'Basic M3U with header only'
            },
            'extended': {
                'required': ['#EXTM3U', '#EXTINF'],
                'optional': ['#EXTENC', '#PLAYLIST'],
                'description': 'Extended M3U with track metadata'
            },
            'vlc': {
                'required': ['#EXTM3U', '#EXTINF'],
                'optional': ['#EXTVLCOPT', '#EXTENC'],
                'description': 'VLC-compatible M3U'
            },
            'winamp': {
                'required': ['#EXTM3U', '#EXTINF'],
                'optional': ['#EXTGENRE', '#EXTALBUM', '#EXTART'],
                'description': 'Winamp-compatible M3U'
            },
            'hls': {
                'required': ['#EXTM3U', '#EXT-X-VERSION'],
                'optional': ['#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE'],
                'description': 'HTTP Live Streaming M3U8'
            }
        }
        
        self.supported_schemes = ['file', 'http', 'https', 'ftp', 'smb']
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.mp4'}
    
    def validate_file(self, file_path: str) -> Dict:
        """Validate a single M3U file."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {
                'valid': False,
                'error': f'File not found: {file_path}',
                'file_info': {}
            }
        
        try:
            # Read file with multiple encoding attempts
            content = self._read_file_safe(file_path)
            
            # Basic file info
            file_info = {
                'filename': file_path.name,
                'path': str(file_path.absolute()),
                'size_bytes': file_path.stat().st_size,
                'extension': file_path.suffix.lower()
            }
            
            # Parse and validate
            parse_result = self._parse_m3u_content(content)
            validation_result = self._validate_structure(parse_result)
            compliance_result = self._check_compliance(parse_result)
            integrity_result = self._check_file_integrity(parse_result, file_path.parent)
            
            return {
                'valid': validation_result['valid'],
                'file_info': file_info,
                'parse_result': parse_result,
                'validation': validation_result,
                'compliance': compliance_result,
                'integrity': integrity_result,
                'summary': self._generate_summary(validation_result, compliance_result, integrity_result)
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'Failed to process file: {e}',
                'file_info': file_info if 'file_info' in locals() else {}
            }
    
    def _read_file_safe(self, file_path: Path) -> str:
        """Read file with multiple encoding attempts."""
        encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        # Fallback to binary read and replace errors
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    
    def _parse_m3u_content(self, content: str) -> Dict:
        """Parse M3U content and extract structure."""
        lines = [line.strip() for line in content.split('\n')]
        
        result = {
            'raw_lines': lines,
            'total_lines': len(lines),
            'empty_lines': sum(1 for line in lines if not line),
            'comment_lines': [],
            'directive_lines': [],
            'path_lines': [],
            'tracks': [],
            'metadata': {},
            'encoding': None
        }
        
        current_track = None
        
        for line_num, line in enumerate(lines, 1):
            if not line:
                continue
            
            if line.startswith('#'):
                # This is a directive or comment
                result['directive_lines'].append({
                    'line_number': line_num,
                    'content': line,
                    'directive': self._parse_directive(line)
                })
                
                if line.startswith('#EXTINF:'):
                    # Start of new track
                    current_track = {
                        'line_number': line_num,
                        'extinf': line,
                        'extinf_parsed': self._parse_extinf(line),
                        'path': None,
                        'path_line_number': None
                    }
                
                elif line.startswith('#EXTENC:'):
                    result['encoding'] = line.split(':', 1)[1].strip()
                
                elif line.startswith('#PLAYLIST:'):
                    result['metadata']['playlist_name'] = line.split(':', 1)[1].strip()
            
            else:
                # This is a file path
                result['path_lines'].append({
                    'line_number': line_num,
                    'path': line,
                    'parsed': self._parse_path(line)
                })
                
                if current_track:
                    current_track['path'] = line
                    current_track['path_line_number'] = line_num
                    current_track['path_parsed'] = self._parse_path(line)
                    result['tracks'].append(current_track)
                    current_track = None
                else:
                    # Path without EXTINF (basic M3U)
                    result['tracks'].append({
                        'line_number': line_num,
                        'extinf': None,
                        'extinf_parsed': {},
                        'path': line,
                        'path_line_number': line_num,
                        'path_parsed': self._parse_path(line)
                    })
        
        return result
    
    def _parse_directive(self, line: str) -> Dict:
        """Parse M3U directive line."""
        if ':' not in line:
            return {'type': line, 'value': None}
        
        directive, value = line.split(':', 1)
        return {'type': directive, 'value': value.strip()}
    
    def _parse_extinf(self, line: str) -> Dict:
        """Parse EXTINF directive."""
        # Format: #EXTINF:duration,artist - title
        match = re.match(r'#EXTINF:\s*(-?\d+(?:\.\d+)?)\s*,\s*(.*)', line)
        if not match:
            return {'valid': False, 'duration': None, 'title': line}
        
        duration = float(match.group(1))
        title_info = match.group(2)
        
        # Try to split artist - title
        if ' - ' in title_info:
            parts = title_info.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        else:
            artist = None
            title = title_info.strip()
        
        return {
            'valid': True,
            'duration': duration,
            'duration_formatted': self._format_duration(duration),
            'artist': artist,
            'title': title,
            'full_title': title_info
        }
    
    def _parse_path(self, path: str) -> Dict:
        """Parse file path and extract information."""
        result = {
            'original': path,
            'type': 'unknown',
            'scheme': None,
            'is_absolute': False,
            'is_url': False,
            'exists': False,
            'extension': None,
            'filename': None
        }
        
        # Check if it's a URL
        if '://' in path:
            result['is_url'] = True
            parsed_url = urlparse(path)
            result['scheme'] = parsed_url.scheme
            result['type'] = 'url'
            
            if parsed_url.scheme in self.supported_schemes:
                result['type'] = 'supported_url'
            
            # Extract filename from URL
            url_path = unquote(parsed_url.path)
            if url_path:
                result['filename'] = Path(url_path).name
                result['extension'] = Path(url_path).suffix.lower()
        
        else:
            # Local file path
            path_obj = Path(path)
            result['is_absolute'] = path_obj.is_absolute()
            result['filename'] = path_obj.name
            result['extension'] = path_obj.suffix.lower()
            result['type'] = 'local_file'
            
            # Check if file exists (for absolute paths or relative to working dir)
            if path_obj.exists():
                result['exists'] = True
        
        # Determine if it's likely an audio file
        if result['extension'] in self.audio_extensions:
            result['is_audio'] = True
        else:
            result['is_audio'] = False
        
        return result
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 0:
            return "Unknown"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def _validate_structure(self, parse_result: Dict) -> Dict:
        """Validate M3U structure."""
        issues = []
        warnings = []
        
        # Check for M3U header
        has_header = any(d['directive']['type'] == '#EXTM3U' 
                        for d in parse_result['directive_lines'])
        
        if not has_header:
            issues.append("Missing #EXTM3U header")
        
        # Check track structure
        tracks_with_extinf = sum(1 for t in parse_result['tracks'] if t['extinf'])
        tracks_without_extinf = len(parse_result['tracks']) - tracks_with_extinf
        
        if tracks_without_extinf > 0 and tracks_with_extinf > 0:
            warnings.append(f"Mixed format: {tracks_with_extinf} tracks with EXTINF, "
                          f"{tracks_without_extinf} without")
        
        # Check for orphaned EXTINF (EXTINF without following path)
        orphaned_extinf = 0
        for i, directive in enumerate(parse_result['directive_lines']):
            if directive['directive']['type'] == '#EXTINF':
                # Check if next non-comment line is a path
                found_path = False
                for j in range(directive['line_number'], len(parse_result['raw_lines'])):
                    next_line = parse_result['raw_lines'][j].strip()
                    if next_line and not next_line.startswith('#'):
                        found_path = True
                        break
                    elif next_line.startswith('#EXTINF'):
                        break
                
                if not found_path:
                    orphaned_extinf += 1
        
        if orphaned_extinf > 0:
            issues.append(f"{orphaned_extinf} EXTINF directive(s) without file path")
        
        # Check for empty playlist
        if not parse_result['tracks']:
            warnings.append("Playlist contains no tracks")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'track_count': len(parse_result['tracks']),
            'has_header': has_header,
            'has_extinf': tracks_with_extinf > 0,
            'mixed_format': tracks_without_extinf > 0 and tracks_with_extinf > 0
        }
    
    def _check_compliance(self, parse_result: Dict) -> Dict:
        """Check compliance with various M3U standards."""
        compliance = {}
        
        # Get all directive types used
        used_directives = set()
        for directive_line in parse_result['directive_lines']:
            used_directives.add(directive_line['directive']['type'])
        
        # Check each standard
        for standard_name, standard in self.m3u_standards.items():
            required_present = all(req in used_directives for req in standard['required'])
            
            if required_present:
                compliance[standard_name] = {
                    'compliant': True,
                    'level': 'full',
                    'missing_required': [],
                    'description': standard['description']
                }
            else:
                missing = [req for req in standard['required'] if req not in used_directives]
                compliance[standard_name] = {
                    'compliant': False,
                    'level': 'none',
                    'missing_required': missing,
                    'description': standard['description']
                }
        
        # Find best matching standard
        compliant_standards = [name for name, info in compliance.items() if info['compliant']]
        best_standard = compliant_standards[0] if compliant_standards else None
        
        return {
            'standards': compliance,
            'best_match': best_standard,
            'compliant_with': compliant_standards,
            'used_directives': list(used_directives)
        }
    
    def _check_file_integrity(self, parse_result: Dict, base_dir: Path) -> Dict:
        """Check integrity of referenced files."""
        results = {
            'total_files': len(parse_result['tracks']),
            'files_found': 0,
            'files_missing': 0,
            'urls_found': 0,
            'invalid_paths': 0,
            'file_details': []
        }
        
        for track in parse_result['tracks']:
            if not track['path']:
                continue
            
            path_info = track['path_parsed']
            file_detail = {
                'path': track['path'],
                'type': path_info['type'],
                'exists': False,
                'is_audio': path_info.get('is_audio', False),
                'size_bytes': None,
                'issues': []
            }
            
            if path_info['is_url']:
                results['urls_found'] += 1
                file_detail['exists'] = 'unknown'  # Can't check URL existence easily
                
            else:
                # Local file
                if path_info['is_absolute']:
                    file_path = Path(track['path'])
                else:
                    file_path = base_dir / track['path']
                
                if file_path.exists():
                    file_detail['exists'] = True
                    file_detail['size_bytes'] = file_path.stat().st_size
                    results['files_found'] += 1
                    
                    # Check if it's actually an audio file
                    if not path_info.get('is_audio', False):
                        mime_type, _ = mimetypes.guess_type(str(file_path))
                        if mime_type and not mime_type.startswith('audio'):
                            file_detail['issues'].append('Not an audio file')
                
                else:
                    file_detail['exists'] = False
                    file_detail['issues'].append('File not found')
                    results['files_missing'] += 1
            
            results['file_details'].append(file_detail)
        
        # Calculate percentages
        if results['total_files'] > 0:
            results['found_percentage'] = (results['files_found'] / results['total_files']) * 100
            results['missing_percentage'] = (results['files_missing'] / results['total_files']) * 100
        else:
            results['found_percentage'] = 0
            results['missing_percentage'] = 0
        
        return results
    
    def _generate_summary(self, validation: Dict, compliance: Dict, integrity: Dict) -> Dict:
        """Generate overall summary."""
        severity_levels = []
        
        if not validation['valid']:
            severity_levels.append('error')
        elif validation['warnings']:
            severity_levels.append('warning')
        
        if integrity['files_missing'] > 0:
            severity_levels.append('warning')
        
        if not compliance['compliant_with']:
            severity_levels.append('error')
        
        overall_status = 'error' if 'error' in severity_levels else ('warning' if 'warning' in severity_levels else 'ok')
        
        return {
            'status': overall_status,
            'valid_structure': validation['valid'],
            'standards_compliant': len(compliance['compliant_with']) > 0,
            'best_standard': compliance['best_match'],
            'file_integrity_ok': integrity['files_missing'] == 0,
            'total_issues': len(validation['issues']),
            'total_warnings': len(validation['warnings']),
            'files_status': f"{integrity['files_found']}/{integrity['total_files']} found"
        }

def print_validation_results(result: Dict):
    """Print detailed validation results."""
    if not result['valid']:
        print(f"VALIDATION FAILED: {result.get('error', 'Unknown error')}")
        return
    
    file_info = result['file_info']
    validation = result['validation']
    compliance = result['compliance']
    integrity = result['integrity']
    summary = result['summary']
    
    print("M3U FILE VALIDATION REPORT")
    print("=" * 50)
    print(f"File: {file_info['filename']}")
    print(f"Size: {file_info['size_bytes']} bytes")
    print(f"Overall Status: {summary['status'].upper()}")
    print()
    
    print("STRUCTURE VALIDATION")
    print("-" * 30)
    print(f"Valid structure: {'YES' if validation['valid'] else 'NO'}")
    print(f"Has M3U header: {'YES' if validation['has_header'] else 'NO'}")
    print(f"Has EXTINF data: {'YES' if validation['has_extinf'] else 'NO'}")
    print(f"Track count: {validation['track_count']}")
    
    if validation['issues']:
        print("Issues:")
        for issue in validation['issues']:
            print(f"  - {issue}")
    
    if validation['warnings']:
        print("Warnings:")
        for warning in validation['warnings']:
            print(f"  - {warning}")
    print()
    
    print("STANDARDS COMPLIANCE")
    print("-" * 30)
    for standard_name, standard_info in compliance['standards'].items():
        status = "COMPLIANT" if standard_info['compliant'] else "NOT COMPLIANT"
        print(f"{standard_name}: {status}")
        if not standard_info['compliant'] and standard_info['missing_required']:
            print(f"  Missing: {', '.join(standard_info['missing_required'])}")
    
    if compliance['best_match']:
        print(f"\nBest match: {compliance['best_match']}")
    print()
    
    print("FILE INTEGRITY")
    print("-" * 30)
    print(f"Total files: {integrity['total_files']}")
    print(f"Files found: {integrity['files_found']} ({integrity['found_percentage']:.1f}%)")
    print(f"Files missing: {integrity['files_missing']} ({integrity['missing_percentage']:.1f}%)")
    print(f"URLs: {integrity['urls_found']}")
    
    if integrity['files_missing'] > 0:
        print("\nMissing files:")
        for detail in integrity['file_details']:
            if not detail['exists'] and detail['type'] != 'url':
                print(f"  - {detail['path']}")
    print()
    
    print("TRACK DETAILS")
    print("-" * 30)
    parse_result = result['parse_result']
    for i, track in enumerate(parse_result['tracks'][:10], 1):  # Show first 10
        print(f"Track {i}:")
        if track['extinf_parsed'].get('valid'):
            extinf = track['extinf_parsed']
            duration = extinf.get('duration_formatted', 'Unknown')
            title = extinf.get('full_title', 'Unknown')
            print(f"  Duration: {duration}")
            print(f"  Title: {title}")
        
        path_info = track['path_parsed']
        exists_status = "EXISTS" if path_info['exists'] else "MISSING"
        if path_info['is_url']:
            exists_status = "URL"
        print(f"  Path: {track['path']} ({exists_status})")
        print()
    
    if len(parse_result['tracks']) > 10:
        print(f"... and {len(parse_result['tracks']) - 10} more tracks")

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python m3u_validator.py <m3u_file> [m3u_file2] ...")
        print("Example: python m3u_validator.py playlist.m3u")
        sys.exit(1)
    
    validator = M3UValidator()
    
    for file_path in sys.argv[1:]:
        if len(sys.argv) > 2:
            print(f"\n{'='*60}")
            print(f"VALIDATING: {file_path}")
            print('='*60)
        
        result = validator.validate_file(file_path)
        print_validation_results(result)
        
        if len(sys.argv) > 2 and file_path != sys.argv[-1]:
            input("\nPress Enter to continue to next file...")

if __name__ == "__main__":
    main()