#!/usr/bin/env python3
"""
PDB Reader Enhanced - Lecteur optimisé pour debug export CDJ
Spécialement adapté pour diagnostiquer les problèmes d'export Traktor Bridge

Nouvelles fonctionnalités :
- Comparaison de fichiers PDB
- Validation de structure CDJ
- Export détaillé pour debug
"""

import os
import sys
import struct
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import argparse
import logging
from difflib import unified_diff

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import optionnel de pyrekordbox
try:
    import pyrekordbox
    from pyrekordbox import Rekordbox6Database, MasterDatabase
    PYREKORDBOX_AVAILABLE = True
    logger.info("pyrekordbox disponible - support Rekordbox 6/7 activé")
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    logger.warning("pyrekordbox non disponible - PDB DeviceSQL uniquement")

@dataclass
class PDBValidationResult:
    """Résultat de validation d'un fichier PDB"""
    is_valid: bool
    cdj_compatible: bool
    issues: List[str]
    warnings: List[str]
    structure_score: float  # 0-100
    
@dataclass
class PDBComparison:
    """Comparaison entre deux fichiers PDB"""
    files: Dict[str, str]
    header_diff: Dict[str, Any]
    table_diff: Dict[str, Any]
    content_diff: Dict[str, Any]
    compatibility_score: float

class PDBValidator:
    """Validateur de fichiers PDB pour compatibilité CDJ"""
    
    CDJ_REQUIREMENTS = {
        'min_page_length': 4096,
        'required_tables': ['tracks', 'artists', 'albums', 'playlists'],
        'max_file_size_mb': 2000,
        'encoding': 'utf-16le'
    }
    
    def __init__(self):
        self.issues = []
        self.warnings = []
    
    def validate_pdb(self, pdb_path: str) -> PDBValidationResult:
        """Valide un fichier PDB pour compatibilité CDJ"""
        self.issues.clear()
        self.warnings.clear()
        
        try:
            reader = PDBReader(pdb_path)
            
            # Validation header
            self._validate_header(reader.header)
            
            # Validation structure
            self._validate_structure(reader.tables)
            
            # Validation contenu
            self._validate_content(reader)
            
            # Score de compatibilité
            structure_score = self._calculate_score()
            
            return PDBValidationResult(
                is_valid=len(self.issues) == 0,
                cdj_compatible=len(self.issues) == 0 and structure_score > 80,
                issues=self.issues.copy(),
                warnings=self.warnings.copy(),
                structure_score=structure_score
            )
            
        except Exception as e:
            self.issues.append(f"Erreur critique: {e}")
            return PDBValidationResult(False, False, self.issues, self.warnings, 0)
    
    def _validate_header(self, header):
        """Valide l'en-tête PDB"""
        if not header.valid:
            self.issues.append("En-tête PDB invalide")
        
        if header.page_length < self.CDJ_REQUIREMENTS['min_page_length']:
            self.warnings.append(f"Taille de page faible: {header.page_length}")
        
        if header.num_tables == 0:
            self.issues.append("Aucune table trouvée")
    
    def _validate_structure(self, tables):
        """Valide la structure des tables"""
        table_names = [t.name for t in tables]
        
        for required in self.CDJ_REQUIREMENTS['required_tables']:
            if required not in table_names:
                self.issues.append(f"Table manquante: {required}")
    
    def _validate_content(self, reader):
        """Valide le contenu des tables"""
        # Vérification basique du contenu
        try:
            tracks_table = next((t for t in reader.tables if t.name == 'tracks'), None)
            if tracks_table and tracks_table.entry_count == 0:
                self.warnings.append("Aucune piste trouvée")
        except:
            pass
    
    def _calculate_score(self) -> float:
        """Calcule un score de compatibilité"""
        score = 100.0
        score -= len(self.issues) * 25  # -25 points par erreur critique
        score -= len(self.warnings) * 5  # -5 points par warning
        return max(0, score)

