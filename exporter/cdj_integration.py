# -*- coding: utf-8 -*-
"""
CDJ Integration Module - Export CDJ-2000NXS2
Implémentation DeviceSQL conforme aux spécifications Pioneer
Target unique : CDJ-2000NXS2
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

# Import des exporteurs conformes
from .cdj_pdb_exporter import PDBExporter, export_nml_to_cdj_pdb
from .cdj_anlz_exporter import ANLZExporter, ANLZFileType, generate_anlz_for_tracks

# Configuration CDJ-2000NXS2 (cible unique)
CDJ_CONFIG = {
    "model": "CDJ-2000NXS2",
    "max_tracks": 10000,
    "pdb_version": 2,
    "anlz_formats": ["DAT", "EXT"],  # .DAT + .EXT pour NXS2
    "supports_color_waveforms": True,
    "max_hot_cues": 8,
}


class CDJExportEngine:
    """Moteur d'export CDJ-2000NXS2 avec format DeviceSQL conforme.

    Implémentation simplifiée ciblant uniquement le CDJ-2000NXS2.
    Génère : PDB binaire + fichiers ANLZ (.DAT/.EXT)
    """

    def __init__(self, progress_queue=None, anlz_processes: int = 2):
        self.progress_queue = progress_queue
        self.anlz_processes = anlz_processes
        self.logger = logging.getLogger(__name__)
        self.config = CDJ_CONFIG

        # Statistiques d'export
        self.export_stats = {
            'database_created': False,
            'anlz_files': 0,
            'tracks_processed': 0,
            'errors': 0,
            'audio_files_copied': 0,
            'audio_files_skipped': 0,
            'audio_files_verified': 0,
            'audio_files_failed_verify': 0
        }
    
    def export_collection_to_cdj(self, tracks: List, playlist_structure: List,
                                output_dir: Path, copy_audio: bool = True,
                                verify_copy: bool = False) -> Dict:
        """Export complet vers format CDJ avec structure Pioneer CORRIGÉ

        Args:
            tracks: Liste des tracks à exporter
            playlist_structure: Structure des playlists (non utilisée pour PDB simple)
            output_dir: Répertoire de sortie
            copy_audio: Copier les fichiers audio
            verify_copy: Vérifier intégrité fichiers copiés (taille + MD5)

        Returns:
            Dict avec statistiques et résultats d'export
        """
        output_dir = Path(output_dir)
        self.logger.info(f"Starting CDJ-2000NXS2 export for {len(tracks)} tracks to {output_dir}")
        
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
                if verify_copy:
                    self.logger.info("File verification enabled (size + MD5 checksum)")
                self._update_progress(10, "Copying audio files...")
                self._copy_audio_files(tracks, contents_dir, verify_copy)
            
            # Étape 2: Générer fichiers ANLZ (avec chemins corrects)
            self.logger.info("Generating ANLZ files...")
            self._update_progress(40, "Generating ANLZ analysis files...")

            anlz_result = generate_anlz_for_tracks(
                tracks,
                output_dir,  # Base path, ANLZ manager gère sous-structure
                self.config.get('anlz_formats', ['DAT', 'EXT']),  # Safe default
                processes=self.anlz_processes  # Multiprocessing (défaut: 2)
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
                'target_model': 'CDJ-2000NXS2',
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
                'target_model': 'CDJ-2000NXS2',
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

    def _verify_file_integrity(self, source: Path, dest: Path) -> bool:
        """Vérifier intégrité fichier copié par MD5 checksum

        Args:
            source: Fichier source
            dest: Fichier destination

        Returns:
            True si hashes MD5 correspondent, False sinon
        """
        import hashlib

        def md5sum(file_path: Path) -> str:
            """Calculer hash MD5 d'un fichier"""
            md5 = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
            return md5.hexdigest()

        try:
            source_hash = md5sum(source)
            dest_hash = md5sum(dest)
            match = source_hash == dest_hash

            if not match:
                self.logger.error(f"MD5 mismatch: source={source_hash[:8]}... dest={dest_hash[:8]}...")

            return match
        except Exception as e:
            self.logger.error(f"MD5 verification error for {dest.name}: {e}")
            return False

    def _update_progress(self, percentage: int, message: str):
        """Mettre à jour la barre de progression"""
        if self.progress_queue:
            self.progress_queue.put(("progress", (percentage, message)))
    
    def _copy_audio_files(self, tracks: List, contents_dir: Path, verify_copy: bool = False):
        """Copier les fichiers audio et mettre à jour les chemins + VÉRIFICATION

        Args:
            tracks: Liste des tracks
            contents_dir: Répertoire Contents/
            verify_copy: Activer vérification intégrité (taille + MD5)
        """
        copied_count = 0
        skipped_count = 0
        verified_count = 0
        failed_verify_count = 0

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
                    # Copier fichier
                    shutil.copy2(source_file, dest_file)

                    # VÉRIFICATION TAILLE (TOUJOURS - Rapide)
                    source_size = source_file.stat().st_size
                    dest_size = dest_file.stat().st_size

                    if source_size != dest_size:
                        self.logger.error(f"Size mismatch after copy: {dest_file.name}")
                        self.logger.error(f"  Source: {source_size:,} bytes")
                        self.logger.error(f"  Dest:   {dest_size:,} bytes")
                        dest_file.unlink()  # Supprimer fichier corrompu
                        self.export_stats['errors'] += 1
                        failed_verify_count += 1
                        skipped_count += 1
                        continue

                    # VÉRIFICATION MD5 (SI DEMANDÉE - Plus lent mais robuste)
                    if verify_copy:
                        if not self._verify_file_integrity(source_file, dest_file):
                            self.logger.error(f"MD5 verification failed: {dest_file.name}")
                            dest_file.unlink()  # Supprimer fichier corrompu
                            self.export_stats['errors'] += 1
                            failed_verify_count += 1
                            skipped_count += 1
                            continue
                        else:
                            verified_count += 1
                            self.logger.debug(f"MD5 verified OK: {dest_file.name}")

                    # IMPORTANT: Mettre à jour le chemin dans track pour PDB
                    track.file_path = f"Contents/{clean_name}"
                    copied_count += 1

                except Exception as e:
                    self.logger.error(f"Failed to copy {source_file}: {e}")
                    self.export_stats['errors'] += 1
                    skipped_count += 1
            else:
                skipped_count += 1

        # Statistiques
        self.export_stats['audio_files_copied'] = copied_count
        self.export_stats['audio_files_skipped'] = skipped_count
        self.export_stats['audio_files_verified'] = verified_count
        self.export_stats['audio_files_failed_verify'] = failed_verify_count

        self.logger.info(f"Audio files - Copied: {copied_count}, Skipped: {skipped_count}")
        if verify_copy:
            self.logger.info(f"Audio verification - MD5 OK: {verified_count}, Failed: {failed_verify_count}")
    
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


# Factory function pour export direct NML -> CDJ
def export_nml_to_cdj(nml_path: str, output_dir: str,
                      music_root: Optional[str] = None,
                      copy_audio: bool = True) -> bool:
    """Export NML vers format CDJ-2000NXS2.

    Args:
        nml_path: Chemin vers le fichier Traktor NML
        output_dir: Répertoire de sortie
        music_root: Racine des fichiers musicaux (optionnel)
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

        # Export vers CDJ-2000NXS2
        exporter = CDJExportEngine()
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


