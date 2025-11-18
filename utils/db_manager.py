"""
Database Manager Module for Traktor Bridge
Handles CDJ database creation and Cipher encryption support
"""

import logging
import sqlite3
import threading
import time
import struct
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

# SQLCipher support
try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False
    logging.warning("pysqlcipher3 not available. Using standard SQLite.")


class DatabaseManager:
    """Database manager with SQLCipher support for CDJ compatibility."""
    
    def __init__(self, db_path: str, use_encryption: bool = True):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self.use_encryption = use_encryption and SQLCIPHER_AVAILABLE
        
        # Standard Rekordbox encryption key
        self.encryption_key = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43a3d643"
        
    @contextmanager
    def get_connection(self, max_retries: int = 3):
        """Context manager with SQLCipher support and retry logic."""
        conn = None
        
        for attempt in range(max_retries):
            try:
                if self.use_encryption:
                    conn = sqlcipher.connect(
                        str(self.db_path),
                        timeout=30,
                        isolation_level=None
                    )
                    conn.execute(f"PRAGMA key = \"x'{self.encryption_key}'\"")
                    conn.execute("PRAGMA cipher_compatibility = 3")
                else:
                    conn = sqlite3.connect(
                        str(self.db_path),
                        timeout=30,
                        isolation_level=None
                    )
                
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                else:
                    raise sqlite3.Error(f"Failed to connect after {max_retries} attempts: {e}")
        
        try:
            yield conn
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def execute_batch(self, query: str, data_batch: List[tuple], batch_size: int = 100):
        """Execute batch operations with validation."""
        if not data_batch:
            return
            
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for i in range(0, len(data_batch), batch_size):
                    batch = data_batch[i:i + batch_size]
                    try:
                        cursor.executemany(query, batch)
                    except sqlite3.Error as e:
                        logging.error(f"Batch execution failed at batch {i//batch_size}: {e}")
                        continue
    
    def create_database_structure(self):
        """Initialize SQLite database with all required Rekordbox tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Core tables for Rekordbox compatibility
            table_definitions = {
                'djmdContent': '''CREATE TABLE IF NOT EXISTS djmdContent (
                    ID INTEGER PRIMARY KEY, 
                    FolderPath TEXT, 
                    FileNameL TEXT, 
                    FileNameS TEXT,
                    Title TEXT, 
                    ArtistID INTEGER, 
                    AlbumID INTEGER, 
                    GenreID INTEGER, 
                    LabelID INTEGER, 
                    KeyID INTEGER,
                    ColorID INTEGER,
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
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT,
                    ArtworkID INTEGER
                )''',
                
                'djmdPlaylist': '''CREATE TABLE IF NOT EXISTS djmdPlaylist (
                    ID INTEGER PRIMARY KEY,
                    Seq INTEGER,
                    Name TEXT,
                    ParentID INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdSongPlaylist': '''CREATE TABLE IF NOT EXISTS djmdSongPlaylist (
                    ID INTEGER PRIMARY KEY,
                    PlaylistID INTEGER,
                    ContentID INTEGER,
                    TrackNo INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdCue': '''CREATE TABLE IF NOT EXISTS djmdCue (
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
                    InPointSeekInfo TEXT,
                    OutPointSeekInfo TEXT,
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
                )''',
                
                'djmdBeatGrid': '''CREATE TABLE IF NOT EXISTS djmdBeatGrid (
                    ID INTEGER PRIMARY KEY,
                    ContentID INTEGER,
                    BeatNo INTEGER,
                    Tempo REAL,
                    Position REAL,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdArtist': '''CREATE TABLE IF NOT EXISTS djmdArtist (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdAlbum': '''CREATE TABLE IF NOT EXISTS djmdAlbum (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT,
                    ArtistID INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdGenre': '''CREATE TABLE IF NOT EXISTS djmdGenre (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdLabel': '''CREATE TABLE IF NOT EXISTS djmdLabel (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdKey': '''CREATE TABLE IF NOT EXISTS djmdKey (
                    ID INTEGER PRIMARY KEY,
                    ScaleName TEXT,
                    Seq INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdColor': '''CREATE TABLE IF NOT EXISTS djmdColor (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT,
                    ColorCode TEXT,
                    SortKey INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdArtwork': '''CREATE TABLE IF NOT EXISTS djmdArtwork (
                    ID INTEGER PRIMARY KEY,
                    Path TEXT,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )''',
                
                'djmdMixerParam': '''CREATE TABLE IF NOT EXISTS djmdMixerParam (
                    ID INTEGER PRIMARY KEY,
                    ContentID INTEGER,
                    GainHigh INTEGER,
                    GainLow INTEGER,
                    PeakHigh INTEGER,
                    PeakLow INTEGER,
                    UUID TEXT,
                    rb_data_status INTEGER,
                    rb_local_data_status INTEGER,
                    rb_local_deleted INTEGER,
                    rb_local_synced INTEGER,
                    usn INTEGER,
                    rb_local_usn INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )'''
            }
            
            # Create all tables
            for table_name, table_sql in table_definitions.items():
                cursor.execute(table_sql)
            
            # Populate default values
            self._populate_default_values(cursor)
    
    def _populate_default_values(self, cursor: sqlite3.Cursor):
        """Add default values for reference tables."""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Standard Rekordbox colors
        colors = [
            (1, "Pink", "#FF007F", 1),
            (2, "Red", "#FF0000", 2),
            (3, "Orange", "#FFA500", 3),
            (4, "Yellow", "#FFFF00", 4),
            (5, "Green", "#00FF00", 5),
            (6, "Aqua", "#25FDE9", 6),
            (7, "Blue", "#0000FF", 7),
            (8, "Purple", "#660099", 8)
        ]
        
        cursor.execute("DELETE FROM djmdColor")
        for color_id, name, code, sort_key in colors:
            cursor.execute("""
                INSERT INTO djmdColor (ID, Name, ColorCode, SortKey, UUID, rb_data_status, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """, (color_id, name, code, sort_key, str(uuid.uuid4()), current_time, current_time))
        
        # Musical keys (Camelot + Traditional)
        keys = [
            (1, "1A", 1), (2, "2A", 2), (3, "3A", 3), (4, "4A", 4),
            (5, "5A", 5), (6, "6A", 6), (7, "7A", 7), (8, "8A", 8),
            (9, "9A", 9), (10, "10A", 10), (11, "11A", 11), (12, "12A", 12),
            (13, "1B", 13), (14, "2B", 14), (15, "3B", 15), (16, "4B", 16),
            (17, "5B", 17), (18, "6B", 18), (19, "7B", 19), (20, "8B", 20),
            (21, "9B", 21), (22, "10B", 22), (23, "11B", 23), (24, "12B", 24)
        ]
        
        cursor.execute("DELETE FROM djmdKey")
        for key_id, scale_name, seq in keys:
            cursor.execute("""
                INSERT INTO djmdKey (ID, ScaleName, Seq, UUID, rb_data_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
            """, (key_id, scale_name, seq, str(uuid.uuid4()), current_time, current_time))
    
    def build_lookup_caches(self) -> Dict[str, Dict[str, int]]:
        """Pre-load existing database entries for performance."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            return {
                'artists': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdArtist")},
                'albums': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdAlbum")},
                'genres': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdGenre")},
                'labels': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdLabel")},
                'keys': {row[1]: row[0] for row in cursor.execute("SELECT ID, ScaleName FROM djmdKey")},
                'content': {row[1]: row[0] for row in cursor.execute("SELECT ID, FileNameL FROM djmdContent")}
            }
    
    def get_or_create_id(self, cursor: sqlite3.Cursor, table: str, name: str, cache: Dict[str, int]) -> Optional[int]:
        """Get ID for metadata item from cache or create new entry."""
        if not name:
            return None
            
        if name in cache:
            return cache[name]
        
        # Check database first
        if table == 'djmdKey':
            cursor.execute(f"SELECT ID FROM {table} WHERE ScaleName = ?", (name,))
        else:
            cursor.execute(f"SELECT ID FROM {table} WHERE Name = ?", (name,))
        
        result = cursor.fetchone()
        if result:
            cache[name] = result[0]
            return result[0]
        
        # Create new entry
        cursor.execute(f"SELECT MAX(ID) FROM {table}")
        max_id = cursor.fetchone()[0] or 0
        new_id = max_id + 1
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        uuid_str = str(uuid.uuid4())
        
        if table == 'djmdKey':
            cursor.execute(f"""
                INSERT INTO {table} (ID, ScaleName, Seq, UUID, rb_data_status, created_at, updated_at) 
                VALUES (?, ?, ?, ?, 0, ?, ?)
            """, (new_id, name, new_id, uuid_str, current_time, current_time))
        else:
            cursor.execute(f"""
                INSERT INTO {table} (ID, Name, UUID, rb_data_status, created_at, updated_at) 
                VALUES (?, ?, ?, 0, ?, ?)
            """, (new_id, name, uuid_str, current_time, current_time))
        
        cache[name] = new_id
        return new_id


class CipherManager:
    """Manages encryption/decryption operations for Rekordbox compatibility."""
    
    @staticmethod
    def validate_cipher_support() -> bool:
        """Check if SQLCipher is available and working."""
        return SQLCIPHER_AVAILABLE
    
    @staticmethod
    def test_encryption(db_path: str, encryption_key: str) -> bool:
        """Test if encryption is working properly."""
        if not SQLCIPHER_AVAILABLE:
            return False
            
        try:
            conn = sqlcipher.connect(db_path)
            conn.execute(f"PRAGMA key = \"x'{encryption_key}'\"")
            conn.execute("CREATE TABLE test_table (id INTEGER)")
            conn.execute("DROP TABLE test_table")
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Cipher test failed: {e}")
            return False
    
    @staticmethod
    def get_standard_rekordbox_key() -> str:
        """Get the standard Rekordbox encryption key."""
        return "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43a3d643"