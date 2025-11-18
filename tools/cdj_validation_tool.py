# CDJ Validation Tool - Analyse et validation en batch des exports Pioneer
# Architecture pour validation automatisée des formats PDB/ANLZ

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

class ValidationLevel(Enum):
    QUICK = "quick"           # Validation basique des headers
    STANDARD = "standard"     # Validation complète des structures
    DEEP = "deep"            # Validation avec comparaison références
    HARDWARE = "hardware"     # Test sur CDJ réel (si disponible)

class ValidationStatus(Enum):
    PASS = "pass"
    WARN = "warning"
    FAIL = "fail"
    SKIP = "skip"

@dataclass
class ValidationResult:
    test_name: str
    status: ValidationStatus
    message: str
    details: Optional[Dict] = None
    execution_time_ms: float = 0
    
@dataclass
class ExportValidationReport:
    export_path: str
    cdj_model: str
    validation_level: ValidationLevel
    timestamp: str
    total_tests: int
    passed: int
    warnings: int
    failed: int
    skipped: int
    execution_time_ms: float
    results: List[ValidationResult]
    
    @property
    def success_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100

class CDJValidationTool:
    """Outil d'analyse et validation en batch des exports CDJ/Pioneer"""
    
    def __init__(self, reference_db_path: Optional[str] = None):
        self.reference_db = self._load_reference_database(reference_db_path)
        self.logger = logging.getLogger(__name__)
        
        # Configuration des tests par modèle CDJ
        self.model_configs = {
            'CDJ-2000': {
                'supported_anlz': ['.DAT'],
                'max_cues': 4,
                'max_tracks': 10000,
                'requires_specific_structure': True
            },
            'CDJ-2000NXS': {
                'supported_anlz': ['.DAT'],
                'max_cues': 8,
                'max_tracks': 20000,
                'supports_color_cues': False
            },
            'CDJ-2000NXS2': {
                'supported_anlz': ['.DAT', '.EXT'],
                'max_cues': 8,
                'max_tracks': 50000,
                'supports_color_cues': True,
                'supports_hd_waveforms': True
            },
            'CDJ-3000': {
                'supported_anlz': ['.DAT', '.EXT', '.2EX'],
                'max_cues': 8,
                'max_tracks': 100000,
                'supports_color_cues': True,
                'supports_hd_waveforms': True,
                'supports_3band_waveforms': True
            }
        }
    
    def validate_export_batch(self, export_paths: List[str], 
                            cdj_model: str = 'CDJ-2000NXS2',
                            validation_level: ValidationLevel = ValidationLevel.STANDARD) -> List[ExportValidationReport]:
        """Validation en batch de multiples exports"""
        reports = []
        
        for export_path in export_paths:
            self.logger.info(f"Validating export: {export_path}")
            report = self.validate_single_export(export_path, cdj_model, validation_level)
            reports.append(report)
            
        return reports
    
    def validate_single_export(self, export_path: str, 
                             cdj_model: str,
                             validation_level: ValidationLevel) -> ExportValidationReport:
        """Validation complète d'un export unique"""
        import time
        start_time = time.time()
        
        export_path = Path(export_path)
        results = []
        
        # Tests de base
        results.extend(self._validate_directory_structure(export_path, cdj_model))
        results.extend(self._validate_pdb_file(export_path, cdj_model))
        results.extend(self._validate_anlz_files(export_path, cdj_model))
        
        # Tests avancés selon le niveau
        if validation_level in [ValidationLevel.STANDARD, ValidationLevel.DEEP]:
            results.extend(self._validate_metadata_consistency(export_path, cdj_model))
            results.extend(self._validate_file_references(export_path))
            
        if validation_level == ValidationLevel.DEEP:
            results.extend(self._validate_against_references(export_path, cdj_model))
            results.extend(self._validate_audio_analysis(export_path))
            
        if validation_level == ValidationLevel.HARDWARE:
            results.extend(self._validate_hardware_compatibility(export_path, cdj_model))
        
        # Compilation du rapport
        total_time = (time.time() - start_time) * 1000
        
        return ExportValidationReport(
            export_path=str(export_path),
            cdj_model=cdj_model,
            validation_level=validation_level,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            total_tests=len(results),
            passed=sum(1 for r in results if r.status == ValidationStatus.PASS),
            warnings=sum(1 for r in results if r.status == ValidationStatus.WARN),
            failed=sum(1 for r in results if r.status == ValidationStatus.FAIL),
            skipped=sum(1 for r in results if r.status == ValidationStatus.SKIP),
            execution_time_ms=total_time,
            results=results
        )
    
    def _validate_directory_structure(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Validation de la structure de dossiers Pioneer"""
        results = []
        
        # Structure attendue
        expected_dirs = ['PIONEER', 'PIONEER/rekordbox', 'PIONEER/USBANLZ']
        optional_dirs = ['Contents']
        
        for dir_path in expected_dirs:
            full_path = export_path / dir_path
            if full_path.exists() and full_path.is_dir():
                results.append(ValidationResult(
                    f"directory_structure_{dir_path.replace('/', '_')}",
                    ValidationStatus.PASS,
                    f"Directory {dir_path} exists"
                ))
            else:
                results.append(ValidationResult(
                    f"directory_structure_{dir_path.replace('/', '_')}",
                    ValidationStatus.FAIL,
                    f"Required directory {dir_path} missing"
                ))
        
        return results
    
    def _validate_pdb_file(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Validation du fichier PDB"""
        results = []
        pdb_path = export_path / 'PIONEER' / 'rekordbox' / 'export.pdb'
        
        if not pdb_path.exists():
            results.append(ValidationResult(
                "pdb_file_exists",
                ValidationStatus.FAIL,
                "export.pdb file not found"
            ))
            return results
        
        # Validation de la taille
        file_size = pdb_path.stat().st_size
        if file_size < 4096:  # Minimum: header + 1 page
            results.append(ValidationResult(
                "pdb_file_size",
                ValidationStatus.FAIL,
                f"PDB file too small: {file_size} bytes"
            ))
        else:
            results.append(ValidationResult(
                "pdb_file_size",
                ValidationStatus.PASS,
                f"PDB file size valid: {file_size} bytes"
            ))
        
        # Validation du header PDB
        try:
            with open(pdb_path, 'rb') as f:
                header = f.read(28)  # Premier header
                
                # Magic number (doit être 0)
                magic = int.from_bytes(header[0:4], 'little')
                if magic == 0:
                    results.append(ValidationResult(
                        "pdb_magic_number",
                        ValidationStatus.PASS,
                        "PDB magic number valid"
                    ))
                else:
                    results.append(ValidationResult(
                        "pdb_magic_number",
                        ValidationStatus.FAIL,
                        f"Invalid PDB magic number: {magic}"
                    ))
                
                # Page size (doit être 4096)
                page_size = int.from_bytes(header[4:8], 'little')
                if page_size == 4096:
                    results.append(ValidationResult(
                        "pdb_page_size",
                        ValidationStatus.PASS,
                        "PDB page size valid (4096)"
                    ))
                else:
                    results.append(ValidationResult(
                        "pdb_page_size",
                        ValidationStatus.FAIL,
                        f"Invalid PDB page size: {page_size}"
                    ))
                
        except Exception as e:
            results.append(ValidationResult(
                "pdb_header_read",
                ValidationStatus.FAIL,
                f"Failed to read PDB header: {e}"
            ))
        
        return results
    
    def _validate_anlz_files(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Validation des fichiers ANLZ"""
        results = []
        anlz_dir = export_path / 'PIONEER' / 'USBANLZ'
        
        if not anlz_dir.exists():
            results.append(ValidationResult(
                "anlz_directory",
                ValidationStatus.FAIL,
                "USBANLZ directory not found"
            ))
            return results
        
        # Configuration selon le modèle CDJ
        config = self.model_configs.get(cdj_model, self.model_configs['CDJ-2000NXS2'])
        supported_formats = config['supported_anlz']
        
        # Recherche des fichiers ANLZ
        dat_files = list(anlz_dir.glob('ANLZ*.DAT'))
        ext_files = list(anlz_dir.glob('ANLZ*.EXT'))
        ex2_files = list(anlz_dir.glob('ANLZ*.2EX'))
        
        # Validation des fichiers .DAT (obligatoires)
        if not dat_files:
            results.append(ValidationResult(
                "anlz_dat_files",
                ValidationStatus.FAIL,
                "No ANLZ .DAT files found"
            ))
        else:
            results.append(ValidationResult(
                "anlz_dat_files",
                ValidationStatus.PASS,
                f"Found {len(dat_files)} ANLZ .DAT files"
            ))
            
            # Validation du format de nommage
            for dat_file in dat_files[:5]:  # Test sur les 5 premiers
                if self._validate_anlz_filename(dat_file.name):
                    results.append(ValidationResult(
                        f"anlz_naming_{dat_file.name}",
                        ValidationStatus.PASS,
                        f"ANLZ filename format valid: {dat_file.name}"
                    ))
                else:
                    results.append(ValidationResult(
                        f"anlz_naming_{dat_file.name}",
                        ValidationStatus.FAIL,
                        f"Invalid ANLZ filename format: {dat_file.name}"
                    ))
        
        # Validation des fichiers .EXT (si supportés)
        if '.EXT' in supported_formats:
            if ext_files:
                results.append(ValidationResult(
                    "anlz_ext_files",
                    ValidationStatus.PASS,
                    f"Found {len(ext_files)} ANLZ .EXT files"
                ))
            else:
                results.append(ValidationResult(
                    "anlz_ext_files",
                    ValidationStatus.WARN,
                    "No ANLZ .EXT files found (optional for this model)"
                ))
        
        # Validation des fichiers .2EX (CDJ-3000 uniquement)
        if '.2EX' in supported_formats:
            if ex2_files:
                results.append(ValidationResult(
                    "anlz_2ex_files",
                    ValidationStatus.PASS,
                    f"Found {len(ex2_files)} ANLZ .2EX files"
                ))
            else:
                results.append(ValidationResult(
                    "anlz_2ex_files",
                    ValidationStatus.WARN,
                    "No ANLZ .2EX files found (optional for CDJ-3000)"
                ))
        
        return results
    
    def _validate_anlz_filename(self, filename: str) -> bool:
        """Validation du format de nom ANLZ"""
        import re
        # Format: ANLZ######.DAT/EXT/2EX
        pattern = r'^ANLZ\d{6}\.(DAT|EXT|2EX)$'
        return bool(re.match(pattern, filename))
    
    def _validate_metadata_consistency(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Validation de la cohérence des métadonnées"""
        results = []
        
        # Cette validation nécessiterait l'intégration avec vos parsers PDB
        # Exemple conceptuel:
        
        try:
            # Supposons une fonction parse_pdb disponible
            # pdb_data = parse_pdb(export_path / 'PIONEER' / 'rekordbox' / 'export.pdb')
            # anlz_count = len(list((export_path / 'PIONEER' / 'USBANLZ').glob('*.DAT')))
            # track_count = len(pdb_data['tracks'])
            
            # if anlz_count == track_count:
            #     results.append(ValidationResult(
            #         "metadata_consistency",
            #         ValidationStatus.PASS,
            #         f"ANLZ count matches track count: {track_count}"
            #     ))
            # else:
            #     results.append(ValidationResult(
            #         "metadata_consistency",
            #         ValidationStatus.WARN,
            #         f"ANLZ count ({anlz_count}) != track count ({track_count})"
            #     ))
            
            # Placeholder pour l'instant
            results.append(ValidationResult(
                "metadata_consistency",
                ValidationStatus.SKIP,
                "Metadata consistency check not implemented yet"
            ))
            
        except Exception as e:
            results.append(ValidationResult(
                "metadata_consistency",
                ValidationStatus.FAIL,
                f"Failed to validate metadata consistency: {e}"
            ))
        
        return results
    
    def _validate_file_references(self, export_path: Path) -> List[ValidationResult]:
        """Validation des références de fichiers"""
        results = []
        
        # Vérification que les fichiers audio référencés existent
        contents_dir = export_path / 'Contents'
        
        if contents_dir.exists():
            audio_files = list(contents_dir.glob('*.*'))
            audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.aiff'}
            valid_audio_files = [f for f in audio_files 
                               if f.suffix.lower() in audio_extensions]
            
            results.append(ValidationResult(
                "audio_files_present",
                ValidationStatus.PASS,
                f"Found {len(valid_audio_files)} audio files in Contents/"
            ))
        else:
            results.append(ValidationResult(
                "audio_files_present",
                ValidationStatus.WARN,
                "No Contents directory found (audio files not copied)"
            ))
        
        return results
    
    def _validate_against_references(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Validation contre base de référence"""
        results = []
        
        if not self.reference_db:
            results.append(ValidationResult(
                "reference_validation",
                ValidationStatus.SKIP,
                "No reference database available"
            ))
            return results
        
        # Comparaison avec exports de référence
        # Implementation dépendrait de la structure de votre reference_db
        
        results.append(ValidationResult(
            "reference_validation",
            ValidationStatus.SKIP,
            "Reference validation not implemented yet"
        ))
        
        return results
    
    def _validate_audio_analysis(self, export_path: Path) -> List[ValidationResult]:
        """Validation de la qualité de l'analyse audio"""
        results = []
        
        # Validation des waveforms ANLZ
        # Nécessiterait l'intégration avec votre parser ANLZ
        
        results.append(ValidationResult(
            "audio_analysis_quality",
            ValidationStatus.SKIP,
            "Audio analysis validation not implemented yet"
        ))
        
        return results
    
    def _validate_hardware_compatibility(self, export_path: Path, cdj_model: str) -> List[ValidationResult]:
        """Tests de compatibilité hardware (si CDJ connecté)"""
        results = []
        
        # Cette fonction nécessiterait une interface avec du hardware réel
        # ou un simulateur CDJ
        
        results.append(ValidationResult(
            "hardware_compatibility",
            ValidationStatus.SKIP,
            "Hardware validation requires physical CDJ connection"
        ))
        
        return results
    
    def _load_reference_database(self, reference_path: Optional[str]) -> Optional[Dict]:
        """Chargement de la base de données de référence"""
        if not reference_path or not Path(reference_path).exists():
            return None
        
        try:
            with open(reference_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load reference database: {e}")
            return None
    
    def export_report(self, report: ExportValidationReport, 
                     output_path: str, format: str = 'json') -> None:
        """Export du rapport de validation"""
        output_path = Path(output_path)
        
        if format == 'json':
            with open(output_path.with_suffix('.json'), 'w') as f:
                json.dump(asdict(report), f, indent=2, default=str)
        
        elif format == 'html':
            html_content = self._generate_html_report(report)
            with open(output_path.with_suffix('.html'), 'w') as f:
                f.write(html_content)
        
        elif format == 'csv':
            import csv
            with open(output_path.with_suffix('.csv'), 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Test Name', 'Status', 'Message', 'Execution Time (ms)'])
                for result in report.results:
                    writer.writerow([result.test_name, result.status.value, 
                                   result.message, result.execution_time_ms])
    
    def _generate_html_report(self, report: ExportValidationReport) -> str:
        """Génération de rapport HTML"""
        status_colors = {
            ValidationStatus.PASS: '#28a745',
            ValidationStatus.WARN: '#ffc107', 
            ValidationStatus.FAIL: '#dc3545',
            ValidationStatus.SKIP: '#6c757d'
        }
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>CDJ Validation Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
                .metric {{ background: white; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .results {{ margin-top: 20px; }}
                .result {{ padding: 10px; margin: 5px 0; border-radius: 3px; }}
                .pass {{ background: #d4edda; }}
                .warn {{ background: #fff3cd; }}
                .fail {{ background: #f8d7da; }}
                .skip {{ background: #e2e3e5; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>CDJ Validation Report</h1>
                <p><strong>Export:</strong> {report.export_path}</p>
                <p><strong>CDJ Model:</strong> {report.cdj_model}</p>
                <p><strong>Validation Level:</strong> {report.validation_level.value}</p>
                <p><strong>Timestamp:</strong> {report.timestamp}</p>
            </div>
            
            <div class="summary">
                <div class="metric">
                    <h3>Success Rate</h3>
                    <p>{report.success_rate:.1f}%</p>
                </div>
                <div class="metric">
                    <h3>Tests Passed</h3>
                    <p>{report.passed}/{report.total_tests}</p>
                </div>
                <div class="metric">
                    <h3>Warnings</h3>
                    <p>{report.warnings}</p>
                </div>
                <div class="metric">
                    <h3>Failures</h3>
                    <p>{report.failed}</p>
                </div>
                <div class="metric">
                    <h3>Execution Time</h3>
                    <p>{report.execution_time_ms:.0f}ms</p>
                </div>
            </div>
            
            <div class="results">
                <h2>Test Results</h2>
        """
        
        for result in report.results:
            css_class = result.status.value
            html += f"""
                <div class="result {css_class}">
                    <strong>{result.test_name}</strong>: {result.message}
                    <small>({result.execution_time_ms:.1f}ms)</small>
                </div>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html


# Exemple d'utilisation
if __name__ == "__main__":
    # Configuration des logs
    logging.basicConfig(level=logging.INFO)
    
    # Création de l'outil de validation
    validator = CDJValidationTool()
    
    # Validation en batch de plusieurs exports
    export_paths = [
        "path/to/export1",
        "path/to/export2", 
        "path/to/export3"
    ]
    
    reports = validator.validate_export_batch(
        export_paths=export_paths,
        cdj_model='CDJ-2000NXS2',
        validation_level=ValidationLevel.STANDARD
    )
    
    # Export des rapports
    for i, report in enumerate(reports):
        validator.export_report(
            report=report,
            output_path=f"validation_report_{i}",
            format='html'
        )
        
        print(f"Export {i+1}: {report.success_rate:.1f}% success rate")
        print(f"  Passed: {report.passed}, Warnings: {report.warnings}, Failed: {report.failed}")
