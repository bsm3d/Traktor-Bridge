#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CDJ Export Inspector - Test and analyze BSM CDJ Exporter functionality
Tests the BSM CDJ Exporter, analyzes database structure, SQL queries, and file hierarchy
"""

import sys
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter
import json

# Import your NML parser and CDJ exporter
from parser.bsm_nml_parser import create_traktor_parser, Track, Node
from exporter.bsm_cdj_exporter import CDJExportEngine, CDJModel

# Optional SQLCipher support
try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False

class CDJExportInspector:
    """Inspector to test BSM CDJ Exporter functionality."""
    
    def __init__(self):
        self.expected_tables = [
            'djmdContent', 'djmdArtist', 'djmdAlbum', 'djmdGenre', 
            'djmdKey', 'djmdCue', 'djmdPlaylist', 'djmdSongPlaylist'
        ]
        
        self.expected_directories = [
            'PIONEER', 'PIONEER/rekordbox', 'PIONEER/USBANLZ', 'Contents'
        ]
        
        self.expected_files = [
            'PIONEER/rekordbox/export.pdb',
            'PIONEER/rekordbox/DeviceSQL.edb'
        ]
    
    def test_cdj_export(self, nml_path: str, output_dir: str, music_root: str = None, 
                       cdj_model: str = 'CDJ-3000', use_encryption: bool = True, 
                       copy_audio: bool = True) -> Dict:
        """Test CDJ export using BSM CDJ Exporter."""
        print(f"Testing BSM CDJ Export from: {nml_path}")
        print(f"Output directory: {output_dir}")
        print(f"CDJ Model: {cdj_model}")
        print(f"Encryption: {use_encryption}")
        print(f"Copy Audio: {copy_audio}")
        print("=" * 60)
        
        try:
            # Parse NML
            parser = create_traktor_parser(nml_path, music_root)
            structure = parser.get_playlists_with_structure()
            
            # Analyze NML data
            nml_analysis = self._analyze_nml_data(structure)
            
            # Test CDJ export
            export_result = self._test_cdj_generation(nml_analysis, output_dir, cdj_model, 
                                                    use_encryption, copy_audio)
            
            # Analyze generated files
            if export_result['success']:
                file_analysis = self._analyze_generated_files(output_dir)
                database_analysis = self._analyze_database(output_dir, use_encryption)
                export_result.update({
                    'file_analysis': file_analysis,
                    'database_analysis': database_analysis
                })
            
            return {
                'success': True,
                'nml_analysis': nml_analysis,
                'export_result': export_result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _analyze_nml_data(self, structure: List[Node]) -> Dict:
        """Analyze NML data before CDJ export."""
        all_tracks = []
        playlists = []
        track_ids = set()
        total_cue_points = 0
        
        def collect_data(nodes: List[Node], path: str = ""):
            nonlocal total_cue_points
            
            for node in nodes:
                if node.type == 'playlist':
                    playlist_info = {
                        'name': node.name,
                        'path': path,
                        'track_count': len(node.tracks),
                        'sample_tracks': []
                    }
                    
                    for track in node.tracks:
                        track_vars = self._extract_track_variables(track)
                        playlist_info['sample_tracks'].append(track_vars)
                        total_cue_points += len(track.cue_points) if hasattr(track, 'cue_points') else 0
                        
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
            'total_cue_points': total_cue_points,
            'playlists': playlists,
            'sample_tracks': all_tracks[:5],
            'track_variables': self._get_track_variable_summary(all_tracks),
            'audio_files_found': sum(1 for t in all_tracks if t.get('file_path', {}).get('has_value', False))
        }
    
    def _extract_track_variables(self, track: Track) -> Dict:
        """Extract all variables from Track object."""
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
        """Summarize track variables for CDJ export mapping."""
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
                'sample_values': sample_values,
                'cdj_mapping': self._get_cdj_field_mapping(var_name)
            }
        
        return summary
    
    def _get_cdj_field_mapping(self, nml_field: str) -> Optional[str]:
        """Map NML field to CDJ database field."""
        mapping = {
            'title': 'Name',
            'artist': 'Artist',
            'album': 'Album', 
            'genre': 'Genre',
            'bpm': 'AverageBpm',
            'musical_key': 'Tonality',
            'file_path': 'Location',
            'playtime': 'TotalTime',
            'bitrate': 'BitRate',
            'ranking': 'Rating',
            'comment': 'Comments',
            'year': 'Year',
            'cue_points': 'djmdCue table'
        }
        return mapping.get(nml_field)
    
    def _test_cdj_generation(self, nml_analysis: Dict, output_dir: str, cdj_model: str,
                           use_encryption: bool, copy_audio: bool) -> Dict:
        """Test actual CDJ generation using BSM CDJ Exporter."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Create CDJ model enum
            model_enum = CDJModel(cdj_model)
            
            # Create exporter
            exporter = CDJExportEngine(model_enum, use_encryption)
            
            # Mock tracks and structure for exporter
            mock_tracks = []
            mock_structure = []
            
            for track_data in nml_analysis['sample_tracks']:
                track = type('MockTrack', (), {})()
                for var_name, var_info in track_data.items():
                    setattr(track, var_name, var_info['value'])
                mock_tracks.append(track)
            
            # Export to CDJ
            result = exporter.export_collection_to_cdj(mock_tracks, mock_structure, 
                                                     output_path, copy_audio)
            
            return {
                'success': True,
                'export_result': result,
                'export_stats': result.get('stats', {}),
                'files_generated': result.get('files', []),
                'target_model': result.get('target_model', cdj_model)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _analyze_generated_files(self, output_dir: str) -> Dict:
        """Analyze the generated CDJ file structure."""
        output_path = Path(output_dir)
        
        analysis = {
            'directory_structure': {},
            'file_inventory': {},
            'anlz_files': {},
            'missing_expected': []
        }
        
        # Check directory structure
        for expected_dir in self.expected_directories:
            dir_path = output_path / expected_dir
            analysis['directory_structure'][expected_dir] = {
                'exists': dir_path.exists(),
                'is_directory': dir_path.is_dir() if dir_path.exists() else False,
                'file_count': len(list(dir_path.iterdir())) if dir_path.exists() and dir_path.is_dir() else 0
            }
        
        # Check expected files
        for expected_file in self.expected_files:
            file_path = output_path / expected_file
            if file_path.exists():
                analysis['file_inventory'][expected_file] = {
                    'exists': True,
                    'size_bytes': file_path.stat().st_size,
                    'readable': self._test_file_readable(file_path)
                }
            else:
                analysis['missing_expected'].append(expected_file)
        
        # Analyze ANLZ files
        anlz_dir = output_path / "PIONEER" / "USBANLZ"
        if anlz_dir.exists():
            anlz_files = list(anlz_dir.glob("ANLZ*.DAT")) + list(anlz_dir.glob("ANLZ*.EXT")) + list(anlz_dir.glob("ANLZ*.2EX"))
            
            analysis['anlz_files'] = {
                'total_files': len(anlz_files),
                'dat_files': len(list(anlz_dir.glob("ANLZ*.DAT"))),
                'ext_files': len(list(anlz_dir.glob("ANLZ*.EXT"))), 
                'ex2_files': len(list(anlz_dir.glob("ANLZ*.2EX"))),
                'sample_files': [{'name': f.name, 'size': f.stat().st_size} for f in anlz_files[:5]]
            }
        
        # Check Contents directory
        contents_dir = output_path / "Contents"
        if contents_dir.exists():
            audio_files = [f for f in contents_dir.iterdir() if f.suffix.lower() in ['.mp3', '.wav', '.flac', '.m4a']]
            analysis['contents_directory'] = {
                'exists': True,
                'total_files': len(list(contents_dir.iterdir())),
                'audio_files': len(audio_files),
                'sample_audio': [f.name for f in audio_files[:5]]
            }
        
        return analysis
    
    def _test_file_readable(self, file_path: Path) -> bool:
        """Test if a file is readable."""
        try:
            with open(file_path, 'rb') as f:
                f.read(10)
            return True
        except Exception:
            return False
    
    def _analyze_database(self, output_dir: str, use_encryption: bool) -> Dict:
        """Analyze the generated CDJ database."""
        db_path = Path(output_dir) / "PIONEER" / "rekordbox" / "export.pdb"
        
        if not db_path.exists():
            return {'error': 'Database file not found'}
        
        try:
            analysis = {
                'database_info': {
                    'file_size': db_path.stat().st_size,
                    'encryption_used': use_encryption,
                    'sqlcipher_available': SQLCIPHER_AVAILABLE
                },
                'table_analysis': {},
                'sql_queries_results': {},
                'data_integrity': {}
            }
            
            # Connect to database
            if use_encryption and SQLCIPHER_AVAILABLE:
                conn = sqlcipher.connect(str(db_path))
                conn.execute("PRAGMA key = \"x'402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43a3d643'\"")
            else:
                conn = sqlite3.connect(str(db_path))
            
            try:
                # Analyze tables
                cursor = conn.cursor()
                
                # Get all tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                
                analysis['table_analysis']['tables_found'] = tables
                analysis['table_analysis']['expected_tables'] = self.expected_tables
                analysis['table_analysis']['missing_tables'] = [t for t in self.expected_tables if t not in tables]
                
                # Analyze each table
                for table in tables:
                    if table in self.expected_tables:
                        analysis['table_analysis'][table] = self._analyze_table(cursor, table)
                
                # Execute test queries
                analysis['sql_queries_results'] = self._execute_test_queries(cursor)
                
                # Check data integrity
                analysis['data_integrity'] = self._check_data_integrity(cursor)
                
            finally:
                conn.close()
            
            return analysis
            
        except Exception as e:
            return {'error': f'Database analysis failed: {e}'}
    
    def _analyze_table(self, cursor: sqlite3.Cursor, table_name: str) -> Dict:
        """Analyze a specific database table."""
        analysis = {}
        
        try:
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            analysis['columns'] = [{'name': col[1], 'type': col[2], 'not_null': bool(col[3]), 
                                  'default': col[4], 'primary_key': bool(col[5])} for col in columns]
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            analysis['row_count'] = cursor.fetchone()[0]
            
            # Get sample data (first 3 rows)
            if analysis['row_count'] > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
                sample_rows = cursor.fetchall()
                column_names = [col['name'] for col in analysis['columns']]
                
                analysis['sample_data'] = []
                for row in sample_rows:
                    row_dict = dict(zip(column_names, row))
                    analysis['sample_data'].append(row_dict)
            
        except Exception as e:
            analysis['error'] = str(e)
        
        return analysis
    
    def _execute_test_queries(self, cursor: sqlite3.Cursor) -> Dict:
        """Execute test SQL queries to verify database functionality."""
        queries = {
            'total_tracks': "SELECT COUNT(*) FROM djmdContent;",
            'total_artists': "SELECT COUNT(*) FROM djmdArtist;",
            'total_cues': "SELECT COUNT(*) FROM djmdCue;",
            'tracks_with_bpm': "SELECT COUNT(*) FROM djmdContent WHERE AverageBpm > 0;",
            'tracks_by_genre': "SELECT g.Name, COUNT(*) as track_count FROM djmdContent c JOIN djmdGenre g ON c.GenreID = g.ID GROUP BY g.Name LIMIT 5;",
            'sample_track_info': "SELECT ID, Name, Artist, AverageBpm, Location FROM djmdContent LIMIT 3;",
            'cue_points_sample': "SELECT ContentID, InMsec, Kind, Comment FROM djmdCue LIMIT 5;",
            'key_distribution': "SELECT k.ScaleName, COUNT(*) as count FROM djmdContent c JOIN djmdKey k ON c.KeyID = k.ID GROUP BY k.ScaleName LIMIT 10;"
        }
        
        results = {}
        
        for query_name, sql in queries.items():
            try:
                cursor.execute(sql)
                result = cursor.fetchall()
                
                # Format results based on query type
                if query_name in ['total_tracks', 'total_artists', 'total_cues', 'tracks_with_bpm']:
                    results[query_name] = result[0][0] if result else 0
                elif query_name in ['tracks_by_genre', 'key_distribution']:
                    results[query_name] = [{'name': row[0], 'count': row[1]} for row in result]
                elif query_name == 'sample_track_info':
                    results[query_name] = [{'ID': row[0], 'Name': row[1], 'Artist': row[2], 
                                          'BPM': row[3], 'Location': row[4]} for row in result]
                elif query_name == 'cue_points_sample':
                    results[query_name] = [{'ContentID': row[0], 'InMsec': row[1], 
                                          'Kind': row[2], 'Comment': row[3]} for row in result]
                else:
                    results[query_name] = result
                    
            except Exception as e:
                results[query_name] = {'error': str(e)}
        
        return results
    
    def _check_data_integrity(self, cursor: sqlite3.Cursor) -> Dict:
        """Check data integrity in the database."""
        integrity = {
            'foreign_key_violations': [],
            'null_critical_fields': [],
            'data_consistency': {}
        }
        
        try:
            # Check foreign key constraints
            fk_checks = [
                ("djmdContent.ArtistID -> djmdArtist.ID", 
                 "SELECT COUNT(*) FROM djmdContent c LEFT JOIN djmdArtist a ON c.ArtistID = a.ID WHERE c.ArtistID > 0 AND a.ID IS NULL;"),
                ("djmdCue.ContentID -> djmdContent.ID",
                 "SELECT COUNT(*) FROM djmdCue cu LEFT JOIN djmdContent c ON cu.ContentID = c.ID WHERE cu.ContentID > 0 AND c.ID IS NULL;")
            ]
            
            for check_name, query in fk_checks:
                cursor.execute(query)
                violations = cursor.fetchone()[0]
                if violations > 0:
                    integrity['foreign_key_violations'].append({
                        'constraint': check_name,
                        'violations': violations
                    })
            
            # Check for null critical fields
            null_checks = [
                ("djmdContent.Name", "SELECT COUNT(*) FROM djmdContent WHERE Name IS NULL OR Name = '';"),
                ("djmdContent.Location", "SELECT COUNT(*) FROM djmdContent WHERE Location IS NULL OR Location = '';")
            ]
            
            for field_name, query in null_checks:
                cursor.execute(query)
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    integrity['null_critical_fields'].append({
                        'field': field_name,
                        'null_count': null_count
                    })
            
            # Data consistency checks
            cursor.execute("SELECT COUNT(*) FROM djmdContent;")
            total_tracks = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT TrackID) FROM djmdContent;")
            unique_track_ids = cursor.fetchone()[0]
            
            integrity['data_consistency']['duplicate_track_ids'] = total_tracks - unique_track_ids
            
        except Exception as e:
            integrity['error'] = str(e)
        
        return integrity

