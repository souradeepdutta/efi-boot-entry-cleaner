"""Dark Windows 11 inspired theme (palette + Qt stylesheet)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#16161a",
    "bg_alt": "#131317",
    "surface": "#1e1e24",
    "surface_alt": "#23232b",
    "surface_high": "#2a2a33",
    "border": "#2f2f39",
    "border_strong": "#3d3d49",
    "text": "#eef1f6",
    "text_muted": "#98a0ad",
    "text_dim": "#6f7683",
    "accent": "#4cc2ff",
    "accent_soft": "rgba(76, 194, 255, 0.14)",
    "danger": "#e8384f",
    "danger_hover": "#ff4a60",
    "success": "#38d39f",
    "warning": "#f5a524",
    "purple": "#b98cff",
    "protected": "#8b93a1",
}

STATUS_COLORS = {
    "Linked": ("#38d39f", "rgba(56, 211, 159, 0.14)"),
    "Orphaned Entry": ("#f5a524", "rgba(245, 165, 36, 0.14)"),
    "Orphaned Folder": ("#b98cff", "rgba(185, 140, 255, 0.14)"),
    "Protected": ("#9aa2b1", "rgba(154, 162, 177, 0.13)"),
}

LOG_COLORS = {
    "info": "#c9d1dc",
    "cmd": "#4cc2ff",
    "out": "#9aa4b2",
    "err": "#ff6b6b",
    "ok": "#38d39f",
    "warn": "#f5a524",
    "dim": "#7d8492",
}


def preferred_font_family() -> str:
    available = set(QFontDatabase.families())
    for family in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"):
        if family in available:
            return family
    return QApplication.font().family()


def mono_font_family() -> str:
    available = set(QFontDatabase.families())
    for family in ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New"):
        if family in available:
            return family
    return "monospace"


def apply_theme(app: QApplication) -> None:
    """Apply palette, base font and stylesheet to the application."""
    family = preferred_font_family()
    font = QFont(family, 10)
    if font.pointSizeF() < 10:
        font.setPointSizeF(10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#0b1116"))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["surface_high"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(COLORS["text_dim"]))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(family))


def build_stylesheet(family: str) -> str:
    c = COLORS
    return f"""
    QWidget {{
        color: {c["text"]};
        font-family: "{family}";
        font-size: 13px;
    }}

    QMainWindow, QDialog {{
        background-color: {c["bg"]};
    }}

    QFrame#Header {{
        background: transparent;
    }}
    QLabel#AppTitle {{
        font-size: 23px;
        font-weight: 700;
        color: {c["text"]};
    }}
    QLabel#AppSubtitle {{
        font-size: 12px;
        color: {c["text_muted"]};
    }}
    QLabel#SectionTitle {{
        font-size: 11px;
        font-weight: 700;
        color: {c["text_dim"]};
    }}
    QLabel#Muted {{
        color: {c["text_muted"]};
    }}
    QLabel#Dim {{
        color: {c["text_dim"]};
        font-size: 12px;
    }}
    QLabel#Pill {{
        background-color: {c["surface_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 11px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 600;
        color: {c["text_muted"]};
    }}

    QFrame#Card, QFrame#Toolbar {{
        background-color: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    QFrame#StatChip {{
        background-color: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}
    QFrame#Notice {{
        background-color: rgba(245, 165, 36, 0.10);
        border: 1px solid rgba(245, 165, 36, 0.45);
        border-radius: 9px;
    }}
    QFrame#ErrorNotice {{
        background-color: rgba(232, 56, 79, 0.10);
        border: 1px solid rgba(232, 56, 79, 0.45);
        border-radius: 9px;
    }}

    QPushButton {{
        background-color: {c["surface_alt"]};
        border: 1px solid {c["border_strong"]};
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 600;
        color: {c["text"]};
    }}
    QPushButton:hover {{
        background-color: {c["surface_high"]};
        border-color: #4a4a58;
    }}
    QPushButton:pressed {{
        background-color: #202027;
    }}
    QPushButton:disabled {{
        background-color: #1d1d23;
        border-color: #2a2a32;
        color: #626a77;
    }}
    QPushButton#Danger {{
        background-color: {c["danger"]};
        border: 1px solid #ff5567;
        color: #ffffff;
        padding: 9px 18px;
    }}
    QPushButton#Danger:hover {{
        background-color: {c["danger_hover"]};
    }}
    QPushButton#Danger:disabled {{
        background-color: #3a2026;
        border-color: #4a2730;
        color: #8c626b;
    }}
    QPushButton#Danger[dryrun="true"] {{
        background-color: {c["accent"]};
        border: 1px solid #8fe2ff;
        color: #06121a;
    }}
    QPushButton#Danger[dryrun="true"]:hover {{
        background-color: #6fd6ff;
    }}
    QPushButton#Danger[dryrun="true"]:disabled {{
        background-color: #1f3a47;
        border-color: #2a4a5a;
        color: #6b8b9b;
    }}
    QPushButton#Ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {c["text_muted"]};
        padding: 4px 8px;
        font-weight: 500;
    }}
    QPushButton#Ghost:hover {{
        background-color: rgba(255, 255, 255, 0.05);
        color: {c["text"]};
    }}
    QToolButton {{
        background: transparent;
        border: none;
        color: {c["text_muted"]};
        padding: 4px 6px;
        font-weight: 600;
    }}
    QToolButton:hover {{
        color: {c["text"]};
    }}

    QTableWidget {{
        background-color: {c["surface"]};
        alternate-background-color: #202027;
        border: 1px solid {c["border"]};
        border-radius: 12px;
        gridline-color: transparent;
        selection-background-color: rgba(76, 194, 255, 0.10);
        selection-color: {c["text"]};
    }}
    QTableWidget::item {{
        border: none;
        padding: 4px 10px;
    }}
    QTableWidget::item:selected {{
        background-color: rgba(76, 194, 255, 0.10);
        color: {c["text"]};
    }}
    QHeaderView::section {{
        background-color: #191920;
        color: {c["text_dim"]};
        padding: 10px 10px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-size: 11px;
        font-weight: 700;
    }}
    QTableCornerButton::section {{
        background-color: #191920;
        border: none;
    }}

    QPlainTextEdit#Console {{
        background-color: {c["bg_alt"]};
        border: 1px solid #26262e;
        border-radius: 8px;
        color: #c8cedb;
        padding: 8px;
        selection-background-color: #2c4c5e;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #3a3a45;
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #4a4a57;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: #3a3a45;
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    QCheckBox {{
        color: {c["text"]};
        spacing: 8px;
    }}

    QToolTip {{
        background-color: {c["surface_high"]};
        color: {c["text"]};
        border: 1px solid {c["border_strong"]};
        padding: 6px;
        border-radius: 6px;
    }}

    QMessageBox {{
        background-color: {c["surface"]};
    }}
    """
