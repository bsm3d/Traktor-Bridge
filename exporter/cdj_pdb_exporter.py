# -*- coding: utf-8 -*-
"""
CDJ PDB Exporter - Format DeviceSQL Conforme CORRIGÉ
Basé sur les spécifications Kaitai et les projets Crate Digger/REX
Compatible CDJ-2000NXS2 (priorité)
"""

import logging
import struct
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, BinaryIO
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from parser.bsm_nml_parser import Track, Node, TraktorNMLParser

# Constants from reverse engineering - CORRIGÉ pour CDJ hardware
PAGE_SIZE = 8192  # Real CDJ hardware uses 8192 byte pages
EMPTY_TABLE = 0x03ffffff

class PageType(Enum):
    """Types de pages DeviceSQL selon spécifications Kaitai"""
    TRACKS = 0
    GENRES = 1
    ARTISTS = 2
    ALBUMS = 3
    LABELS = 4
    KEYS = 5
    COLORS = 6
    PLAYLIST_TREE = 7
    PLAYLIST_ENTRIES = 8
    UNKNOWN_9 = 9
    UNKNOWN_10 = 10
    HISTORY_PLAYLISTS = 11
    HISTORY_ENTRIES = 12
    ARTWORK = 13
    UNKNOWN_14 = 14
    UNKNOWN_15 = 15
    COLUMNS = 16
    UNKNOWN_17 = 17
    UNKNOWN_18 = 18
    HISTORY = 19

@dataclass
class TablePointer:
    """Pointeur de table dans l'en-tête PDB"""
    type: PageType
    empty_candidate: int
    first_page: int
    last_page: int
    
    def to_bytes(self) -> bytes:
        return struct.pack('<IIII', 
                          self.type.value, 
                          self.empty_candidate,
                          self.first_page, 
                          self.last_page)

@dataclass 
class PageHeader:
    """En-tête de page DeviceSQL"""
    gap: int = 0
    page_index: int = 0
    type: PageType = PageType.TRACKS
    next_page: int = 0
    sequence: int = 0
    gap2: int = 0
    num_rows_small: int = 0
    bitmask: int = 0
    gap3: int = 0
    page_flags: int = 0x24
    free_size: int = 0
    used_size: int = 0
    gap4: int = 0
    num_rows_large: int = 0
    gap5: int = 0
    gap6: int = 0
    
    def to_bytes(self) -> bytes:
        return struct.pack('<IIIIIIBBBBHHHHH',
                          self.gap, self.page_index, self.type.value,
                          self.next_page, self.sequence, self.gap2,
                          self.num_rows_small, self.bitmask, self.gap3,
                          self.page_flags, self.free_size, self.used_size,
                          self.gap4, self.num_rows_large, self.gap5)

class DeviceSQLString:
    """Encodage des chaînes DeviceSQL selon spécifications Kaitai - CORRIGÉ"""
    
    def __init__(self, text: str):
        self.text = text or ""
    
    def to_bytes(self) -> bytes:
        """Encode selon les règles DeviceSQL CORRECTES"""
        if not self.text:
            return b'\x00'
        
        utf8_bytes = self.text.encode('utf-8')
        
        # Short ASCII (jusqu'à 126 bytes ET ASCII pur uniquement)
        if len(utf8_bytes) <= 126 and self._is_ascii(self.text):
            # Format court : length * 2 + 1
            length_and_kind = len(utf8_bytes) * 2 + 1
            return bytes([length_and_kind]) + utf8_bytes
        
        # Long ASCII (format 0x40) - CORRIGÉ
        elif self._is_ascii(self.text) and len(utf8_bytes) <= 65535:
            # 0x40 = bit pattern: 0100 0000 (S=0, E=1, A=1, other=0)
            header = struct.pack('<HH', len(utf8_bytes) + 4, 0)
            return b'\x40' + header + utf8_bytes
        
        # Long UTF-16LE (format 0x90) - CORRIGÉ
        else:
            utf16_bytes = self.text.encode('utf-16le')
            # 0x90 = bit pattern: 1001 0000 (S=0, E=1, A=0, N=0, W=1)
            header = struct.pack('<HH', len(utf16_bytes) + 4, 0)
            return b'\x90' + header + utf16_bytes
    
    def _is_ascii(self, text: str) -> bool:
        """Vérifier que texte est ASCII pur"""
        try:
            text.encode('ascii')
            return True
        except UnicodeEncodeError:
            return False