def print_nml_analysis(nml_analysis: Dict):
    """Print NML analysis results."""
    print("NML DATA ANALYSIS")
    print("-" * 40)
    print(f"Playlists: {nml_analysis['total_playlists']}")
    print(f"Unique tracks: {nml_analysis['total_unique_tracks']}")
    print(f"Total cue points: {nml_analysis['total_cue_points']}")
    print(f"Audio files found: {nml_analysis['audio_files_found']}")
    print()
    
    print("TRACK VARIABLES → CDJ MAPPING:")
    print("-" * 40)
    for var_name, info in nml_analysis['track_variables'].items():
        cdj_field = info['cdj_mapping'] or 'Not mapped'
        print(f"{var_name:20} → {cdj_field:20} {info['coverage']:10} ({info['percentage']:5.1f}%)")
    print()

def print_export_results(export_result: Dict):
    """Print CDJ export results."""
    print("CDJ EXPORT RESULTS")
    print("-" * 40)
    
    if export_result['success']:
        print(f"Export: SUCCESS")
        print(f"Target model: {export_result['target_model']}")
        print(f"Export stats: {export_result['export_stats']}")
        print(f"Files generated: {len(export_result['files_generated'])}")
        
        # File analysis
        if 'file_analysis' in export_result:
            print_file_analysis(export_result['file_analysis'])
        
        # Database analysis
        if 'database_analysis' in export_result:
            print_database_analysis(export_result['database_analysis'])
    else:
        print(f"Export: FAILED")
        print(f"Error: {export_result['error']}")