class PDBComparator:
    """Comparateur de fichiers PDB"""
    
    def compare_pdb_files(self, file1: str, file2: str) -> PDBComparison:
        """Compare deux fichiers PDB"""
        try:
            reader1 = PDBReader(file1)
            reader2 = PDBReader(file2)
            
            data1 = reader1.read_complete_database()
            data2 = reader2.read_complete_database()
            
            # Comparaison des en-têtes
            header_diff = self._compare_headers(
                data1['database_info'].get('header'),
                data2['database_info'].get('header')
            )
            
            # Comparaison des tables
            table_diff = self._compare_tables(
                data1['tables'],
                data2['tables']
            )
            
            # Comparaison du contenu
            content_diff = self._compare_content(data1, data2)
            
            # Score de compatibilité
            compatibility_score = self._calculate_compatibility_score(
                header_diff, table_diff, content_diff
            )
            
            return PDBComparison(
                files={'file1': file1, 'file2': file2},
                header_diff=header_diff,
                table_diff=table_diff,
                content_diff=content_diff,
                compatibility_score=compatibility_score
            )
            
        except Exception as e:
            logger.error(f"Erreur comparaison: {e}")
            return PDBComparison({}, {}, {}, {}, 0)
    
    def _compare_headers(self, header1, header2):
        """Compare les en-têtes"""
        if not header1 or not header2:
            return {'error': 'En-tête manquant'}
        
        diff = {}
        for key in header1.keys():
            if header1[key] != header2.get(key):
                diff[key] = {'file1': header1[key], 'file2': header2.get(key)}
        
        return diff
    
    def _compare_tables(self, tables1, tables2):
        """Compare les tables"""
        diff = {
            'missing_in_file1': [],
            'missing_in_file2': [],
            'count_differences': {}
        }
        
        tables1_names = set(tables1.keys())
        tables2_names = set(tables2.keys())
        
        diff['missing_in_file1'] = list(tables2_names - tables1_names)
        diff['missing_in_file2'] = list(tables1_names - tables2_names)
        
        # Comparaison des comptes
        for table_name in tables1_names & tables2_names:
            count1 = tables1[table_name].get('count', 0)
            count2 = tables2[table_name].get('count', 0)
            if count1 != count2:
                diff['count_differences'][table_name] = {
                    'file1': count1,
                    'file2': count2
                }
        
        return diff
    
    def _compare_content(self, data1, data2):
        """Compare le contenu détaillé"""
        # Comparaison simplifiée des statistiques
        stats1 = data1['database_info']['stats']
        stats2 = data2['database_info']['stats']
        
        content_diff = {}
        for key in ['total_tracks', 'total_playlists', 'total_artists']:
            if stats1.get(key) != stats2.get(key):
                content_diff[key] = {
                    'file1': stats1.get(key),
                    'file2': stats2.get(key)
                }
        
        return content_diff
    
    def _calculate_compatibility_score(self, header_diff, table_diff, content_diff):
        """Calcule un score de compatibilité entre fichiers"""
        score = 100.0
        
        # Pénalités
        score -= len(header_diff) * 10
        score -= len(table_diff.get('missing_in_file1', [])) * 15
        score -= len(table_diff.get('missing_in_file2', [])) * 15
        score -= len(table_diff.get('count_differences', {})) * 5
        score -= len(content_diff) * 10
        
        return max(0, score)

