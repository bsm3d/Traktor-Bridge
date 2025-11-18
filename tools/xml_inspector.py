#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML Export Inspector - Test BSM XML Exporter functionality
Tests the BSM XML Exporter and analyzes generated output
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List
from collections import Counter

# Import your NML parser and XML exporter
from parser.bsm_nml_parser import create_traktor_parser, Track, Node
from exporter.bsm_xml_exporter import RekordboxXMLExporter

class XMLExportInspector:
    """Inspector to test BSM XML Exporter functionality."""
    
    def __init__(self):
        self.expected_track_attributes = [
            'TrackID', 'Name', 'Artist', 'Album', 'Genre', 'Kind', 'Size',
            'TotalTime', 'AverageBpm', 'DateAdded', 'BitRate', 'SampleRate',
            'Location', 'Rating', 'Tonality', 'Comments'
        ]
    
    def test_export(self, nml_path: str, output_dir: str, music_root: str = None) -> Dict:
        """Test XML export from NML using BSM XML Exporter."""
        print(f"Testing BSM XML Export from: {nml_path}")
        print(f"Output directory: {output_dir}")
        print("=" * 60)
        
        try:
            # Parse NML
            parser = create_traktor_parser(nml_path, music_root)
            structure = parser.get_playlists_with_structure()
            
            # Extract data for analysis
            nml_data = self._analyze_nml_data(structure)
            
            # Test XML export
            export_result = self._test_xml_generation(nml_data, output_dir)
            
            # Analyze generated XML
            if export_result['success']:
                xml_analysis = self._analyze_generated_xml(export_result['xml_file'])
                export_result['xml_analysis'] = xml_analysis
            
            return {
                'success': True,
                'nml_data': nml_data,
                'export_result': export_result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _analyze_nml_data(self, structure: List[Node]) -> Dict:
        """Analyze NML data before export."""
        all_tracks = []
        playlists = []
        track_ids = set()
        
        def collect_data(nodes: List[Node], path: str = ""):
            for node in nodes:
                if node.type == 'playlist':
                    playlist_info = {
                        'name': node.name,
                        'path': path,
                        'track_count': len(node.tracks),
                        'sample_tracks': []
                    }
                    
                    for i, track in enumerate(node.tracks[:3]):  # Sample first 3
                        track_vars = self._extract_track_variables(track)
                        playlist_info['sample_tracks'].append(track_vars)
                        
                        # Collect unique tracks
                        track_key = track.audio_id or track.file_path
                        if track_key and track_key not in track_ids:
                            all_tracks.append(track_vars)
                            track_ids.add(track_key)
                    
                    playlists.append(playlist_info)
                
                elif node.type == 'folder':
                    folder_path = f"{path}/{node.name}" if path else node.name
                    collect_data(node.children, folder_path)
        
        collect_data(structure)
        
        return {
            'total_playlists': len(playlists),
            'total_unique_tracks': len(all_tracks),
            'playlists': playlists,
            'sample_tracks': all_tracks[:5],  # First 5 unique tracks
            'track_variables': self._get_track_variable_summary(all_tracks)
        }
    
    def _extract_track_variables(self, track: Track) -> Dict:
        """Extract variables from Track object."""
        variables = {}
        
        for attr_name in dir(track):
            if not attr_name.startswith('_') and not callable(getattr(track, attr_name)):
                value = getattr(track, attr_name, None)
                variables[attr_name] = {
                    'value': value,
                    'type': type(value).__name__,
                    'has_value': value is not None and value != ''
                }
        
        return variables
    
    def _get_track_variable_summary(self, tracks: List[Dict]) -> Dict:
        """Summarize track variables across all tracks."""
        if not tracks:
            return {}
        
        summary = {}
        for var_name in tracks[0].keys():
            has_value_count = sum(1 for track in tracks if track[var_name]['has_value'])
            sample_values = [track[var_name]['value'] for track in tracks[:3] 
                           if track[var_name]['has_value']]
            
            summary[var_name] = {
                'coverage': f"{has_value_count}/{len(tracks)}",
                'percentage': (has_value_count / len(tracks)) * 100,
                'sample_values': sample_values
            }
        
        return summary
    
    def _test_xml_generation(self, nml_data: Dict, output_dir: str) -> Dict:
        """Test actual XML generation using BSM XML Exporter."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        xml_file = output_path / "test_export.xml"
        
        try:
            # Create exporter
            exporter = RekordboxXMLExporter()
            
            # Mock tracks for exporter (simplified)
            mock_tracks = []
            for track_data in nml_data['sample_tracks']:
                track = type('MockTrack', (), {})()
                for var_name, var_info in track_data.items():
                    setattr(track, var_name, var_info['value'])
                mock_tracks.append(track)
            
            # Generate XML
            xml_content = exporter.export_collection(mock_tracks, [], xml_file)
            export_stats = exporter.get_export_stats()
            
            return {
                'success': True,
                'xml_file': xml_file,
                'file_size': xml_file.stat().st_size,
                'export_stats': export_stats,
                'xml_content_preview': xml_content[:500] + "..." if len(xml_content) > 500 else xml_content
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'xml_file': xml_file
            }
    
    def _analyze_generated_xml(self, xml_file: Path) -> Dict:
        """Analyze the XML generated by BSM exporter."""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            analysis = {
                'structure': self._analyze_xml_structure(root),
                'tracks': self._analyze_xml_tracks(root),
                'export_quality': self._assess_export_quality(root)
            }
            
            return analysis
            
        except Exception as e:
            return {'error': f'XML analysis failed: {e}'}
    
    def _analyze_xml_structure(self, root: ET.Element) -> Dict:
        """Analyze XML structure."""
        return {
            'root_tag': root.tag,
            'root_attributes': dict(root.attrib),
            'sections': [child.tag for child in root],
            'total_elements': len(list(root.iter()))
        }
    
    def _analyze_xml_tracks(self, root: ET.Element) -> Dict:
        """Analyze TRACK elements in XML."""
        tracks = root.findall('.//TRACK')
        
        if not tracks:
            return {'error': 'No TRACK elements found'}
        
        # Analyze attributes
        all_attributes = set()
        attribute_coverage = {}
        
        for track in tracks:
            all_attributes.update(track.attrib.keys())
        
        for attr in all_attributes:
            values = [track.get(attr, '') for track in tracks]
            non_empty = [v for v in values if v]
            attribute_coverage[attr] = {
                'total': len(tracks),
                'has_value': len(non_empty),
                'coverage_percent': (len(non_empty) / len(tracks)) * 100,
                'sample_value': non_empty[0] if non_empty else ''
            }
        
        return {
            'total_tracks': len(tracks),
            'attributes_found': sorted(list(all_attributes)),
            'attribute_coverage': attribute_coverage,
            'sample_track': dict(tracks[0].attrib) if tracks else {}
        }
    
    def _assess_export_quality(self, root: ET.Element) -> Dict:
        """Assess quality of the export."""
        quality = {
            'has_required_sections': True,
            'issues': [],
            'completeness_score': 0
        }
        
        # Check required sections
        required_sections = ['PRODUCT', 'COLLECTION', 'PLAYLISTS']
        for section in required_sections:
            if root.find(section) is None:
                quality['has_required_sections'] = False
                quality['issues'].append(f'Missing {section} section')
        
        # Check track completeness
        tracks = root.findall('.//TRACK')
        if tracks:
            required_attrs = ['TrackID', 'Name', 'Artist', 'Location']
            complete_tracks = 0
            
            for track in tracks:
                if all(attr in track.attrib and track.attrib[attr] for attr in required_attrs):
                    complete_tracks += 1
            
            quality['completeness_score'] = (complete_tracks / len(tracks)) * 100
            
            if quality['completeness_score'] < 100:
                quality['issues'].append(f'Only {complete_tracks}/{len(tracks)} tracks have all required attributes')
        
        return quality

def print_nml_analysis(nml_data: Dict):
    """Print NML data analysis."""
    print("NML DATA ANALYSIS")
    print("-" * 40)
    print(f"Playlists found: {nml_data['total_playlists']}")
    print(f"Unique tracks: {nml_data['total_unique_tracks']}")
    print()
    
    print("TRACK VARIABLES IN NML:")
    print("-" * 40)
    for var_name, info in nml_data['track_variables'].items():
        print(f"{var_name:20} {info['coverage']:10} ({info['percentage']:5.1f}%)")
        if info['sample_values']:
            sample = str(info['sample_values'][0])[:30] + "..." if len(str(info['sample_values'][0])) > 30 else str(info['sample_values'][0])
            print(f"{'':32} Sample: {sample}")
    print()

def print_export_results(export_result: Dict):
    """Print export test results."""
    print("XML EXPORT TEST RESULTS")
    print("-" * 40)
    
    if export_result['success']:
        print(f"Export: SUCCESS")
        print(f"File: {export_result['xml_file']}")
        print(f"Size: {export_result['file_size']} bytes")
        print(f"Stats: {export_result['export_stats']}")
        
        if 'xml_analysis' in export_result:
            xml_analysis = export_result['xml_analysis']
            
            if 'error' not in xml_analysis:
                print()
                print("GENERATED XML ANALYSIS:")
                print("-" * 30)
                
                structure = xml_analysis['structure']
                print(f"Root: {structure['root_tag']}")
                print(f"Sections: {structure['sections']}")
                print(f"Total elements: {structure['total_elements']}")
                
                tracks = xml_analysis['tracks']
                if 'error' not in tracks:
                    print(f"Tracks exported: {tracks['total_tracks']}")
                    print(f"Attributes per track: {len(tracks['attributes_found'])}")
                    print("Attributes found:", ", ".join(tracks['attributes_found']))
                    
                    print("\nAttribute Coverage:")
                    for attr, coverage in tracks['attribute_coverage'].items():
                        print(f"  {attr:20} {coverage['coverage_percent']:5.1f}% ({coverage['has_value']}/{coverage['total']})")
                
                quality = xml_analysis['export_quality']
                print(f"\nExport Quality Score: {quality['completeness_score']:.1f}%")
                if quality['issues']:
                    print("Issues found:")
                    for issue in quality['issues']:
                        print(f"  - {issue}")
    else:
        print(f"Export: FAILED")
        print(f"Error: {export_result['error']}")

def main():
    """Main function."""
    if len(sys.argv) < 3:
        print("Usage: python xml_export_inspector.py <nml_file> <output_dir> [music_root]")
        print("Example: python xml_export_inspector.py collection.nml ./xml_test")
        sys.exit(1)
    
    nml_path = sys.argv[1]
    output_dir = sys.argv[2]
    music_root = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not Path(nml_path).exists():
        print(f"NML file not found: {nml_path}")
        sys.exit(1)
    
    inspector = XMLExportInspector()
    result = inspector.test_export(nml_path, output_dir, music_root)
    
    if not result['success']:
        print(f"Inspector failed: {result['error']}")
        sys.exit(1)
    
    # Print results
    print_nml_analysis(result['nml_data'])
    print_export_results(result['export_result'])

if __name__ == "__main__":
    main()