def print_file_analysis(file_analysis: Dict):
    """Print file structure analysis."""
    print("\nFILE STRUCTURE ANALYSIS")
    print("-" * 40)
    
    print("Directory Structure:")
    for dir_name, info in file_analysis['directory_structure'].items():
        status = "✓" if info['exists'] else "✗"
        print(f"  {status} {dir_name} ({info['file_count']} files)")
    
    if file_analysis['missing_expected']:
        print(f"\nMissing expected files:")
        for missing in file_analysis['missing_expected']:
            print(f"  ✗ {missing}")
    
    print(f"\nFile Inventory:")
    for file_name, info in file_analysis['file_inventory'].items():
        readable = "readable" if info['readable'] else "not readable"
        print(f"  ✓ {file_name} ({info['size_bytes']} bytes, {readable})")
    
    if 'anlz_files' in file_analysis:
        anlz = file_analysis['anlz_files']
        print(f"\nANLZ Files:")
        print(f"  Total: {anlz['total_files']}")
        print(f"  .DAT files: {anlz['dat_files']}")
        print(f"  .EXT files: {anlz['ext_files']}")
        print(f"  .2EX files: {anlz['ex2_files']}")

def print_database_analysis(db_analysis: Dict):
    """Print database analysis results with SQL queries shown."""
    print("\nDATABASE ANALYSIS")
    print("-" * 40)
    
    if 'error' in db_analysis:
        print(f"Database analysis error: {db_analysis['error']}")
        return
    
    db_info = db_analysis['database_info']
    print(f"Database size: {db_info['file_size']} bytes")
    print(f"Encryption: {db_info['encryption_used']}")
    print(f"SQLCipher available: {db_info['sqlcipher_available']}")
    
    # Table analysis
    tables = db_analysis['table_analysis']
    print(f"\nTables found: {len(tables['tables_found'])}")
    if tables['missing_tables']:
        print(f"Missing tables: {tables['missing_tables']}")
    
    print("\nTable Details:")
    for table in ['djmdContent', 'djmdArtist', 'djmdCue']:
        if table in tables:
            info = tables[table]
            if 'error' not in info:
                print(f"  {table}: {info['row_count']} rows, {len(info['columns'])} columns")
    
    # SQL Query Results with SQL statements shown
    print("\nSQL QUERY RESULTS:")
    print("-" * 30)
    queries = db_analysis['sql_queries_results']
    
    for query_name, query_info in queries.items():
        if isinstance(query_info, dict) and 'error' in query_info and 'sql_statement' not in query_info:
            # Old format
            print(f"{query_name}: ERROR - {query_info['error']}")
        elif isinstance(query_info, dict) and 'sql_statement' in query_info:
            # New format with SQL shown
            print(f"\n{query_name}:")
            print(f"  SQL: {query_info['sql_statement']}")
            print(f"  Time: {query_info['execution_time_ms']}ms")
            
            if query_info['error']:
                print(f"  ERROR: {query_info['error']}")
            elif query_info['result'] is not None:
                result = query_info['result']
                if query_name in ['total_tracks', 'total_artists', 'total_cues', 'tracks_with_bpm']:
                    print(f"  Result: {result}")
                elif query_name in ['tracks_by_genre', 'key_distribution']:
                    print(f"  Results:")
                    for item in result[:3]:
                        print(f"    {item['name']}: {item['count']}")
                elif query_name == 'sample_track_info':
                    print(f"  Sample tracks:")
                    for track in result:
                        print(f"    ID:{track['ID']} - {track['Artist']} - {track['Name']} ({track['BPM']} BPM)")
                elif query_name == 'export_structure_check':
                    print(f"  Table structure ({len(result)} columns):")
                    for col in result[:5]:  # Show first 5 columns
                        print(f"    {col['column']} ({col['type']})")
                elif query_name == 'database_schema':
                    print(f"  Tables in schema:")
                    for table in result:
                        print(f"    {table['table']}")
        else:
            # Legacy format
            if query_name in ['total_tracks', 'total_artists', 'total_cues', 'tracks_with_bpm']:
                print(f"{query_name}: {query_info}")
            elif query_name in ['tracks_by_genre', 'key_distribution']:
                print(f"{query_name}:")
                for item in query_info[:3]:
                    print(f"  {item['name']}: {item['count']}")
    
    # Data integrity
    integrity = db_analysis['data_integrity']
    if 'error' not in integrity:
        print(f"\nDATA INTEGRITY:")
        print(f"Foreign key violations: {len(integrity['foreign_key_violations'])}")
        print(f"Null critical fields: {len(integrity['null_critical_fields'])}")
        if integrity['data_consistency']['duplicate_track_ids'] > 0:
            print(f"Duplicate TrackIDs: {integrity['data_consistency']['duplicate_track_ids']}")

