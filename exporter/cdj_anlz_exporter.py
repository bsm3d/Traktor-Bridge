# -*- coding: utf-8 -*-
"""
CDJ ANLZ Exporter - Générateur de fichiers d'analyse CORRIGÉ
Compatible CDJ-2000NXS2 avec structure de chemins conforme
Génère .DAT et .EXT selon spécifications Pioneer
Supporte le multiprocessing pour accélérer la génération
"""

import logging
import struct
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional, BinaryIO
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from concurrent.futures import ProcessPoolExecutor, as_completed

try:
    import librosa
    import numpy as np
    AUDIO_ANALYSIS_AVAILABLE = True
except ImportError:
    AUDIO_ANALYSIS_AVAILABLE = False

from parser.bsm_nml_parser import Track

@dataclass
class ANLZSection:
    """Section ANLZ avec binary data pour CDJ"""
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

class ANLZFileType(Enum):
    """Types de fichiers ANLZ selon modèle CDJ"""
    DAT = ".DAT"  # Format basique (tous CDJ)
    EXT = ".EXT"  # Waveforms couleur (CDJ-2000NXS+)
    TWO_EX = ".2EX"  # 3-band waveforms (CDJ-3000)

class AudioAnalyzer:
    """Analyseur audio pour génération ANLZ"""
    
    def __init__(self):
        self.available = AUDIO_ANALYSIS_AVAILABLE
        self.logger = logging.getLogger(__name__)
        
    def analyze_track(self, file_path: str) -> Dict:
        """Analyser track audio pour données ANLZ"""
        if not self.available:
            self.logger.warning("Audio analysis unavailable, using defaults")
            return self._get_default_analysis()
        
        try:
            # Charger audio avec librosa
            y, sr = librosa.load(file_path, sr=44100)
            
            # Analyse BPM/beat tracking
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            
            # Analyse spectrale pour waveform
            stft = librosa.stft(y, hop_length=512)
            magnitude = np.abs(stft)
            
            # Downsampling pour CDJ (150 samples/seconde)
            target_samples = int(len(y) / sr * 150)
            if target_samples > 0:
                waveform = self._generate_waveform(magnitude, target_samples)
            else:
                waveform = []
            
            return {
                'bpm': float(tempo),
                'duration': len(y) / sr,
                'sample_rate': sr,
                'beats': beats.tolist() if len(beats) > 0 else [],
                'waveform': waveform
            }
            
        except Exception as e:
            self.logger.error(f"Audio analysis failed for {file_path}: {e}")
            return self._get_default_analysis()
    
    def _get_default_analysis(self) -> Dict:
        """Analyse par défaut si librosa indisponible"""
        return {
            'bpm': 120.0,
            'duration': 180.0,
            'sample_rate': 44100,
            'beats': [],
            'waveform': []
        }
    
    def _generate_waveform(self, magnitude, target_samples: int) -> List[int]:
        """Générer waveform pour CDJ (5-bit height)"""
        # Moyenner sur les fréquences pour obtenir amplitude
        waveform_data = np.mean(magnitude, axis=0)
        
        # Resampling vers target_samples
        if len(waveform_data) > target_samples:
            step = len(waveform_data) // target_samples
            waveform_data = waveform_data[::step][:target_samples]
        
        # Normaliser vers 5-bit (0-31)
        if np.max(waveform_data) > 0:
            normalized = waveform_data / np.max(waveform_data) * 31
            return [int(x) for x in normalized]
        
        return [0] * target_samples

class ANLZPathManager:
    """Gestionnaire des chemins ANLZ conformes Pioneer - CORRIGÉ"""
    
    @staticmethod
    def generate_anlz_path(track_id: int, file_type: ANLZFileType) -> str:
        """Générer chemin ANLZ conforme : P###/########/ANLZ0000.XXX"""
        
        # Générer hash du track_id pour folder structure
        hash_input = f"track_{track_id}".encode('utf-8')
        hash_digest = hashlib.md5(hash_input).hexdigest()
        
        # Folder P### (3 digits basé sur track_id)
        folder_id = (track_id % 1000)
        p_folder = f"P{folder_id:03d}"
        
        # Hash folder (8 hex digits)
        hash_folder = hash_digest[:8].upper()
        
        # Chemin final conforme
        return f"PIONEER/USBANLZ/{p_folder}/{hash_folder}/ANLZ0000{file_type.value}"
    
    @staticmethod
    def create_anlz_directories(base_path: Path, anlz_path: str):
        """Créer structure de dossiers ANLZ"""
        full_path = base_path / anlz_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

