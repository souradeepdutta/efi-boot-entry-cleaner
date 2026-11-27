"""Custom painted widgets: toggle switch, table delegates, stats and console."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, LOG_COLORS, STATUS_COLORS, mono_font_family


class ToggleSwitch(QAbstractButton):
    """An iOS/Win11 style switch painted with QPainter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self.setFocusPolicy(Qt.StrongFocus)
        self._hover = False

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def enterEvent(self, event: QEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0, 2, 44, 20)
        checked = self.isChecked()
        if checked:
            track_color = QColor(COLORS["accent"])
        elif self._hover:
            track_color = QColor("#4a4a57")
        else:
            track_color = QColor("#3a3a45")
        if not self.isEnabled():
            track_color.setAlpha(90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)

        knob_x = 24 if checked else 2
        painter.setBrush(QColor("#ffffff" if self.isEnabled() else "#9aa0ab"))
        painter.drawEllipse(QRectF(knob_x, 2, 20, 20))

        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(COLORS["accent"]), 1))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 43, 23), 11, 11)


class CheckRow(QAbstractButton):
    """A check box drawn to match the table (native indicators vary by theme)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._hover = False

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance(self.text()) + 40, 28)

    def enterEvent(self, event: QEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, (self.height() - 18) / 2, 18, 18)
        checked = self.isChecked()
        enabled = self.isEnabled()
        highlight = self._hover or self.hasFocus()

        if checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLORS["accent"] if enabled else "#3a4a55"))
            painter.drawRoundedRect(box, 5, 5)
            pen = QPen(QColor("#0b1116"), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(box.left() + 4.5, box.center().y() + 0.5)
            path.lineTo(box.left() + 7.8, box.bottom() - 5)
            path.lineTo(box.right() - 4.5, box.top() + 5.5)
            painter.drawPath(path)
        else:
            border = COLORS["accent"] if highlight and enabled else "#4a4a58"
            painter.setPen(QPen(QColor(border), 1.5))
            painter.setBrush(QColor(COLORS["surface_alt"]))
            painter.drawRoundedRect(box, 5, 5)

        painter.setPen(QColor(COLORS["text"] if enabled else COLORS["text_dim"]))
        painter.drawText(
            QRectF(30, 0, self.width() - 30, self.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text(),
        )


class StatusBadgeDelegate(QStyledItemDelegate):
    """Paints the colour-coded status pill."""

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        status = index.data(Qt.UserRole) or ""
        foreground, background = STATUS_COLORS.get(
            status, (COLORS["text_muted"], "rgba(255,255,255,0.06)")
        )
        text = str(status)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(option.font)
        font.setPointSizeF(max(8.0, option.font.pointSizeF() - 1.2))
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 34
        height = 22
        rect = QRect(
            option.rect.left() + 10,
            option.rect.center().y() - height // 2,
            min(width, option.rect.width() - 12),
            height,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(rect), 11, 11)
        painter.setBrush(QColor(foreground))
        painter.drawEllipse(QPointF(rect.left() + 11, rect.center().y() + 0.5), 3, 3)
        painter.setPen(QPen(QColor(foreground)))
        painter.drawText(
            rect.adjusted(20, 0, -8, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            metrics.elidedText(text, Qt.ElideRight, rect.width() - 26),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(150, 44)


class CheckboxDelegate(QStyledItemDelegate):
    """Paints a rounded checkbox, or a lock for protected rows."""

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self.table = table

    def paint(self, painter: QPainter, option, index) -> None:
        style = option.widget.style() if option.widget else None
        if style is not None:
            style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        item = self.table.item(index.row(), 0)
        protected = item is not None and not bool(item.flags() & Qt.ItemIsUserCheckable)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        center = option.rect.center()
        if protected:
            color = QColor(COLORS["text_dim"])
            painter.setPen(QPen(color, 1.4))
            painter.setBrush(Qt.NoBrush)
            body = QRectF(center.x() - 7, center.y() - 2, 14, 11)
            painter.drawRoundedRect(body, 2.5, 2.5)
            painter.drawArc(QRectF(center.x() - 4.5, center.y() - 11, 9, 12), 0, 180 * 16)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(center.x(), center.y() + 3), 1.4, 1.4)
        else:
            checked = item is not None and item.checkState() == Qt.Checked
            box = QRectF(center.x() - 9, center.y() - 9, 18, 18)
            if checked:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(COLORS["accent"]))
                painter.drawRoundedRect(box, 5, 5)
                pen = QPen(QColor("#0b1116"), 2.0)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                path = QPainterPath()
                path.moveTo(box.left() + 4.5, box.center().y() + 0.5)
                path.lineTo(box.left() + 7.8, box.bottom() - 5)
                path.lineTo(box.right() - 4.5, box.top() + 5.5)
                painter.drawPath(path)
            else:
                painter.setPen(QPen(QColor("#4a4a58"), 1.5))
                painter.setBrush(QColor(COLORS["surface_alt"]))
                painter.drawRoundedRect(box, 5, 5)
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if (
            event.type() == QEvent.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.LeftButton
        ):
            item = self.table.item(index.row(), 0)
            if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                return True
        return super().editorEvent(event, model, option, index)


class StatChip(QFrame):
    """Small KPI chip: coloured dot, count and label."""

    def __init__(self, label: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatChip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 13px;")
        layout.addWidget(dot)

        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self.count_label)

        self.text_label = QLabel(label)
        self.text_label.setObjectName("Muted")
        layout.addWidget(self.text_label)
        layout.addStretch(1)

    def set_count(self, value: int) -> None:
        self.count_label.setText(str(value))


class SmallTextButton(QToolButton):
    """Small borderless text button used inside the console header."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QToolButton {{ color: {COLORS['text_dim']}; padding: 2px 6px; }}"
            f"QToolButton:hover {{ color: {COLORS['text']}; }}"
        )