def print_sql_construction_analysis(sql_analysis: Dict):
    """Print SQL construction analysis."""
    if 'error' in sql_analysis:
        print(f"\nSQL construction analysis error: {sql_analysis['error']}")
        return
    
    print("\nSQL CONSTRUCTION ANALYSIS")
    print("-" * 40)
    
    # Table creation analysis
    if 'table_creation_analysis' in sql_analysis:
        print("Table Creation Statements:")
        for table_name, info in sql_analysis['table_creation_analysis'].items():
            print(f"\n  {table_name}:")
            print(f"    Columns: {info['column_count']}")
            print(f"    Has PK: {info['has_primary_key']}")
            print(f"    Has FK: {info['has_foreign_keys']}")
            if len(info['create_statement']) < 200:
                print(f"    SQL: {info['create_statement']}")
            else:
                print(f"    SQL: {info['create_statement'][:200]}...")
    
    # Query performance
    if 'query_performance' in sql_analysis:
        print(f"\nQuery Performance Tests:")
        for test_name, perf_info in sql_analysis['query_performance'].items():
            status = "✓" if perf_info['success'] else "✗"
            print(f"  {status} {test_name}:")
            print(f"    SQL: {perf_info['sql']}")
            if perf_info['success']:
                print(f"    Time: {perf_info['execution_time_ms']}ms")
            else:
                print(f"    Error: {perf_info['error']}")
    
    # SQL syntax validation
    if 'sql_syntax_validation' in sql_analysis:
        print(f"\nSQL Syntax Validation:")
        for check_name, check_info in sql_analysis['sql_syntax_validation'].items():
            print(f"  {check_name}:")
            print(f"    SQL: {check_info['sql']}")
            if 'error' in check_info:
                print(f"    Error: {check_info['error']}")
            else:
                print(f"    Issues: {check_info.get('issues_found', 0)}")

