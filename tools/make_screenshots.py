"""Render README screenshots from the demo mode (no ESP, no admin needed)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
# Render at 1:1 so the tallest useful window fits on a 1080p screen.
os.environ.setdefault("QT_SCALE_FACTOR", "1")

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.correlator import Status  # noqa: E402
from ui.dialogs import ConfirmDialog  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.theme import apply_theme  # noqa: E402


def wait(milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def check_rows(window: MainWindow, keys: set[str]) -> None:
    for index in range(window.table.rowCount()):
        item = window.table.item(index, 0)
        if item is not None and str(item.data(Qt.UserRole)) in keys:
            item.setCheckState(Qt.Checked)


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = MainWindow(demo=True)
    window.resize(1240, 1010)
    window.show()
    wait(600)

    cleanup_statuses = {Status.ORPHANED_ENTRY, Status.ORPHANED_FOLDER}
    keys = {row.key for row in window.rows if row.status in cleanup_statuses}
    check_rows(window, keys)
    wait(200)

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    window.grab().save(str(assets / "screenshot-main.png"), "PNG")
    print("Wrote screenshot-main.png")

    window.dry_switch.setChecked(True)
    window.log_panel.set_expanded(True)
    wait(150)
    window.controller.remove(window.selected_rows(), window.rows, dry_run=True)
    wait(150)
    window.grab().save(str(assets / "screenshot-dryrun.png"), "PNG")
    print("Wrote screenshot-dryrun.png")

    window.dry_switch.setChecked(False)
    wait(100)
    dialog = ConfirmDialog(
        window.selected_rows(),
        window.rows,
        window.controller.next_backup_directory(),
        dry_run=False,
        parent=window,
    )
    dialog.show()
    wait(250)
    dialog.confirm_checkbox.setChecked(True)
    wait(50)
    dialog.grab().save(str(assets / "screenshot-confirm.png"), "PNG")
    print("Wrote screenshot-confirm.png")

    dialog.close()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
