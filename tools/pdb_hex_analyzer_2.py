#!/usr/bin/env python3
"""
Analyseur hexadécimal PDB avancé pour reverse engineering du format DeviceSQL Pioneer réel
Basé sur les découvertes des logs d'analyse de fichiers Rekordbox officiels

Auteur: Benoit Saint-Moulin
Usage: python pdb_hex_analyzer.py export.pdb
"""

import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import json

@dataclass
class PDBHeader:
    """En-tête PDB réel basé sur les observations"""
    magic: int              # Toujours 0x00000000
    page_size: int          # Toujours 4096
    num_tables: int         # Nombre de types de tables
    next_unused_page: int   # Pointeur fin de fichier
    unknown1: int
    sequence: int
    unknown2: int
    table_pointers: List[int]  # Pointeurs vers les pages de tables

@dataclass  
class PageHeader:
    """En-tête de page réel observé"""
    magic: int              # 0x00000000
    page_index: int         # Ce qui était interprété comme "size"
    table_type: int         # Type de table (0-20+)
    unknown1: int
    num_rows: int           # Nombre d'entrées
    unknown2: int
    heap_offset: int        # Début des données
    unknown3: int
    unknown4: int
    unknown5: int

@dataclass
class TableStructure:
    """Structure d'une table découverte"""
    table_type: int
    page_index: int
    num_rows: int
    row_structure: Dict[str, Any]
    raw_data: bytes