class TrackRow:
    """Ligne de track selon spécifications exactes CORRIGÉ"""
    
    def __init__(self, track: Track, track_id: int, 
                 artist_id: int = 1, album_id: int = 1, 
                 genre_id: int = 1, key_id: int = 1):
        self.track = track
        self.track_id = track_id
        self.artist_id = artist_id
        self.album_id = album_id
        self.genre_id = genre_id
        self.key_id = key_id
    
    def to_bytes(self) -> bytes:
        """Generate binary track row selon format exact CORRIGÉ"""
        # Structure fixe (88 bytes selon spécifications RÉELLES + strings)
        fixed_part = bytearray(88)
        
        # Magic word et index shift - CORRIGÉ selon observations
        struct.pack_into('<HH', fixed_part, 0, 0x2400, 0x100)  # Magic observé dans real PDB
        
        # Bitmask et métadonnées audio
        bitmask = 0x0C0700  # Valeur observée dans vrais exports CDJ
        sample_rate = 44100
        file_size = 0
        if self.track.file_path and Path(self.track.file_path).exists():
            file_size = Path(self.track.file_path).stat().st_size
        
        struct.pack_into('<III', fixed_part, 4, bitmask, sample_rate, 0)  # composer_id = 0
        struct.pack_into('<I', fixed_part, 16, file_size)
        
        # Magic constants observées dans vraies bases CDJ
        struct.pack_into('<IIHH', fixed_part, 20, 0, 19048, 30967)
        
        # IDs de référence
        struct.pack_into('<IIIIII', fixed_part, 32, 
                        0,  # artwork_id
                        self.key_id,
                        0,  # original_artist_id  
                        0,  # label_id
                        0,  # remixer_id
                        self.track.bitrate or 320)
        
        # Métadonnées track
        struct.pack_into('<IIII', fixed_part, 56,
                        getattr(self.track, 'track_number', 1),
                        int((self.track.bpm or 120) * 100),  # BPM * 100
                        self.genre_id,
                        self.album_id)
        
        struct.pack_into('<II', fixed_part, 72, self.artist_id, self.track_id)
        
        # Métadonnées supplémentaires - structure corrigée
        struct.pack_into('<HHHHHH', fixed_part, 80,
                        getattr(self.track, 'disc_number', 1),
                        0,  # play_count
                        getattr(self.track, 'year', 2024),
                        16,  # sample_depth
                        int(self.track.playtime or 180),  # duration
                        41)  # magic constant
        
        # Rating et couleur - ajusté pour structure 88 bytes
        rating = self._convert_rating(self.track.ranking)
        
        # Générer les chaînes avec encodage correct
        strings_data = bytearray()
        string_offsets = []
        current_offset = 88  # Début des chaînes après structure fixe
        
        # 21 chaînes requises selon format CDJ
        string_fields = [
            "",  # isrc
            "",  # texter  
            "",  # unknown_string_2
            "",  # unknown_string_3
            "",  # unknown_string_4
            "",  # message
            "",  # kuvo_public
            "",  # autoload_hotcues
            "",  # unknown_string_5
            "",  # unknown_string_6
            datetime.now().strftime('%Y-%m-%d'),  # date_added
            "",  # release_date
            "",  # mix_name
            "",  # unknown_string_7
            f"PIONEER/USBANLZ/ANLZ{self.track_id:06d}.DAT",  # analyze_path
            datetime.now().strftime('%Y-%m-%d'),  # analyze_date
            "",  # comment
            self.track.title or "Unknown",  # title
            "",  # unknown_string_8
            Path(self.track.file_path).name if self.track.file_path else "unknown.mp3",  # filename
            self.track.file_path or "unknown.mp3"  # file_path
        ]
        
        # Encoder chaque chaîne avec DeviceSQL
        for field in string_fields:
            string_offsets.append(current_offset)
            encoded_string = DeviceSQLString(field).to_bytes()
            strings_data.extend(encoded_string)
            current_offset += len(encoded_string)
        
        # Écrire les offsets dans la partie fixe (21 offsets de 2 bytes)
        # Position 88-42 = 46 pour les offsets
        offset_start = 46  # Ajusté pour structure 88 bytes
        for i, offset in enumerate(string_offsets):
            if offset_start + (i * 2) < 88:  # Vérifier bounds
                struct.pack_into('<H', fixed_part, offset_start + (i * 2), offset)
        
        return bytes(fixed_part) + bytes(strings_data)
    
    def _convert_rating(self, traktor_rating) -> int:
        """Convert Traktor rating to Rekordbox scale"""
        if not traktor_rating:
            return 0
        
        # Traktor: 0-255, Rekordbox: 0-5
        normalized = float(traktor_rating) / 255.0
        return int(normalized * 5)

