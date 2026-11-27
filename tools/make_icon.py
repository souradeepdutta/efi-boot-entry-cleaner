"""Render the application icon and banner assets with Qt (no extra deps)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)


def shield_path(canvas: float) -> QPainterPath:
    """A shield centred in a square of *canvas* pixels."""
    s = canvas
    path = QPainterPath()
    path.moveTo(s * 0.50, s * 0.16)
    path.cubicTo(s * 0.62, s * 0.22, s * 0.70, s * 0.24, s * 0.79, s * 0.25)
    path.lineTo(s * 0.79, s * 0.50)
    path.cubicTo(s * 0.79, s * 0.68, s * 0.66, s * 0.80, s * 0.50, s * 0.86)
    path.cubicTo(s * 0.34, s * 0.80, s * 0.21, s * 0.68, s * 0.21, s * 0.50)
    path.lineTo(s * 0.21, s * 0.25)
    path.cubicTo(s * 0.30, s * 0.24, s * 0.38, s * 0.22, s * 0.50, s * 0.16)
    path.closeSubpath()
    return path


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scale = size / 256.0
    painter.scale(scale, scale)

    # Rounded dark tile
    tile = QRectF(6, 6, 244, 244)
    background = QLinearGradient(QPointF(0, 0), QPointF(256, 256))
    background.setColorAt(0.0, QColor("#22242c"))
    background.setColorAt(1.0, QColor("#101116"))
    painter.setPen(QPen(QColor("#343742"), 3))
    painter.setBrush(background)
    painter.drawRoundedRect(tile, 52, 52)

    # Soft accent glow
    glow = QLinearGradient(QPointF(60, 40), QPointF(200, 220))
    glow.setColorAt(0.0, QColor(76, 194, 255, 42))
    glow.setColorAt(1.0, QColor(76, 194, 255, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(glow)
    painter.drawRoundedRect(QRectF(18, 18, 220, 220), 44, 44)

    # Shield
    shield = shield_path(256)
    shield_gradient = QLinearGradient(QPointF(64, 48), QPointF(196, 218))
    shield_gradient.setColorAt(0.0, QColor("#6fd6ff"))
    shield_gradient.setColorAt(0.55, QColor("#3ea9e8"))
    shield_gradient.setColorAt(1.0, QColor("#1f78b4"))
    painter.setBrush(shield_gradient)
    painter.setPen(QPen(QColor(174, 230, 255, 110), 2))
    painter.drawPath(shield)

    # Inner highlight
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 40), 2))
    inner = QPainterPath()
    inner.moveTo(64, 62)
    inner.cubicTo(92, 72, 112, 74, 128, 76)
    painter.drawPath(inner)

    # Check mark
    check = QPainterPath()
    check.moveTo(84, 131)
    check.lineTo(116, 164)
    check.lineTo(176, 100)
    pen = QPen(QColor("#0d2233"), 19)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(check)

    # Tiny status dot: a clean system
    painter.setPen(QPen(QColor("#0f1116"), 4))
    painter.setBrush(QColor("#38d39f"))
    painter.drawEllipse(QPointF(197, 197), 17, 17)

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def write_ico(path: Path, sizes: list[int]) -> None:
    images = [png_bytes(render(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    directory = bytearray()
    for size, payload in zip(sizes, images, strict=True):
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset
        )
        offset += len(payload)
    path.write_bytes(header + bytes(directory) + b"".join(images))


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - required for QImage/QPainter fonts
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    render(256).save(str(assets / "icon-256.png"), "PNG")
    render(512).save(str(assets / "icon-512.png"), "PNG")
    write_ico(assets / "app.ico", [16, 24, 32, 48, 64, 128, 256])
    print(f"Wrote {assets / 'app.ico'} and icon PNGs")


if __name__ == "__main__":
    main()