class ANLZGenerator:
    """Générateur de fichiers ANLZ selon spécifications Pioneer"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.analyzer = AudioAnalyzer()

    def _resolve_audio_path(self, file_path: str, output_dir: Path = None) -> Path:
        """Résoudre le chemin audio (relatif ou absolu)

        Si file_path est relatif (ex: Contents/track.mp3), le résoudre
        contre output_dir pour obtenir le chemin absolu.

        Args:
            file_path: Chemin du fichier audio (peut être relatif)
            output_dir: Répertoire racine d'export

        Returns:
            Path absolu vers le fichier audio
        """
        audio_path = Path(file_path)

        # Si chemin absolu et existe, utiliser tel quel
        if audio_path.is_absolute() and audio_path.exists():
            return audio_path

        # Si chemin relatif (ex: Contents/...), résoudre contre output_dir
        if output_dir and not audio_path.is_absolute():
            resolved = Path(output_dir) / audio_path
            if resolved.exists():
                self.logger.debug(f"Resolved relative path: {file_path} -> {resolved}")
                return resolved

        # Fallback: retourner le chemin original (peut échouer)
        return audio_path

    def generate_dat_file(self, track: Track, track_id: int, output_path: Path,
                          output_dir: Path = None) -> bool:
        """Générer fichier .DAT (format basique)

        Args:
            track: Track object avec métadonnées
            track_id: ID unique de la track
            output_path: Chemin complet du fichier ANLZ à créer
            output_dir: Répertoire racine d'export (pour résoudre chemins relatifs)
        """
        try:
            # Résoudre chemin audio (peut être relatif après copie)
            audio_path = self._resolve_audio_path(track.file_path, output_dir)

            # Analyser audio
            analysis = self.analyzer.analyze_track(str(audio_path))
            
            # Construire sections ANLZ
            sections = []
            
            # PPTH - Beat Grid (positions des beats)
            ppth_section = self._generate_ppth_section(analysis)
            sections.append(ppth_section)
            
            # PQTZ - Quantized beats (grille rythmique)
            pqtz_section = self._generate_pqtz_section(analysis)
            sections.append(pqtz_section)
            
            # PWV3 - Waveform simple (monochrome)
            pwv3_section = self._generate_pwv3_section(analysis)
            sections.append(pwv3_section)
            
            # PCOB - Hot cues basiques
            pcob_section = self._generate_pcob_section(track)
            sections.append(pcob_section)
            
            # Écrire fichier
            self._write_anlz_file(output_path, sections)
            
            self.logger.debug(f"Generated DAT file: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to generate DAT file: {e}")
            return False
    
    def generate_ext_file(self, track: Track, track_id: int, output_path: Path,
                          output_dir: Path = None) -> bool:
        """Générer fichier .EXT (waveforms couleur NXS2)

        Args:
            track: Track object avec métadonnées
            track_id: ID unique de la track
            output_path: Chemin complet du fichier ANLZ à créer
            output_dir: Répertoire racine d'export (pour résoudre chemins relatifs)
        """
        try:
            # Résoudre chemin audio (peut être relatif après copie)
            audio_path = self._resolve_audio_path(track.file_path, output_dir)

            analysis = self.analyzer.analyze_track(str(audio_path))
            
            sections = []
            
            # PWV5 - Waveform couleur (2 bytes par sample)
            pwv5_section = self._generate_pwv5_section(analysis)
            sections.append(pwv5_section)
            
            # PCO2 - Hot cues étendus avec couleur
            pco2_section = self._generate_pco2_section(track)
            sections.append(pco2_section)
            
            self._write_anlz_file(output_path, sections)
            
            self.logger.debug(f"Generated EXT file: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to generate EXT file: {e}")
            return False
    
    def _generate_ppth_section(self, analysis: Dict) -> ANLZSection:
        """Générer section PPTH (beat positions)"""
        payload = bytearray()
        
        # Header PPTH
        payload.extend(struct.pack('>I', len(analysis.get('beats', []))))
        
        # Positions des beats en millisecondes
        for beat_time in analysis.get('beats', []):
            beat_ms = int(beat_time * 1000)
            payload.extend(struct.pack('>I', beat_ms))
        
        return ANLZSection('PPTH', 12, bytes(payload))
    
    def _generate_pqtz_section(self, analysis: Dict) -> ANLZSection:
        """Générer section PQTZ (quantized beat grid)"""
        payload = bytearray()
        
        # BPM en centièmes
        bpm_centi = int(analysis.get('bpm', 120) * 100)
        payload.extend(struct.pack('>I', bpm_centi))
        
        # Beat grid data (simplifié)
        beats = analysis.get('beats', [])
        if beats:
            for i, beat in enumerate(beats[:64]):  # Limiter à 64 beats
                beat_ms = int(beat * 1000)
                beat_number = (i % 4) + 1  # Position dans mesure (1-4)
                payload.extend(struct.pack('>II', beat_ms, beat_number))
        
        return ANLZSection('PQTZ', 12, bytes(payload))
    
    def _generate_pwv3_section(self, analysis: Dict) -> ANLZSection:
        """Générer section PWV3 (waveform monochrome)"""
        payload = bytearray()
        
        waveform = analysis.get('waveform', [])
        
        # Header PWV3
        payload.extend(struct.pack('>I', len(waveform)))
        
        # Waveform data (1 byte par sample)
        for amplitude in waveform:
            # Limiter à 5 bits (0-31) et shifter
            clamped = max(0, min(31, amplitude))
            payload.extend(struct.pack('B', clamped << 3))
        
        # Padding si nécessaire
        while len(payload) % 4 != 0:
            payload.append(0)
        
        return ANLZSection('PWV3', 12, bytes(payload))
    
    def _generate_pwv5_section(self, analysis: Dict) -> ANLZSection:
        """Générer section PWV5 (waveform couleur)"""
        payload = bytearray()
        
        waveform = analysis.get('waveform', [])
        
        # Header PWV5
        payload.extend(struct.pack('>I', len(waveform)))
        
        # Waveform couleur (2 bytes par sample)
        for amplitude in waveform:
            # Format couleur CDJ-2000NXS2:
            # Bits 15-13: Rouge (3 bits)
            # Bits 12-10: Vert (3 bits) 
            # Bits 9-7:   Bleu (3 bits)
            # Bits 6-2:   Hauteur (5 bits)
            # Bits 1-0:   Unused
            
            height = max(0, min(31, amplitude))
            
            # Couleur basée sur amplitude (simple gradient)
            if height > 20:
                # Rouge pour peaks
                color = (7 << 13) | (0 << 10) | (0 << 7)
            elif height > 10:
                # Jaune pour medium
                color = (7 << 13) | (7 << 10) | (0 << 7)
            else:
                # Vert pour low
                color = (0 << 13) | (7 << 10) | (0 << 7)
            
            sample_data = color | (height << 2)
            payload.extend(struct.pack('>H', sample_data))
        
        return ANLZSection('PWV5', 12, bytes(payload))
    
    def _generate_pcob_section(self, track: Track) -> ANLZSection:
        """Générer section PCOB (hot cues basiques)"""
        payload = bytearray()
        
        # Hot cues depuis Traktor
        cues = getattr(track, 'cue_points', []) or []
        hot_cues = [c for c in cues if c.get('hotcue', -1) >= 0][:8]  # Max 8 pour NXS2
        
        # Header PCOB
        payload.extend(struct.pack('>I', len(hot_cues)))
        
        # Data pour chaque cue
        for cue in hot_cues:
            cue_time_ms = int(cue.get('start', 0))
            hot_cue_num = cue.get('hotcue', 0)
            cue_type = 1  # 1 = position, 2 = loop
            
            payload.extend(struct.pack('>III', cue_time_ms, hot_cue_num, cue_type))
        
        return ANLZSection('PCOB', 12, bytes(payload))
    
    def _generate_pco2_section(self, track: Track) -> ANLZSection:
        """Générer section PCO2 (hot cues étendus couleur)"""
        payload = bytearray()
        
        cues = getattr(track, 'cue_points', []) or []
        hot_cues = [c for c in cues if c.get('hotcue', -1) >= 0][:8]
        
        # Header PCO2
        payload.extend(struct.pack('>I', len(hot_cues)))
        
        # Couleurs Pioneer standard
        pioneer_colors = [
            0xFF0000,  # Rouge
            0xFFFF00,  # Jaune  
            0x00FF00,  # Vert
            0x00FFFF,  # Cyan
            0x0000FF,  # Bleu
            0xFF00FF,  # Magenta
            0xFF8000,  # Orange
            0x8000FF   # Violet
        ]
        
        for i, cue in enumerate(hot_cues):
            # PCPT marker
            payload.extend(b'PCPT')
            payload.extend(struct.pack('>I', 0x1C))  # Section size
            payload.extend(struct.pack('>I', 0x26))  # Magic constant
            
            hot_cue_num = cue.get('hotcue', i)
            cue_time_ms = int(cue.get('start', 0))
            color_rgb = pioneer_colors[hot_cue_num % len(pioneer_colors)]
            
            payload.extend(struct.pack('>I', hot_cue_num))
            payload.extend(struct.pack('>I', 0))  # Unknown
            payload.extend(struct.pack('>I', 0x00100000))  # Position flag
            payload.extend(struct.pack('>I', color_rgb))  # Couleur RGB
            payload.extend(struct.pack('B', 1))  # Active flag
            payload.extend(b'\x00\x03\x08')  # Magic bytes
            payload.extend(struct.pack('>I', cue_time_ms))
            payload.extend(struct.pack('>I', 0xFFFFFFFF))  # End marker
        
        return ANLZSection('PCO2', 12, bytes(payload))
    
    def _write_anlz_file(self, output_path: Path, sections: List[ANLZSection]):
        """Écrire fichier ANLZ avec sections"""
        with open(output_path, 'wb') as f:
            # Magic header ANLZ
            f.write(b'PMAI')  # Pioneer Media Analysis Information
            
            # File size placeholder
            size_pos = f.tell()
            f.write(struct.pack('>I', 0))
            
            # Sections count
            f.write(struct.pack('>I', len(sections)))
            
            # Reserved bytes
            f.write(b'\x00' * 4)
            
            # Write all sections
            for section in sections:
                f.write(section.to_bytes())
            
            # Update file size
            file_size = f.tell()
            f.seek(size_pos)
            f.write(struct.pack('>I', file_size))

# ==============================================================================
# Fonctions top-level pour multiprocessing (doivent être picklables)
# ==============================================================================

def _normalize_anlz_types(file_types: List[str]) -> List[ANLZFileType]:
    """Normaliser les types ANLZ (accepte 'DAT', '.DAT', 'dat', etc.)"""
    types = []
    for ft in file_types:
        norm = str(ft).strip().upper().lstrip('.')
        if norm == 'DAT':
            types.append(ANLZFileType.DAT)
        elif norm == 'EXT':
            types.append(ANLZFileType.EXT)
        elif norm == '2EX':
            types.append(ANLZFileType.TWO_EX)
    return types


def _anlz_worker(job: dict) -> dict:
    """
    Worker multiprocessing pour générer ANLZ d'une track.
    Doit être top-level pour être picklable sur Windows (spawn).

    Args:
        job: Dict contenant:
            - track_id: int
            - audio_path: str (chemin ABSOLU)
            - cue_points: list (optionnel)
            - output_dir: str
            - file_types: list[str] ex: ['DAT', 'EXT']

    Returns:
        Dict avec files_generated, files (str paths), errors
    """
    exporter = ANLZExporter()

    # Créer un track minimal picklable (évite de sérialiser l'objet Track complet)
    track = SimpleNamespace()
    track.file_path = job["audio_path"]
    track.cue_points = job.get("cue_points") or []

    anlz_types = _normalize_anlz_types(job.get("file_types", ["DAT", "EXT"]))

    result = exporter.export_track_anlz(
        track=track,
        track_id=int(job["track_id"]),
        output_dir=Path(job["output_dir"]),
        file_types=anlz_types
    )

    # Convertir Path -> str pour sérialisation inter-process
    result["files"] = [str(p) for p in result.get("files", [])]
    return result


class ANLZExporter:
    """Exporteur principal ANLZ avec gestion des chemins"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.generator = ANLZGenerator()
        self.path_manager = ANLZPathManager()

    def export_track_anlz(self, track: Track, track_id: int,
                         output_dir: Path, file_types: List[ANLZFileType]) -> Dict:
        """Exporter fichiers ANLZ pour une track

        Args:
            track: Track object avec métadonnées
            track_id: ID unique de la track
            output_dir: Répertoire racine d'export (utilisé pour résoudre chemins relatifs)
            file_types: Liste des types de fichiers ANLZ à générer
        """
        result = {
            'files_generated': 0,
            'files': [],
            'errors': 0
        }

        for file_type in file_types:
            try:
                # Générer chemin conforme
                anlz_path = self.path_manager.generate_anlz_path(track_id, file_type)
                full_path = self.path_manager.create_anlz_directories(output_dir, anlz_path)

                # Générer fichier selon type (passer output_dir pour résolution chemins)
                success = False
                if file_type == ANLZFileType.DAT:
                    success = self.generator.generate_dat_file(track, track_id, full_path, output_dir)
                elif file_type == ANLZFileType.EXT:
                    success = self.generator.generate_ext_file(track, track_id, full_path, output_dir)
                
                if success:
                    result['files_generated'] += 1
                    result['files'].append(full_path)
                    self.logger.debug(f"Generated {file_type.value}: {anlz_path}")
                else:
                    result['errors'] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to export {file_type.value} for track {track_id}: {e}")
                result['errors'] += 1
        
        return result

