# -*- coding: utf-8 -*-
"""
Traktor Bridge - Rekordbox Software Export Engine
Component: bsm_rekordbox_exporter.py

Generates files for Rekordbox SOFTWARE (not CDJ hardware):
- SQLite/SQLCipher database (.pdb format for Rekordbox software)
- ANLZ files for Rekordbox visualization
- Compatible with BSM NML Parser output

Note: This exports to Rekordbox SOFTWARE format, not CDJ hardware format.
For CDJ hardware export, use bsm_cdj_exporter.py instead.
"""

import logging
import struct
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, BinaryIO
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager
from datetime import datetime

from parser.bsm_nml_parser import Track, Node, TraktorNMLParser
from utils.file_validator import AudioFileValidator

# Optional dependencies
try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False

try:
    import librosa
    import numpy as np
    AUDIO_ANALYSIS_AVAILABLE = True
except ImportError:
    AUDIO_ANALYSIS_AVAILABLE = False

class RekordboxVersion(Enum):
    """Supported Rekordbox software versions"""
    RB6 = "6.x"
    RB7 = "7.x"

@dataclass
class ANLZSection:
    """ANLZ section with binary data for Rekordbox visualization"""
    fourcc: str
    header_length: int
    payload: bytes
    
    def to_bytes(self) -> bytes:
        """Generate section bytes"""
        header = struct.pack('>4sII', 
                           self.fourcc.encode('ascii'),
                           self.header_length,
                           len(self.payload))
        return header + self.payload

