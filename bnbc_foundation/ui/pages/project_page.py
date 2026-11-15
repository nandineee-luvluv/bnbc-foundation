"""Project information page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from ..common import Card, SectionTitle
from ...core.models import Project
from ...core.units import normalize_system


class ProjectPage(QWidget):
    new_requested = Signal()
    sample_requested = Signal()
    open_requested = Signal()
    save_requested = Signal()
    units_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        layout = QGridLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        layout.addWidget(SectionTitle("Project information"), 0, 0, 1, 2)

        info_card = Card("Identification")
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit()
        self.location = QLineEdit()
        self.engineer = QLineEdit()
        self.date = QLineEdit()
        self.code = QLineEdit()
        self.units = QComboBox()
        self.units.addItems(["SI", "US"])
        self.units.setToolTip(
            "SI: m, mm, kN, kN.m, kPa, MPa. "
            "US: ft, in, kip, kip.ft, ksf, ksi. The engine stores SI values."
        )
        self.notes = QTextEdit()
        self.notes.setMinimumHeight(120)
        form.addRow("Project name", self.name)
        form.addRow("Location", self.location)
        form.addRow("Engineer", self.engineer)
        form.addRow("Date", self.date)
        form.addRow("Design code", self.code)
        form.addRow("Units", self.units)
        form.addRow("Notes", self.notes)
        info_card.add_layout(form)
        layout.addWidget(info_card, 1, 0)

        actions = Card("Project actions")
        buttons = QHBoxLayout()
        self.btn_new = QPushButton("New project")
        self.btn_sample = QPushButton("Load sample")
        self.btn_open = QPushButton("Open JSON...")
        self.btn_save = QPushButton("Save JSON...")
        for b in (self.btn_new, self.btn_sample, self.btn_open, self.btn_save):
            b.setObjectName("Secondary")
            buttons.addWidget(b)
        buttons.addStretch(1)
        actions.add_layout(buttons)
        actions.add(QTextEdit(
            "The synthetic sample contains five columns, one shear wall, one borehole "
            "with five soil layers and both service and factored reactions. Use it to "
            "explore the workflow, then replace the data with your own project."
        ))
        layout.addWidget(actions, 1, 1)
        layout.setRowStretch(1, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)

        self.btn_new.clicked.connect(self.new_requested)
        self.btn_sample.clicked.connect(self.sample_requested)
        self.btn_open.clicked.connect(self.open_requested)
        self.btn_save.clicked.connect(self.save_requested)
        self.units.currentTextChanged.connect(self.units_changed)

    def load_project(self, project: Project) -> None:
        info = project.info
        self.name.setText(info.name)
        self.location.setText(info.location)
        self.engineer.setText(info.engineer)
        self.date.setText(info.date)
        self.code.setText(info.code)
        self.units.blockSignals(True)
        self.units.setCurrentText(normalize_system(info.units))
        self.units.blockSignals(False)
        self.notes.setPlainText(info.notes)

    def apply_to_project(self, project: Project) -> None:
        info = project.info
        info.name = self.name.text().strip() or "Untitled Foundation Project"
        info.location = self.location.text().strip()
        info.engineer = self.engineer.text().strip()
        info.date = self.date.text().strip()
        info.code = self.code.text().strip() or "BNBC 2020"
        info.units = normalize_system(self.units.currentText())
        info.notes = self.notes.toPlainText().strip()