# Factory function pour l'intégration BSM
def generate_anlz_for_tracks(tracks: List[Track], output_dir: Path,
                             file_types: List[str],
                             processes: int = 2) -> Dict:
    """Générer fichiers ANLZ pour collection de tracks.

    Supporte le multiprocessing pour accélérer la génération sur CPU multi-core.

    Args:
        tracks: Liste des tracks à traiter
        output_dir: Répertoire racine d'export
        file_types: Liste des types ANLZ à générer ('DAT', 'EXT', '2EX')
        processes: Nombre de process parallèles (défaut: 2, max: cpu_count)

    Returns:
        Dict avec files_generated, files, errors
    """
    logger = logging.getLogger(__name__)
    output_dir = Path(output_dir)

    # Clamp raisonnable: min 1, max CPU count
    cpu_count = os.cpu_count() or 1
    processes = max(1, min(int(processes or 1), cpu_count))

    logger.info(f"Generating ANLZ files for {len(tracks)} tracks, types: {file_types}")

    total_files = 0
    all_files = []
    total_errors = 0

    # Préparer les jobs avec chemins audio ABSOLUS
    jobs = []
    for i, track in enumerate(tracks, 1):
        # Résoudre le chemin audio (peut être relatif après copie vers Contents/)
        audio_path = Path(getattr(track, "file_path", "") or "")
        if audio_path and not audio_path.is_absolute():
            audio_path = output_dir / audio_path

        jobs.append({
            "track_id": i,
            "audio_path": str(audio_path),
            "cue_points": getattr(track, "cue_points", None),
            "output_dir": str(output_dir),
            "file_types": list(file_types),
        })

    # Mode séquentiel (fallback si processes <= 1)
    if processes <= 1:
        logger.info("ANLZ multiprocessing disabled (sequential mode)")
        exporter = ANLZExporter()
        anlz_types = _normalize_anlz_types(file_types)

        for job in jobs:
            track_ns = SimpleNamespace(
                file_path=job["audio_path"],
                cue_points=job.get("cue_points") or []
            )
            result = exporter.export_track_anlz(track_ns, job["track_id"], output_dir, anlz_types)
            total_files += result.get("files_generated", 0)
            all_files.extend([str(p) for p in result.get("files", [])])
            total_errors += result.get("errors", 0)

        logger.info(f"ANLZ generation completed: {total_files} files, {total_errors} errors")
        return {"files_generated": total_files, "files": all_files, "errors": total_errors}

    # Mode multiprocessing
    logger.info(f"ANLZ multiprocessing enabled: {processes} processes")

    with ProcessPoolExecutor(max_workers=processes) as pool:
        futures = [pool.submit(_anlz_worker, job) for job in jobs]

        for fut in as_completed(futures):
            try:
                result = fut.result()
                total_files += int(result.get("files_generated", 0))
                all_files.extend(result.get("files", []))
                total_errors += int(result.get("errors", 0))
            except Exception as e:
                logger.error(f"ANLZ worker failed: {e}", exc_info=True)
                total_errors += 1

    logger.info(f"ANLZ generation completed: {total_files} files, {total_errors} errors")
    return {"files_generated": total_files, "files": all_files, "errors": total_errors}