class RekordboxDatabaseManager:
    """Database manager for Rekordbox SOFTWARE with SQLCipher support"""
    
    def __init__(self, db_path: str, use_encryption: bool = True):
        self.db_path = Path(db_path)
        self.use_encryption = use_encryption and SQLCIPHER_AVAILABLE
        self._lock = threading.RLock()
        
        # Standard Rekordbox software encryption key
        self.encryption_key = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43a3d643"
        
    @contextmanager
    def get_connection(self):
        """Context manager with SQLCipher support for Rekordbox software"""
        conn = None
        try:
            if self.use_encryption:
                conn = sqlcipher.connect(str(self.db_path))
                conn.execute(f"PRAGMA key = \"x'{self.encryption_key}'\"")
                conn.execute("PRAGMA cipher_compatibility = 4")
            else:
                conn = sqlite3.connect(str(self.db_path))
            
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            
        finally:
            if conn:
                conn.close()
    
    def create_rekordbox_database_structure(self):
        """Create complete Rekordbox SOFTWARE database structure"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Main content table for Rekordbox software
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdContent (
                ID INTEGER PRIMARY KEY,
                FolderPath TEXT,
                FileNameL TEXT,
                FileNameS TEXT,
                Title TEXT,
                ArtistID INTEGER,
                AlbumID INTEGER,
                GenreID INTEGER,
                LabelID INTEGER,
                BPM REAL,
                Length INTEGER,
                BitRate INTEGER,
                BitDepth INTEGER,
                TrackNo INTEGER,
                Rating INTEGER,
                FileType INTEGER,
                Comment TEXT,
                AnalysisDataPath TEXT,
                FileSize INTEGER,
                SampleRate INTEGER,
                Analysed INTEGER,
                ReleaseDate TEXT,
                DateCreated TEXT,
                HotCueAutoLoad TEXT,
                AutoGain REAL,
                KeyID INTEGER,
                ColorID INTEGER,
                ArtworkID INTEGER,
                UUID TEXT,
                rb_data_status INTEGER,
                rb_local_data_status INTEGER,
                rb_local_deleted INTEGER,
                rb_local_synced INTEGER,
                usn INTEGER,
                rb_local_usn INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            # Reference tables for Rekordbox software
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdArtist (
                ID INTEGER PRIMARY KEY,
                Name TEXT,
                rb_data_status INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdAlbum (
                ID INTEGER PRIMARY KEY,
                Name TEXT,
                ArtistID INTEGER,
                rb_data_status INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdGenre (
                ID INTEGER PRIMARY KEY,
                Name TEXT,
                rb_data_status INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdKey (
                ID INTEGER PRIMARY KEY,
                ScaleName TEXT,
                Seq INTEGER,
                rb_data_status INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS djmdCue (
                ID INTEGER PRIMARY KEY,
                ContentID INTEGER,
                InMsec INTEGER,
                InFrame INTEGER,
                InMpegFrame INTEGER,
                InMpegAbs INTEGER,
                OutMsec INTEGER,
                OutFrame INTEGER,
                OutMpegFrame INTEGER,
                OutMpegAbs INTEGER,
                Kind INTEGER,
                Color INTEGER,
                ActiveLoop INTEGER,
                Comment TEXT,
                BeatLoopSize INTEGER,
                CueMicrosec INTEGER,
                ContentUUID TEXT,
                UUID TEXT,
                rb_data_status INTEGER,
                rb_local_data_status INTEGER,
                rb_local_deleted INTEGER,
                rb_local_synced INTEGER,
                usn INTEGER,
                rb_local_usn INTEGER,
                created_at TEXT,
                updated_at TEXT
            )''')
            
            conn.commit()
            self._populate_rekordbox_reference_tables(cursor)
    
    def _populate_rekordbox_reference_tables(self, cursor):
        """Populate reference tables with standard Rekordbox values"""
        # Keys (Open Key format for Rekordbox software)
        keys = [
            (1, "1A", 1), (2, "2A", 2), (3, "3A", 3), (4, "4A", 4),
            (5, "5A", 5), (6, "6A", 6), (7, "7A", 7), (8, "8A", 8),
            (9, "9A", 9), (10, "10A", 10), (11, "11A", 11), (12, "12A", 12),
            (13, "1B", 13), (14, "2B", 14), (15, "3B", 15), (16, "4B", 16),
            (17, "5B", 17), (18, "6B", 18), (19, "7B", 19), (20, "8B", 20),
            (21, "9B", 21), (22, "10B", 22), (23, "11B", 23), (24, "12B", 24)
        ]
        
        cursor.executemany("INSERT OR IGNORE INTO djmdKey (ID, ScaleName, Seq, rb_data_status, created_at, updated_at) VALUES (?, ?, ?, 0, datetime('now'), datetime('now'))", keys)

class RekordboxAudioAnalyzer:
    """Audio analysis for Rekordbox software visualization"""
    
    def __init__(self):
        self.available = AUDIO_ANALYSIS_AVAILABLE
     
        # Suppress librosa/mpg123 warnings
        if self.available:
            import warnings
            warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
            
    def analyze_track_for_rekordbox(self, file_path: str) -> Dict:
        """Analyze audio file for Rekordbox software waveforms"""
        if not self.available or not Path(file_path).exists():
            return self._get_default_rekordbox_analysis()
        
        try:
            y, sr = librosa.load(file_path, sr=44100, mono=True)
            
            # BPM and beat tracking for Rekordbox
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
            
            # Waveform generation for Rekordbox visualization
            waveform_data = self._generate_rekordbox_waveform(y, sr)
            color_waveform = self._generate_rekordbox_color_waveform(y, sr)
            
            # Beat grid for Rekordbox
            beat_grid = self._generate_rekordbox_beat_grid(beats, tempo)
            
            return {
                'bpm': float(tempo),
                'waveform': waveform_data,
                'color_waveform': color_waveform,
                'beat_grid': beat_grid,
                'duration': len(y) / sr
            }
            
        except Exception as e:
            logging.warning(f"Rekordbox audio analysis failed for {file_path}: {e}")
            return self._get_default_rekordbox_analysis()
    
    def _get_default_rekordbox_analysis(self) -> Dict:
        """Default analysis for Rekordbox software when audio processing unavailable"""
        return {
            'bpm': 120.0,
            'waveform': bytes([128] * 400),
            'color_waveform': bytes([64, 64, 64] * 1200),
            'beat_grid': [],
            'duration': 180.0
        }
    
    def _generate_rekordbox_waveform(self, y, sr) -> bytes:
        """Generate 400-byte monochrome waveform for Rekordbox"""
        if len(y) == 0:
            return bytes([128] * 400)
        
        samples_per_point = len(y) / 400
        waveform = bytearray(400)
        
        for i in range(400):
            start_idx = int(i * samples_per_point)
            end_idx = int(min((i + 1) * samples_per_point, len(y)))
            
            if start_idx < end_idx:
                chunk = y[start_idx:end_idx]
                amplitude = np.max(np.abs(chunk))
                waveform[i] = int(np.clip(amplitude * 255, 0, 255))
            else:
                waveform[i] = 0
        
        return bytes(waveform)

    def _generate_rekordbox_color_waveform(self, y, sr) -> bytes:
        """Generate color waveform for Rekordbox software visualization"""
        if len(y) == 0:
            return bytes([64, 64, 64] * 1200)
        
        samples_per_point = len(y) / 1200
        color_waveform = bytearray()
        
        for i in range(1200):
            start_idx = int(i * samples_per_point)
            end_idx = int(min((i + 1) * samples_per_point, len(y)))
            
            if start_idx < end_idx and end_idx - start_idx > 512:
                chunk = y[start_idx:end_idx]
                
                fft = np.abs(np.fft.rfft(chunk, n=1024))
                
                low = np.mean(fft[:85])
                mid = np.mean(fft[85:341])
                high = np.mean(fft[341:])
                
                low_val = int(np.clip(low * 1000, 0, 255))
                mid_val = int(np.clip(mid * 1000, 0, 255))
                high_val = int(np.clip(high * 1000, 0, 255))
                
                color_waveform.extend([low_val, mid_val, high_val])
            else:
                color_waveform.extend([32, 32, 32])
        
        return bytes(color_waveform)
    
    def _generate_rekordbox_beat_grid(self, beats, tempo) -> List[Dict]:
        """Generate beat grid for Rekordbox software"""
        beat_grid = []
        
        for i, beat_time in enumerate(beats):
            beat_grid.append({
                'time_ms': int(beat_time * 1000),
                'beat_number': (i % 4) + 1,
                'tempo': float(tempo)
            })
        
        return beat_grid

class RekordboxExportEngine:
    """Export engine for Rekordbox SOFTWARE (not CDJ hardware)"""
    
    def __init__(self, rekordbox_version: RekordboxVersion = RekordboxVersion.RB6, use_encryption: bool = True, progress_queue=None):
        self.rekordbox_version = rekordbox_version
        self.use_encryption = use_encryption
        self.logger = logging.getLogger(__name__)
        self.audio_analyzer = RekordboxAudioAnalyzer()
        self.progress_queue = progress_queue
        
        self.export_stats = {
            'database_created': False,
            'anlz_files': 0,
            'tracks_processed': 0,
            'errors': 0
        }
    
    def export_collection_to_rekordbox(self, tracks: List[Track], playlist_structure: List[Node], output_dir: Path, copy_audio: bool = True) -> Dict:
        """Export complete collection to Rekordbox SOFTWARE format"""
        output_dir = Path(output_dir)
        
        # Create Rekordbox software directory structure
        pioneer_dir = output_dir / "PIONEER"
        rekordbox_dir = pioneer_dir / "rekordbox"
        anlz_dir = pioneer_dir / "USBANLZ"
        contents_dir = output_dir / "Contents"
        
        for directory in [pioneer_dir, rekordbox_dir, anlz_dir, contents_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self._reset_stats()
        generated_files = []
        total_tracks = len(tracks)
        
        # Generate ANLZ files for Rekordbox visualization
        for i, track in enumerate(tracks, 1):
            try:
                anlz_files = self._generate_rekordbox_anlz_files(track, anlz_dir, i, total_tracks)
                generated_files.extend(anlz_files)
                self.export_stats['tracks_processed'] += 1
            except Exception as e:
                self.logger.error(f"Rekordbox ANLZ error for {track.title}: {e}")
                self.export_stats['errors'] += 1
        
        # Copy audio files if requested
        if copy_audio:
            self._copy_audio_files_for_rekordbox(tracks, contents_dir)
        
        # Create Rekordbox software database
        db_path = rekordbox_dir / "export.pdb"
        db_manager = RekordboxDatabaseManager(str(db_path), self.use_encryption)
        
        try:
            db_manager.create_rekordbox_database_structure()
            self._populate_rekordbox_database(db_manager, tracks, playlist_structure)
            generated_files.append(db_path)
            self.export_stats['database_created'] = True
            
        except Exception as e:
            self.logger.error(f"Rekordbox database creation failed: {e}")
            self.export_stats['errors'] += 1
        
        return {
            'files': generated_files,
            'stats': self.export_stats.copy(),
            'rekordbox_version': self.rekordbox_version.value,
            'audio_copied': copy_audio,
            'target': 'Rekordbox Software'
        }
    
    def _reset_stats(self):
        """Reset export statistics"""
        self.export_stats = {k: 0 if isinstance(v, int) else False for k, v in self.export_stats.items()}
 
    def _copy_audio_files_for_rekordbox(self, tracks: List[Track], contents_dir: Path):
        """Copy audio files for Rekordbox software and update track paths"""
        import shutil
        copied_count = 0
        skipped_count = 0
        
        for track in tracks:
            if track.file_path and Path(track.file_path).exists():
                source_file = Path(track.file_path)
                dest_file = contents_dir / source_file.name
                
                # Skip if file already exists
                if dest_file.exists():
                    track.file_path = f"Contents/{dest_file.name}"
                    skipped_count += 1
                    self.logger.info(f"Skipped existing file for Rekordbox: {source_file.name}")
                    continue
                
                try:
                    shutil.copy2(source_file, dest_file)
                    track.file_path = f"Contents/{dest_file.name}"
                    copied_count += 1
                    self.logger.debug(f"Copied for Rekordbox: {source_file.name}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to copy for Rekordbox {source_file}: {e}")
                    self.export_stats['errors'] += 1
        
        self.logger.info(f"Rekordbox audio files - Copied: {copied_count}, Skipped: {skipped_count}")
        self.export_stats['audio_files_copied'] = copied_count
        self.export_stats['audio_files_skipped'] = skipped_count
     
    def _populate_rekordbox_database(self, db_manager: RekordboxDatabaseManager, tracks: List[Track], playlist_structure: List[Node]):
        """Populate Rekordbox software database with tracks and references"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build reference mappings for Rekordbox
            artist_map = self._build_rekordbox_artist_mapping(cursor, tracks)
            album_map = self._build_rekordbox_album_mapping(cursor, tracks)
            genre_map = self._build_rekordbox_genre_mapping(cursor, tracks)
            
            # Insert tracks for Rekordbox
            for track_id, track in enumerate(tracks, 1):
                self._insert_rekordbox_track(cursor, track, track_id, artist_map, album_map, genre_map)
                
                # Insert cue points for Rekordbox
                for cue in track.cue_points:
                    self._insert_rekordbox_cue_point(cursor, cue, track_id)
            
            conn.commit()
    
    def _build_rekordbox_artist_mapping(self, cursor, tracks: List[Track]) -> Dict[str, int]:
        """Build artist reference table for Rekordbox software"""
        artists = {track.artist for track in tracks if track.artist}
        artist_map = {}
        
        for i, artist in enumerate(artists, 1):
            cursor.execute("INSERT OR IGNORE INTO djmdArtist (ID, Name, rb_data_status, created_at, updated_at) VALUES (?, ?, 0, datetime('now'), datetime('now'))", (i, artist))
            artist_map[artist] = i
        
        return artist_map
    
    def _build_rekordbox_album_mapping(self, cursor, tracks: List[Track]) -> Dict[str, int]:
        """Build album reference table for Rekordbox software"""
        albums = {track.album for track in tracks if track.album}
        album_map = {}
        
        for i, album in enumerate(albums, 1):
            cursor.execute("INSERT OR IGNORE INTO djmdAlbum (ID, Name, ArtistID, rb_data_status, created_at, updated_at) VALUES (?, ?, 1, 0, datetime('now'), datetime('now'))", (i, album))
            album_map[album] = i
        
        return album_map
    
    def _build_rekordbox_genre_mapping(self, cursor, tracks: List[Track]) -> Dict[str, int]:
        """Build genre reference table for Rekordbox software"""
        genres = {track.genre for track in tracks if track.genre}
        genre_map = {}
        
        for i, genre in enumerate(genres, 1):
            cursor.execute("INSERT OR IGNORE INTO djmdGenre (ID, Name, rb_data_status, created_at, updated_at) VALUES (?, ?, 0, datetime('now'), datetime('now'))", (i, genre))
            genre_map[genre] = i
        
        return genre_map
    
    def _insert_rekordbox_track(self, cursor, track: Track, track_id: int, artist_map: Dict, album_map: Dict, genre_map: Dict):
        """Insert track into Rekordbox software database"""
        anlz_path = f"PIONEER/USBANLZ/ANLZ{track_id:06d}.DAT"
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''INSERT OR REPLACE INTO djmdContent 
            (ID, FolderPath, FileNameL, FileNameS, Title, ArtistID, AlbumID, GenreID, LabelID,
             BPM, Length, BitRate, BitDepth, TrackNo, Rating, FileType, Comment, 
             AnalysisDataPath, FileSize, SampleRate, Analysed, ReleaseDate, DateCreated,
             HotCueAutoLoad, AutoGain, KeyID, ColorID, ArtworkID, UUID, 
             rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
             usn, rb_local_usn, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (track_id,
             str(Path(track.file_path).parent) if track.file_path else "",
             Path(track.file_path).name if track.file_path else "",
             Path(track.file_path).name if track.file_path else "",
             track.title,
             artist_map.get(track.artist, 1),
             album_map.get(track.album, 1),
             genre_map.get(track.genre, 1),
             1,  # LabelID
             track.bpm,
             int(track.playtime),
             track.bitrate,
             16,  # BitDepth
             getattr(track, 'track_number', 1),
             self._convert_rating_for_rekordbox(track.ranking),
             1,   # FileType (1=MP3)
             "",  # Comment
             anlz_path,
             Path(track.file_path).stat().st_size if track.file_path and Path(track.file_path).exists() else 0,
             44100,  # SampleRate
             1,      # Analysed
             str(getattr(track, 'year', '')) if hasattr(track, 'year') else "",
             current_time,
             "",     # HotCueAutoLoad
             0.0,    # AutoGain
             self._convert_key_to_rekordbox_id(track.musical_key),
             track.color_tag if hasattr(track, 'color_tag') else 0,
             None,   # ArtworkID
             f"track_{track_id}",  # UUID
             0, 0, 0, 0, 0, 0,     # rb_* fields
             current_time, current_time))
        
    def _insert_rekordbox_cue_point(self, cursor, cue: Dict, track_id: int):
        """Insert cue point into Rekordbox software database"""
        try:
            # Generate unique ID
            cursor.execute("SELECT COALESCE(MAX(ID), 0) FROM djmdCue")
            cue_id = cursor.fetchone()[0] + 1
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''INSERT INTO djmdCue 
                (ID, ContentID, InMsec, InFrame, InMpegFrame, InMpegAbs, 
                 OutMsec, OutFrame, OutMpegFrame, OutMpegAbs, Kind, Color, 
                 ActiveLoop, Comment, BeatLoopSize, CueMicrosec, 
                 ContentUUID, UUID, rb_data_status, rb_local_data_status, 
                 rb_local_deleted, rb_local_synced, usn, rb_local_usn, 
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (cue_id, track_id,
                 cue.get('start', 0),
                 int(cue.get('start', 0) * 75 / 1000),
                 int(cue.get('start', 0) * 75 / 1000),
                 int(cue.get('start', 0) * 75 / 1000),
                 cue.get('start', 0) + cue.get('len', 0),
                 int((cue.get('start', 0) + cue.get('len', 0)) * 75 / 1000),
                 int((cue.get('start', 0) + cue.get('len', 0)) * 75 / 1000),
                 int((cue.get('start', 0) + cue.get('len', 0)) * 75 / 1000),
                 self._convert_cue_type_to_rekordbox(cue.get('type', 0)),
                 self._convert_cue_color_to_int(cue.get('color', '')),
                 0,  # ActiveLoop
                 cue.get('name', ''),
                 0,  # BeatLoopSize
                 cue.get('start', 0) * 1000,  # CueMicrosec
                 f"track_{track_id}",  # ContentUUID
                 f"cue_{cue_id}",      # UUID
                 0, 0, 0, 0, 0, 0,     # rb_* fields
                 current_time, current_time))
                 
        except sqlite3.IntegrityError as e:
            self.logger.warning(f"Rekordbox cue point skipped for track {track_id}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to insert Rekordbox cue point for track {track_id}: {e}")
        
    def _convert_key_to_rekordbox_id(self, key: str) -> int:
        """Convert musical key to Rekordbox software ID"""
        if not key:
            return 1
        
        # Open Key to Rekordbox ID mapping
        key_mapping = {
            '1A': 21, '1B': 12, '2A': 16, '2B': 7, '3A': 23, '3B': 2,
            '4A': 18, '4B': 9, '5A': 13, '5B': 4, '6A': 20, '6B': 11,
            '7A': 15, '7B': 6, '8A': 22, '8B': 1, '9A': 17, '9B': 8,
            '10A': 24, '10B': 3, '11A': 19, '11B': 10, '12A': 14, '12B': 5
        }
        
        # If numeric Traktor key, convert to Open Key first
        if key.isdigit():
            traktor_to_open = {
                0: "8A", 1: "3A", 2: "10A", 3: "5A", 4: "12A", 5: "7A",
                6: "2A", 7: "9A", 8: "4A", 9: "11A", 10: "6A", 11: "1A",
                12: "8B", 13: "3B", 14: "10B", 15: "5B", 16: "12B", 17: "7B",
                18: "2B", 19: "9B", 20: "4B", 21: "11B", 22: "6B", 23: "1B"
            }
            key = traktor_to_open.get(int(key), "")
        
        return key_mapping.get(key, 1)
    
    def _convert_rating_for_rekordbox(self, ranking: int) -> int:
        """Convert Traktor ranking to Rekordbox software rating"""
        if ranking <= 0:
            return 0
        return min(5, int((ranking / 255.0) * 5))
    
    def _convert_cue_type_to_rekordbox(self, traktor_type: int) -> int:
        """Convert Traktor cue type to Rekordbox software format"""
        mapping = {0: 1, 1: 1, 2: 1, 3: 1, 4: 4, 5: 2}  # 4=grid, 2=loop, 1=cue
        return mapping.get(traktor_type, 1)
    
    def _convert_cue_color_to_int(self, color_str: str) -> int:
        """Convert color string to integer for Rekordbox"""
        if not color_str:
            return 0
        
        try:
            if color_str.startswith('#'):
                return int(color_str[1:], 16)
            return int(color_str)
        except ValueError:
            return 0
    
    def _generate_rekordbox_anlz_files(self, track: Track, output_dir: Path, track_id: int, total_tracks: int) -> List[Path]:
        """Generate ANLZ files for Rekordbox software visualization"""
        generated_files = []
        
        try:
            self.logger.info(f"Processing track for Rekordbox {track_id}: {track.title} - {track.artist}")
            
            # Analyze audio for Rekordbox
            analysis = {}
            if track.file_path and Path(track.file_path).exists():
                self.logger.debug(f"Audio file exists for Rekordbox: {track.file_path}")
                analysis = self.audio_analyzer.analyze_track_for_rekordbox(track.file_path)
                self.logger.debug(f"Rekordbox audio analysis completed: BPM={analysis.get('bpm', 'N/A')}")
            else:
                self.logger.warning(f"Audio file missing for Rekordbox track {track_id}: {track.file_path}")
                analysis = self.audio_analyzer._get_default_rekordbox_analysis()

            # Generate main .DAT file for Rekordbox
            dat_path = output_dir / f"ANLZ{track_id:06d}.DAT"
            self.logger.debug(f"Generating Rekordbox DAT file: {dat_path}")
            try:
                self._generate_rekordbox_anlz_dat(track, analysis, dat_path)
                generated_files.append(dat_path)
                self.logger.debug(f"Rekordbox DAT file generated: {dat_path.stat().st_size} bytes")
            except Exception as e:
                self.logger.error(f"Rekordbox DAT generation failed for track {track_id}: {e}")
                raise
            
            self.export_stats['anlz_files'] += len(generated_files)
            self.logger.info(f"Rekordbox track {track_id} ANLZ completed: {len(generated_files)} files")
            
            # Progress update
            if self.progress_queue:
                progress = int(track_id * 100 / total_tracks)
                self.progress_queue.put(("progress", (progress, f"Rekordbox ANLZ completed: {track_id}/{total_tracks}")))
            
            return generated_files
            
        except Exception as e:
            self.logger.error(f"Rekordbox ANLZ generation failed for track {track_id} ({track.title}): {e}")
            self.export_stats['errors'] += 1
            import traceback
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def _generate_rekordbox_anlz_dat(self, track: Track, analysis: Dict, output_path: Path):
        """Generate main ANLZ .DAT file for Rekordbox software"""
        sections = []
        
        # PPTH section (file path for Rekordbox)
        ppth_section = self._create_rekordbox_ppth_section(track)
        sections.append(ppth_section)
        
        # PQTZ section (beat grid for Rekordbox)
        if analysis.get('beat_grid'):
            pqtz_section = self._create_rekordbox_pqtz_section(analysis['beat_grid'])
            sections.append(pqtz_section)
        
        # PCOB section (cue points for Rekordbox)
        if track.cue_points:
            cue_section = self._create_rekordbox_pcob_section(track.cue_points)
            sections.append(cue_section)
        
        # PWAV section (waveform for Rekordbox)
        pwav_section = self._create_rekordbox_pwav_section(analysis.get('waveform', bytes([128] * 400)))
        sections.append(pwav_section)
        
        self._write_rekordbox_anlz_file(sections, output_path)
    
    def _create_rekordbox_ppth_section(self, track: Track) -> ANLZSection:
        """Create PPTH section for Rekordbox software"""
        filename = Path(track.file_path).name if track.file_path else "unknown.mp3"
        path_utf16 = filename.encode('utf-16be') + b'\x00\x00'
        
        payload = struct.pack('>I', len(path_utf16)) + path_utf16
        return ANLZSection('PPTH', 12, payload)
    
    def _create_rekordbox_pqtz_section(self, beat_grid: List[Dict]) -> ANLZSection:
        """Create PQTZ section for Rekordbox software"""
        payload = bytearray()
        
        # Limit to 1000 beats for Rekordbox
        limited_beats = beat_grid[:1000]
        payload.extend(struct.pack('>I', len(limited_beats)))
        
        for beat in limited_beats:
            beat_number = beat.get('beat_number', 1)
            tempo_100 = int(beat.get('tempo', 120) * 100)
            time_ms = beat.get('time_ms', 0)
            
            payload.extend(struct.pack('>HHI', beat_number, tempo_100, time_ms))
        
        return ANLZSection('PQTZ', 12, bytes(payload))
    
    def _create_rekordbox_pwav_section(self, waveform_data: bytes) -> ANLZSection:
        """Create PWAV section for Rekordbox software"""
        # Ensure exactly 400 bytes for Rekordbox
        if len(waveform_data) != 400:
            waveform_data = waveform_data[:400].ljust(400, b'\x80')
        
        payload = struct.pack('>I', 0x00100000) + waveform_data
        return ANLZSection('PWAV', 16, payload)
    
    def _create_rekordbox_pcob_section(self, cue_points: List[Dict]) -> ANLZSection:
        """Create PCOB section for Rekordbox software"""
        payload = bytearray()
        
        valid_cues = [c for c in cue_points if c.get('hotcue', 0) > 0][:8]
        payload.extend(struct.pack('>I', len(valid_cues)))
        
        for cue in valid_cues:
            payload.extend(b'PCPT')
            payload.extend(struct.pack('>I', 0x1C))
            payload.extend(struct.pack('>I', 0x26))
            payload.extend(struct.pack('>I', cue.get('hotcue', 0)))
            payload.extend(struct.pack('>I', 0))
            payload.extend(struct.pack('>I', 0x00100000))
            payload.extend(struct.pack('>HH', 0, 0))
            payload.extend(struct.pack('B', 1))
            payload.extend(b'\x00\x03\xe8')
            payload.extend(struct.pack('>I', cue.get('start', 0)))
            payload.extend(struct.pack('>I', 0xFFFFFFFF))
        
        return ANLZSection('PCOB', 12, bytes(payload))
    
    def _write_rekordbox_anlz_file(self, sections: List[ANLZSection], output_path: Path):
        """Write complete ANLZ file for Rekordbox software"""
        try:
            self.logger.debug(f"Writing Rekordbox ANLZ file: {output_path}")
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                # Calculate total size
                total_size = 20  # Header
                for section in sections:
                    total_size += 12 + len(section.payload)
                
                self.logger.debug(f"Total Rekordbox ANLZ size: {total_size} bytes")
                
                # ANLZ header for Rekordbox
                f.write(b'PMAI')
                f.write(struct.pack('>I', 20))
                f.write(struct.pack('>I', total_size))
                f.write(b'\x00' * 8)
                
                # Write sections for Rekordbox
                for i, section in enumerate(sections):
                    try:
                        section_data = section.to_bytes()
                        f.write(section_data)
                        self.logger.debug(f"Rekordbox section {i} ({section.fourcc}): {len(section_data)} bytes")
                    except Exception as e:
                        self.logger.error(f"Failed to write Rekordbox section {i} ({section.fourcc}): {e}")
                        raise
            
            # Verify file was written
            if output_path.exists():
                actual_size = output_path.stat().st_size
                self.logger.debug(f"Rekordbox ANLZ file written: {actual_size} bytes")
            else:
                raise FileNotFoundError(f"Rekordbox ANLZ file not created: {output_path}")
            
            self.logger.debug(f"Rekordbox ANLZ generated successfully: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Rekordbox ANLZ write error {output_path}: {e}")
            # Clean up partial file
            if output_path.exists():
                try:
                    output_path.unlink()
                    self.logger.debug(f"Cleaned up partial Rekordbox file: {output_path}")
                except Exception:
                    pass
            raise

# Factory function for Rekordbox software export
def export_nml_to_rekordbox(nml_path: str, output_dir: str, 
                           music_root: Optional[str] = None,
                           rekordbox_version: RekordboxVersion = RekordboxVersion.RB6,
                           use_encryption: bool = True,
                           copy_audio: bool = True) -> bool:
    """Convert Traktor NML to Rekordbox SOFTWARE format (not CDJ hardware)"""
    try:
        from parser.bsm_nml_parser import create_traktor_parser
        
        # Parse NML
        parser = create_traktor_parser(nml_path, music_root)
        playlist_structure = parser.get_playlists_with_structure()
        
        # Collect all tracks
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
        
        # Export to Rekordbox software
        exporter = RekordboxExportEngine(rekordbox_version, use_encryption)
        result = exporter.export_collection_to_rekordbox(all_tracks, playlist_structure, Path(output_dir), copy_audio)
        
        return result['stats']['errors'] == 0
        
    except Exception as e:
        logging.error(f"NML to Rekordbox software export failed: {e}")
        return False