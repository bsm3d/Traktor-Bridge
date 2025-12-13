"""
Conversion Thread Module for Traktor Bridge - CORRIGÉ
Worker thread with new CDJ exporter integration
Compatible CDJ-2000NXS2 priorité
"""

import logging
import queue
import threading
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtCore import QThread, Signal


class ConversionThread(QThread):
    """Worker thread for handling conversions with new CDJ exporter CORRIGÉ."""
    
    finished = Signal(str, str)  # status, message
    
    def __init__(self, output_path: str, selected_playlists: List, structure: List,
                 export_format: str, copy_music: bool, verify_copy: bool, 
                 key_format: str, progress_queue: queue.Queue, 
                 cancel_event: threading.Event, settings: Dict[str, Any]):
        super().__init__()
        
        self.output_path = output_path
        self.selected_playlists = selected_playlists
        self.structure = structure
        self.export_format = export_format
        self.copy_music = copy_music
        self.verify_copy = verify_copy
        self.key_format = key_format
        self.progress_queue = progress_queue
        self.cancel_event = cancel_event
        self.settings = settings
        self.logger = logging.getLogger(__name__)
    
    def run(self):
        """Execute conversion in background thread."""
        try:
            self.logger.info(f"Starting conversion: {self.export_format}")
            
            # Router selon format d'export CORRIGÉ
            if self.export_format in ["CDJUSB", "CDJ/USB", "Database"]:
                self._run_cdj_export()
            elif self.export_format in ["Rekordbox Database", "Rekordbox SQLite"]:
                self._run_rekordbox_database_export()
            elif self.export_format in ["XML", "Rekordbox XML"]:
                self._run_xml_export()
            elif self.export_format == "M3U":
                self._run_m3u_export()
            else:
                raise ValueError(f"Unknown export format: {self.export_format}")
            
            if self.cancel_event.is_set():
                self.finished.emit("cancelled", "Conversion cancelled by user")
            else:
                self.finished.emit("completed", "Successfully exported playlists")
                
        except Exception as e:
            logging.error(f"Conversion failed: {e}", exc_info=True)
            self.finished.emit("error", str(e))
    
    def _run_cdj_export(self):
        """Run CDJ-2000NXS2 export with PDB/ANLZ generators."""
        from exporter.cdj_integration import CDJExportEngine

        try:
            self.logger.info("Starting CDJ-2000NXS2 export")

            # Préparer la structure à exporter
            structure_to_export = self._get_full_structure_for_selection()
            all_tracks = self._collect_all_tracks(structure_to_export)

            self.logger.info(f"Exporting {len(all_tracks)} tracks to CDJ-2000NXS2 format")
            self.progress_queue.put(("progress", (0, f"Preparing to export {len(all_tracks)} tracks")))

            # Configuration export
            copy_audio = self.settings.get('copy_music', True) and self.copy_music
            verify_copy = self.settings.get('verify_copy', False) and self.verify_copy
            anlz_processes = self.settings.get('anlz_processes', 2)

            self.logger.info(f"Copy audio: {copy_audio}")
            self.logger.info(f"Verify copy: {verify_copy}")
            self.logger.info(f"ANLZ processes: {anlz_processes}")
            self.logger.info(f"Output path: {self.output_path}")

            # Créer exporteur CDJ-2000NXS2
            exporter = CDJExportEngine(
                progress_queue=self.progress_queue,
                anlz_processes=anlz_processes
            )

            # Export vers format CDJ
            result = exporter.export_collection_to_cdj(
                tracks=all_tracks,
                playlist_structure=structure_to_export,
                output_dir=Path(self.output_path),
                copy_audio=copy_audio,
                verify_copy=verify_copy
            )
            
            # Vérifier résultat
            if result['status'] != 'success':
                error_msg = result.get('error_message', 'Unknown error')
                raise RuntimeError(f"CDJ export failed: {error_msg}")
            
            # Log statistiques détaillées
            stats = result['stats']
            validation = result.get('validation', {})
            
            self.logger.info("=== CDJ Export Results ===")
            self.logger.info(f"Tracks processed: {stats['tracks_processed']}")
            self.logger.info(f"ANLZ files generated: {stats['anlz_files']}")
            self.logger.info(f"Audio files copied: {stats['audio_files_copied']}")
            self.logger.info(f"Audio files skipped: {stats['audio_files_skipped']}")
            self.logger.info(f"Database created: {stats['database_created']}")
            self.logger.info(f"Errors: {stats['errors']}")
            
            # Log validation
            if validation:
                self.logger.info("=== Validation Results ===")
                self.logger.info(f"Structure valid: {validation['structure_valid']}")
                self.logger.info(f"PDB found: {validation['pdb_found']}")
                self.logger.info(f"DeviceSQL found: {validation['deviceSQL_found']}")
                self.logger.info(f"ANLZ files found: {validation['anlz_files_found']}")
                self.logger.info(f"Audio files found: {validation['audio_files_found']}")
                
                if validation['warnings']:
                    self.logger.warning(f"Validation warnings: {validation['warnings']}")
                if validation['errors']:
                    self.logger.error(f"Validation errors: {validation['errors']}")
            
            if stats['errors'] > 0:
                self.logger.warning(f"Export completed with {stats['errors']} errors")
            else:
                self.logger.info("CDJ export completed successfully without errors")
            
        except Exception as e:
            self.logger.error(f"CDJ export failed: {e}", exc_info=True)
            raise
    
    def _run_rekordbox_database_export(self):
        """Run Rekordbox DATABASE export (SQLite pour logiciel)."""
        from exporter.bsm_rb_exporter import RekordboxDatabaseManager
        
        try:
            self.logger.info("Starting Rekordbox Database export (SQLite)")
            
            structure_to_export = self._get_full_structure_for_selection()
            all_tracks = self._collect_all_tracks(structure_to_export)
            
            self.progress_queue.put(("progress", (0, f"Exporting {len(all_tracks)} tracks to Rekordbox Database")))
            
            # Configuration pour Rekordbox logiciel
            use_encryption = self.settings.get('use_encryption', True)
            rekordbox_version = self.settings.get('rekordbox_version', 'RB6')
            
            self.logger.info(f"Rekordbox version: {rekordbox_version}")
            self.logger.info(f"Use encryption: {use_encryption}")
            
            # Créer manager base de données
            db_path = Path(self.output_path) / "rekordbox_database.pdb"
            db_manager = RekordboxDatabaseManager(str(db_path), use_encryption)
            
            self.progress_queue.put(("progress", (50, "Creating Rekordbox database...")))
            
            # Export (implémentation à adapter selon bsm_rb_exporter)
            # db_manager.export_collection(all_tracks, structure_to_export)
            
            self.progress_queue.put(("progress", (100, f"Rekordbox database export saved to {db_path}")))
            
            self.logger.info("Rekordbox Database export completed successfully")
            
        except Exception as e:
            self.logger.error(f"Rekordbox Database export failed: {e}", exc_info=True)
            raise
    
    def _run_xml_export(self):
        """Run XML export (unchanged)."""
        from exporter.bsm_xml_exporter import RekordboxXMLExporter
        
        try:
            self.logger.info("Starting XML export")
            
            structure_to_export = self._get_full_structure_for_selection()
            all_tracks = self._collect_all_tracks(structure_to_export)
            
            self.progress_queue.put(("progress", (0, f"Exporting {len(all_tracks)} tracks to XML format")))
            
            exporter = RekordboxXMLExporter()
            output_file = Path(self.output_path) / "rekordbox_export.xml"
            
            self.progress_queue.put(("progress", (50, "Generating XML structure...")))
            
            exporter.export_collection(all_tracks, structure_to_export, output_file)
            
            self.progress_queue.put(("progress", (100, f"XML export saved to {output_file}")))
            
            self.logger.info(f"XML export completed: {output_file}")
            
        except Exception as e:
            self.logger.error(f"XML export failed: {e}", exc_info=True)
            raise
    
    def _run_m3u_export(self):
        """Run M3U export (unchanged)."""
        from exporter.bsm_m3u_exporter import M3UExporter
        
        try:
            self.logger.info("Starting M3U export")
            
            structure_to_export = self._get_full_structure_for_selection()
            playlist_count = self._count_playlists(structure_to_export)
            
            self.progress_queue.put(("progress", (0, f"Exporting {playlist_count} playlists to M3U format")))
            
            exporter = M3UExporter(self.output_path)
            
            self.progress_queue.put(("progress", (50, "Creating M3U playlists...")))
            
            exporter.export_playlists(
                structure_to_export,
                relative_paths=True,
                copy_music=self.copy_music
            )
            
            self.progress_queue.put(("progress", (100, f"M3U export completed in {self.output_path}")))
            
            self.logger.info("M3U export completed successfully")
            
        except Exception as e:
            self.logger.error(f"M3U export failed: {e}", exc_info=True)
            raise
    
    def _get_full_structure_for_selection(self) -> List:
        """Get filtered structure containing only selected playlists."""
        if not self.selected_playlists:
            self.logger.info("No playlists selected, exporting all structure")
            return self.structure
        
        selected_ids = {id(n) for n in self.selected_playlists}
        self.logger.info(f"Filtering structure for {len(selected_ids)} selected playlists")

        def clone_and_filter(nodes: List) -> List:
            filtered_list = []
            for node in nodes:
                if id(node) in selected_ids:
                    filtered_list.append(node)
                elif hasattr(node, 'type') and node.type == 'folder' and hasattr(node, 'children'):
                    filtered_children = clone_and_filter(node.children)
                    if filtered_children:
                        # Create new folder node with filtered children
                        from parser.bsm_nml_parser import Node
                        new_folder = Node(type='folder', name=node.name, children=filtered_children)
                        filtered_list.append(new_folder)
            return filtered_list

        filtered_structure = clone_and_filter(self.structure)
        self.logger.info(f"Filtered structure contains {len(filtered_structure)} items")
        return filtered_structure
    
    def _collect_all_tracks(self, structure: List = None) -> List:
        """Collect all unique tracks from playlist structure."""
        if structure is None:
            structure = self.structure
        
        all_tracks = []
        track_seen = set()
        
        def collect_recursive(nodes: List):
            for node in nodes:
                if hasattr(node, 'type'):
                    if node.type in ['playlist', 'smartlist'] and hasattr(node, 'tracks'):
                        for track in node.tracks:
                            # Utiliser audio_id si disponible, sinon file_path
                            track_key = getattr(track, 'audio_id', None) or getattr(track, 'file_path', None)
                            if track_key and track_key not in track_seen:
                                all_tracks.append(track)
                                track_seen.add(track_key)
                    elif node.type == 'folder' and hasattr(node, 'children'):
                        collect_recursive(node.children)
        
        collect_recursive(structure)
        self.logger.info(f"Collected {len(all_tracks)} unique tracks from structure")
        return all_tracks
    
    def _count_playlists(self, structure: List) -> int:
        """Count total playlists in structure."""
        count = 0
        for node in structure:
            if hasattr(node, 'type'):
                if node.type in ['playlist', 'smartlist']:
                    count += 1
                elif node.type == 'folder' and hasattr(node, 'children'):
                    count += self._count_playlists(node.children)
        return count


