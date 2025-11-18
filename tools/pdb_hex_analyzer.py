#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyseur Hexadécimal PDB DeviceSQL - Version Robuste
Outil de reverse engineering avec logging complet et gestion d'erreurs renforcée
Analyse structure binaire pour conformité CDJ hardware
"""

import struct
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union


class RobustLogger:
    """Système de logging robuste avec multiple outputs."""
    
    def __init__(self, log_file: Optional[str] = None, console_level: int = logging.INFO):
        self.logger = logging.getLogger('PDBAnalyzer')
        self.logger.setLevel(logging.DEBUG)
        
        # Éviter les handlers multiples
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Format détaillé
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(funcName)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Handler fichier
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
                self.logger.info(f"Logging vers fichier: {log_file}")
            except Exception as e:
                self.logger.warning(f"Impossible de créer le log fichier: {e}")
    
    def debug(self, msg: str): self.logger.debug(msg)
    def info(self, msg: str): self.logger.info(msg)
    def warning(self, msg: str): self.logger.warning(msg)
    def error(self, msg: str): self.logger.error(msg)
    def critical(self, msg: str): self.logger.critical(msg)
    
    def log_exception(self, msg: str):
        """Log une exception avec traceback complet."""
        self.logger.error(f"{msg}\n{traceback.format_exc()}")


class DataValidator:
    """Validateur de données binaires pour éviter les corruptions."""
    
    @staticmethod
    def validate_file_size(data: bytes, min_size: int = 1024) -> bool:
        """Valide la taille minimale du fichier."""
        return len(data) >= min_size
    
    @staticmethod
    def validate_page_bounds(offset: int, page_size: int, data_length: int) -> bool:
        """Valide que la page est dans les limites du fichier."""
        return 0 <= offset < data_length and offset + page_size <= data_length
    
    @staticmethod
    def validate_string_bounds(offset: int, max_length: int, data_length: int) -> bool:
        """Valide qu'une chaîne ne dépasse pas les limites."""
        return 0 <= offset < data_length and offset + max_length <= data_length
    
    @staticmethod
    def validate_magic_bytes(data: bytes, expected_patterns: List[bytes]) -> bool:
        """Valide la présence de magic bytes attendus."""
        if len(data) < 4:
            return False
        return any(data.startswith(pattern) for pattern in expected_patterns)


