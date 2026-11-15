"""PySide6 main window and background design worker."""

from __future__ import annotations

import copy
import os
import re
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Borehole, Project, ProjectInfo, SoilLayer, sample_project
from ..core.report import (
    export_all,
    export_csv,
    export_excel,
    export_import_template,
    export_pdf,
    load_project,
    save_project,
    selected_results,
)
from ..core.selector import run_design
from ..core.units import normalize_system
from .common import APP_STYLESHEET
from .pages.export_page import ExportPage
from .pages.loads_page import LoadsPage
from .pages.materials_page import MaterialsPage
from .pages.options_page import OptionsPage
from .pages.project_page import ProjectPage
from .pages.results_page import ResultsPage
from .pages.soil_page import SoilPage


class DesignWorker(QThread):
    completed = Signal(object)       # (DesignRun, Project)
    failed = Signal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)

    def run(self) -> None:  # pragma: no cover - executed in a thread
        try:
            result = run_design(self.project)
            self.completed.emit((result, self.project))
        except Exception:
            self.failed.emit(traceback.format_exc())


def empty_project() -> Project:
    borehole = Borehole(
        id="BH-1", x=0.0, y=0.0, gwt=2.0,
        layers=[
            SoilLayer(bottom_depth=3.0, soil_type="Fill", description="Fill",
                      gamma=18.0, gamma_sat=19.0, n_raw=6, n60=5),
            SoilLayer(bottom_depth=12.0, soil_type="CL", description="Clay",
                      gamma=18.0, gamma_sat=19.0, cu=30.0, n_raw=8, n60=7),
        ],
    )
    return Project(info=ProjectInfo(name="New Foundation Project"), boreholes=[borehole])


