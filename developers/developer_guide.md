# Traktor Bridge 2.0 - Developer Guide

**Author**: Benoit (BSM) Saint-Moulin
**Version**: 2.0
**Last Updated**: November 2024

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Environment](#development-environment)
3. [Code Structure](#code-structure)
4. [Adding New Features](#adding-new-features)
5. [Creating New Exporters](#creating-new-exporters)
6. [Testing](#testing)
7. [Debugging](#debugging)
8. [Contributing](#contributing)
9. [Coding Standards](#coding-standards)
10. [Release Process](#release-process)

---

## Getting Started

### Prerequisites

- **Python**: 3.8 or higher
- **Git**: For version control
- **IDE**: VSCode, PyCharm, or similar with Python support

### Clone Repository

```bash
git clone https://github.com/bsm3d/Traktor-Bridge-2.git
cd Traktor-Bridge-2
```

### Install Dependencies

```bash
# Core dependencies
pip install PySide6 pygame tinytag pillow mutagen

# Development dependencies
pip install pytest pytest-cov black pylint mypy

# Optional for enhanced features
pip install lxml chardet librosa aubio pysqlcipher3
```

### Verify Installation

```bash
python main.py
```

---

## Development Environment

### Recommended IDE Setup

#### VSCode

**Extensions:**
- Python
- Pylance
- Python Docstring Generator
- GitLens

**settings.json:**
```json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length", "100"],
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true
}
```

#### PyCharm

**Settings:**
- **Code Style**: PEP 8
- **Line Length**: 100
- **Formatter**: Black
- **Linter**: Pylint
- **Type Checker**: mypy

### Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Code Structure

### Module Organization

```
Traktor-Bridge-2/
├── main.py                    # Application entry point
├── exporter/                  # Export engines
│   ├── cdj_integration.py     # CDJ orchestrator
│   ├── cdj_pdb_exporter.py    # PDB binary generator
│   ├── cdj_anlz_exporter.py   # ANLZ waveform generator
│   ├── bsm_xml_exporter.py    # XML exporter
│   ├── bsm_m3u_exporter.py    # M3U exporter
│   └── bsm_rb_exporter.py     # Rekordbox DB exporter
├── parser/                    # NML parsing
│   └── bsm_nml_parser.py      # Traktor parser
├── utils/                     # Utilities
│   ├── playlist.py            # Playlist management
│   ├── key_translator.py      # Key translation
│   ├── audio_manager.py       # Audio playback
│   ├── db_manager.py          # Database management
│   ├── loading_system.py      # Loading system
│   ├── file_validator.py      # File validation
│   └── path_validator.py      # Path validation
├── ui/                        # User interface
│   ├── about.py               # About dialog
│   ├── details.py             # Details viewer
│   ├── options.py             # Settings dialog
│   ├── log.py                 # Log viewer
│   ├── timeline.py            # Timeline viewer
│   └── usage.py               # Usage guide
├── threads/                   # Background processing
│   └── conversion.py          # Conversion thread
└── tools/                     # Developer tools
    ├── pdb_reader.py          # PDB inspector
    ├── cdj_usb_validator.py   # USB validator
    └── nml_inspector.py       # NML inspector
```

### Key Files

- **main.py**: Application entry point and main GUI
- **parser/bsm_nml_parser.py**: Core NML parsing logic
- **exporter/cdj_integration.py**: CDJ export orchestration
- **threads/conversion.py**: Background conversion worker

---

## Adding New Features

### Step-by-Step Guide

#### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

#### 2. Implement Feature

**Example: Adding a new export option**

```python
# In ui/options.py

class OptionsDialog(QDialog):
    def __init__(self, app_config, settings, parent=None):
        super().__init__(parent)
        # ... existing code ...

    def _create_export_options(self):
        """Create export options section."""
        # Add new checkbox
        self.new_option_check = QCheckBox("Enable New Feature")
        self.new_option_check.setChecked(
            self.settings.get('new_feature_enabled', False)
        )
        self.new_option_check.toggled.connect(
            self._on_new_option_toggled
        )

    def _on_new_option_toggled(self, checked: bool):
        """Handle new option toggle."""
        self.settings['new_feature_enabled'] = checked
        self.settings_changed.emit(self.settings)
```

#### 3. Update Settings

```python
# In main.py

class ConverterGUI(QMainWindow, LoadingSystemMixin):
    def __init__(self):
        # Add default setting
        self.settings = {
            # ... existing settings ...
            'new_feature_enabled': False,
        }
```

#### 4. Implement Logic

```python
# In threads/conversion.py

class ConversionThread(QThread):
    def run(self):
        try:
            # Check if new feature is enabled
            if self.settings.get('new_feature_enabled', False):
                self._apply_new_feature()
        except Exception as e:
            self.finished.emit("error", str(e))

    def _apply_new_feature(self):
        """Implement new feature logic."""
        # Your implementation here
        pass
```

#### 5. Test Feature

```bash
# Run application
python main.py

# Test with different settings
# Verify logs
# Check output
```

#### 6. Commit Changes

```bash
git add .
git commit -m "Add new feature: description"
git push origin feature/your-feature-name
```

---

## Creating New Exporters

### Exporter Template

```python
"""
New Format Exporter for Traktor Bridge
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from parser.bsm_nml_parser import Track, Node


class NewFormatExporter:
    """
    Exporter for [Format Name].

    Features:
    - Feature 1
    - Feature 2
    - Feature 3
    """

    def __init__(self, progress_queue: Optional[queue.Queue] = None):
        """
        Initialize exporter.

        Args:
            progress_queue: Queue for progress reporting
        """
        self.progress_queue = progress_queue
        self.logger = logging.getLogger(__name__)

    def export_collection(
        self,
        tracks: List[Track],
        playlist_structure: List[Node],
        output_path: Path,
        **options
    ) -> Dict[str, Any]:
        """
        Export collection to new format.

        Args:
            tracks: List of tracks to export
            playlist_structure: Playlist hierarchy
            output_path: Output file/directory
            **options: Additional export options

        Returns:
            Export result dictionary with status and statistics
        """
        try:
            self._report_progress(0, "Starting export...")

            # Create output directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Export tracks
            exported_count = self._export_tracks(tracks, output_path)
            self._report_progress(50, f"Exported {exported_count} tracks")

            # Export playlists
            playlist_count = self._export_playlists(
                playlist_structure, output_path
            )
            self._report_progress(100, "Export completed")

            return {
                'status': 'success',
                'tracks_exported': exported_count,
                'playlists_created': playlist_count,
                'output_path': str(output_path)
            }

        except Exception as e:
            self.logger.error(f"Export failed: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e)
            }

    def _export_tracks(
        self,
        tracks: List[Track],
        output_path: Path
    ) -> int:
        """
        Export track metadata.

        Args:
            tracks: Tracks to export
            output_path: Output directory

        Returns:
            Number of tracks exported
        """
        exported = 0

        for i, track in enumerate(tracks):
            try:
                # Export track
                self._export_track(track, output_path)
                exported += 1

                # Report progress every 100 tracks
                if i % 100 == 0:
                    percentage = int((i / len(tracks)) * 50)
                    self._report_progress(
                        percentage,
                        f"Exporting tracks: {i}/{len(tracks)}"
                    )

            except Exception as e:
                self.logger.warning(f"Failed to export {track.title}: {e}")

        return exported

    def _export_track(self, track: Track, output_path: Path) -> None:
        """
        Export single track.

        Args:
            track: Track to export
            output_path: Output directory
        """
        # Implement track export logic
        pass

    def _export_playlists(
        self,
        structure: List[Node],
        output_path: Path
    ) -> int:
        """
        Export playlist structure.

        Args:
            structure: Playlist hierarchy
            output_path: Output directory

        Returns:
            Number of playlists exported
        """
        count = 0

        for node in structure:
            if node.type == 'playlist':
                self._export_playlist(node, output_path)
                count += 1
            elif node.type == 'folder' and node.children:
                count += self._export_playlists(node.children, output_path)

        return count

    def _export_playlist(self, playlist: Node, output_path: Path) -> None:
        """
        Export single playlist.

        Args:
            playlist: Playlist to export
            output_path: Output directory
        """
        # Implement playlist export logic
        pass

    def _report_progress(self, percentage: int, message: str) -> None:
        """
        Report progress to queue.

        Args:
            percentage: Completion percentage (0-100)
            message: Progress message
        """
        if self.progress_queue:
            self.progress_queue.put(("progress", (percentage, message)))

    def _validate_output(self, output_path: Path) -> List[str]:
        """
        Validate export output.

        Args:
            output_path: Output directory

        Returns:
            List of validation issues (empty if valid)
        """
        issues = []

        # Implement validation logic

        return issues
```

### Integrate Exporter

**1. Add to conversion thread:**

```python
# In threads/conversion.py

class ConversionThread(QThread):
    def run(self):
        try:
            # ... existing formats ...

            elif export_format == "New Format":
                from exporter.new_format_exporter import NewFormatExporter

                exporter = NewFormatExporter(self.progress_queue)
                result = exporter.export_collection(
                    tracks=all_tracks,
                    playlist_structure=self.structure,
                    output_path=Path(self.output_path),
                    # Add custom options
                    custom_option=self.settings.get('custom_option')
                )

                if result['status'] == 'success':
                    self.finished.emit("completed", "Export successful")
                else:
                    self.finished.emit("error", result['error'])
```

**2. Add to UI:**

```python
# In main.py

# Add to export format list
export_formats = [
    "CDJ/USB",
    "Rekordbox Database",
    "Rekordbox XML",
    "M3U",
    "New Format"  # Add your format
]
```

---

## Testing

### Unit Testing

**Create test file:**

```python
# tests/test_new_exporter.py

import pytest
from pathlib import Path
from exporter.new_format_exporter import NewFormatExporter
from parser.bsm_nml_parser import Track, Node


@pytest.fixture
def sample_track():
    """Create sample track for testing."""
    return Track(
        title="Test Track",
        artist="Test Artist",
        album="Test Album",
        genre="Test Genre",
        bpm=128.0,
        musical_key="5",
        # ... other fields ...
    )


@pytest.fixture
def sample_playlist(sample_track):
    """Create sample playlist for testing."""
    return Node(
        type='playlist',
        name='Test Playlist',
        tracks=[sample_track],
        children=[],
        uuid='test-uuid',
        search_expression=''
    )


def test_export_track(sample_track, tmp_path):
    """Test single track export."""
    exporter = NewFormatExporter()

    result = exporter.export_collection(
        tracks=[sample_track],
        playlist_structure=[],
        output_path=tmp_path
    )

    assert result['status'] == 'success'
    assert result['tracks_exported'] == 1


def test_export_playlist(sample_playlist, tmp_path):
    """Test playlist export."""
    exporter = NewFormatExporter()

    result = exporter.export_collection(
        tracks=sample_playlist.tracks,
        playlist_structure=[sample_playlist],
        output_path=tmp_path
    )

    assert result['status'] == 'success'
    assert result['playlists_created'] == 1


def test_invalid_output_path(sample_track):
    """Test error handling for invalid paths."""
    exporter = NewFormatExporter()

    result = exporter.export_collection(
        tracks=[sample_track],
        playlist_structure=[],
        output_path=Path("/invalid/path")
    )

    assert result['status'] == 'error'
```

**Run tests:**

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_new_exporter.py

# Run with coverage
pytest --cov=exporter --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Integration Testing

```python
# tests/test_integration.py

def test_full_conversion_workflow(tmp_path):
    """Test complete NML to export workflow."""
    from parser.bsm_nml_parser import create_traktor_parser
    from exporter.new_format_exporter import NewFormatExporter
    from utils.playlist import PlaylistManager

    # Parse NML
    parser = create_traktor_parser("tests/fixtures/collection.nml")
    assert parser.parse_xml()

    # Get structure
    structure = parser.get_playlists_with_structure()
    assert len(structure) > 0

    # Collect tracks
    tracks = PlaylistManager.collect_all_tracks(structure)
    assert len(tracks) > 0

    # Export
    exporter = NewFormatExporter()
    result = exporter.export_collection(
        tracks=tracks,
        playlist_structure=structure,
        output_path=tmp_path
    )

    assert result['status'] == 'success'
```

---

## Debugging

### Logging

**Enable debug logging:**

```python
# In main.py

def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.DEBUG,  # Changed from INFO
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('traktor_bridge_debug.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
```

**Add debug statements:**

```python
# In your code
self.logger.debug(f"Processing track: {track.title}")
self.logger.debug(f"Export settings: {settings}")
```

### Developer Tools

#### PDB Reader

Inspect binary PDB files:

```bash
python tools/pdb_reader.py /path/to/export.pdb
```

**Output:**
```
Page 0: TRACKS (48 rows)
Page 1: ARTISTS (120 rows)
Page 2: ALBUMS (85 rows)
...
```

#### CDJ USB Validator

Validate CDJ USB structure:

```bash
python tools/cdj_usb_validator.py /media/usb
```

**Output:**
```
✓ PIONEER directory exists
✓ USBANLZ directory exists
✓ export.pdb found
✓ DeviceSQL.edb found
✓ 150 ANLZ files found
✓ USB structure valid
```

#### NML Inspector

Inspect NML files:

```bash
python tools/nml_inspector.py /path/to/collection.nml
```

**Output:**
```
NML Version: 19
Encoding: UTF-8
Total Entries: 5234
Total Playlists: 47
Total Folders: 12
```

### Debugging UI Issues

**Enable Qt debugging:**

```python
# In main.py

import os
os.environ['QT_DEBUG_PLUGINS'] = '1'

app = QApplication(sys.argv)
```

**Use Qt Designer:**

```bash
# Open .ui files in Qt Designer
designer ui/main_window.ui
```

---

## Contributing

### Contribution Workflow

1. **Fork Repository**

```bash
# Fork on GitHub
# Clone your fork
git clone https://github.com/your-username/Traktor-Bridge-2.git
cd Traktor-Bridge-2
git remote add upstream https://github.com/bsm3d/Traktor-Bridge-2.git
```

2. **Create Feature Branch**

```bash
git checkout -b feature/your-feature-name
```

3. **Make Changes**

- Write code
- Add tests
- Update documentation

4. **Run Tests**

```bash
# Run tests
pytest

# Run linter
pylint exporter/ parser/ utils/

# Run type checker
mypy exporter/ parser/ utils/
```

5. **Commit Changes**

```bash
git add .
git commit -m "Add feature: description

- Detail 1
- Detail 2
- Detail 3"
```

6. **Push to Fork**

```bash
git push origin feature/your-feature-name
```

7. **Create Pull Request**

- Go to GitHub
- Click "New Pull Request"
- Select your branch
- Fill in description
- Submit

### Pull Request Guidelines

**Title Format:**
```
[Feature] Add new export format
[Fix] Correct CDJ path hashing
[Docs] Update API documentation
[Refactor] Improve parser performance
```

**Description Template:**
```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Changes
- Change 1
- Change 2
- Change 3

## Testing
How was this tested?

## Screenshots (if applicable)
![Screenshot](url)

## Checklist
- [ ] Tests pass
- [ ] Linter passes
- [ ] Documentation updated
- [ ] CHANGELOG updated
```

---

## Coding Standards

### PEP 8 Compliance

- **Line Length**: 100 characters
- **Indentation**: 4 spaces
- **Naming**:
  - Classes: `PascalCase`
  - Functions: `snake_case`
  - Constants: `UPPER_CASE`
  - Private: `_leading_underscore`

### Documentation

**Module Docstrings:**

```python
"""
Module Name - Brief Description

Detailed description of module functionality.

Classes:
    ClassName: Brief description
    AnotherClass: Brief description

Functions:
    function_name: Brief description
"""
```

**Class Docstrings:**

```python
class ExampleClass:
    """
    Brief description of class.

    Detailed description with multiple paragraphs if needed.

    Attributes:
        attribute1 (type): Description
        attribute2 (type): Description

    Example:
        >>> obj = ExampleClass()
        >>> obj.method()
        'result'
    """
```

**Function Docstrings:**

```python
def example_function(param1: str, param2: int) -> bool:
    """
    Brief description of function.

    Detailed description with multiple paragraphs if needed.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is invalid
        TypeError: When param2 is not an integer

    Example:
        >>> example_function("test", 42)
        True
    """
```

### Type Hints

```python
from typing import List, Dict, Optional, Any, Tuple

def process_tracks(
    tracks: List[Track],
    output_path: Path,
    options: Optional[Dict[str, Any]] = None
) -> Tuple[int, List[str]]:
    """Process tracks with type hints."""
    pass
```

### Error Handling

```python
def safe_operation():
    """Proper error handling."""
    try:
        # Try operation
        result = risky_operation()
    except SpecificError as e:
        # Handle specific error
        logger.error(f"Specific error: {e}")
        raise
    except Exception as e:
        # Handle general error
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
    finally:
        # Cleanup
        cleanup_resources()
```

---

## Release Process

### Version Numbering

**Semantic Versioning**: MAJOR.MINOR.PATCH

- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes

### Release Checklist

1. **Update Version**

```python
# In main.py
class AppConfig:
    VERSION = "2.1.0"
```

2. **Update CHANGELOG**

```markdown
# Changelog

## [2.1.0] - 2024-11-17

### Added
- New export format support
- Enhanced key translation

### Fixed
- CDJ path hashing bug
- Memory leak in audio player

### Changed
- Improved performance for large collections
```

3. **Run Tests**

```bash
pytest --cov=. --cov-report=html
pylint exporter/ parser/ utils/
mypy exporter/ parser/ utils/
```

4. **Build Distribution**

```bash
# Create distribution
python setup.py sdist bdist_wheel

# Test installation
pip install dist/traktor_bridge-2.1.0-py3-none-any.whl
```

5. **Tag Release**

```bash
git tag -a v2.1.0 -m "Release version 2.1.0"
git push origin v2.1.0
```

6. **Create GitHub Release**

- Go to GitHub Releases
- Create new release
- Add release notes
- Upload distribution files

---

## Advanced Topics

### Custom Parser Extensions

```python
# Extend TraktorNMLParser

class CustomNMLParser(TraktorNMLParser):
    """Custom parser with extensions."""

    def parse_custom_field(self, entry_elem):
        """Parse custom field from NML."""
        custom_value = entry_elem.get('CUSTOM_FIELD', '')
        # Process custom value
        return custom_value
```

### Plugin System (Future)

```python
# Plugin interface

class ExporterPlugin:
    """Base class for exporter plugins."""

    def get_name(self) -> str:
        """Get plugin name."""
        raise NotImplementedError

    def export(self, tracks, structure, output_path, **options):
        """Export implementation."""
        raise NotImplementedError


# Plugin registration
def register_plugin(plugin_class):
    """Register new exporter plugin."""
    PLUGIN_REGISTRY[plugin_class.get_name()] = plugin_class
```

---

**Document Version**: 1.0
**Last Updated**: November 2024
**Author**: Benoit (BSM) Saint-Moulin

For questions or support, please open an issue on GitHub.