class LogPanel(QFrame):
    """Collapsible console with colour-coded, timestamped output."""

    expandedChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.toggle_button = QToolButton()
        self.toggle_button.setText("▸  Console")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle)
        header.addWidget(self.toggle_button)
        header.addStretch(1)

        self.line_count = QLabel("0 lines")
        self.line_count.setObjectName("Dim")
        header.addWidget(self.line_count)

        clear = SmallTextButton("Clear")
        clear.clicked.connect(self.clear)
        header.addWidget(clear)

        outer.addLayout(header)

        self.text = QPlainTextEdit()
        self.text.setObjectName("Console")
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        font = self.text.font()
        font.setFamily(mono_font_family())
        font.setPointSize(9)
        self.text.setFont(font)
        self.text.setMinimumHeight(150)
        self.text.setVisible(False)
        outer.addWidget(self.text)

        self._formats: dict[str, tuple] = {}
        self._lines = 0

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.text.setVisible(expanded)
        self.toggle_button.setText("▾  Console" if expanded else "▸  Console")
        self.expandedChanged.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def clear(self) -> None:
        self.text.clear()
        self._lines = 0
        self.line_count.setText("0 lines")

    def _format(self, color: str):
        cached = self._formats.get(color)
        if cached is None:
            char_format = self.text.currentCharFormat()
            char_format.setForeground(QColor(color))
            cached = char_format
            self._formats[color] = cached
        return cached

    def append(self, level: str, message: str) -> None:
        color = LOG_COLORS.get(level, LOG_COLORS["info"])
        timestamp_format = self._format(LOG_COLORS["dim"])
        text_format = self._format(color)
        body = str(message).rstrip("\n")
        lines = body.splitlines() or [""]
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        for line in lines:
            cursor.insertText(f"{datetime.now():%H:%M:%S}  ", timestamp_format)
            cursor.insertText(line + "\n", text_format)
        self._lines += len(lines)
        self.line_count.setText(f"{self._lines} lines")
        self.text.ensureCursorVisible()


class EmptyState(QFrame):
    """Shown when the table has no rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        self.icon = QLabel("✓")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"color: {COLORS['success']}; font-size: 42px; font-weight: 300;")
        layout.addWidget(self.icon)

        self.title = QLabel("Nothing to clean up")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(self.title)

        self.hint = QLabel("No stale UEFI boot entries or unreferenced EFI folders were found.")
        self.hint.setObjectName("Muted")
        self.hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint)

    def set_message(self, title: str, hint: str, icon: str = "✓", color: str | None = None) -> None:
        self.icon.setText(icon)
        self.icon.setStyleSheet(
            f"color: {color or COLORS['success']}; font-size: 42px; font-weight: 300;"
        )
        self.title.setText(title)
        self.hint.setText(hint)