class ArtistRow:
    """Ligne artiste selon format DeviceSQL"""
    
    def __init__(self, name: str, artist_id: int):
        self.name = name
        self.artist_id = artist_id
    
    def to_bytes(self) -> bytes:
        """Generate artist row binary data"""
        # Structure de base : 16 bytes + 2 strings
        fixed_part = bytearray(16)
        
        # Artist ID et flags
        struct.pack_into('<II', fixed_part, 0, 0, self.artist_id)
        struct.pack_into('<II', fixed_part, 8, 0, 0)
        
        # Strings : name (near) et name (far)
        name_data = DeviceSQLString(self.name).to_bytes()
        
        # Offsets des chaînes
        offset = 16
        struct.pack_into('<H', fixed_part, 12, offset)  # near offset
        struct.pack_into('<H', fixed_part, 14, offset)  # far offset (même)
        
        return bytes(fixed_part) + name_data

class AlbumRow:
    """Ligne album selon format DeviceSQL"""
    
    def __init__(self, name: str, album_id: int, artist_id: int = 1):
        self.name = name
        self.album_id = album_id
        self.artist_id = artist_id
    
    def to_bytes(self) -> bytes:
        """Generate album row binary data"""
        # Structure : ID + artist_id + string offset
        fixed_part = bytearray(14)
        
        struct.pack_into('<III', fixed_part, 0, 0, self.album_id, self.artist_id)
        
        # String data
        name_data = DeviceSQLString(self.name).to_bytes()
        
        # Offset
        struct.pack_into('<H', fixed_part, 12, 14)  # offset après fixed part
        
        return bytes(fixed_part) + name_data

class GenreRow:
    """Ligne genre selon format DeviceSQL"""
    
    def __init__(self, name: str, genre_id: int):
        self.name = name
        self.genre_id = genre_id
    
    def to_bytes(self) -> bytes:
        """Generate genre row binary data"""
        fixed_part = bytearray(6)
        
        struct.pack_into('<IH', fixed_part, 0, self.genre_id, 6)  # ID + offset
        
        name_data = DeviceSQLString(self.name).to_bytes()
        
        return bytes(fixed_part) + name_data