class SafeDeviceSQLDecoder:
    """Décodeur de chaînes DeviceSQL avec protection contre les corruptions."""
    
    def __init__(self, logger: RobustLogger):
        self.logger = logger
        self.decode_attempts = 0
        self.decode_errors = 0
    
    def decode_string(self, data: bytes, offset: int, max_reasonable_length: int = 1024) -> Tuple[str, int]:
        """Décode une chaîne DeviceSQL avec validation complète."""
        self.decode_attempts += 1
        
        try:
            # Validation préliminaire
            if not DataValidator.validate_string_bounds(offset, 4, len(data)):
                self.decode_errors += 1
                self.logger.warning(f"Offset {offset} hors limites pour décodage chaîne")
                return "[ERREUR: Offset invalide]", offset + 1
            
            length_and_kind = data[offset]
            self.logger.debug(f"Décodage chaîne à offset {offset}, length_and_kind=0x{length_and_kind:02x}")
            
            # Chaîne vide
            if length_and_kind == 0:
                return "", offset + 1
            
            # Short ASCII (bit 0 = 1)
            if length_and_kind & 1:
                return self._decode_short_ascii(data, offset, length_and_kind, max_reasonable_length)
            
            # Long string (bit 0 = 0)
            else:
                return self._decode_long_string(data, offset, max_reasonable_length)
        
        except Exception as e:
            self.decode_errors += 1
            self.logger.error(f"Exception lors du décodage à offset {offset}: {e}")
            return f"[ERREUR: Exception {type(e).__name__}]", offset + 1
    
    def _decode_short_ascii(self, data: bytes, offset: int, length_and_kind: int, max_length: int) -> Tuple[str, int]:
        """Décode une chaîne ASCII courte."""
        length = (length_and_kind - 1) // 2
        
        # Validation de longueur
        if length < 0 or length > max_length:
            self.logger.warning(f"Longueur ASCII suspecte: {length} à offset {offset}")
            return f"[ERREUR: Longueur {length}]", offset + 1
        
        end_offset = offset + 1 + length
        if end_offset > len(data):
            self.logger.warning(f"Chaîne ASCII dépasse les limites à offset {offset}")
            return f"[ERREUR: Dépassement]", offset + 1
        
        try:
            string_bytes = data[offset + 1:end_offset]
            string = string_bytes.decode('ascii', errors='replace')
            self.logger.debug(f"ASCII décodé: '{string}' (longueur {length})")
            return string, end_offset
        
        except UnicodeDecodeError as e:
            self.logger.warning(f"Erreur décodage ASCII à offset {offset}: {e}")
            return f"[ERREUR: Unicode ASCII]", end_offset
    
    def _decode_long_string(self, data: bytes, offset: int, max_length: int) -> Tuple[str, int]:
        """Décode une chaîne longue (ASCII ou UTF-16)."""
        if offset + 4 > len(data):
            self.logger.warning(f"En-tête long string manquant à offset {offset}")
            return "[ERREUR: En-tête manquant]", offset + 1
        
        format_flag = data[offset]
        padding = data[offset + 1]
        total_length = struct.unpack('<H', data[offset + 2:offset + 4])[0]
        
        self.logger.debug(f"Long string: format=0x{format_flag:02x}, padding=0x{padding:02x}, length={total_length}")
        
        # Validation de longueur
        if total_length < 4 or total_length > max_length:
            self.logger.warning(f"Longueur long string suspecte: {total_length} à offset {offset}")
            return f"[ERREUR: Longueur {total_length}]", offset + 4
        
        end_offset = offset + total_length
        if end_offset > len(data):
            self.logger.warning(f"Long string dépasse les limites à offset {offset}")
            return f"[ERREUR: Dépassement]", offset + total_length
        
        string_data = data[offset + 4:end_offset]
        
        try:
            if format_flag == 0x40:  # Long ASCII
                string = string_data.decode('ascii', errors='replace')
                self.logger.debug(f"Long ASCII décodé: '{string}'")
            elif format_flag == 0x90:  # UTF-16 BE
                string = string_data.decode('utf-16be', errors='replace')
                self.logger.debug(f"UTF-16 BE décodé: '{string}'")
            else:
                self.logger.warning(f"Format flag inconnu: 0x{format_flag:02x}")
                string = f"[FORMAT INCONNU: 0x{format_flag:02x}]"
            
            return string, end_offset
        
        except UnicodeDecodeError as e:
            self.logger.warning(f"Erreur décodage long string à offset {offset}: {e}")
            return f"[ERREUR: Unicode long]", end_offset
    
    def get_stats(self) -> Dict[str, int]:
        """Retourne les statistiques de décodage."""
        return {
            "attempts": self.decode_attempts,
            "errors": self.decode_errors,
            "success_rate": (self.decode_attempts - self.decode_errors) / max(self.decode_attempts, 1) * 100
        }