class MainWindow(QMainWindow):
    def __init__(self, project: Project | None = None):
        super().__init__()
        self.project = project or sample_project()
        self.project_path: str | None = None
        self._thread: DesignWorker | None = None
        self.setWindowTitle("BNBC 2020 Foundation Designer")
        self.resize(1480, 940)
        self.setMinimumSize(1150, 720)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._build_actions()
        self._load_project_into_pages()
        self.statusBar().showMessage("Sample project loaded. Press Run Design to calculate.")

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav_frame = QWidget()
        nav_frame.setFixedWidth(218)
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        logo = QLabel("BNBC 2020\nFOUNDATION DESIGNER")
        logo.setStyleSheet(
            "background:#163D5F;color:white;font-weight:bold;font-size:13px;"
            "padding:18px 14px;border-bottom:1px solid #2A5E8E;"
        )
        nav_layout.addWidget(logo)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        nav_layout.addWidget(self.nav, 1)
        version = QLabel("SI units  |  BNBC 2020\nv0.1 calculation prototype")
        self.units_label = version
        version.setStyleSheet("color:#9DC3E6;background:#163D5F;padding:10px 14px;font-size:9px;")
        nav_layout.addWidget(version)
        root.addWidget(nav_frame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        header = QWidget()
        header.setStyleSheet("background:white;border-bottom:1px solid #D6DCE5;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        self.header_title = QLabel("Sample Residential Building")
        self.header_title.setStyleSheet("font-size:16px;font-weight:bold;color:#1F4E79;")
        self.header_sub = QLabel("")
        self.header_sub.setStyleSheet("color:#667085;font-size:10px;")
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.addWidget(self.header_title)
        title_box.addWidget(self.header_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)
        self.run_button = QPushButton("Run design")
        self.run_button.setMinimumWidth(130)
        header_layout.addWidget(self.progress)
        header_layout.addWidget(self.run_button)
        content_layout.addWidget(header)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        self.project_page = ProjectPage()
        self.materials_page = MaterialsPage()
        self.soil_page = SoilPage()
        self.loads_page = LoadsPage()
        self.options_page = OptionsPage()
        self.results_page = ResultsPage()
        self.export_page = ExportPage()
        self.pages = [
            ("Project", self.project_page),
            ("Materials", self.materials_page),
            ("Soil profile", self.soil_page),
            ("Columns & walls", self.loads_page),
            ("Options", self.options_page),
            ("Results", self.results_page),
            ("Export", self.export_page),
        ]
        for name, page in self.pages:
            self.nav.addItem(QListWidgetItem(name))
            self.stack.addWidget(page)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.run_button.clicked.connect(self.run_design)

        self.project_page.new_requested.connect(self.new_project)
        self.project_page.sample_requested.connect(self.load_sample)
        self.project_page.open_requested.connect(self.open_project_dialog)
        self.project_page.save_requested.connect(self.save_project_dialog)
        self.project_page.units_changed.connect(self._units_changed)
        self.export_page.export_requested.connect(self.export)
        self.export_page.template_requested.connect(self.write_template)
        self.export_page.save_project_requested.connect(self.save_project_dialog)
        self.export_page.open_project_requested.connect(self.open_project_dialog)

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for text, shortcut, slot in (
            ("New project", QKeySequence.New, self.new_project),
            ("Load synthetic sample", None, self.load_sample),
            ("Open project...", QKeySequence.Open, self.open_project_dialog),
            ("Save project", QKeySequence.Save, self.save_project_dialog),
            ("Save project as...", None, lambda: self.save_project_dialog(save_as=True)),
            ("Export all reports...", None, lambda: self.export("all")),
            ("Quit", QKeySequence.Quit, self.close),
        ):
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)

        design_menu = self.menuBar().addMenu("&Design")
        run_action = QAction("Run design", self)
        run_action.setShortcut("Ctrl+R")
        run_action.triggered.connect(self.run_design)
        design_menu.addAction(run_action)
        results_action = QAction("Show results", self)
        results_action.triggered.connect(lambda: self.nav.setCurrentRow(5))
        design_menu.addAction(results_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def _update_header(self) -> None:
        self.header_title.setText(self.project.info.name or "Untitled Foundation Project")
        count = len(self.project.elements)
        results = len(selected_results(self.project))
        status = f"{count} elements"
        if results:
            status += f"  |  {results} foundation results"
        self.header_sub.setText(status)
        self.setWindowTitle(f"{self.project.info.name} - BNBC 2020 Foundation Designer")

    def _load_project_into_pages(self) -> None:
        for _, page in self.pages:
            if page in (self.results_page, self.export_page):
                continue
            page.load_project(self.project)
        self.results_page.show_results(self.project)
        self._update_header()
        system = normalize_system(self.project.info.units)
        name = "US customary" if system == "US" else "SI"
        self.units_label.setText(f"{name} units  |  BNBC 2020\nv0.1 calculation prototype")

    def _units_changed(self, text: str) -> None:
        self.project.info.units = normalize_system(text)
        self._load_project_into_pages()
        self.statusBar().showMessage(
            f"Display units: {'US customary' if self.project.info.units == 'US' else 'SI'}"
        )

    def _collect(self) -> bool:
        try:
            for _, page in self.pages:
                if page in (self.results_page, self.export_page):
                    continue
                page.apply_to_project(self.project)
        except Exception as exc:
            QMessageBox.warning(self, "Input error", str(exc))
            return False
        self._update_header()
        return True

    def _validate(self) -> bool:
        if not self.project.elements:
            QMessageBox.warning(self, "No elements",
                                "Add at least one column or shear wall before running the design.")
            return False
        if not self.project.boreholes:
            QMessageBox.warning(self, "No borehole",
                                "Add at least one borehole and soil layer before running the design.")
            return False
        if any(not bh.layers for bh in self.project.boreholes):
            QMessageBox.warning(self, "Soil layers",
                                "Every borehole must contain at least one soil layer.")
            return False
        ids = [e.id for e in self.project.elements]
        if len(ids) != len(set(ids)):
            QMessageBox.warning(self, "Duplicate IDs",
                                "Element IDs must be unique. Check the Columns & walls page.")
            return False
        for element in self.project.elements:
            if element.kind == "column":
                if element.is_circular and element.diameter <= 0:
                    QMessageBox.warning(
                        self, "Column geometry",
                        f"{element.id}: a circular column needs a positive diameter."
                    )
                    return False
                if not element.is_circular and (element.length <= 0 or element.width <= 0):
                    QMessageBox.warning(
                        self, "Column geometry",
                        f"{element.id}: rectangular column length and width must be positive."
                    )
                    return False
            else:
                if element.wall_thickness <= 0:
                    QMessageBox.warning(
                        self, "Wall geometry",
                        f"{element.id}: wall thickness must be positive."
                    )
                    return False
                endpoints = (element.x1, element.y1, element.x2, element.y2)
                provided = [value is not None for value in endpoints]
                if any(provided) and not element.has_wall_endpoints():
                    QMessageBox.warning(
                        self, "Wall geometry",
                        f"{element.id}: provide all four wall endpoints and make the "
                        "start and end points distinct, or leave all endpoints blank."
                    )
                    return False
                if not element.has_wall_endpoints() and element.length <= 0:
                    QMessageBox.warning(
                        self, "Wall geometry",
                        f"{element.id}: enter wall endpoints or a positive wall length."
                    )
                    return False
        if self.project.options.site_xmin >= self.project.options.site_xmax:
            QMessageBox.warning(self, "Site boundary",
                                "Site x minimum must be less than the maximum.")
            return False
        if self.project.options.site_ymin >= self.project.options.site_ymax:
            QMessageBox.warning(self, "Site boundary",
                                "Site y minimum must be less than the maximum.")
            return False
        return True

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = empty_project()
        self.project_path = None
        self.results_page.clear()
        self.project.results = []
        self.project.warnings = []
        self._load_project_into_pages()
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("New project created.")

    def load_sample(self) -> None:
        if not self._confirm_discard():
            return
        self.project = sample_project()
        self.project_path = None
        self._load_project_into_pages()
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("Synthetic sample project loaded. Press Run Design.")

    def _confirm_discard(self) -> bool:
        if not self.project.elements and not self.project.boreholes:
            return True
        answer = QMessageBox.question(
            self, "Replace project",
            "Replace the current project? Unsaved input will be lost.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def open_project_dialog(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open foundation project", "", "Foundation project (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", f"Could not read the project file:\n{exc}")
            return
        self.project = project
        self.project_path = path
        self._load_project_into_pages()
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage(f"Opened {path}")

    def save_project_dialog(self, save_as: bool = False) -> None:
        if not self._collect():
            return
        path = self.project_path
        if save_as or not path:
            default = re.sub(r"[^A-Za-z0-9_-]+", "_", self.project.info.name).strip("_") or "project"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save foundation project", f"{default}.json",
                "Foundation project (*.json);;All files (*)"
            )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_project(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.project_path = path
        self.statusBar().showMessage(f"Saved {path}")
        self.export_page.append_log(f"Saved project: {path}")

    # ------------------------------------------------------------------
    # Design run
    # ------------------------------------------------------------------

    def run_design(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if not self._collect() or not self._validate():
            return
        self.run_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Running foundation selection and design...")
        self._thread = DesignWorker(self.project, self)
        self._thread.completed.connect(self._design_finished)
        self._thread.failed.connect(self._design_failed)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _design_finished(self, payload) -> None:
        run, project = payload
        self.project = project
        self.project.warnings = list(run.warnings)
        self._thread = None
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self._load_project_into_pages()
        self.results_page.show_results(self.project)
        self.nav.setCurrentRow(5)
        ok = sum(1 for r in self.project.results if r.status == "OK")
        check = sum(1 for r in self.project.results if r.status == "CHECK")
        fail = sum(1 for r in self.project.results if r.status == "FAIL")
        self.statusBar().showMessage(
            f"Design complete: {ok} OK, {check} CHECK, {fail} FAIL, "
            f"{len(run.warnings)} warning(s)."
        )

    def _design_failed(self, message: str) -> None:
        self._thread = None
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        self.statusBar().showMessage("Design failed.")
        QMessageBox.critical(self, "Design failed",
                             "The calculation stopped with an error:\n\n" + message[-4000:])

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def _output_dir(self) -> Path:
        directory = Path(os.path.expanduser(self.export_page.directory.text().strip() or "exports"))
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _stem(self) -> str:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", self.project.info.name).strip("_")
        return stem or "foundation"

    def export(self, kind: str) -> None:
        if not self._collect():
            return
        directory = self._output_dir()
        stem = self._stem()
        try:
            if kind == "all":
                paths = export_all(self.project, directory)
                message = "\n".join(f"{name}: {path}" for name, path in paths.items())
            elif kind == "excel":
                path = export_excel(self.project, directory / f"{stem}.xlsx")
                message = path
            elif kind == "pdf":
                path = export_pdf(self.project, directory / f"{stem}.pdf")
                message = path
            elif kind == "csv":
                path = export_csv(self.project, directory / f"{stem}.csv")
                message = path
            elif kind == "json":
                path = save_project(self.project, directory / f"{stem}.json")
                message = path
            else:
                return
            self.export_page.append_log(f"{kind.upper()} exported:\n{message}")
            self.statusBar().showMessage(f"{kind.upper()} export complete.")
            QMessageBox.information(self, "Export complete", message)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{exc}\n\n{traceback.format_exc()[-2000:]}")
            self.export_page.append_log(f"Export failed: {exc}")

    def write_template(self) -> None:
        try:
            directory = self._output_dir()
            path = export_import_template(directory / f"{self._stem()}_import_template.xlsx")
            self.export_page.append_log(f"Import template written:\n{path}")
            QMessageBox.information(self, "Template written", path)
        except Exception as exc:
            QMessageBox.critical(self, "Template failed", str(exc))

    def _about(self) -> None:
        QMessageBox.about(
            self, "About",
            "<h3>BNBC 2020 Foundation Designer</h3>"
            "<p>Geotechnical and structural design of isolated, combined, strip, raft, "
            "single-pile and pile-group foundations.</p>"
            "<p>Design aid only. Results must be reviewed by a qualified engineer.</p>"
        )

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            answer = QMessageBox.question(
                self, "Design running",
                "A design run is still in progress. Close the application?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._thread.wait(2000)
        event.accept()