class Page:
    """Page DeviceSQL avec gestion heap/index"""
    
    def __init__(self, page_type: PageType, page_index: int):
        self.header = PageHeader(page_index=page_index, type=page_type)
        self.rows = []
        self.row_offsets = []
        self.heap_size = 0
        
    def add_row(self, row_data: bytes) -> bool:
        """Ajouter une ligne si espace suffisant"""
        required_space = len(row_data) + 2  # +2 pour offset dans index
        available = PAGE_SIZE - 40 - self.heap_size - (len(self.rows) + 1) * 2
        
        if required_space > available:
            return False
            
        # Ajouter au heap
        offset = 40 + self.heap_size  # 40 = taille header
        self.row_offsets.append(offset)
        self.rows.append(row_data)
        self.heap_size += len(row_data)
        
        # Mettre à jour header
        self.header.num_rows_small = len(self.rows)
        self.header.num_rows_large = len(self.rows)
        self.header.used_size = self.heap_size
        self.header.free_size = PAGE_SIZE - 40 - self.heap_size - len(self.rows) * 2
        
        return True
    
    def to_bytes(self) -> bytes:
        """Générer page binaire complète"""
        page_data = bytearray(PAGE_SIZE)
        
        # Header
        header_bytes = self.header.to_bytes()
        page_data[0:40] = header_bytes
        
        # Heap (données des lignes)
        heap_offset = 40
        for row_data in self.rows:
            end_offset = heap_offset + len(row_data)
            page_data[heap_offset:end_offset] = row_data
            heap_offset = end_offset
        
        # Index (offsets depuis la fin de page)
        self._write_row_index(page_data, len(self.rows))
        
        return bytes(page_data)
    
    def _write_row_index(self, page_data: bytearray, num_rows: int):
        """Écrire index des lignes depuis la fin de page"""
        if num_rows == 0:
            return
            
        # Grouper par 16 (structure observée)
        num_groups = (num_rows - 1) // 16 + 1
        
        for group_index in range(num_groups):
            # Position de base du groupe
            base_offset = PAGE_SIZE - (group_index + 1) * 0x24
            
            # Flags de présence (tous les bits à 1 pour les lignes présentes)
            start_row = group_index * 16
            end_row = min(start_row + 16, num_rows)
            rows_in_group = end_row - start_row
            
            present_flags = (1 << rows_in_group) - 1
            struct.pack_into('<H', page_data, base_offset - 4, present_flags)
            
            # Offsets des lignes (en ordre inverse)
            for i in range(rows_in_group):
                row_index = start_row + i
                offset_pos = base_offset - 6 - (i * 2)
                row_offset = self.row_offsets[row_index] - 40  # Relatif au heap
                struct.pack_into('<H', page_data, offset_pos, row_offset)

