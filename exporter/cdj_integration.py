# -*- coding: utf-8 -*-
"""
CDJ Integration Module - Interface BSM CORRIGÉ
Remplace bsm_cdj_exporter.py avec implémentation DeviceSQL conforme
Compatible CDJ-2000NXS2 priorité
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, BinaryIO
from enum import Enum

# Import des nouveaux exporteurs conformes
from .cdj_pdb_exporter import PDBExporter, export_nml_to_cdj_pdb
from .cdj_anlz_exporter import ANLZExporter, ANLZFileType, generate_anlz_for_tracks

class CDJModel(Enum):
    """Modèles CDJ supportés - Focus CDJ-2000NXS2"""
    CDJ_2000 = "CDJ-2000"
    CDJ_2000NXS2 = "CDJ-2000NXS2" 
    CDJ_3000 = "CDJ-3000"
    XDJ_1000MK2 = "XDJ-1000MK2"

class CDJExportEngine:
    """Moteur d'export CDJ avec format DeviceSQL conforme CORRIGÉ
    
    Remplace l'ancien CDJExportEngine avec une implémentation basée sur
    les spécifications Kaitai et les projets open source validés.
    Focus priorité : CDJ-2000NXS2
    """
    
    def __init__(self, target_model: CDJModel = CDJModel.CDJ_2000NXS2, 
                 use_encryption: bool = False, progress_queue=None):
        self.target_model = target_model
        self.use_encryption = False  # PDB toujours non-chiffré pour CDJ hardware
        self.progress_queue = progress_queue
        self.logger = logging.getLogger(__name__)
        
        # Configuration par modèle
        self.config = self._get_model_config(target_model)
        
        # Statistiques d'export
        self.export_stats = {
            'database_created': False,
            'anlz_files': 0,
            'tracks_processed': 0,
            'errors': 0,
            'audio_files_copied': 0,
            'audio_files_skipped': 0
        }
    
    def _get_model_config(self, target_model):
        """Return configuration dict for a given CDJ model name.

        Uses string keys to avoid NameError and normalizes input for flexible matching.
        """
        import re

        def normalize(name: Optional[str]) -> str:
            if not name:
                return ""
            # Uppercase and remove non-alphanumeric characters for robust matching
            return re.sub(r'[^A-Z0-9]', '', str(name).upper())

        # Model configurations (string keys)
        models = {
            "CDJ2000": {
                "model": "CDJ-2000",
                "max_tracks": 10000,
                "pdb_version": 1,
                # additional CDJ-2000 specific settings can be added here
            },
            "CDJ2000NXS2": {
                "model": "CDJ-2000NXS2",
                "max_tracks": 10000,
                "pdb_version": 2,
                # additional NXS2-specific settings
            },
            # Add other models as needed, using normalized keys (no non-alnum chars)
            "DEFAULT": {
                "model": "Generic CDJ",
                "max_tracks": 8000,
                "pdb_version": 1,
            }
        }

        norm_target = normalize(target_model)

        # Exact match
        if norm_target in models:
            return models[norm_target]

        # Partial match (e.g. "CDJ2000" inside "CDJ2000NXS2")
        for key, cfg in models.items():
            if key == "DEFAULT":
                continue
            if key in norm_target:
                return cfg

        # Fallback
        return models["DEFAULT"]
    
    def export_collection_to_cdj(self, tracks: List, playlist_structure: List, 
                                output_dir: Path, copy_audio: bool = True) -> Dict:
        """Export complet vers format CDJ avec structure Pioneer CORRIGÉ
        
        Args:
            tracks: Liste des tracks à exporter
            playlist_structure: Structure des playlists (non utilisée pour PDB simple)
            output_dir: Répertoire de sortie
            copy_audio: Copier les fichiers audio
            
        Returns:
            Dict avec statistiques et résultats d'export
        """
        output_dir = Path(output_dir)
        self.logger.info(f"Starting CDJ export for {len(tracks)} tracks to {output_dir}")
        self.logger.info(f"Target model: {self.target_model.value}")
        
        # Créer structure Pioneer COMPLÈTE
        pioneer_dir = output_dir / "PIONEER"
        rekordbox_dir = pioneer_dir / "rekordbox"
        anlz_dir = pioneer_dir / "USBANLZ"
        contents_dir = output_dir / "Contents"
        
        # Créer dossiers requis
        for directory in [pioneer_dir, rekordbox_dir, anlz_dir, contents_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self._reset_stats()
        generated_files = []
        
        try:
            # Étape 1: Copier fichiers audio AVANT génération PDB (chemins modifiés)
            if copy_audio:
                self.logger.info("Copying audio files...")
                self._update_progress(10, "Copying audio files...")
                self._copy_audio_files(tracks, contents_dir)
            
            # Étape 2: Générer fichiers ANLZ (avec chemins corrects)
            self.logger.info("Generating ANLZ files...")
            self._update_progress(40, "Generating ANLZ analysis files...")
            
            anlz_result = generate_anlz_for_tracks(
                tracks, 
                output_dir,  # Base path, ANLZ manager gère sous-structure
                self.config.get('anlz_formats', ['DAT', 'EXT'])  # Safe default
            )
            
            generated_files.extend(anlz_result['files'])
            self.export_stats['anlz_files'] = anlz_result['files_generated']
            self.export_stats['errors'] += anlz_result['errors']
            
            self.logger.info(f"Generated {anlz_result['files_generated']} ANLZ files")
            
            # Étape 3: Générer base de données PDB
            self.logger.info("Generating PDB database...")
            self._update_progress(70, "Creating PDB database...")
            
            pdb_path = rekordbox_dir / "export.pdb"
            pdb_exporter = PDBExporter()
            pdb_result = pdb_exporter.export_collection_to_pdb(tracks, pdb_path)
            
            generated_files.append(pdb_path)
            
            # Vérifier si DeviceSQL.edb a été créé
            deviceSQL_path = rekordbox_dir / "DeviceSQL.edb"
            if deviceSQL_path.exists():
                generated_files.append(deviceSQL_path)
            
            self.export_stats['database_created'] = pdb_result['status'] == 'success'
            self.export_stats['tracks_processed'] = pdb_result['tracks_exported']
            
            if pdb_result['status'] != 'success':
                self.export_stats['errors'] += 1
                raise RuntimeError("PDB generation failed")
            
            self.logger.info(f"PDB database created: {pdb_path}")
            if deviceSQL_path.exists():
                self.logger.info(f"DeviceSQL.edb copy created for CDJ recognition")
            
            # Étape 4: Finalisation et validation
            self._update_progress(100, "Export completed successfully")
            
            # Créer rapport de validation
            validation_result = self._validate_cdj_export(output_dir, tracks)
            
            result = {
                'files': generated_files,
                'stats': self.export_stats.copy(),
                'target_model': self.target_model.value,
                'audio_copied': copy_audio,
                'status': 'success',
                'validation': validation_result
            }
            
            self.logger.info(f"CDJ export completed successfully")
            self.logger.info(f"Files generated: {len(generated_files)}")
            self.logger.info(f"Tracks processed: {self.export_stats['tracks_processed']}")
            self.logger.info(f"ANLZ files: {self.export_stats['anlz_files']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"CDJ export failed: {e}", exc_info=True)
            self.export_stats['errors'] += 1
            
            return {
                'files': generated_files,
                'stats': self.export_stats.copy(),
                'target_model': self.target_model.value,
                'audio_copied': copy_audio,
                'status': 'error',
                'error_message': str(e)
            }
    
    def _reset_stats(self):
        """Remettre à zéro les statistiques"""
        for key in self.export_stats:
            if isinstance(self.export_stats[key], int):
                self.export_stats[key] = 0
            elif isinstance(self.export_stats[key], bool):
                self.export_stats[key] = False
    
    def _update_progress(self, percentage: int, message: str):
        """Mettre à jour la barre de progression"""
        if self.progress_queue:
            self.progress_queue.put(("progress", (percentage, message)))
    
    def _copy_audio_files(self, tracks: List, contents_dir: Path):
        """Copier les fichiers audio et mettre à jour les chemins CORRIGÉ"""
        copied_count = 0
        skipped_count = 0
        
        for track in tracks:
            if hasattr(track, 'file_path') and track.file_path and Path(track.file_path).exists():
                source_file = Path(track.file_path)
                
                # Nettoyer nom de fichier pour compatibilité FAT32
                clean_name = self._sanitize_filename(source_file.name)
                dest_file = contents_dir / clean_name
                
                # Éviter les doublons
                if dest_file.exists():
                    # Modifier chemin dans track pour PDB
                    track.file_path = f"Contents/{clean_name}"
                    skipped_count += 1
                    continue
                
                try:
                    shutil.copy2(source_file, dest_file)
                    # IMPORTANT: Mettre à jour le chemin dans track pour PDB
                    track.file_path = f"Contents/{clean_name}"
                    copied_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to copy {source_file}: {e}")
                    self.export_stats['errors'] += 1
                    skipped_count += 1
            else:
                skipped_count += 1
        
        self.export_stats['audio_files_copied'] = copied_count
        self.export_stats['audio_files_skipped'] = skipped_count
        self.logger.info(f"Audio files - Copied: {copied_count}, Skipped: {skipped_count}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Nettoyer nom de fichier pour compatibilité CDJ/FAT32"""
        import re
        import unicodedata
        
        # Décomposer accents
        normalized = unicodedata.normalize('NFKD', filename)
        ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
        
        # Remplacer caractères invalides FAT32
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            ascii_only = ascii_only.replace(char, '_')
        
        # Nettoyer espaces multiples
        ascii_only = re.sub(r'\s+', ' ', ascii_only).strip()
        
        # Limiter longueur (255 caractères max FAT32)
        if len(ascii_only) > 250:  # Garder marge pour extension
            name, ext = ascii_only.rsplit('.', 1) if '.' in ascii_only else (ascii_only, '')
            ascii_only = name[:250-len(ext)-1] + ('.' + ext if ext else '')
        
        return ascii_only
    
    def _validate_cdj_export(self, export_dir: Path, tracks: List) -> Dict:
        """Valider structure export CDJ"""
        validation = {
            'structure_valid': True,
            'pdb_found': False,
            'deviceSQL_found': False,
            'anlz_files_found': 0,
            'audio_files_found': 0,
            'warnings': [],
            'errors': []
        }
        
        # Vérifier structure Pioneer
        pioneer_dir = export_dir / "PIONEER"
        if not pioneer_dir.exists():
            validation['errors'].append("PIONEER directory not found")
            validation['structure_valid'] = False
            return validation
        
        rekordbox_dir = pioneer_dir / "rekordbox"
        if not rekordbox_dir.exists():
            validation['errors'].append("PIONEER/rekordbox directory not found")
            validation['structure_valid'] = False
        
        # Vérifier fichiers PDB
        pdb_file = rekordbox_dir / "export.pdb"
        if pdb_file.exists():
            validation['pdb_found'] = True
        else:
            validation['errors'].append("export.pdb not found")
        
        deviceSQL_file = rekordbox_dir / "DeviceSQL.edb"
        if deviceSQL_file.exists():
            validation['deviceSQL_found'] = True
        else:
            validation['warnings'].append("DeviceSQL.edb not found (CDJ recognition may fail)")
        
        # Compter fichiers ANLZ
        anlz_dir = pioneer_dir / "USBANLZ"
        if anlz_dir.exists():
            # Compter tous les fichiers .DAT et .EXT dans sous-dossiers
            dat_files = list(anlz_dir.rglob("*.DAT"))
            ext_files = list(anlz_dir.rglob("*.EXT"))
            validation['anlz_files_found'] = len(dat_files) + len(ext_files)
            
            expected_files = len(tracks) * len(self.config.get('anlz_formats', ['DAT', 'EXT']))
            if validation['anlz_files_found'] < expected_files:
                validation['warnings'].append(
                    f"Only {validation['anlz_files_found']} ANLZ files found, "
                    f"expected {expected_files}"
                )
        
        # Compter fichiers audio
        contents_dir = export_dir / "Contents"
        if contents_dir.exists():
            audio_files = list(contents_dir.glob("*"))
            validation['audio_files_found'] = len(audio_files)
        
        self.logger.info(f"Export validation: {validation}")
        return validation


