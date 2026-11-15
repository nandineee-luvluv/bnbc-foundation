"""Export and project-file page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..common import Card, SectionTitle


class ExportPage(QWidget):
    export_requested = Signal(str)
    template_requested = Signal()
    save_project_requested = Signal()
    open_project_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(SectionTitle("Export and project files"))

        card = Card("Output folder")
        row = QHBoxLayout()
        self.directory = QLineEdit("exports")
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setObjectName("Secondary")
        row.addWidget(self.directory, 1)
        row.addWidget(self.btn_browse)
        card.add_layout(row)
        layout.addWidget(card)

        docs = Card("Reports")
        drow = QHBoxLayout()
        self.btn_excel = QPushButton("Excel workbook")
        self.btn_pdf = QPushButton("PDF report")
        self.btn_csv = QPushButton("CSV schedule")
        self.btn_json = QPushButton("JSON project")
        self.btn_all = QPushButton("Export all")
        for b in (self.btn_excel, self.btn_pdf, self.btn_csv, self.btn_json, self.btn_all):
            drow.addWidget(b)
        drow.addStretch(1)
        docs.add_layout(drow)
        tip = QLabel(
            "The Excel workbook contains Summary, Foundation Schedule, Geotech Checks, "
            "Structural Checks, Rebar Schedule, Bar Bending Schedule, Quantities, Soil "
            "Inputs and Code Basis sheets. The PDF is a printable design report."
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        docs.add(tip)
        layout.addWidget(docs)

        files = Card("Project files and import template")
        frow = QHBoxLayout()
        self.btn_save = QPushButton("Save project JSON...")
        self.btn_open = QPushButton("Open project JSON...")
        self.btn_template = QPushButton("Write Excel import template")
        for b in (self.btn_save, self.btn_open, self.btn_template):
            b.setObjectName("Secondary")
            frow.addWidget(b)
        frow.addStretch(1)
        files.add_layout(frow)
        layout.addWidget(files)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Export messages appear here.")
        layout.addWidget(self.log, 1)

        self.btn_excel.clicked.connect(lambda: self.export_requested.emit("excel"))
        self.btn_pdf.clicked.connect(lambda: self.export_requested.emit("pdf"))
        self.btn_csv.clicked.connect(lambda: self.export_requested.emit("csv"))
        self.btn_json.clicked.connect(lambda: self.export_requested.emit("json"))
        self.btn_all.clicked.connect(lambda: self.export_requested.emit("all"))
        self.btn_template.clicked.connect(self.template_requested)
        self.btn_save.clicked.connect(self.save_project_requested)
        self.btn_open.clicked.connect(self.open_project_requested)
        self.btn_browse.clicked.connect(self._browse)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder", self.directory.text())
        if path:
            self.directory.setText(path)

    def append_log(self, message: str) -> None:
        self.log.append(message)