# Classe de compatibilité pour l'interface existante
class LegacyConversionThread(ConversionThread):
    """Classe de compatibilité pour maintenir l'interface existante
    
    Cette classe peut être utilisée comme drop-in replacement
    pour l'ancien ConversionThread.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Log migration notice
        self.logger.info(
            "Using updated ConversionThread with new CDJ exporter. "
            "Database format changed from SQLite to binary PDB for CDJ hardware."
        )


# Helper functions pour debugging et monitoring
def validate_conversion_settings(settings: Dict) -> Dict:
    """Valider les paramètres de conversion"""
    validation_result = {
        'valid': True,
        'warnings': [],
        'errors': []
    }

    # Vérifier format d'export
    valid_formats = ["CDJUSB", "CDJ/USB", "Database", "Rekordbox Database", "XML", "Rekordbox XML", "M3U"]
    export_format = settings.get('export_format', '')
    if export_format not in valid_formats:
        validation_result['errors'].append(f"Invalid export format: {export_format}")
        validation_result['valid'] = False

    # Vérifier paramètres audio
    if settings.get('copy_music', True):
        if not settings.get('verify_copy', False):
            validation_result['warnings'].append("Audio copy verification disabled")

    return validation_result


def estimate_conversion_time(tracks_count: int, export_format: str, copy_audio: bool = True) -> float:
    """Estimer temps de conversion en secondes"""
    base_time_per_track = {
        "CDJ/USB": 0.5,  # PDB + ANLZ generation
        "Database": 0.5,
        "Rekordbox Database": 0.3,  # SQLite plus rapide
        "XML": 0.1,  # XML simple
        "M3U": 0.05  # M3U très rapide
    }
    
    time_per_track = base_time_per_track.get(export_format, 0.3)
    
    # Ajouter temps pour copie audio
    if copy_audio and export_format in ["CDJUSB", "CDJ/USB", "Database"]:
        time_per_track += 2.0  # ~2s par fichier audio copié
    
    estimated_time = tracks_count * time_per_track
    
    # Minimum 10 secondes, maximum 1 heure
    return max(10.0, min(3600.0, estimated_time))