# Factory function pour compatibilité avec l'interface BSM existante
def export_nml_to_cdj(nml_path: str, output_dir: str, 
                     music_root: Optional[str] = None,
                     model: CDJModel = CDJModel.CDJ_2000NXS2,
                     use_encryption: bool = False,
                     copy_audio: bool = True) -> bool:
    """Interface de compatibilité pour remplacer l'ancien exporteur
    
    Args:
        nml_path: Chemin vers le fichier Traktor NML
        output_dir: Répertoire de sortie
        music_root: Racine des fichiers musicaux (optionnel)
        model: Modèle CDJ cible
        use_encryption: Chiffrement (ignoré pour PDB)
        copy_audio: Copier les fichiers audio
        
    Returns:
        True si l'export a réussi, False sinon
    """
    try:
        from parser.bsm_nml_parser import create_traktor_parser
        
        # Parser le NML
        parser = create_traktor_parser(nml_path, music_root)
        playlist_structure = parser.get_playlists_with_structure()
        
        # Collecter tous les tracks
        all_tracks = []
        track_seen = set()
        
        def collect_tracks(nodes):
            for node in nodes:
                if hasattr(node, 'type'):
                    if node.type in ['playlist', 'smartlist'] and hasattr(node, 'tracks'):
                        for track in node.tracks:
                            track_key = getattr(track, 'audio_id', None) or getattr(track, 'file_path', None)
                            if track_key and track_key not in track_seen:
                                all_tracks.append(track)
                                track_seen.add(track_key)
                    elif node.type == 'folder' and hasattr(node, 'children'):
                        collect_tracks(node.children)
        
        collect_tracks(playlist_structure)
        
        if not all_tracks:
            logging.warning("No tracks found in NML file")
            return False
        
        # Export vers CDJ
        exporter = CDJExportEngine(model, False)  # use_encryption=False pour PDB
        result = exporter.export_collection_to_cdj(
            all_tracks, 
            playlist_structure, 
            Path(output_dir), 
            copy_audio
        )
        
        success = result['status'] == 'success' and result['stats']['errors'] == 0
        
        if success:
            logging.info(f"CDJ export successful: {result['stats']}")
        else:
            logging.error(f"CDJ export failed: {result.get('error_message', 'Unknown error')}")
        
        return success
        
    except Exception as e:
        logging.error(f"NML to CDJ export failed: {e}")
        return False


