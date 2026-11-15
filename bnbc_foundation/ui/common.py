"""Shared helpers for the PySide6 pages."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.units import convert, factor, label, to_si


def set_spin(box: QDoubleSpinBox, value: float, quantity: str, system: str) -> None:
    """Show an SI value in a spin box using the selected display units."""
    if not hasattr(box, "_si_bounds"):
        box._si_bounds = (box.minimum(), box.maximum())
        box._si_step = box.singleStep()
        box._si_decimals = box.decimals()
    lo, hi = box._si_bounds
    f = factor(quantity, system)
    box.blockSignals(True)
    box.setDecimals(box._si_decimals if system == "SI" else max(box._si_decimals, 2))
    box.setRange(lo * f, hi * f)
    box.setSingleStep(max(box._si_step * f, 10 ** -box.decimals()))
    box.setValue(convert(value, quantity, system))
    unit = label(quantity, system)
    box.setSuffix(f" {unit}" if unit else "")
    box.blockSignals(False)


def get_spin(box: QDoubleSpinBox, quantity: str, system: str) -> float:
    """Read a spin box and return the value in internal SI units."""
    return to_si(box.value(), quantity, system)


def parse_list(text_value: str, quantity: str, system: str, scale: float = 1.0) -> list[float]:
    """Parse a comma/semicolon list of display values into SI values."""
    out = []
    for part in str(text_value).replace(";", ",").split(","):
        try:
            value = float(part.strip())
        except ValueError:
            continue
        if value > 0:
            out.append(to_si(value, quantity, system) * scale)
    return sorted(set(out))


def format_list(values, quantity: str, system: str, scale: float = 1.0) -> str:
    """Format SI values as a display-unit list."""
    return ", ".join(f"{convert(v * scale, quantity, system):g}" for v in values)



def dspin(
    minimum: float = -1e9,
    maximum: float = 1e9,
    value: float = 0.0,
    decimals: int = 2,
    step: float = 0.05,
    suffix: str = "",
) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    box._si_bounds = (minimum, maximum)
    box._si_step = step
    box._si_decimals = decimals
    if suffix:
        box.setSuffix(f" {suffix}")
    box.setMinimumWidth(100)
    return box


def item(value: Any) -> QTableWidgetItem:
    text = "" if value is None else str(value)
    cell = QTableWidgetItem(text)
    cell.setTextAlignment(Qt.AlignCenter)
    return cell


def num(cell: QTableWidgetItem | None, default: float = 0.0) -> float:
    if cell is None:
        return default
    try:
        return float(cell.text().strip().replace(",", ""))
    except (TypeError, ValueError):
        return default


def text(cell: QTableWidgetItem | None, default: str = "") -> str:
    if cell is None:
        return default
    value = cell.text().strip()
    return value if value else default


def make_table(headers: list[str], stretch_last: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    return table


class Card(QFrame):
    """A light bordered panel with a title and content layout."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            font = QFont()
            font.setBold(True)
            font.setPointSize(11)
            label.setFont(font)
            self._layout.addWidget(label)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class SectionTitle(QLabel):
    def __init__(self, title: str):
        super().__init__(title)
        self.setObjectName("SectionTitle")
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        self.setFont(font)


def error_color(status: str) -> QColor:
    status = (status or "").upper()
    if status == "OK":
        return QColor("#C6EFCE")
    if status == "CHECK":
        return QColor("#FFEB9C")
    return QColor("#FFC7CE")


APP_STYLESHEET = """
QMainWindow, QWidget#Page { background: #F4F6F9; }
QFrame#Card { background: #FFFFFF; border: 1px solid #D6DCE5; border-radius: 8px; }
QLabel#CardTitle { color: #1F4E79; }
QLabel#SectionTitle { color: #1F4E79; }
QLabel#Muted { color: #667085; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
    background: #FFFFFF; border: 1px solid #C9D2E0; border-radius: 5px;
    padding: 4px 6px; selection-background-color: #2E75B6;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 1px solid #2E75B6;
}
QPushButton {
    background: #2E75B6; color: white; border: none; border-radius: 5px;
    padding: 7px 14px; font-weight: 600;
}
QPushButton:hover { background: #1F5E99; }
QPushButton:disabled { background: #AEB6C2; }
QPushButton#Secondary { background: #E8EDF4; color: #1F4E79; border: 1px solid #C9D2E0; }
QPushButton#Secondary:hover { background: #D6E1EE; }
QPushButton#Danger { background: #C00000; }
QPushButton#Danger:hover { background: #9A0000; }
QListWidget#Nav { background: #1F4E79; border: none; color: #D9E2F3; font-size: 12px; outline: none; }
QListWidget#Nav::item { padding: 14px 16px; border-bottom: 1px solid #2A5E8E; }
QListWidget#Nav::item:selected { background: #2E75B6; color: white; border-left: 4px solid #9DC3E6; }
QListWidget#Nav::item:hover { background: #2A5E8E; }
QHeaderView::section {
    background: #1F4E79; color: white; padding: 6px; border: none;
    border-right: 1px solid #3A6D9A; font-weight: bold;
}
QTableWidget { gridline-color: #DDE3EC; alternate-background-color: #F8FAFD; }
QProgressBar { border: 1px solid #C9D2E0; border-radius: 5px; text-align: center; height: 18px; }
QProgressBar::chunk { background: #2E75B6; border-radius: 4px; }
QToolTip { background: #1F2937; color: white; padding: 4px; }
"""
