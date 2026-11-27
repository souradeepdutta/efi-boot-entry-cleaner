"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.controller import AppController, RemovalReport
from core.correlator import RowItem, Status, count_by_status
from core.efi_paths import format_size
from core.privileges import is_admin
from core.resources import app_icon_path
from core.version import APP_NAME, __version__
from ui.demo import DemoController
from ui.dialogs import AboutDialog, ConfirmDialog
from ui.theme import COLORS, mono_font_family
from ui.widgets import (
    CheckboxDelegate,
    EmptyState,
    LogPanel,
    StatChip,
    StatusBadgeDelegate,
    ToggleSwitch,
)

STATUS_LABELS = {
    Status.LINKED: "Linked",
    Status.ORPHANED_ENTRY: "Orphaned entries",
    Status.ORPHANED_FOLDER: "Orphaned folders",
    Status.PROTECTED: "Protected",
}


class RemovalWorker(QThread):
    """Runs the backup + deletion sequence off the UI thread."""

    report_ready = Signal(object)

    def __init__(
        self,
        controller,
        selected: list[RowItem],
        all_rows: list[RowItem],
        dry_run: bool,
        delete_folders: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.selected = selected
        self.all_rows = all_rows
        self.dry_run = dry_run
        self.delete_folders = delete_folders

    def run(self) -> None:
        try:
            report = self.controller.remove(
                self.selected,
                self.all_rows,
                dry_run=self.dry_run,
                delete_folders=self.delete_folders,
            )
        except Exception as exc:
            report = RemovalReport(
                dry_run=self.dry_run,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        self.report_ready.emit(report)


class MainWindow(QMainWindow):
    log_signal = Signal(str, str)

    def __init__(self, controller=None, demo: bool = False) -> None:
        super().__init__()
        self.demo = demo
        if controller is None:
            controller = (
                DemoController(self.log_signal.emit)
                if demo
                else AppController(self.log_signal.emit)
            )
        self.controller = controller

        self.rows: list[RowItem] = []
        self._rows_by_key: dict[str, RowItem] = {}
        self._populating = False
        self._busy = False
        self._scan_ok = False
        self._worker: RemovalWorker | None = None
        self.dry_run = False

        self.mono_font = QFont(mono_font_family())
        self.mono_font.setPointSizeF(9.0)

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setMinimumSize(1000, 640)
        self.resize(1200, 840)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self.log_signal.connect(self._append_log)
        self._install_shortcuts()
        self._update_identity()
        self._update_stats([])
        self._update_selection()

        QTimer.singleShot(150, self.refresh)

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addLayout(self._build_stats())

        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        self.dry_banner = self._build_dry_banner()
        layout.addWidget(self.dry_banner)

        self.error_banner = self._build_error_banner()
        layout.addWidget(self.error_banner)

        self.table = self._build_table()
        self.empty_state = EmptyState()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty_state)
        layout.addWidget(self.stack, 1)

        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel)

        layout.addLayout(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        row = QHBoxLayout(header)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(14)

        icon_path = app_icon_path()
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setPixmap(QIcon(str(icon_path)).pixmap(44, 44))
            icon_label.setFixedSize(44, 44)
            row.addWidget(icon_label)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        titles.addWidget(title)
        subtitle = QLabel(
            "Review, back up, and remove stale UEFI boot entries — and the EFI folders they left behind."
        )
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        self.identity_pill = QLabel("●  ADMINISTRATOR")
        self.identity_pill.setObjectName("Pill")
        row.addWidget(self.identity_pill)

        self.esp_pill = QLabel("ESP  ·  not mounted")
        self.esp_pill.setObjectName("Pill")
        row.addWidget(self.esp_pill)

        about = QPushButton("?")
        about.setObjectName("Ghost")
        about.setFixedSize(30, 30)
        about.setCursor(Qt.PointingHandCursor)
        about.setToolTip("About and safety notes")
        about.clicked.connect(self._show_about)
        row.addWidget(about)
        return header

    def _build_stats(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.chips = {
            Status.LINKED: StatChip(STATUS_LABELS[Status.LINKED], COLORS["success"]),
            Status.ORPHANED_ENTRY: StatChip(
                STATUS_LABELS[Status.ORPHANED_ENTRY], COLORS["warning"]
            ),
            Status.ORPHANED_FOLDER: StatChip(
                STATUS_LABELS[Status.ORPHANED_FOLDER], COLORS["purple"]
            ),
            Status.PROTECTED: StatChip(STATUS_LABELS[Status.PROTECTED], COLORS["protected"]),
        }
        for chip in self.chips.values():
            row.addWidget(chip)
        return row

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        self.refresh_button = QPushButton("⟳   Refresh")
        self.refresh_button.setToolTip("Re-scan the firmware boot entries and the ESP (F5)")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet(f"color: {COLORS['border']};")
        divider.setFixedHeight(24)
        row.addWidget(divider)

        dry_label = QLabel("Dry-run mode")
        dry_label.setObjectName("Muted")
        row.addWidget(dry_label)

        self.dry_switch = ToggleSwitch()
        self.dry_switch.setToolTip(
            "When enabled, commands are logged but nothing is deleted on disk or in the BCD store."
        )
        self.dry_switch.toggled.connect(self._on_dry_run_toggled)
        row.addWidget(self.dry_switch)

        self.open_backups_button = QPushButton("Open Backups")
        self.open_backups_button.setToolTip("Open %LOCALAPPDATA%\\EFIBootCleaner\\backups")
        self.open_backups_button.setCursor(Qt.PointingHandCursor)
        self.open_backups_button.clicked.connect(self._open_backups)
        row.addWidget(self.open_backups_button)

        row.addStretch(1)

        self.selection_label = QLabel("No items selected")
        self.selection_label.setObjectName("Muted")
        row.addWidget(self.selection_label)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.setObjectName("Danger")
        self.remove_button.setProperty("dryrun", False)
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setEnabled(False)
        self.remove_button.setToolTip("Remove the checked boot entries and EFI folders")
        self.remove_button.clicked.connect(self._start_removal)
        row.addWidget(self.remove_button)
        return bar

    def _build_dry_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("Notice")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(8)
        icon = QLabel("⚠")
        icon.setStyleSheet(f"color: {COLORS['warning']}; font-size: 15px;")
        layout.addWidget(icon)
        text = QLabel(
            "Dry-run mode is on — nothing will be deleted. The exact commands are written to the console."
        )
        text.setStyleSheet(f"color: {COLORS['warning']};")
        text.setWordWrap(True)
        layout.addWidget(text, 1)
        off = QPushButton("Turn off")
        off.setObjectName("Ghost")
        off.setCursor(Qt.PointingHandCursor)
        off.clicked.connect(lambda: self.dry_switch.setChecked(False))
        layout.addWidget(off)
        banner.setVisible(False)
        return banner

    def _build_error_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("ErrorNotice")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(8)
        icon = QLabel("✕")
        icon.setStyleSheet(f"color: {COLORS['danger']}; font-size: 14px;")
        layout.addWidget(icon)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label, 1)
        retry = QPushButton("Retry")
        retry.setObjectName("Ghost")
        retry.setCursor(Qt.PointingHandCursor)
        retry.clicked.connect(self.refresh)
        layout.addWidget(retry)
        banner.setVisible(False)
        return banner

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ["", "STATUS", "DESCRIPTION / FOLDER", "BCD IDENTIFIER", "EFI PATH", "SIZE"]
        )
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setWordWrap(False)
        table.setSortingEnabled(False)
        table.setFocusPolicy(Qt.StrongFocus)
        table.verticalHeader().setDefaultSectionSize(46)
        table.setItemDelegateForColumn(0, CheckboxDelegate(table))
        table.setItemDelegateForColumn(1, StatusBadgeDelegate(table))
        table.itemChanged.connect(self._on_item_changed)

        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        table.setColumnWidth(0, 48)
        table.setColumnWidth(1, 152)
        table.setColumnWidth(3, 230)
        table.setColumnWidth(5, 104)
        return table

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        self.select_all_button = QPushButton("Select all removable")
        self.select_all_button.setObjectName("Ghost")
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self._select_all_removable)
        row.addWidget(self.select_all_button)

        self.clear_button = QPushButton("Clear selection")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear_selection)
        row.addWidget(self.clear_button)

        row.addStretch(1)

        self.backups_label = QLabel("Backups: %LOCALAPPDATA%\\EFIBootCleaner\\backups")
        self.backups_label.setObjectName("Dim")
        row.addWidget(self.backups_label)

        row.addSpacing(12)

        version = QLabel(f"v{__version__}  ·  MIT")
        version.setObjectName("Dim")
        row.addWidget(version)
        return row

    def _install_shortcuts(self) -> None:
        shortcuts = (
            (QKeySequence("F5"), self.refresh),
            (QKeySequence("Ctrl+L"), self.log_panel.toggle),
            (QKeySequence("Delete"), self._start_removal),
            (QKeySequence("Ctrl+Q"), self.close),
        )
        for sequence, slot in shortcuts:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(slot)

    def _update_identity(self) -> None:
        if self.demo:
            self.identity_pill.setText("●  DEMO MODE")
            self.identity_pill.setStyleSheet(f"color: {COLORS['purple']};")
        elif is_admin():
            self.identity_pill.setText("●  ADMINISTRATOR")
            self.identity_pill.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self.identity_pill.setText("●  NOT ELEVATED")
            self.identity_pill.setStyleSheet(f"color: {COLORS['warning']};")

        from core.controller import backups_root

        self.backups_label.setToolTip(str(backups_root()))

    # --------------------------------------------------------------- scanning
    def refresh(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._scan_ok = False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        self._append_log("dim", "Refreshing boot entries and EFI folders …")
        try:
            result = self.controller.scan()
        except Exception as exc:
            self._handle_scan_error(str(exc))
        else:
            self._scan_ok = True
            self._set_error(None)
            self._populate(result)
            if result.drive:
                self.esp_pill.setText(f"ESP  ·  {result.drive}:")
            if result.already_mounted:
                self._append_log(
                    "dim",
                    "The ESP was already mounted; it will be left mounted when the app closes.",
                )
        finally:
            QApplication.restoreOverrideCursor()
            self._set_busy(False)

    def _handle_scan_error(self, message: str) -> None:
        self.rows = []
        self._rows_by_key = {}
        self._populating = True
        try:
            self.table.setRowCount(0)
        finally:
            self._populating = False
        self.stack.setCurrentWidget(self.empty_state)
        self.empty_state.set_message(
            "Could not read the boot data",
            "Run the app as Administrator, then press Refresh. Details are in the console.",
            icon="!",
            color=COLORS["danger"],
        )
        self.esp_pill.setText("ESP  ·  unavailable")
        self._set_error(message)
        self._update_stats([])
        self._update_selection()
        self.log_panel.set_expanded(True)
        self._append_log("err", message)

    def _populate(self, result) -> None:
        self.rows = list(result.rows)
        self._rows_by_key = {row.key: row for row in self.rows}
        self._populating = True
        try:
            self.table.setRowCount(0)
            for row in self.rows:
                self._append_row(row)
        finally:
            self._populating = False

        self.stack.setCurrentWidget(self.table if self.rows else self.empty_state)
        if not self.rows:
            self.empty_state.set_message(
                "Nothing to clean up",
                "No stale UEFI boot entries or unreferenced EFI folders were found.",
            )
        self._update_stats(self.rows)
        self._update_selection()

    def _append_row(self, row: RowItem) -> None:
        index = self.table.rowCount()
        self.table.insertRow(index)

        check = QTableWidgetItem()
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if row.deletable:
            flags |= Qt.ItemIsUserCheckable
        check.setFlags(flags)
        check.setCheckState(Qt.Unchecked)
        check.setData(Qt.UserRole, row.key)
        check.setToolTip(
            "Select this item for removal"
            if row.deletable
            else f"Protected — {row.protection_reason or 'system item'}"
        )
        self.table.setItem(index, 0, check)

        status = QTableWidgetItem("")
        status.setData(Qt.UserRole, row.status.value)
        status.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        status.setToolTip(row.protection_reason or row.note or row.status.value)
        self.table.setItem(index, 1, status)

        title = QTableWidgetItem(row.title)
        title.setToolTip(self._tooltip(row))
        self.table.setItem(index, 2, title)

        identifier = QTableWidgetItem(row.identifier or "—")
        identifier.setFont(self.mono_font)
        identifier.setForeground(QColor(COLORS["accent"] if row.identifier else COLORS["text_dim"]))
        identifier.setToolTip(row.identifier or "No BCD entry")
        self.table.setItem(index, 3, identifier)

        path = QTableWidgetItem(row.efi_path or "—")
        path.setFont(self.mono_font)
        path.setToolTip(row.efi_path or "")
        self.table.setItem(index, 4, path)

        size = QTableWidgetItem(format_size(row.folder_size))
        size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size.setForeground(QColor(COLORS["text_muted"]))
        size.setToolTip(
            f"{row.folder_size:,} bytes" if row.folder_size is not None else "No folder"
        )
        self.table.setItem(index, 5, size)

        if not row.deletable:
            for column in (2, 4, 5):
                item = self.table.item(index, column)
                item.setForeground(QColor(COLORS["text_dim"]))
            title.setForeground(QColor("#8a92a0"))

    def _tooltip(self, row: RowItem) -> str:
        parts = [f"<b>{row.title}</b>", row.status.value]
        if row.identifier:
            parts.append(f"Identifier: {row.identifier}")
        if row.efi_path:
            parts.append(f"Path: {row.efi_path}")
        if row.folder_path:
            parts.append(f"ESP folder: {row.folder_path}")
        if row.folder_size is not None:
            parts.append(f"Size: {format_size(row.folder_size)}")
        if row.protection_reason:
            parts.append(f"<span style='color:{COLORS['warning']}'>{row.protection_reason}</span>")
        if row.note:
            parts.append(row.note)
        return "<br>".join(parts)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._populating or item.column() != 0:
            return
        self._update_selection()

    def selected_rows(self) -> list[RowItem]:
        selected: list[RowItem] = []
        for index in range(self.table.rowCount()):
            item = self.table.item(index, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            row = self._rows_by_key.get(str(item.data(Qt.UserRole)))
            if row is not None:
                selected.append(row)
        return selected

    # -------------------------------------------------------------- selection
    def _select_all_removable(self) -> None:
        self._populating = True
        try:
            for index in range(self.table.rowCount()):
                item = self.table.item(index, 0)
                if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(Qt.Checked)
        finally:
            self._populating = False
        self._update_selection()

    def _clear_selection(self) -> None:
        self._populating = True
        try:
            for index in range(self.table.rowCount()):
                item = self.table.item(index, 0)
                if item is not None:
                    item.setCheckState(Qt.Unchecked)
        finally:
            self._populating = False
        self._update_selection()

    def _update_selection(self) -> None:
        selected = self.selected_rows()
        count = len(selected)
        self.selection_label.setText(self.controller.describe_rows(selected))
        enabled = bool(count) and not self._busy and self._scan_ok
        self.remove_button.setEnabled(enabled)
        if self.dry_run:
            self.remove_button.setText(
                f"Simulate {count} Item{'s' if count != 1 else ''}" if count else "Dry-Run Remove"
            )
        else:
            self.remove_button.setText(
                f"Remove {count} Item{'s' if count != 1 else ''}" if count else "Remove Selected"
            )

    def _update_stats(self, rows: list[RowItem]) -> None:
        counts = count_by_status(rows)
        for status, chip in self.chips.items():
            chip.set_count(counts[status])

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in (
            self.refresh_button,
            self.open_backups_button,
            self.select_all_button,
            self.clear_button,
        ):
            button.setEnabled(not busy)
        self.dry_switch.setEnabled(not busy)
        self.error_banner.setVisible(bool(self.error_banner.property("hasError")) and not busy)
        self._update_selection()

    def _set_error(self, message: str | None) -> None:
        self.error_banner.setProperty("hasError", bool(message))
        if message:
            self.error_label.setText(message)
            self.error_banner.setVisible(True)
        else:
            self.error_label.setText("")
            self.error_banner.setVisible(False)

    # ----------------------------------------------------------------- actions
    def _on_dry_run_toggled(self, checked: bool) -> None:
        self.dry_run = checked
        self.dry_banner.setVisible(checked)
        self.remove_button.setProperty("dryrun", checked)
        style = self.remove_button.style()
        style.unpolish(self.remove_button)
        style.polish(self.remove_button)
        self.remove_button.update()
        self._update_selection()
        if checked:
            self._append_log(
                "warn", "Dry-run mode enabled — commands will be logged, nothing will be changed."
            )
        else:
            self._append_log("info", "Dry-run mode disabled — removals are live.")

    def _open_backups(self) -> None:
        try:
            path = self.controller.open_backups_folder()
        except OSError as exc:
            message = f"Could not open the backups folder: {exc}"
            self._append_log("err", message)
            QMessageBox.warning(self, "Open backups", message)
            return
        self._append_log("info", f"Opened backups folder: {path}")

    def _start_removal(self) -> None:
        if self._busy or not self._scan_ok:
            return
        selected = self.selected_rows()
        if not selected:
            return

        try:
            backup_dir = self.controller.next_backup_directory()
        except Exception:
            from core.controller import backups_root

            backup_dir = backups_root()

        dialog = ConfirmDialog(selected, self.rows, backup_dir, self.dry_run, self)
        if dialog.exec() != QDialog.Accepted:
            self._append_log("dim", "Removal cancelled.")
            return

        self.log_panel.set_expanded(True)
        self._append_log(
            "info",
            "Starting dry run …"
            if self.dry_run
            else f"Starting removal of {len(selected)} item(s) …",
        )
        self._set_busy(True)
        worker = RemovalWorker(
            self.controller,
            selected,
            self.rows,
            self.dry_run,
            dialog.delete_folders,
            self,
        )
        worker.report_ready.connect(self._on_report_ready)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_report_ready(self, report: RemovalReport) -> None:
        self._worker = None
        for message in report.errors:
            self._append_log("err", message)
        for path, reason in report.skipped_folders:
            self._append_log("warn", f"Kept folder {path}: {reason}")

        if report.dry_run:
            self._append_log("warn", "Dry run finished — nothing was changed.")
        elif report.aborted:
            self._append_log("err", "Removal was aborted before any change.")
        elif report.ok:
            self._append_log(
                "ok",
                f"Removed {len(report.deleted_entries)} boot entr"
                f"{'y' if len(report.deleted_entries) == 1 else 'ies'} and "
                f"{len(report.deleted_folders)} EFI folder(s).",
            )
            if report.backup:
                self._append_log("dim", f"Backup: {report.backup.directory}")

        if report.errors:
            QMessageBox.warning(
                self,
                "Finished with errors",
                "Some items could not be removed:\n\n" + "\n".join(report.errors)[:2500],
            )

        self._set_busy(False)
        self.refresh()

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------ events
    def _append_log(self, level: str, message: str) -> None:
        self.log_panel.append(level, message)
        if level == "err":
            self.log_panel.set_expanded(True)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self,
                "Removal in progress",
                "Please wait until the current removal has finished before closing.",
            )
            event.ignore()
            return
        try:
            self.controller.cleanup()
        finally:
            super().closeEvent(event)