# Classes de compatibilité pour l'ancien code
class CDJDatabaseManager:
    """Classe de compatibilité - l'ancien gestionnaire de base SQLite
    
    Note: La nouvelle implémentation génère directement des fichiers PDB
    binaires au lieu d'utiliser SQLite + conversion.
    """
    
    def __init__(self, db_path: str, use_encryption: bool = True):
        self.db_path = Path(db_path)
        self.use_encryption = False  # PDB non-chiffré
        self.logger = logging.getLogger(__name__)
        
        # Avertissement sur la migration
        self.logger.warning(
            "CDJDatabaseManager is deprecated. "
            "Use PDBExporter directly for better compatibility."
        )
    
    def create_database_structure(self):
        """Méthode de compatibilité - ne fait rien"""
        pass
    
    def get_connection(self):
        """Méthode de compatibilité - retourne None"""
        class DummyConnection:
            def __enter__(self):
                return None
            def __exit__(self, *args):
                pass
        return DummyConnection()


# Classe pour remplacer AudioAnalyzer (compatibilité)
class AudioAnalyzer:
    """Classe de compatibilité pour l'ancien analyseur audio"""
    
    def __init__(self):
        # Utiliser le nouvel analyseur
        from .cdj_anlz_exporter import AudioAnalyzer as NewAnalyzer
        self._analyzer = NewAnalyzer()
        self.available = self._analyzer.available
    
    def analyze_track(self, file_path: str) -> Dict:
        """Interface de compatibilité"""
        return self._analyzer.analyze_track(file_path)
    
    def _get_default_analysis(self) -> Dict:
        """Interface de compatibilité"""
        return self._analyzer._get_default_analysis()


