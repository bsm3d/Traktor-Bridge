#!/usr/bin/env python3
"""
CDJ USB Validator - Analyseur et validateur de clés USB pour CDJ Pioneer
Vérifie la compatibilité complète d'une clé USB avec les lecteurs CDJ Pioneer

Fonctionnalités :
- Validation structure de dossiers Pioneer
- Vérification noms de fichiers et caractères interdits
- Analyse des fichiers de base de données (.pdb)
- Validation des fichiers d'analyse (.anlz)
- Vérification des formats audio supportés
- Contrôle des limites CDJ (taille, profondeur, nombre de fichiers)
- Rapport détaillé avec recommandations de correction

Auteur: Benoit Saint-Moulin
Usage: python cdj_usb_validator.py /path/to/usb/drive
"""

import os
import sys
import struct
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime
import argparse
import logging
import re
import mimetypes

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class CDJLimitations:
    """Limitations techniques des CDJ Pioneer"""
    max_folder_depth: int = 8
    max_files_per_folder: int = 999
    max_total_tracks: int = 10000
    max_filename_length: int = 255
    max_path_length: int = 260
    supported_audio_formats: Set[str] = field(default_factory=lambda: {
        '.mp3', '.wav', '.aiff', '.flac', '.alac', '.aac'
    })
    forbidden_chars: Set[str] = field(default_factory=lambda: {
        '<', '>', ':', '"', '|', '?', '*', '\x00'
    })
    required_structure: Dict[str, str] = field(default_factory=lambda: {
        'PIONEER': 'Dossier racine Pioneer obligatoire',
        'PIONEER/rekordbox': 'Base de données Rekordbox',
        'PIONEER/USBANLZ': 'Fichiers d\'analyse'
    })

@dataclass
class FileValidation:
    """Résultat de validation d'un fichier"""
    path: str
    is_valid: bool
    file_type: str
    size_mb: float
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class FolderValidation:
    """Résultat de validation d'un dossier"""
    path: str
    depth: int
    file_count: int
    audio_file_count: int
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class USBValidationReport:
    """Rapport complet de validation USB"""
    usb_path: str
    validation_date: str
    is_cdj_compatible: bool
    compatibility_score: float
    total_issues: int
    total_warnings: int
    
    # Statistiques globales
    total_audio_files: int
    total_size_gb: float
    max_depth_found: int
    
    # Validations détaillées
    structure_validation: Dict[str, bool]
    folder_validations: List[FolderValidation]
    file_validations: List[FileValidation]
    database_validation: Dict[str, Any]
    
    # Recommandations
    critical_issues: List[str]
    recommendations: List[str]