# Classe PDBReader originale (conservée)
class PDBReader:
    """Lecteur de fichiers PDB avec fonctionnalités étendues"""
    
    TABLE_TYPES = {
        0: ("tracks", "Pistes - métadonnées principales"),
        1: ("genres", "Genres musicaux"),
        2: ("artists", "Artistes"),
        3: ("albums", "Albums"),
        4: ("labels", "Labels/Maisons de disque"),
        5: ("keys", "Clés musicales"),
        6: ("colors", "Couleurs de tags"),
        7: ("playlist_tree", "Structure hiérarchique des playlists"),
        8: ("playlist_entries", "Entrées des playlists"),
        13: ("artwork", "Pochettes d'albums"),
        17: ("history_playlists", "Playlists d'historique"),
        18: ("history_entries", "Entrées d'historique")
    }
    
    # [Le reste de la classe PDBReader reste identique...]
    def __init__(self, db_path: str, cipher_key: Optional[str] = None):
        self.db_path = Path(db_path)
        self.cipher_key = cipher_key
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {self.db_path}")
        
        self.db_type = self._detect_database_type()
        
        if self.db_type == "pdb":
            self._init_pdb()
        else:
            raise ValueError(f"Type non supporté: {self.db_type}")
    
    def _detect_database_type(self) -> str:
        try:
            with open(self.db_path, 'rb') as f:
                header = f.read(4)
                if len(header) >= 4:
                    signature = struct.unpack('<I', header)[0]
                    if signature == 0:
                        return "pdb"
        except:
            pass
        raise ValueError("Type de base non reconnu")
    
    def _init_pdb(self):
        self.file_handle = open(self.db_path, 'rb')
        self.header = self._read_pdb_header()
        if not self.header.valid:
            raise ValueError("En-tête PDB invalide")
        self.tables = self._read_table_info()
    
    # [Autres méthodes identiques...]

def main():
    """Interface CLI étendue"""
    parser = argparse.ArgumentParser(description='Lecteur PDB avec outils de debug CDJ')
    parser.add_argument('database', help='Fichier PDB à analyser')
    parser.add_argument('--compare', '-c', help='Comparer avec un autre fichier PDB')
    parser.add_argument('--validate', '-val', action='store_true', help='Valider pour compatibilité CDJ')
    parser.add_argument('--summary', '-s', action='store_true', help='Résumé uniquement')
    parser.add_argument('--output', '-o', help='Fichier JSON de sortie')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mode verbeux')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Validation CDJ
        if args.validate:
            validator = PDBValidator()
            result = validator.validate_pdb(args.database)
            
            print(f"\n=== VALIDATION CDJ ===")
            print(f"✅ Valide: {'Oui' if result.is_valid else 'Non'}")
            print(f"🎧 Compatible CDJ: {'Oui' if result.cdj_compatible else 'Non'}")
            print(f"📊 Score: {result.structure_score:.1f}/100")
            
            if result.issues:
                print(f"\n❌ ERREURS:")
                for issue in result.issues:
                    print(f"  - {issue}")
            
            if result.warnings:
                print(f"\n⚠️  AVERTISSEMENTS:")
                for warning in result.warnings:
                    print(f"  - {warning}")
        
        # Comparaison
        if args.compare:
            comparator = PDBComparator()
            comparison = comparator.compare_pdb_files(args.database, args.compare)
            
            print(f"\n=== COMPARAISON PDB ===")
            print(f"📁 Fichier 1: {comparison.files.get('file1', 'N/A')}")
            print(f"📁 Fichier 2: {comparison.files.get('file2', 'N/A')}")
            print(f"🎯 Compatibilité: {comparison.compatibility_score:.1f}/100")
            
            if comparison.header_diff:
                print(f"\n📋 Différences en-tête:")
                for key, diff in comparison.header_diff.items():
                    print(f"  {key}: {diff['file1']} vs {diff['file2']}")
            
            if comparison.table_diff:
                print(f"\n📊 Différences tables:")
                td = comparison.table_diff
                if td.get('missing_in_file1'):
                    print(f"  Manquant dans fichier 1: {td['missing_in_file1']}")
                if td.get('missing_in_file2'):
                    print(f"  Manquant dans fichier 2: {td['missing_in_file2']}")
                if td.get('count_differences'):
                    print(f"  Différences de comptes:")
                    for table, counts in td['count_differences'].items():
                        print(f"    {table}: {counts['file1']} vs {counts['file2']}")
        
        # Lecture standard
        if not args.validate and not args.compare:
            reader = PDBReader(args.database)
            
            if args.summary:
                summary = reader.get_database_summary()
                print_summary(summary)
            else:
                data = reader.read_complete_database()
                # Affichage détaillé...
                print("Analyse détaillée non implémentée dans cet extrait")
            
            reader.close()
    
    except Exception as e:
        print(f"❌ Erreur: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()