# Migration guide pour utilisateurs existants
def get_migration_guide() -> str:
    """Guide de migration depuis l'ancien exporteur"""
    return """
    Migration Guide - Ancien vers Nouveau Exporteur CDJ
    ==================================================
    
    L'ancien exporteur utilisait SQLite + conversion, le nouveau génère
    directement des fichiers PDB binaires conformes aux spécifications.
    
    Changements principaux:
    ----------------------
    1. Plus de SQLCipher / base SQLite intermédiaire
    2. Format PDB binaire natif (compatible CDJ-2000NXS2)
    3. Fichiers ANLZ générés selon spécifications Kaitai
    4. Support multi-modèles (CDJ-2000, NXS2, 3000)
    5. Structure chemins ANLZ conforme (P###/########/)
    
    Interface de compatibilité:
    ---------------------------
    - export_nml_to_cdj() : Interface principale inchangée
    - CDJExportEngine : Interface similaire, implémentation nouvelle
    - CDJDatabaseManager : Deprecated, utiliser PDBExporter
    
    Nouveaux exporteurs:
    -------------------
    - PDBExporter : Export PDB binaire conforme (8192 byte pages)
    - ANLZExporter : Export ANLZ multi-format avec chemins corrects
    
    Avantages:
    ----------
    ✓ Compatible CDJ-2000NXS2 (priorité)
    ✓ Pas de dépendance SQLCipher
    ✓ Fichiers conformes aux spécifications Pioneer
    ✓ Support waveforms couleur (NXS2)
    ✓ DeviceSQL.edb pour reconnaissance CDJ
    ✓ Structure ANLZ hashée conforme
    """
