# Benoit Saint-Moulin
# Traktor Bridge : colours and the one stylesheet

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
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    background: {BG_MED}; border: 1px solid {BG_LIGHT}; border-radius: 3px; padding: 3px; }}
QTreeWidget, QTableWidget {{ background: {BG_MED}; alternate-background-color: #3b4148;
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
QToolTip {{ background: {BG_MED}; color: {FG}; border: 1px solid {BG_LIGHT}; }}
"""
