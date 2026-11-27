"""Modal dialogs: removal confirmation and about."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.correlator import RowItem
from core.efi_paths import format_size
from core.version import APP_NAME, REPO_URL, __version__
from ui.theme import COLORS, mono_font_family
from ui.widgets import CheckRow


def _mono(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(_monospace_font())
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _monospace_font():
    from PySide6.QtGui import QFont

    font = QFont(mono_font_family())
    font.setPointSize(9)
    return font


class SectionHeader(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text.upper())
        self.setObjectName("SectionTitle")


class ConfirmDialog(QDialog):
    """Shows exactly what will be deleted before anything happens."""

    def __init__(
        self,
        rows: Sequence[RowItem],
        all_rows: Sequence[RowItem],
        backup_dir: Path,
        dry_run: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.rows = list(rows)
        self.all_rows = list(all_rows)
        self.backup_dir = backup_dir
        self.dry_run = dry_run
        self.setWindowTitle("Dry run preview" if dry_run else "Confirm removal")
        self.setModal(True)
        self.resize(680, 560)
        self.setMinimumWidth(640)

        entry_rows = [row for row in self.rows if row.identifier and row.deletable]
        folder_paths: list[Path] = []
        seen: set[str] = set()
        for row in self.rows:
            if row.folder_path is None or not row.deletable:
                continue
            key = str(row.folder_path).casefold()
            if key not in seen:
                seen.add(key)
                folder_paths.append(row.folder_path)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(12)

        title = QLabel("Dry run preview" if dry_run else "Remove selected items?")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Nothing will be changed. The exact commands are written to the console."
            if dry_run
            else "Windows boot entries and EFI folders will be permanently removed. "
            "A backup is created first."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 4, 6, 4)
        body_layout.setSpacing(12)

        body_layout.addWidget(SectionHeader(f"UEFI boot entries · {len(entry_rows)}"))
        if entry_rows:
            for row in entry_rows:
                body_layout.addWidget(self._entry_widget(row))
        else:
            body_layout.addWidget(self._muted("No boot entries selected."))

        body_layout.addWidget(SectionHeader(f"ESP folders · {len(folder_paths)}"))
        if folder_paths:
            for path in folder_paths:
                size = next(
                    (
                        row.folder_size
                        for row in self.rows
                        if row.folder_path
                        and str(row.folder_path).casefold() == str(path).casefold()
                    ),
                    None,
                )
                body_layout.addWidget(self._line(str(path), f"{format_size(size)} on disk"))
        else:
            body_layout.addWidget(self._muted("No folders selected."))

        shared = self._shared_folder_warnings(folder_paths)
        if shared:
            body_layout.addWidget(SectionHeader("Heads up"))
            for warning in shared:
                body_layout.addWidget(self._muted(warning, warning=True))

        body_layout.addWidget(SectionHeader("Backup location"))
        if dry_run:
            body_layout.addWidget(self._line(str(backup_dir), "would be created"))
        else:
            body_layout.addWidget(self._line(str(backup_dir), "BCD export + folder copies"))

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.delete_folders_checkbox = CheckRow("Also delete the EFI folder(s) listed above")
        self.delete_folders_checkbox.setChecked(bool(folder_paths))
        self.delete_folders_checkbox.setEnabled(bool(folder_paths))
        outer.addWidget(self.delete_folders_checkbox)

        self.confirm_checkbox = CheckRow(
            "I understand this permanently modifies my UEFI boot configuration"
        )
        if not dry_run:
            outer.addWidget(self.confirm_checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        self.confirm_button = QPushButton("Run dry run" if dry_run else "Delete permanently")
        if not dry_run:
            self.confirm_button.setObjectName("Danger")
            self.confirm_button.setEnabled(False)
            self.confirm_checkbox.toggled.connect(self.confirm_button.setEnabled)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        outer.addLayout(buttons)

        self.confirm_button.setDefault(not dry_run)
        cancel.setDefault(dry_run)

    @property
    def delete_folders(self) -> bool:
        return self.delete_folders_checkbox.isChecked()

    def _entry_widget(self, row: RowItem) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(row.title)
        name.setStyleSheet("font-weight: 600;")
        top.addWidget(name)
        top.addStretch(1)
        identifier = QLabel(row.identifier)
        identifier.setFont(_monospace_font())
        identifier.setStyleSheet(f"color: {COLORS['accent']};")
        top.addWidget(identifier)
        layout.addLayout(top)

        path = QLabel(row.efi_path or "(no EFI path)")
        path.setFont(_monospace_font())
        path.setStyleSheet(f"color: {COLORS['text_muted']};")
        path.setWordWrap(True)
        layout.addWidget(path)
        if row.folder_path:
            folder = QLabel(f"Folder: {row.folder_path}")
            folder.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
            folder.setWordWrap(True)
            layout.addWidget(folder)
        return card

    @staticmethod
    def _muted(text: str, warning: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {COLORS['warning'] if warning else COLORS['text_dim']};")
        return label

    @staticmethod
    def _line(primary: str, secondary: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        first = QLabel(primary)
        first.setFont(_monospace_font())
        first.setWordWrap(True)
        layout.addWidget(first)
        second = QLabel(secondary)
        second.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addWidget(second)
        return widget

    def _shared_folder_warnings(self, folder_paths: Sequence[Path]) -> list[str]:
        selected_keys = {row.key for row in self.rows}
        warnings: list[str] = []
        for folder in folder_paths:
            owners = [
                row.title
                for row in self.all_rows
                if row.key not in selected_keys
                and row.identifier
                and row.folder_path
                and str(row.folder_path).casefold() == str(folder).casefold()
            ]
            if owners:
                warnings.append(f"{folder} is still used by {', '.join(owners)} and will be kept.")
        return warnings


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.setFixedWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        version = QLabel(f"Version {__version__} · MIT License")
        version.setObjectName("Muted")
        layout.addWidget(version)

        description = QLabel(
            "A small Windows 11 utility that lists your firmware boot entries next to "
            "the folders on the EFI System Partition, then removes the stale ones in "
            "one click — with a backup, a dry-run mode and hard-locked system entries."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        safety = QLabel(
            "<b>Hard-locked:</b> {bootmgr}, {fwbootmgr}, {current}, {default}, {memdiag}, "
            "the active Windows Boot Manager, <code>\\EFI\\Microsoft</code> and "
            "<code>\\EFI\\Boot</code>."
        )
        safety.setWordWrap(True)
        safety.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(safety)

        link = QLabel(f'<a style="color:{COLORS["accent"]}" href="{REPO_URL}">{REPO_URL}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        layout.addWidget(link)

        disclaimer = QLabel(
            "Provided as-is, without warranty. A backup is created before every change, "
            "and the backup folder path is shown before you confirm."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setObjectName("Dim")
        layout.addWidget(disclaimer)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