class CDJUSBValidator:
    """Validateur principal pour clés USB CDJ"""
    
    def __init__(self, usb_path: str):
        """Initialise le validateur avec le chemin de la clé USB"""
        self.usb_path = Path(usb_path)
        self.limitations = CDJLimitations()
        
        if not self.usb_path.exists():
            raise FileNotFoundError(f"Chemin USB introuvable: {usb_path}")
        
        if not self.usb_path.is_dir():
            raise ValueError(f"Le chemin doit être un dossier: {usb_path}")
        
        # Statistiques globales
        self.total_audio_files = 0
        self.total_size_bytes = 0
        self.max_depth = 0
        
        # Collecteurs de validation
        self.folder_validations = []
        self.file_validations = []
        self.critical_issues = []
        self.recommendations = []
        
        logger.info(f"Validateur CDJ initialisé pour: {self.usb_path}")
    
    def validate_complete_usb(self) -> USBValidationReport:
        """Lance une validation complète de la clé USB"""
        logger.info("🚀 Début de la validation complète USB CDJ")
        
        try:
            # 1. Validation de la structure Pioneer
            structure_validation = self._validate_pioneer_structure()
            
            # 2. Scan et validation récursive
            self._scan_and_validate_recursive(self.usb_path, 0)
            
            # 3. Validation des bases de données
            database_validation = self._validate_databases()
            
            # 4. Calcul du score de compatibilité
            compatibility_score = self._calculate_compatibility_score()
            
            # 5. Génération des recommandations
            self._generate_recommendations()
            
            # 6. Construction du rapport
            report = USBValidationReport(
                usb_path=str(self.usb_path),
                validation_date=datetime.now().isoformat(),
                is_cdj_compatible=compatibility_score >= 85.0,
                compatibility_score=compatibility_score,
                total_issues=sum(len(fv.issues) for fv in self.folder_validations) + 
                           sum(len(fv.issues) for fv in self.file_validations),
                total_warnings=sum(len(fv.warnings) for fv in self.folder_validations) + 
                             sum(len(fv.warnings) for fv in self.file_validations),
                total_audio_files=self.total_audio_files,
                total_size_gb=round(self.total_size_bytes / (1024**3), 2),
                max_depth_found=self.max_depth,
                structure_validation=structure_validation,
                folder_validations=self.folder_validations,
                file_validations=self.file_validations,
                database_validation=database_validation,
                critical_issues=self.critical_issues,
                recommendations=self.recommendations
            )
            
            logger.info(f"✅ Validation terminée - Score: {compatibility_score:.1f}/100")
            return report
            
        except Exception as e:
            logger.error(f"❌ Erreur durant la validation: {e}")
            raise
    
    def _validate_pioneer_structure(self) -> Dict[str, bool]:
        """Valide la structure de dossiers Pioneer requise"""
        logger.info("📁 Validation de la structure Pioneer...")
        
        structure_validation = {}
        
        for required_path, description in self.limitations.required_structure.items():
            full_path = self.usb_path / required_path
            exists = full_path.exists() and full_path.is_dir()
            structure_validation[required_path] = exists
            
            if not exists:
                issue = f"Dossier requis manquant: {required_path} ({description})"
                self.critical_issues.append(issue)
                logger.warning(f"⚠️  {issue}")
            else:
                logger.info(f"✅ {required_path} - OK")
        
        return structure_validation
    
    def _scan_and_validate_recursive(self, current_path: Path, depth: int):
        """Scan récursif avec validation de chaque élément"""
        if depth > self.limitations.max_folder_depth:
            self.critical_issues.append(f"Profondeur excessive: {current_path} (>{self.limitations.max_folder_depth})")
            return
        
        self.max_depth = max(self.max_depth, depth)
        
        try:
            items = list(current_path.iterdir())
        except PermissionError:
            self.critical_issues.append(f"Accès refusé: {current_path}")
            return
        
        # Validation du dossier courant
        folder_validation = self._validate_folder(current_path, items, depth)
        self.folder_validations.append(folder_validation)
        
        # Traitement des éléments
        for item in items:
            if item.is_file():
                file_validation = self._validate_file(item)
                self.file_validations.append(file_validation)
                
                # Mise à jour des statistiques
                if file_validation.file_type == 'audio':
                    self.total_audio_files += 1
                self.total_size_bytes += item.stat().st_size
                
            elif item.is_dir():
                # Récursion dans les sous-dossiers
                self._scan_and_validate_recursive(item, depth + 1)
    
    def _validate_folder(self, folder_path: Path, items: List[Path], depth: int) -> FolderValidation:
        """Valide un dossier spécifique"""
        issues = []
        warnings = []
        
        # Comptage des fichiers
        files = [item for item in items if item.is_file()]
        audio_files = [f for f in files if self._is_audio_file(f)]
        
        # Validation du nom de dossier
        folder_name = folder_path.name
        if not self._is_valid_filename(folder_name):
            issues.append(f"Nom de dossier invalide: {folder_name}")
        
        # Validation du nombre de fichiers
        if len(files) > self.limitations.max_files_per_folder:
            issues.append(f"Trop de fichiers: {len(files)} > {self.limitations.max_files_per_folder}")
        
        # Avertissement si beaucoup de fichiers
        if len(files) > 500:
            warnings.append(f"Nombreux fichiers ({len(files)}) - performance CDJ possible")
        
        # Validation de la profondeur
        if depth > self.limitations.max_folder_depth:
            issues.append(f"Profondeur excessive: {depth} > {self.limitations.max_folder_depth}")
        
        return FolderValidation(
            path=str(folder_path.relative_to(self.usb_path)),
            depth=depth,
            file_count=len(files),
            audio_file_count=len(audio_files),
            is_valid=len(issues) == 0,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_file(self, file_path: Path) -> FileValidation:
        """Valide un fichier spécifique"""
        issues = []
        warnings = []
        
        # Détermination du type de fichier
        file_type = self._classify_file(file_path)
        
        # Taille du fichier
        try:
            size_bytes = file_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
        except OSError:
            size_mb = 0
            issues.append("Impossible de lire la taille du fichier")
        
        # Validation du nom de fichier
        if not self._is_valid_filename(file_path.name):
            issues.append(f"Nom de fichier invalide: {file_path.name}")
        
        # Validation de la longueur du chemin
        full_path_str = str(file_path)
        if len(full_path_str) > self.limitations.max_path_length:
            issues.append(f"Chemin trop long: {len(full_path_str)} > {self.limitations.max_path_length}")
        
        # Validations spécifiques par type
        if file_type == 'audio':
            self._validate_audio_file(file_path, size_mb, issues, warnings)
        elif file_type == 'database':
            self._validate_database_file(file_path, size_mb, issues, warnings)
        elif file_type == 'analysis':
            self._validate_analysis_file(file_path, size_mb, issues, warnings)
        
        return FileValidation(
            path=str(file_path.relative_to(self.usb_path)),
            is_valid=len(issues) == 0,
            file_type=file_type,
            size_mb=round(size_mb, 2),
            issues=issues,
            warnings=warnings
        )
    
    def _validate_audio_file(self, file_path: Path, size_mb: float, issues: List[str], warnings: List[str]):
        """Validations spécifiques aux fichiers audio"""
        # Vérification de l'extension
        if file_path.suffix.lower() not in self.limitations.supported_audio_formats:
            issues.append(f"Format audio non supporté: {file_path.suffix}")
        
        # Vérification de la taille
        if size_mb > 100:  # Fichier très volumineux
            warnings.append(f"Fichier audio volumineux: {size_mb:.1f} MB")
        elif size_mb < 0.5:  # Fichier très petit
            warnings.append(f"Fichier audio très petit: {size_mb:.1f} MB")
        
        # Vérification de la lisibilité
        try:
            with open(file_path, 'rb') as f:
                header = f.read(1024)
                if not header:
                    issues.append("Fichier audio vide ou corrompu")
        except Exception:
            issues.append("Impossible de lire le fichier audio")
    
    def _validate_database_file(self, file_path: Path, size_mb: float, issues: List[str], warnings: List[str]):
        """Validations spécifiques aux fichiers de base de données"""
        if file_path.name.lower() != 'export.pdb':
            warnings.append(f"Nom de base non standard: {file_path.name}")
        
        # Validation de la structure PDB basique
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if len(header) >= 4:
                    signature = struct.unpack('<I', header)[0]
                    if signature != 0:
                        issues.append("Signature PDB invalide")
                else:
                    issues.append("Fichier PDB trop petit")
        except Exception:
            issues.append("Impossible de lire le fichier PDB")
    
    def _validate_analysis_file(self, file_path: Path, size_mb: float, issues: List[str], warnings: List[str]):
        """Validations spécifiques aux fichiers d'analyse"""
        if not file_path.suffix.lower() in ['.anlz', '.ext']:
            warnings.append(f"Extension d'analyse inhabituelle: {file_path.suffix}")
        
        # Validation de la structure ANLZ basique
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if len(header) >= 8:
                    # Vérification basique de l'en-tête ANLZ
                    magic = header[:4]
                    if magic not in [b'ANLZ', b'PMAI', b'PMCO']:
                        warnings.append("En-tête ANLZ non reconnu")
                else:
                    issues.append("Fichier ANLZ trop petit")
        except Exception:
            issues.append("Impossible de lire le fichier ANLZ")
    
    def _validate_databases(self) -> Dict[str, Any]:
        """Validation approfondie des bases de données"""
        database_validation = {
            'pdb_found': False,
            'pdb_valid': False,
            'anlz_files': 0,
            'analysis_coverage': 0.0
        }
        
        # Recherche du fichier export.pdb
        pdb_path = self.usb_path / 'PIONEER' / 'rekordbox' / 'export.pdb'
        if pdb_path.exists():
            database_validation['pdb_found'] = True
            
            # Validation basique du PDB
            try:
                with open(pdb_path, 'rb') as f:
                    header = f.read(28)
                    if len(header) >= 28:
                        signature, page_length, num_tables = struct.unpack('<III', header[:12])
                        if signature == 0 and page_length > 0 and num_tables > 0:
                            database_validation['pdb_valid'] = True
            except Exception:
                pass
        
        # Comptage des fichiers ANLZ
        anlz_path = self.usb_path / 'PIONEER' / 'USBANLZ'
        if anlz_path.exists():
            anlz_files = list(anlz_path.glob('**/*.anlz'))
            database_validation['anlz_files'] = len(anlz_files)
            
            # Calcul approximatif de la couverture d'analyse
            if self.total_audio_files > 0:
                database_validation['analysis_coverage'] = min(100.0, 
                    (len(anlz_files) / self.total_audio_files) * 100)
        
        return database_validation
    
    def _calculate_compatibility_score(self) -> float:
        """Calcule un score de compatibilité CDJ (0-100)"""
        score = 100.0
        
        # Pénalités pour les problèmes critiques
        score -= len(self.critical_issues) * 20
        
        # Pénalités pour les problèmes de fichiers/dossiers
        total_file_issues = sum(len(fv.issues) for fv in self.file_validations)
        total_folder_issues = sum(len(fv.issues) for fv in self.folder_validations)
        
        score -= total_file_issues * 5
        score -= total_folder_issues * 10
        
        # Bonus pour une structure Pioneer complète
        structure_complete = all(self._validate_pioneer_structure().values())
        if structure_complete:
            score += 10
        
        # Pénalité si pas de base de données
        db_validation = self._validate_databases()
        if not db_validation['pdb_found']:
            score -= 30
        elif not db_validation['pdb_valid']:
            score -= 20
        
        return max(0.0, min(100.0, score))
    
    def _generate_recommendations(self):
        """Génère des recommandations d'amélioration"""
        self.recommendations = []
        
        # Recommandations basées sur la structure
        structure = self._validate_pioneer_structure()
        for path, exists in structure.items():
            if not exists:
                self.recommendations.append(f"Créer le dossier manquant: {path}")
        
        # Recommandations basées sur les fichiers
        invalid_files = [fv for fv in self.file_validations if not fv.is_valid]
        if invalid_files:
            self.recommendations.append(f"Corriger {len(invalid_files)} fichiers invalides")
        
        # Recommandations basées sur les performances
        if self.total_audio_files > 8000:
            self.recommendations.append("Réduire le nombre de pistes (<8000) pour de meilleures performances")
        
        if self.max_depth > 6:
            self.recommendations.append("Réorganiser la hiérarchie (profondeur recommandée: ≤6 niveaux)")
        
        # Recommandations pour la base de données
        db_validation = self._validate_databases()
        if not db_validation['pdb_found']:
            self.recommendations.append("Générer une base de données export.pdb avec Rekordbox ou Traktor Bridge")
        
        if db_validation['analysis_coverage'] < 50:
            self.recommendations.append("Analyser plus de pistes pour améliorer la navigation CDJ")
    
    def _classify_file(self, file_path: Path) -> str:
        """Classifie un fichier par type"""
        suffix = file_path.suffix.lower()
        name = file_path.name.lower()
        
        if suffix in self.limitations.supported_audio_formats:
            return 'audio'
        elif suffix == '.pdb' or name == 'export.pdb':
            return 'database'
        elif suffix in ['.anlz', '.ext']:
            return 'analysis'
        elif suffix in ['.jpg', '.jpeg', '.png', '.bmp']:
            return 'artwork'
        elif suffix in ['.txt', '.log']:
            return 'text'
        else:
            return 'other'
    
    def _is_audio_file(self, file_path: Path) -> bool:
        """Vérifie si un fichier est un fichier audio supporté"""
        return file_path.suffix.lower() in self.limitations.supported_audio_formats
    
    def _is_valid_filename(self, filename: str) -> bool:
        """Vérifie si un nom de fichier est valide pour CDJ"""
        # Vérification des caractères interdits
        if any(char in filename for char in self.limitations.forbidden_chars):
            return False
        
        # Vérification de la longueur
        if len(filename) > self.limitations.max_filename_length:
            return False
        
        # Vérification des caractères de contrôle
        if any(ord(char) < 32 for char in filename):
            return False
        
        # Vérification des noms réservés Windows (importante pour compatibilité)
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
        name_without_ext = filename.split('.')[0].upper()
        if name_without_ext in reserved_names:
            return False
        
        return True

class USBReportGenerator:
    """Générateur de rapports de validation USB"""
    
    @staticmethod
    def print_console_report(report: USBValidationReport):
        """Affiche un rapport détaillé dans la console"""
        print("\n" + "="*80)
        print("🎧 CDJ USB VALIDATION REPORT")
        print("="*80)
        
        # Informations générales
        print(f"\n📍 USB Drive: {report.usb_path}")
        print(f"📅 Validation Date: {report.validation_date}")
        print(f"🎯 Compatibility Score: {report.compatibility_score:.1f}/100")
        
        # Status général
        status_icon = "✅" if report.is_cdj_compatible else "❌"
        print(f"{status_icon} CDJ Compatible: {'YES' if report.is_cdj_compatible else 'NO'}")
        
        # Statistiques
        print(f"\n📊 STATISTICS")
        print(f"   🎵 Total Audio Files: {report.total_audio_files}")
        print(f"   💾 Total Size: {report.total_size_gb} GB")
        print(f"   📁 Max Folder Depth: {report.max_depth_found}")
        print(f"   ⚠️  Issues: {report.total_issues}")
        print(f"   🔔 Warnings: {report.total_warnings}")
        
        # Validation de structure
        print(f"\n🏗️  PIONEER STRUCTURE")
        for path, valid in report.structure_validation.items():
            icon = "✅" if valid else "❌"
            print(f"   {icon} {path}")
        
        # Base de données
        print(f"\n🗃️  DATABASE STATUS")
        db = report.database_validation
        pdb_icon = "✅" if db['pdb_found'] and db['pdb_valid'] else "❌"
        print(f"   {pdb_icon} export.pdb: {'Valid' if db['pdb_valid'] else 'Invalid/Missing'}")
        print(f"   🔍 ANLZ Files: {db['anlz_files']}")
        print(f"   📈 Analysis Coverage: {db['analysis_coverage']:.1f}%")
        
        # Problèmes critiques
        if report.critical_issues:
            print(f"\n🚨 CRITICAL ISSUES")
            for issue in report.critical_issues:
                print(f"   ❌ {issue}")
        
        # Recommandations
        if report.recommendations:
            print(f"\n💡 RECOMMENDATIONS")
            for i, rec in enumerate(report.recommendations, 1):
                print(f"   {i}. {rec}")
        
        # Résumé par dossiers avec problèmes
        problem_folders = [fv for fv in report.folder_validations if not fv.is_valid]
        if problem_folders:
            print(f"\n📁 PROBLEMATIC FOLDERS ({len(problem_folders)})")
            for fv in problem_folders[:10]:  # Limite à 10 pour l'affichage
                print(f"   📂 {fv.path}")
                for issue in fv.issues:
                    print(f"      ❌ {issue}")
        
        # Résumé par fichiers avec problèmes
        problem_files = [fv for fv in report.file_validations if not fv.is_valid]
        if problem_files:
            print(f"\n📄 PROBLEMATIC FILES ({len(problem_files)})")
            for fv in problem_files[:10]:  # Limite à 10 pour l'affichage
                print(f"   📄 {fv.path} ({fv.file_type}, {fv.size_mb} MB)")
                for issue in fv.issues:
                    print(f"      ❌ {issue}")
        
        print("\n" + "="*80)
        
        # Conseil final
        if report.is_cdj_compatible:
            print("🎉 Cette clé USB devrait fonctionner correctement avec vos CDJ !")
        else:
            print("⚠️  Cette clé USB nécessite des corrections avant utilisation avec CDJ.")
        
        print("="*80)
    
    @staticmethod
    def save_json_report(report: USBValidationReport, output_path: str):
        """Sauvegarde le rapport en JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
        print(f"📄 Rapport JSON sauvegardé: {output_path}")
    
    @staticmethod
    def save_html_report(report: USBValidationReport, output_path: str):
        """Génère un rapport HTML interactif"""
        html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CDJ USB Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; color: #333; border-bottom: 2px solid #007acc; padding-bottom: 20px; }}
        .score {{ font-size: 3em; font-weight: bold; color: {'#4CAF50' if report.is_cdj_compatible else '#f44336'}; }}
        .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #007acc; background: #f8f9fa; }}
        .issue {{ color: #f44336; }}
        .warning {{ color: #ff9800; }}
        .success {{ color: #4CAF50; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .stat-box {{ background: #e3f2fd; padding: 15px; border-radius: 5px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎧 CDJ USB Validation Report</h1>
            <div class="score">{report.compatibility_score:.1f}/100</div>
            <p>{'✅ CDJ Compatible' if report.is_cdj_compatible else '❌ CDJ Incompatible'}</p>
        </div>
        
        <div class="section">
            <h2>📊 Statistics</h2>
            <div class="stats">
                <div class="stat-box">
                    <h3>🎵 Audio Files</h3>
                    <p>{report.total_audio_files}</p>
                </div>
                <div class="stat-box">
                    <h3>💾 Total Size</h3>
                    <p>{report.total_size_gb} GB</p>
                </div>
                <div class="stat-box">
                    <h3>📁 Max Depth</h3>
                    <p>{report.max_depth_found}</p>
                </div>
                <div class="stat-box">
                    <h3>⚠️ Issues</h3>
                    <p class="issue">{report.total_issues}</p>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>💡 Recommendations</h2>
            <ul>
                {''.join(f'<li>{rec}</li>' for rec in report.recommendations)}
            </ul>
        </div>
    </div>
</body>
</html>
        """
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"🌐 Rapport HTML sauvegardé: {output_path}")