class RobustPageAnalyzer:
    """Analyseur de pages avec gestion d'erreurs renforcée."""
    
    def __init__(self, data: bytes, logger: RobustLogger, page_size: int = 8192):
        self.data = data
        self.logger = logger
        self.page_size = page_size
        self.num_pages = len(data) // page_size
        self.decoder = SafeDeviceSQLDecoder(logger)
        
        self.logger.info(f"Initialisation analyseur: {len(data)} bytes, {self.num_pages} pages de {page_size} bytes")
    
    def analyze_page(self, page_index: int) -> Dict[str, Any]:
        """Analyse une page avec validation complète."""
        self.logger.debug(f"Analyse de la page {page_index}")
        
        # Validation de l'index
        if page_index < 0 or page_index >= self.num_pages:
            error_msg = f"Index de page invalide: {page_index} (max: {self.num_pages - 1})"
            self.logger.error(error_msg)
            return {"error": error_msg, "page_index": page_index}
        
        offset = page_index * self.page_size
        
        # Validation des limites
        if not DataValidator.validate_page_bounds(offset, self.page_size, len(self.data)):
            error_msg = f"Page {page_index} dépasse les limites du fichier"
            self.logger.error(error_msg)
            return {"error": error_msg, "page_index": page_index}
        
        try:
            return self._analyze_page_safe(page_index, offset)
        
        except Exception as e:
            self.logger.log_exception(f"Exception lors de l'analyse de la page {page_index}")
            return {
                "error": f"Exception: {type(e).__name__}",
                "page_index": page_index,
                "exception_details": str(e)
            }
    
    def _analyze_page_safe(self, page_index: int, offset: int) -> Dict[str, Any]:
        """Analyse sécurisée d'une page."""
        page_data = self.data[offset:offset + self.page_size]
        
        # En-tête de page (20 bytes minimum)
        if len(page_data) < 20:
            return {"error": "Page trop petite", "page_index": page_index}
        
        try:
            magic = struct.unpack('<I', page_data[0:4])[0]
            reported_size = struct.unpack('<I', page_data[4:8])[0]
            num_rows = struct.unpack('<I', page_data[8:12])[0]
            heap_offset = struct.unpack('<I', page_data[12:16])[0]
            page_type = struct.unpack('<I', page_data[16:20])[0]
        
        except struct.error as e:
            self.logger.error(f"Erreur de parsing en-tête page {page_index}: {e}")
            return {"error": f"Parsing en-tête: {e}", "page_index": page_index}
        
        self.logger.debug(f"Page {page_index}: magic=0x{magic:08x}, size={reported_size}, rows={num_rows}, heap={heap_offset}, type={page_type}")
        
        # Validation des valeurs
        validation_errors = []
        
        if reported_size != self.page_size:
            validation_errors.append(f"Taille rapportée {reported_size} != taille attendue {self.page_size}")
        
        if num_rows > 1000:  # Limite raisonnable
            validation_errors.append(f"Nombre de lignes suspect: {num_rows}")
        
        if heap_offset > self.page_size:
            validation_errors.append(f"Heap offset hors limites: {heap_offset}")
        
        if page_type > 20:  # Types connus jusqu'à ~18
            validation_errors.append(f"Type de page inhabituel: {page_type}")
        
        page_info = {
            "page_index": page_index,
            "offset": offset,
            "magic": f"0x{magic:08x}",
            "page_size": reported_size,
            "num_rows": num_rows,
            "heap_offset": heap_offset,
            "page_type": page_type,
            "validation_errors": validation_errors,
            "rows": []
        }
        
        # Analyser les lignes si les validations passent
        if not validation_errors and 0 < num_rows <= 100:  # Limite conservative
            page_info["rows"] = self._analyze_rows_safe(page_data, num_rows, page_type)
        elif validation_errors:
            self.logger.warning(f"Page {page_index} a des erreurs de validation: {validation_errors}")
        
        return page_info
    
    def _analyze_rows_safe(self, page_data: bytes, num_rows: int, page_type: int) -> List[Dict[str, Any]]:
        """Analyse sécurisée des lignes d'une page."""
        rows = []
        
        for i in range(num_rows):
            try:
                pointer_offset = 20 + (i * 4)
                
                if pointer_offset + 4 > len(page_data):
                    self.logger.warning(f"Pointeur ligne {i} hors limites")
                    continue
                
                row_offset = struct.unpack('<I', page_data[pointer_offset:pointer_offset + 4])[0]
                
                if row_offset >= len(page_data):
                    self.logger.warning(f"Offset ligne {i} hors limites: {row_offset}")
                    continue
                
                row_info = self._analyze_row_safe(page_data, row_offset, page_type, i)
                rows.append(row_info)
            
            except Exception as e:
                self.logger.error(f"Erreur analyse ligne {i}: {e}")
                rows.append({"error": str(e), "row_index": i})
        
        return rows
    
    def _analyze_row_safe(self, page_data: bytes, row_offset: int, page_type: int, row_index: int) -> Dict[str, Any]:
        """Analyse sécurisée d'une ligne."""
        
        if page_type == 0:  # Table des morceaux
            return self._analyze_track_row_safe(page_data, row_offset, row_index)
        elif page_type in [1, 2, 3, 4, 5, 6]:  # Tables de référence
            return self._analyze_reference_row_safe(page_data, row_offset, page_type, row_index)
        else:
            return {
                "type": "unknown",
                "page_type": page_type,
                "row_index": row_index,
                "offset": row_offset
            }
    
    def _analyze_track_row_safe(self, page_data: bytes, row_offset: int, row_index: int) -> Dict[str, Any]:
        """Analyse sécurisée d'une ligne de morceau."""
        
        if row_offset + 169 > len(page_data):
            return {
                "type": "track",
                "error": "Ligne tronquée",
                "row_index": row_index,
                "offset": row_offset
            }
        
        try:
            track_data = page_data[row_offset:row_offset + 169]
            
            # Parsing sécurisé des métadonnées
            unknown1 = struct.unpack('<H', track_data[0:2])[0]
            sample_rate = struct.unpack('<I', track_data[8:12])[0]
            file_size = struct.unpack('<I', track_data[16:20])[0]
            tempo = struct.unpack('<I', track_data[84:88])[0] / 100.0
            genre_id = struct.unpack('<I', track_data[88:92])[0]
            album_id = struct.unpack('<I', track_data[92:96])[0]
            artist_id = struct.unpack('<I', track_data[96:100])[0]
            track_id = struct.unpack('<I', track_data[100:104])[0]
            
            # Décodage sécurisé de quelques chaînes principales
            strings = []
            string_data_start = row_offset + 169
            
            # Essayer de décoder les 3 premières chaînes
            for i in range(min(3, 21)):
                ptr_offset = 127 + (i * 2)
                if ptr_offset + 2 <= len(track_data):
                    pointer = struct.unpack('<H', track_data[ptr_offset:ptr_offset + 2])[0]
                    string_offset = string_data_start + pointer
                    
                    if string_offset < len(page_data):
                        string_val, _ = self.decoder.decode_string(page_data, string_offset)
                        strings.append(f"String {i}: {string_val}")
            
            return {
                "type": "track",
                "row_index": row_index,
                "track_id": track_id,
                "artist_id": artist_id,
                "album_id": album_id,
                "genre_id": genre_id,
                "tempo": tempo,
                "sample_rate": sample_rate,
                "file_size": file_size,
                "strings_preview": strings
            }
        
        except Exception as e:
            self.logger.error(f"Erreur parsing track row {row_index}: {e}")
            return {
                "type": "track",
                "error": str(e),
                "row_index": row_index,
                "offset": row_offset
            }
    
    def _analyze_reference_row_safe(self, page_data: bytes, row_offset: int, page_type: int, row_index: int) -> Dict[str, Any]:
        """Analyse sécurisée d'une ligne de référence."""
        
        if row_offset + 8 > len(page_data):
            return {
                "type": "reference",
                "error": "Ligne tronquée",
                "row_index": row_index,
                "offset": row_offset
            }
        
        try:
            id1 = struct.unpack('<I', page_data[row_offset:row_offset + 4])[0]
            id2 = struct.unpack('<I', page_data[row_offset + 4:row_offset + 8])[0]
            
            string_val, _ = self.decoder.decode_string(page_data, row_offset + 8)
            
            table_names = {1: "genre", 2: "artist", 3: "album", 4: "label", 5: "key", 6: "color"}
            table_name = table_names.get(page_type, "unknown")
            
            return {
                "type": table_name,
                "row_index": row_index,
                "id": id1,
                "id2": id2,
                "name": string_val
            }
        
        except Exception as e:
            self.logger.error(f"Erreur parsing reference row {row_index}: {e}")
            return {
                "type": "reference",
                "error": str(e),
                "row_index": row_index,
                "offset": row_offset
            }