def print_compatibility_results(compatibility: Dict):
    """Print module compatibility results."""
    print("MODULE COMPATIBILITY")
    print("-" * 40)
    
    print(f"SQLCipher available: {compatibility['sqlcipher_available']}")
    print(f"DatabaseManager available: {compatibility['db_manager_available']}")
    print(f"ConversionThread available: {compatibility['conversion_thread_available']}")
    
    if 'db_manager_test' in compatibility:
        db_test = compatibility['db_manager_test']
        if 'error' in db_test:
            print(f"DatabaseManager test: FAILED - {db_test['error']}")
        else:
            print(f"DatabaseManager test: PASSED")
            print(f"  Instantiation: {db_test.get('instantiation', False)}")
            print(f"  Has create_database_structure: {db_test.get('expected_tables', False)}")
    
    if 'conversion_test' in compatibility:
        conv_test = compatibility['conversion_test']
        if 'error' in conv_test:
            print(f"ConversionThread test: FAILED - {conv_test['error']}")
        else:
            print(f"ConversionThread test: PASSED")
            print(f"  Has database export method: {conv_test.get('has_database_export', False)}")

def print_export_results(export_result: Dict):
    """Print CDJ export results with enhanced SQL analysis."""
    print("CDJ EXPORT RESULTS")
    print("-" * 40)
    
    if export_result['success']:
        print(f"Export: SUCCESS")
        print(f"Target model: {export_result['target_model']}")
        print(f"Export stats: {export_result['export_stats']}")
        print(f"Files generated: {len(export_result['files_generated'])}")
        
        # File analysis
        if 'file_analysis' in export_result:
            print_file_analysis(export_result['file_analysis'])
        
        # Database analysis
        if 'database_analysis' in export_result:
            print_database_analysis(export_result['database_analysis'])
        
        # SQL construction analysis
        if 'sql_construction_analysis' in export_result:
            print_sql_construction_analysis(export_result['sql_construction_analysis'])
    else:
        print(f"Export: FAILED")
        print(f"Error: {export_result['error']}")