def main():
    """Interface en ligne de commande"""
    parser = argparse.ArgumentParser(
        description='Validateur de clés USB pour CDJ Pioneer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python cdj_usb_validator.py /media/usb/
  python cdj_usb_validator.py E:\\ --output-json report.json
  python cdj_usb_validator.py /Volumes/USB --output-html report.html --verbose
        """
    )
    
    parser.add_argument('usb_path', help='Chemin vers la clé USB à valider')
    parser.add_argument('--output-json', '-j', help='Sauvegarder le rapport en JSON')
    parser.add_argument('--output-html', '-html', help='Générer un rapport HTML')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mode verbeux')
    parser.add_argument('--quiet', '-q', action='store_true', help='Mode silencieux (erreurs uniquement)')
    
    args = parser.parse_args()
    
    # Configuration du logging
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    
    try:
        # Validation
        validator = CDJUSBValidator(args.usb_path)
        report = validator.validate_complete_usb()
        
        # Affichage console
        if not args.quiet:
            USBReportGenerator.print_console_report(report)
        
        # Sauvegarde JSON
        if args.output_json:
            USBReportGenerator.save_json_report(report, args.output_json)
        
        # Génération HTML
        if args.output_html:
            USBReportGenerator.save_html_report(report, args.output_html)
        
        # Code de sortie
        sys.exit(0 if report.is_cdj_compatible else 1)
        
    except FileNotFoundError as e:
        print(f"❌ Erreur: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()