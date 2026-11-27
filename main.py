"""Entry point: UAC elevation, Qt bootstrap and crash logging."""

from __future__ import annotations

import argparse
import ctypes
import sys
import traceback
from datetime import datetime

from core.privileges import is_admin, is_windows, relaunch_as_admin, show_error_dialog
from core.version import APP_NAME, __version__


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="EFI-Boot-Entry-Cleaner",
        description=(
            "View, select and remove stale UEFI boot entries together with their "
            "leftover folders on the EFI System Partition."
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with simulated data. Nothing is mounted, read or deleted.",
    )
    parser.add_argument(
        "--no-elevate",
        action="store_true",
        help="Do not request Administrator rights (development only; bcdedit will fail).",
    )
    parser.add_argument(
        "--no-relaunch",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {__version__}",
    )
    return parser.parse_args(argv)


def ensure_elevation(args: argparse.Namespace) -> None:
    """Request UAC elevation and exit the unelevated instance."""
    if not is_windows() or args.demo or args.no_elevate:
        return
    if is_admin():
        return

    if args.no_relaunch:
        show_error_dialog(
            APP_NAME,
            "Administrator rights are required to read bcdedit and mount the EFI "
            "System Partition.\n\nRight-click the app and choose 'Run as administrator'.",
        )
        raise SystemExit(1)

    if relaunch_as_admin(["--no-relaunch"]):
        raise SystemExit(0)

    show_error_dialog(
        APP_NAME,
        "The elevation prompt was cancelled, so the app cannot continue.\n\n"
        "Administrator rights are required to read and modify UEFI boot entries.",
    )
    raise SystemExit(1)


def install_crash_handler() -> None:
    """Write unexpected crashes to %LOCALAPPDATA%\\EFIBootCleaner\\logs."""
    from core.controller import logs_root

    def handler(exc_type, exc_value, exc_traceback) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_path = None
        try:
            directory = logs_root()
            directory.mkdir(parents=True, exist_ok=True)
            log_path = directory / f"crash-{datetime.now():%Y-%m-%d_%H-%M-%S}.log"
            log_path.write_text(text, encoding="utf-8", errors="replace")
        except OSError:
            log_path = None

        message = f"Something went wrong:\n\n{exc_value}"
        if log_path:
            message += f"\n\nDetails were written to:\n{log_path}"
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME, message)
            else:
                show_error_dialog(APP_NAME, message)
        except Exception:
            show_error_dialog(APP_NAME, message)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handler


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    ensure_elevation(args)

    if is_windows():
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SouradeepDutta.EFIBootEntryCleaner"
        )

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from core.resources import app_icon_path
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    install_crash_handler()

    app = QApplication(sys.argv)
    app.setApplicationName("EFI Boot Entry Cleaner")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Souradeep Dutta")
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app)

    window = MainWindow(demo=args.demo)
    app.aboutToQuit.connect(window.controller.cleanup)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