def main():
    """Main function with enhanced compatibility testing."""
    if len(sys.argv) < 3:
        print("Usage: python cdj_export_inspector.py <nml_file> <output_dir> [options]")
        print("Options:")
        print("  --music-root <path>     Music root directory")
        print("  --model <model>         CDJ model (CDJ-2000NXS2, CDJ-3000)")
        print("  --no-encryption         Disable database encryption")
        print("  --no-copy-audio         Skip audio file copying")
        print("  --test-compatibility    Test module compatibility only")
        print("Example: python cdj_export_inspector.py collection.nml ./cdj_test --model CDJ-3000")
        sys.exit(1)
    
    # Check for compatibility test only
    if '--test-compatibility' in sys.argv:
        inspector = CDJExportInspector()
        compatibility = inspector._test_module_compatibility()
        print_compatibility_results(compatibility)
        sys.exit(0)
    
    nml_path = sys.argv[1]
    output_dir = sys.argv[2]
    
    # Parse options
    music_root = None
    cdj_model = 'CDJ-3000'
    use_encryption = True
    copy_audio = True
    
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == '--music-root' and i + 1 < len(sys.argv):
            music_root = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--model' and i + 1 < len(sys.argv):
            cdj_model = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--no-encryption':
            use_encryption = False
            i += 1
        elif sys.argv[i] == '--no-copy-audio':
            copy_audio = False
            i += 1
        else:
            i += 1
    
    if not Path(nml_path).exists():
        print(f"NML file not found: {nml_path}")
        sys.exit(1)
    
    inspector = CDJExportInspector()
    result = inspector.test_cdj_export(nml_path, output_dir, music_root, 
                                      cdj_model, use_encryption, copy_audio)
    
    if not result['success']:
        print(f"Inspector failed: {result['error']}")
        sys.exit(1)
    
    # Print results
    if 'compatibility' in result:
        print_compatibility_results(result['compatibility'])
        print()
    
    print_nml_analysis(result['nml_analysis'])
    print_export_results(result['export_result_direct'])
    
    # Show thread test results if available
    if 'export_result_thread' in result:
        thread_result = result['export_result_thread']
        print(f"\nCONVERSION THREAD TEST:")
        print(f"Thread creation: {'SUCCESS' if thread_result['success'] else 'FAILED'}")
        if thread_result['success']:
            print(f"Method available: {thread_result['method_available']}")
            print(f"Settings applied: {thread_result['settings_applied']}")
        else:
            print(f"Error: {thread_result['error']}")

if __name__ == "__main__":
    main()