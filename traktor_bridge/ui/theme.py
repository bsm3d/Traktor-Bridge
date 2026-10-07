# Benoit Saint-Moulin
# Traktor Bridge : colours and the one stylesheet

from pathlib import Path

ICONS = str(Path(__file__).resolve().parent / "icons").replace("\\", "/")
BG_DARK = "#212529"
BG_MED = "#343a40"
BG_LIGHT = "#495057"
FG = "#f8f9fa"
FG_MUTED = "#adb5bd"
ACCENT = "#00b4d8"
HOVER = "#0096c7"
RED = "#dc3545"
YELLOW = "#ffc107"
GREEN = "#4caf50"

# CDJ hot cue pads A-H
CUE_COLORS = ["#28e214", "#305aff", "#ff127b", "#ff7f00", "#30d2ff", "#aa72ff", "#e0641b", "#10b176"]
LOOP_COLOR = "#ff8c00"
MEMORY_COLOR = "#ff3b3b"

STYLE = f"""
QWidget {{ background: {BG_DARK}; color: {FG}; font-size: 10pt; }}
QGroupBox {{ border: 1px solid {BG_LIGHT}; border-radius: 4px; margin-top: 10px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {FG_MUTED}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {BG_MED}; border: 1px solid {BG_LIGHT}; border-radius: 3px; padding: 3px; }}
QTreeWidget, QTableWidget, QTableView {{ background: {BG_MED}; alternate-background-color: #3b4148;
    border: 1px solid {BG_LIGHT}; selection-background-color: {ACCENT}; }}
QHeaderView::section {{ background: {BG_LIGHT}; color: {FG}; border: none; padding: 4px; }}
QPushButton {{ background: {BG_LIGHT}; border: none; border-radius: 3px; padding: 5px 12px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:disabled {{ color: {FG_MUTED}; background: {BG_MED}; }}
QPushButton#go {{ background: {ACCENT}; font-weight: bold; padding: 8px 20px; }}
QPushButton#go:hover {{ background: {HOVER}; }}
QProgressBar {{ background: {BG_MED}; border: none; border-radius: 3px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {ACCENT}; }}
QTabBar::tab {{ background: {BG_MED}; padding: 6px 14px; }}
QTabBar::tab:selected {{ background: {BG_LIGHT}; }}
QTabWidget::pane {{ border: 1px solid {FG}; }}
QToolTip {{ background: {BG_MED}; color: {FG}; border: 1px solid {BG_LIGHT}; }}
QScrollBar:horizontal {{
    background: {BG_DARK}; border: none; height: 14px; margin: 0 16px; }}
QScrollBar:vertical {{
    background: {BG_DARK}; border: none; width: 14px; margin: 16px 0; }}
QScrollBar::handle:horizontal {{
    background: {ACCENT}; min-width: 28px; margin: 3px 0; border-radius: 4px; }}
QScrollBar::handle:vertical {{
    background: {ACCENT}; min-height: 28px; margin: 0 3px; border-radius: 4px; }}
QScrollBar::handle:hover, QScrollBar::handle:pressed {{ background: {HOVER}; }}
QScrollBar::handle:disabled {{ background: {BG_LIGHT}; }}
QScrollBar::sub-line:horizontal {{
    subcontrol-origin: margin; subcontrol-position: left;
    width: 16px; border: none; background: {BG_DARK}; }}
QScrollBar::add-line:horizontal {{
    subcontrol-origin: margin; subcontrol-position: right;
    width: 16px; border: none; background: {BG_DARK}; }}
QScrollBar::sub-line:vertical {{
    subcontrol-origin: margin; subcontrol-position: top;
    height: 16px; border: none; background: {BG_DARK}; }}
QScrollBar::add-line:vertical {{
    subcontrol-origin: margin; subcontrol-position: bottom;
    height: 16px; border: none; background: {BG_DARK}; }}
QScrollBar::sub-line:hover, QScrollBar::add-line:hover {{ background: {BG_MED}; }}
QScrollBar::left-arrow {{ image: url("{ICONS}/scroll-left.svg"); width: 6px; height: 10px; }}
QScrollBar::right-arrow {{ image: url("{ICONS}/scroll-right.svg"); width: 6px; height: 10px; }}
QScrollBar::up-arrow {{ image: url("{ICONS}/spin-up.svg"); width: 10px; height: 6px; }}
QScrollBar::down-arrow {{ image: url("{ICONS}/spin-down.svg"); width: 10px; height: 6px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSlider::groove:horizontal {{
    background: {BG_LIGHT}; height: 4px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: {ACCENT}; border-radius: 2px; }}
QSlider::add-page:horizontal {{
    background: {BG_LIGHT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; border: 2px solid {FG}; width: 10px;
    margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {HOVER}; }}
QSlider::handle:horizontal:disabled {{ background: {FG_MUTED}; border-color: {BG_LIGHT}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border-left: 1px solid {BG_LIGHT}; background: {BG_MED}; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border-left: 1px solid {BG_LIGHT}; background: {BG_MED}; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {BG_LIGHT}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{ICONS}/spin-up.svg"); width: 10px; height: 6px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{ICONS}/spin-down.svg"); width: 10px; height: 6px; }}
"""