class PDBExporter:
    """Exporteur PDB conforme aux spécifications DeviceSQL CORRIGÉ"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.next_page_index = 1
        self.sequence = 2
        self.tables = {}
        
    def export_collection_to_pdb(self, tracks: List[Track], 
                                output_path: Path) -> Dict:
        """Export complet vers format PDB"""
        self.logger.info(f"Exporting {len(tracks)} tracks to PDB format")
        
        # Construire les tables de référence
        artists_map = self._build_artists_map(tracks)
        albums_map = self._build_albums_map(tracks)
        genres_map = self._build_genres_map(tracks)
        
        # Créer les pages
        self._create_reference_pages(artists_map, albums_map, genres_map)
        self._create_track_pages(tracks, artists_map, albums_map, genres_map)
        
        # Générer le fichier PDB
        self._write_pdb_file(output_path)
        
        # Créer DeviceSQL.edb (copie pour reconnaissance CDJ)
        deviceSQL_path = output_path.parent / "DeviceSQL.edb"
        import shutil
        shutil.copy2(output_path, deviceSQL_path)
        self.logger.info(f"Created DeviceSQL.edb copy for CDJ recognition")
        
        return {
            'status': 'success',
            'tracks_exported': len(tracks),
            'pages_created': len(self.tables),
            'file_path': output_path
        }
    
    def _build_artists_map(self, tracks: List[Track]) -> Dict[str, int]:
        """Construire le mapping artistes"""
        artists = {track.artist for track in tracks if track.artist}
        return {artist: i + 1 for i, artist in enumerate(sorted(artists))}
    
    def _build_albums_map(self, tracks: List[Track]) -> Dict[str, int]:
        """Construire le mapping albums"""
        albums = {track.album for track in tracks if track.album}
        return {album: i + 1 for i, album in enumerate(sorted(albums))}
    
    def _build_genres_map(self, tracks: List[Track]) -> Dict[str, int]:
        """Construire le mapping genres"""
        genres = {track.genre for track in tracks if track.genre}
        return {genre: i + 1 for i, genre in enumerate(sorted(genres))}
    
    def _create_reference_pages(self, artists_map: Dict, albums_map: Dict, genres_map: Dict):
        """Créer les pages de référence"""
        # Pages Artists
        if artists_map:
            artists_pages = self._create_table_pages(PageType.ARTISTS)
            for artist_name, artist_id in artists_map.items():
                row = ArtistRow(artist_name, artist_id)
                self._add_row_to_pages(artists_pages, row.to_bytes())
        
        # Pages Albums  
        if albums_map:
            albums_pages = self._create_table_pages(PageType.ALBUMS)
            for album_name, album_id in albums_map.items():
                row = AlbumRow(album_name, album_id)
                self._add_row_to_pages(albums_pages, row.to_bytes())
        
        # Pages Genres
        if genres_map:
            genres_pages = self._create_table_pages(PageType.GENRES)
            for genre_name, genre_id in genres_map.items():
                row = GenreRow(genre_name, genre_id)
                self._add_row_to_pages(genres_pages, row.to_bytes())
    
    def _create_track_pages(self, tracks: List[Track], artists_map: Dict, 
                           albums_map: Dict, genres_map: Dict):
        """Créer les pages de tracks"""
        tracks_pages = self._create_table_pages(PageType.TRACKS)
        
        for i, track in enumerate(tracks, 1):
            artist_id = artists_map.get(track.artist, 1)
            album_id = albums_map.get(track.album, 1)
            genre_id = genres_map.get(track.genre, 1)
            
            row = TrackRow(track, i, artist_id, album_id, genre_id)
            self._add_row_to_pages(tracks_pages, row.to_bytes())
    
    def _create_table_pages(self, page_type: PageType) -> List[Page]:
        """Créer les pages pour un type de table"""
        pages = []
        self.tables[page_type] = pages
        return pages
    
    def _add_row_to_pages(self, pages: List[Page], row_data: bytes):
        """Ajouter une ligne aux pages (créer nouvelle page si nécessaire)"""
        if not pages or not pages[-1].add_row(row_data):
            # Créer nouvelle page
            new_page = Page(pages[0].header.type if pages else PageType.TRACKS, 
                           self.next_page_index)
            self.next_page_index += 1
            
            # Lier à la page précédente
            if pages:
                pages[-1].header.next_page = new_page.header.page_index
            
            pages.append(new_page)
            new_page.add_row(row_data)
    
    def _write_pdb_file(self, output_path: Path):
        """Écrire le fichier PDB complet"""
        with open(output_path, 'wb') as f:
            # En-tête de fichier
            self._write_file_header(f)
            
            # Pages (la première page est l'en-tête)
            f.write(b'\x00' * (PAGE_SIZE - f.tell()))
            
            # Écrire toutes les pages des tables
            for page_type, pages in self.tables.items():
                for page in pages:
                    f.write(page.to_bytes())
    
    def _write_file_header(self, f: BinaryIO):
        """Écrire l'en-tête du fichier PDB"""
        # Construire les pointeurs de table
        table_pointers = []
        current_page = 1
        
        for page_type, pages in self.tables.items():
            if pages:
                first_page = pages[0].header.page_index
                last_page = pages[-1].header.page_index
                
                pointer = TablePointer(
                    type=page_type,
                    empty_candidate=last_page + 1,
                    first_page=first_page,
                    last_page=last_page
                )
                table_pointers.append(pointer)
        
        # En-tête principal
        f.write(struct.pack('<I', 0))  # magic (toujours 0)
        f.write(struct.pack('<I', PAGE_SIZE))  # len_page
        f.write(struct.pack('<I', len(table_pointers)))  # num_tables
        f.write(struct.pack('<I', self.next_page_index))  # next_unused_page
        f.write(struct.pack('<I', 5))  # unknown1 (observé comme 5)
        f.write(struct.pack('<I', self.sequence))  # sequence
        f.write(struct.pack('<I', 0))  # gap
        
        # Pointeurs des tables
        for pointer in table_pointers:
            f.write(pointer.to_bytes())

# Factory function pour l'intégration avec BSM
def export_nml_to_cdj_pdb(nml_path: str, output_dir: str, 
                         music_root: Optional[str] = None) -> bool:
    """Convertir NML Traktor vers format PDB CDJ"""
    try:
        from parser.bsm_nml_parser import create_traktor_parser
        
        # Parser NML
        parser = create_traktor_parser(nml_path, music_root)
        playlist_structure = parser.get_playlists_with_structure()
        
        # Collecter tous les tracks
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
        
        # Export vers PDB
        exporter = PDBExporter()
        output_path = Path(output_dir) / "export.pdb"
        result = exporter.export_collection_to_pdb(all_tracks, output_path)
        
        logging.info(f"PDB export completed: {result}")
        return result['status'] == 'success'
        
    except Exception as e:
        logging.error(f"PDB export failed: {e}")
        return False