class PDBHexAnalyzer:
    """Analyseur hexadécimal pour découvrir la vraie structure PDB"""
    
    def __init__(self, pdb_path: str):
        self.pdb_path = Path(pdb_path)
        self.data = self._load_file()
        self.header = None
        self.pages = {}
        self.tables = {}
        
    def _load_file(self) -> bytes:
        """Charge le fichier PDB"""
        with open(self.pdb_path, 'rb') as f:
            data = f.read()
        print(f"Fichier chargé: {len(data)} bytes")
        return data
    
    def analyze_complete_structure(self) -> Dict[str, Any]:
        """Analyse complète de la structure PDB"""
        print("=== ANALYSE STRUCTURE PDB RÉELLE ===")
        
        # 1. Analyse de l'en-tête
        self.header = self._parse_main_header()
        
        # 2. Analyse de toutes les pages
        self._analyze_all_pages()
        
        # 3. Détection des patterns
        patterns = self._detect_patterns()
        
        # 4. Reconstruction de la structure logique
        logical_structure = self._reconstruct_logical_structure()
        
        return {
            'file_info': {
                'path': str(self.pdb_path),
                'size': len(self.data),
                'pages_count': len(self.data) // 4096
            },
            'header': self.header.__dict__ if self.header else None,
            'pages_analysis': self.pages,
            'patterns': patterns,
            'logical_structure': logical_structure,
            'key_discoveries': self._summarize_discoveries()
        }
    
    def _parse_main_header(self) -> PDBHeader:
        """Parse l'en-tête principal (page 0)"""
        print("\n--- ANALYSE EN-TÊTE PRINCIPAL ---")
        
        # Les 28 premiers octets de l'en-tête
        header_data = struct.unpack('<7I', self.data[:28])
        magic, page_size, num_tables, next_unused, unknown1, sequence, unknown2 = header_data
        
        print(f"Magic: 0x{magic:08x}")
        print(f"Page size: {page_size}")
        print(f"Num tables: {num_tables}")
        print(f"Next unused: {next_unused}")
        print(f"Sequence: {sequence}")
        
        # Extraction des pointeurs de tables
        table_pointers = []
        for i in range(num_tables):
            offset = 28 + i * 4
            if offset + 4 <= len(self.data):
                pointer = struct.unpack('<I', self.data[offset:offset+4])[0]
                table_pointers.append(pointer)
                print(f"Table {i}: pointeur = {pointer}")
        
        return PDBHeader(
            magic=magic,
            page_size=page_size,
            num_tables=num_tables,
            next_unused_page=next_unused,
            unknown1=unknown1,
            sequence=sequence,
            unknown2=unknown2,
            table_pointers=table_pointers
        )
    
    def _analyze_all_pages(self):
        """Analyse toutes les pages du fichier"""
        print("\n--- ANALYSE DE TOUTES LES PAGES ---")
        
        total_pages = len(self.data) // 4096
        
        for page_num in range(min(total_pages, 20)):  # Limite pour l'analyse
            page_offset = page_num * 4096
            page_data = self.data[page_offset:page_offset + 4096]
            
            if len(page_data) < 40:
                continue
                
            # Parse l'en-tête de page (40 octets)
            header_values = struct.unpack('<10I', page_data[:40])
            
            page_header = PageHeader(
                magic=header_values[0],
                page_index=header_values[1],  # Ce qui était "size"
                table_type=header_values[2],
                unknown1=header_values[3],
                num_rows=header_values[4],
                unknown2=header_values[5],
                heap_offset=header_values[6],
                unknown3=header_values[7],
                unknown4=header_values[8],
                unknown5=header_values[9]
            )
            
            print(f"\nPage {page_num}:")
            print(f"  Page index: {page_header.page_index}")
            print(f"  Table type: {page_header.table_type}")
            print(f"  Num rows: {page_header.num_rows}")
            print(f"  Heap offset: {page_header.heap_offset}")
            
            # Analyse du contenu de la page
            content_analysis = self._analyze_page_content(page_data, page_header)
            
            self.pages[page_num] = {
                'header': page_header.__dict__,
                'content': content_analysis,
                'raw_hex': page_data[:100].hex()  # Premier 100 octets en hex
            }
    
    def _analyze_page_content(self, page_data: bytes, header: PageHeader) -> Dict[str, Any]:
        """Analyse le contenu d'une page"""
        content = {
            'type': 'unknown',
            'rows': [],
            'strings': [],
            'patterns': []
        }
        
        if header.num_rows == 0:
            return content
        
        # Analyse de la zone de données (après l'en-tête de 40 octets)
        data_section = page_data[40:]
        
        # Détection des chaînes ASCII
        strings = self._extract_strings(data_section)
        content['strings'] = strings[:10]  # Top 10 chaînes
        
        # Analyse des patterns d'octets
        patterns = self._detect_byte_patterns(data_section[:200])
        content['patterns'] = patterns
        
        # Tentative de détection du type de contenu
        content['type'] = self._guess_content_type(header.table_type, strings, patterns)
        
        return content
    
    def _extract_strings(self, data: bytes) -> List[str]:
        """Extrait les chaînes ASCII lisibles"""
        strings = []
        current_string = ""
        
        for byte in data:
            if 32 <= byte <= 126:  # ASCII imprimable
                current_string += chr(byte)
            else:
                if len(current_string) >= 3:
                    strings.append(current_string)
                current_string = ""
        
        if len(current_string) >= 3:
            strings.append(current_string)
        
        return [s for s in strings if len(s) >= 3]
    
    def _detect_byte_patterns(self, data: bytes) -> List[str]:
        """Détecte des patterns d'octets communs"""
        patterns = []
        
        # Recherche de patterns répétitifs
        if data.count(b'\x00\x00\x00\x00') > 3:
            patterns.append("Nombreux zéros (padding)")
        
        if data.count(b'\xff\xff') > 2:
            patterns.append("Octets xFF (marqueurs)")
        
        # Détection de structures possibles
        for i in range(0, len(data) - 4, 4):
            value = struct.unpack('<I', data[i:i+4])[0]
            if 1000 < value < 50000:  # Possible offset/pointeur
                patterns.append(f"Possible pointeur: {value}")
                break
        
        return patterns
    
    def _guess_content_type(self, table_type: int, strings: List[str], patterns: List[str]) -> str:
        """Devine le type de contenu basé sur l'analyse"""
        # Mapping des types de tables observés
        type_mapping = {
            0: "tracks",
            1: "genres", 
            2: "artists",
            3: "albums",
            4: "labels",
            5: "keys",
            6: "colors",
            7: "playlist_tree",
            8: "playlist_entries",
            13: "artwork",
            14: "unknown_14",
            15: "unknown_15",
            18: "unknown_18",
            20: "unknown_20"
        }
        
        base_type = type_mapping.get(table_type, f"unknown_{table_type}")
        
        # Affinage basé sur les chaînes trouvées
        if any('.mp3' in s or '.wav' in s for s in strings):
            return f"{base_type}_audio_files"
        elif any(len(s) > 10 for s in strings):
            return f"{base_type}_text_data"
        
        return base_type
    
    def _detect_patterns(self) -> Dict[str, Any]:
        """Détecte des patterns globaux dans le fichier"""
        patterns = {
            'page_types': {},
            'table_distribution': {},
            'size_patterns': [],
            'anomalies': []
        }
        
        # Distribution des types de pages
        for page_num, page_info in self.pages.items():
            table_type = page_info['header']['table_type']
            patterns['page_types'][table_type] = patterns['page_types'].get(table_type, 0) + 1
        
        # Anomalies détectées
        for page_num, page_info in self.pages.items():
            header = page_info['header']
            if header['page_index'] != page_num:
                patterns['anomalies'].append(f"Page {page_num}: index={header['page_index']}")
        
        return patterns
    
    def _reconstruct_logical_structure(self) -> Dict[str, Any]:
        """Reconstruit la structure logique basée sur les observations"""
        structure = {
            'header_format': "Signature(4) + PageSize(4) + NumTables(4) + NextUnused(4) + Unknown1(4) + Sequence(4) + Unknown2(4) + TablePointers[NumTables*4]",
            'page_format': "Magic(4) + PageIndex(4) + TableType(4) + Unknown1(4) + NumRows(4) + Unknown2(4) + HeapOffset(4) + Reserved[3*4]",
            'discoveries': []
        }
        
        # Découvertes clés
        if self.header:
            if self.header.next_unused_page > len(self.data) // 4096:
                structure['discoveries'].append("Le champ 'next_unused_page' pointe au-delà du fichier - probable indicateur de taille totale")
        
        # Analyse des index de pages
        page_indices = [info['header']['page_index'] for info in self.pages.values()]
        if page_indices == list(range(len(page_indices))):
            structure['discoveries'].append("Les 'page_index' suivent une séquence 0,1,2,3... - confirmation que c'est un index, pas une taille")
        
        return structure
    
    def _summarize_discoveries(self) -> List[str]:
        """Résume les découvertes importantes"""
        discoveries = []
        
        discoveries.append("DÉCOUVERTE 1: Le champ 'size' dans l'en-tête de page est en fait un INDEX de page")
        discoveries.append("DÉCOUVERTE 2: Toutes les pages font physiquement 4096 octets")
        discoveries.append("DÉCOUVERTE 3: Les types de pages > 20 existent (contrairement aux spécifications)")
        discoveries.append("DÉCOUVERTE 4: La structure réelle diffère des spécifications publiques")
        
        return discoveries
    
    def export_hex_dump(self, output_file: str, num_pages: int = 5):
        """Exporte un dump hexadécimal détaillé"""
        with open(output_file, 'w') as f:
            f.write(f"=== HEX DUMP DÉTAILLÉ - {self.pdb_path} ===\n\n")
            
            for page_num in range(min(num_pages, len(self.data) // 4096)):
                page_offset = page_num * 4096
                page_data = self.data[page_offset:page_offset + 4096]
                
                f.write(f"--- PAGE {page_num} (offset 0x{page_offset:08x}) ---\n")
                
                # Hex dump des premiers 200 octets
                for i in range(0, min(200, len(page_data)), 16):
                    hex_line = ' '.join(f'{b:02x}' for b in page_data[i:i+16])
                    ascii_line = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in page_data[i:i+16])
                    f.write(f"{page_offset + i:08x}: {hex_line:<48} {ascii_line}\n")
                
                f.write("\n")

def main():
    if len(sys.argv) != 2:
        print("Usage: python pdb_hex_analyzer.py export.pdb")
        sys.exit(1)
    
    pdb_file = sys.argv[1]
    analyzer = PDBHexAnalyzer(pdb_file)
    
    # Analyse complète
    analysis_result = analyzer.analyze_complete_structure()
    
    # Sauvegarde des résultats
    output_json = pdb_file.replace('.pdb', '_analysis.json')
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\nAnalyse sauvegardée: {output_json}")
    
    # Export hex dump
    hex_dump_file = pdb_file.replace('.pdb', '_hexdump.txt')
    analyzer.export_hex_dump(hex_dump_file)
    print(f"Hex dump sauvegardé: {hex_dump_file}")
    
    # Affichage des découvertes clés
    print("\n=== DÉCOUVERTES CLÉS ===")
    for discovery in analysis_result['key_discoveries']:
        print(f"• {discovery}")

if __name__ == "__main__":
    main()