class RobustPDBAnalyzer:
    """Analyseur principal robuste avec logging complet."""
    
    def __init__(self, file_path: str, log_file: Optional[str] = None):
        self.file_path = Path(file_path)
        self.data = None
        self.file_header = None
        self.page_analyzer = None
        
        # Configuration du logging
        if log_file is None:
            log_file = self.file_path.parent / f"pdb_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        self.logger = RobustLogger(str(log_file))
        self.logger.info(f"Début d'analyse PDB: {self.file_path}")
    
    def load_file(self) -> bool:
        """Charge et valide le fichier PDB."""
        try:
            self.logger.info(f"Chargement du fichier: {self.file_path}")
            
            if not self.file_path.exists():
                self.logger.error(f"Fichier non trouvé: {self.file_path}")
                return False
            
            file_size = self.file_path.stat().st_size
            self.logger.info(f"Taille du fichier: {file_size} bytes")
            
            with open(self.file_path, 'rb') as f:
                self.data = f.read()
            
            # Validations de base
            if not DataValidator.validate_file_size(self.data, 1024):
                self.logger.error("Fichier trop petit pour être un PDB valide")
                return False
            
            if not DataValidator.validate_magic_bytes(self.data, [b'\x00\x00\x00\x00']):
                self.logger.warning("Magic bytes non standards détectés")
            
            self.logger.info(f"Fichier chargé avec succès: {len(self.data)} bytes")
            return True
        
        except Exception as e:
            self.logger.log_exception("Erreur lors du chargement du fichier")
            return False
    
    def analyze_file_header(self) -> Dict[str, Any]:
        """Analyse l'en-tête avec validation complète."""
        self.logger.info("Analyse de l'en-tête du fichier")
        
        if len(self.data) < 28:
            error_msg = "Fichier trop petit pour contenir un en-tête valide"
            self.logger.error(error_msg)
            return {"error": error_msg}
        
        try:
            magic = struct.unpack('<I', self.data[0:4])[0]
            page_size = struct.unpack('<I', self.data[4:8])[0]
            num_tables = struct.unpack('<I', self.data[8:12])[0]
            next_unused = struct.unpack('<I', self.data[12:16])[0]
            unknown = struct.unpack('<I', self.data[16:20])[0]
            sequence = struct.unpack('<I', self.data[20:24])[0]
            padding = struct.unpack('<I', self.data[24:28])[0]
            
            self.logger.debug(f"En-tête parsé: magic=0x{magic:08x}, page_size={page_size}, num_tables={num_tables}")
            
            # Validations
            validation_errors = []
            
            if page_size not in [4096, 8192, 16384]:
                validation_errors.append(f"Taille de page inhabituelle: {page_size}")
            
            if num_tables > 50:
                validation_errors.append(f"Nombre de tables suspect: {num_tables}")
            
            if next_unused * page_size > len(self.data):
                validation_errors.append(f"Next unused page hors limites: {next_unused}")
            
            self.file_header = {
                "magic": f"0x{magic:08x}",
                "page_size": page_size,
                "num_tables": num_tables,
                "next_unused_page": next_unused,
                "unknown_field": f"0x{unknown:08x}",
                "sequence": sequence,
                "padding": f"0x{padding:08x}",
                "validation_errors": validation_errors,
                "tables": []
            }
            
            # Index des tables
            for i in range(min(num_tables, 20)):  # Limite sécuritaire
                offset = 28 + (i * 4)
                if offset + 4 <= len(self.data):
                    table_type = struct.unpack('<H', self.data[offset:offset + 2])[0]
                    start_page = struct.unpack('<H', self.data[offset + 2:offset + 4])[0]
                    
                    self.file_header["tables"].append({
                        "type": table_type,
                        "start_page": start_page
                    })
                    
                    self.logger.debug(f"Table {table_type}: page {start_page}")
            
            # Initialiser l'analyseur de pages
            self.page_analyzer = RobustPageAnalyzer(self.data, self.logger, page_size)
            
            if validation_errors:
                self.logger.warning(f"Erreurs de validation en-tête: {validation_errors}")
            else:
                self.logger.info("En-tête validé avec succès")
            
            return self.file_header
        
        except Exception as e:
            self.logger.log_exception("Erreur lors de l'analyse de l'en-tête")
            return {"error": f"Exception: {type(e).__name__}"}
    
    def analyze_pages(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """Analyse les pages avec gestion d'erreurs."""
        self.logger.info(f"Analyse de {max_pages} pages maximum")
        
        if not self.page_analyzer:
            self.logger.error("Analyseur de pages non initialisé")
            return []
        
        pages = []
        actual_pages = min(self.page_analyzer.num_pages, max_pages)
        
        for i in range(actual_pages):
            self.logger.debug(f"Analyse page {i}/{actual_pages - 1}")
            page_info = self.page_analyzer.analyze_page(i)
            pages.append(page_info)
            
            # Log des erreurs de page
            if "error" in page_info:
                self.logger.warning(f"Erreur page {i}: {page_info['error']}")
        
        # Statistiques de décodage
        decoder_stats = self.page_analyzer.decoder.get_stats()
        self.logger.info(f"Statistiques décodage: {decoder_stats}")
        
        return pages
    
    def create_detailed_report(self) -> str:
        """Génère un rapport détaillé avec toutes les informations."""
        self.logger.info("Génération du rapport détaillé")
        
        if not self.load_file():
            return "Erreur: Impossible de charger le fichier"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append(f"RAPPORT D'ANALYSE PDB DETAILLE")
        report_lines.append(f"Fichier: {self.file_path}")
        report_lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 80)
        
        # En-tête
        header = self.analyze_file_header()
        if "error" in header:
            report_lines.append(f"\nERREUR EN-TÊTE: {header['error']}")
            return '\n'.join(report_lines)
        
        report_lines.append(f"\n=== EN-TÊTE FICHIER ===")
        report_lines.append(f"Magic: {header['magic']}")
        report_lines.append(f"Taille de page: {header['page_size']} bytes")
        report_lines.append(f"Nombre de tables: {header['num_tables']}")
        report_lines.append(f"Prochaine page libre: {header['next_unused_page']}")
        report_lines.append(f"Séquence: {header['sequence']}")
        
        if header['validation_errors']:
            report_lines.append(f"\n⚠️  ERREURS DE VALIDATION:")
            for error in header['validation_errors']:
                report_lines.append(f"   - {error}")
        
        # Tables
        report_lines.append(f"\n=== INDEX DES TABLES ===")
        for table in header['tables']:
            report_lines.append(f"Table {table['type']}: commence page {table['start_page']}")
        
        # Pages
        pages = self.analyze_pages(8)
        report_lines.append(f"\n=== ANALYSE DES PAGES ({len(pages)} analysées) ===")
        
        for page in pages:
            if "error" in page:
                report_lines.append(f"\nPage {page['page_index']}: ERREUR - {page['error']}")
                continue
            
            report_lines.append(f"\n--- Page {page['page_index']} (type {page['page_type']}) ---")
            report_lines.append(f"Lignes: {page['num_rows']}, Heap: {page['heap_offset']}")
            
            if page['validation_errors']:
                report_lines.append(f"⚠️  Erreurs: {', '.join(page['validation_errors'])}")
            
            # Afficher quelques lignes
            for row in page['rows'][:3]:
                if "error" in row:
                    report_lines.append(f"   ERREUR ligne {row.get('row_index', '?')}: {row['error']}")
                elif row['type'] == 'track':
                    report_lines.append(f"   Morceau {row['track_id']}: {row['tempo']} BPM")
                    if row.get('strings_preview'):
                        for string_info in row['strings_preview'][:2]:
                            report_lines.append(f"      {string_info}")
                elif row['type'] in ['artist', 'album', 'genre', 'key', 'color']:
                    report_lines.append(f"   {row['type'].title()} {row['id']}: {row['name']}")
        
        # Statistiques finales
        if self.page_analyzer:
            stats = self.page_analyzer.decoder.get_stats()
            report_lines.append(f"\n=== STATISTIQUES DE DECODAGE ===")
            report_lines.append(f"Tentatives: {stats['attempts']}")
            report_lines.append(f"Erreurs: {stats['errors']}")
            report_lines.append(f"Taux de succès: {stats['success_rate']:.1f}%")
        
        self.logger.info("Rapport généré avec succès")
        return '\n'.join(report_lines)


def main():
    """Interface robuste en ligne de commande."""
    print("=== Analyseur PDB Robuste avec Logging ===")
    print("Version renforcée pour reverse engineering DeviceSQL")
    print()
    
    # Obtenir le fichier à analyser
    file_path = input("Chemin vers export.pdb: ").strip()
    if not file_path:
        print("Erreur: Chemin requis")
        return 1
    
    # Créer l'analyseur
    analyzer = RobustPDBAnalyzer(file_path)
    
    try:
        # Générer le rapport
        print("\nAnalyse en cours...")
        report = analyzer.create_detailed_report()
        
        # Afficher le rapport
        print("\n" + "="*50)
        print(report)
        
        # Sauvegarder
        report_file = Path(file_path).parent / f"pdb_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n✓ Rapport sauvegardé: {report_file}")
        print(f"✓ Log détaillé disponible dans le même répertoire")
        
        return 0
    
    except Exception as e:
        print(f"\nErreur critique: {e}")
        print(f"Détails: {traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    exit(main())
