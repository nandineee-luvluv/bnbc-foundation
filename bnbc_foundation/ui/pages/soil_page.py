"""Borehole, soil-layer and SPT page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..common import (
    Card,
    SectionTitle,
    dspin,
    get_spin,
    item,
    make_table,
    num,
    set_spin,
    text,
)
from ...core.models import Borehole, Project, SoilLayer
from ...core.report import import_soil_csv, import_soil_excel
from ...core.units import convert, label, system_of, to_si

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - optional in headless installs
    FigureCanvasQTAgg = None
    Figure = None


def layer_headers(system: str = "SI") -> list[str]:
    length = label("length", system)
    unit_weight = label("unit_weight", system)
    pressure = label("pressure", system)
    stress = label("stress", system)
    subgrade = label("subgrade", system)
    return [
        f"Bottom ({length})", "Soil type", "Description",
        f"gamma ({unit_weight})", f"gamma sat ({unit_weight})",
        f"c' ({pressure})", "phi' (deg)", f"cu ({pressure})",
        "N raw", "N60", f"qc ({stress})", f"CPT fs ({pressure})",
        "Cc", "e0", "OCR", "LL", "PL", "Fines %",
        f"Es ({pressure})", f"k ({subgrade})",
        f"q allow ({pressure})", f"Skin ({pressure})", f"End ({pressure})",
        f"Skin driven ({pressure})", f"End driven ({pressure})",
        f"Skin bored ({pressure})", f"End bored ({pressure})",
    ]


LAYER_HEADERS = layer_headers("SI")


class SoilPage(QWidget):
    _COLUMN_QUANTITY = {
        0: "length",        # bottom depth
        3: "unit_weight",   # gamma
        4: "unit_weight",   # gamma sat
        5: "pressure",      # c'
        7: "pressure",      # cu
        10: "stress",       # qc
        11: "pressure",     # CPT fs
        18: "pressure",     # Es
        19: "subgrade",     # k
        20: "pressure", 21: "pressure", 22: "pressure",
        23: "pressure", 24: "pressure", 25: "pressure", 26: "pressure",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._system = "SI"
        self._boreholes: list[Borehole] = []
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(SectionTitle("Soil profile, SPT and direct capacities"))

        top_card = Card("Borehole")
        top = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(180)
        self.btn_add_bh = QPushButton("Add borehole")
        self.btn_del_bh = QPushButton("Remove")
        self.btn_del_bh.setObjectName("Danger")
        self.btn_import = QPushButton("Import soil Excel/CSV...")
        self.btn_import.setObjectName("Secondary")
        top.addWidget(self.combo)
        top.addWidget(self.btn_add_bh)
        top.addWidget(self.btn_del_bh)
        top.addStretch(1)
        top.addWidget(self.btn_import)
        top_card.add_layout(top)

        fields = QHBoxLayout()
        self.bh_id = QLineEdit()
        self.bh_x = dspin(-10000, 10000, 0, 2, 0.5, "m")
        self.bh_y = dspin(-10000, 10000, 0, 2, 0.5, "m")
        self.gwt = dspin(0, 100, 2, 2, 0.5, "m")
        fields.addWidget(self._label("Borehole ID"))
        fields.addWidget(self.bh_id)
        fields.addSpacing(12)
        fields.addWidget(self._label("x"))
        fields.addWidget(self.bh_x)
        fields.addWidget(self._label("y"))
        fields.addWidget(self.bh_y)
        fields.addWidget(self._label("GWT depth"))
        fields.addWidget(self.gwt)
        fields.addStretch(1)
        top_card.add_layout(fields)
        layout.addWidget(top_card)

        splitter = QSplitter(Qt.Horizontal)
        left = Card("Soil layers")
        layer_buttons = QHBoxLayout()
        self.btn_add_layer = QPushButton("Add layer")
        self.btn_del_layer = QPushButton("Remove layer")
        self.btn_del_layer.setObjectName("Danger")
        self.btn_plot = QPushButton("Refresh SPT plot")
        self.btn_plot.setObjectName("Secondary")
        layer_buttons.addWidget(self.btn_add_layer)
        layer_buttons.addWidget(self.btn_del_layer)
        layer_buttons.addWidget(self.btn_plot)
        layer_buttons.addStretch(1)
        left.add_layout(layer_buttons)
        self.table = make_table(LAYER_HEADERS, stretch_last=False)
        self.table.setMinimumHeight(380)
        left.add(self.table)
        splitter.addWidget(left)

        right = Card("SPT profile")
        if FigureCanvasQTAgg is not None:
            self.figure = Figure(figsize=(4.0, 4.8))
            self.canvas = FigureCanvasQTAgg(self.figure)
            right.add(self.canvas)
        else:
            self.canvas = None
            right.add(QLineEdit("matplotlib is not available"))
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.combo.currentIndexChanged.connect(self._on_borehole_changed)
        self.btn_add_bh.clicked.connect(self._add_borehole)
        self.btn_del_bh.clicked.connect(self._remove_borehole)
        self.btn_add_layer.clicked.connect(self._add_layer)
        self.btn_del_layer.clicked.connect(self._remove_layer)
        self.btn_plot.clicked.connect(self._plot)
        self.btn_import.clicked.connect(self._import)

    @staticmethod
    def _label(value: str):
        from PySide6.QtWidgets import QLabel
        label = QLabel(value)
        label.setObjectName("Muted")
        return label

    # ------------------------------------------------------------------
    # Project binding
    # ------------------------------------------------------------------

    def load_project(self, project: Project) -> None:
        self._loading = True
        self._system = system_of(project)
        self.table.setHorizontalHeaderLabels(layer_headers(self._system))
        self._boreholes = project.boreholes or [Borehole(id="BH-1", layers=[SoilLayer()])]
        self.combo.clear()
        self.combo.addItems([bh.id for bh in self._boreholes])
        self.combo.setCurrentIndex(0)
        self._loading = False
        self._load_borehole(0)
        self._plot()

    def apply_to_project(self, project: Project) -> None:
        self._flush_borehole()
        self._flush_layers()
        project.boreholes = self._boreholes

    # ------------------------------------------------------------------
    # Borehole handling
    # ------------------------------------------------------------------

    def _current(self) -> Borehole | None:
        index = self.combo.currentIndex()
        if 0 <= index < len(self._boreholes):
            return self._boreholes[index]
        return None

    def _load_borehole(self, index: int) -> None:
        if not (0 <= index < len(self._boreholes)):
            return
        bh = self._boreholes[index]
        self._loading = True
        self.bh_id.setText(bh.id)
        set_spin(self.bh_x, bh.x, "length", self._system)
        set_spin(self.bh_y, bh.y, "length", self._system)
        set_spin(self.gwt, bh.gwt, "length", self._system)
        self._load_layers(bh)
        self._loading = False

    def _flush_borehole(self) -> None:
        if self._loading:
            return
        bh = self._current()
        if bh is None:
            return
        bh.id = self.bh_id.text().strip() or "BH-1"
        bh.x = get_spin(self.bh_x, "length", self._system)
        bh.y = get_spin(self.bh_y, "length", self._system)
        bh.gwt = get_spin(self.gwt, "length", self._system)

    def _flush_layers(self) -> None:
        if self._loading:
            return
        bh = self._current()
        if bh is None:
            return
        layers = []
        for row in range(self.table.rowCount()):
            bottom = to_si(num(self.table.item(row, 0)), "length", self._system)
            if bottom <= 0:
                continue
            layer = SoilLayer(
                bottom_depth=bottom,
                soil_type=text(self.table.item(row, 1), "CL"),
                description=text(self.table.item(row, 2)),
                gamma=to_si(num(self.table.item(row, 3), 18.0), "unit_weight", self._system),
                gamma_sat=to_si(num(self.table.item(row, 4), 19.0), "unit_weight", self._system),
                cohesion=to_si(num(self.table.item(row, 5)), "pressure", self._system),
                friction_angle=num(self.table.item(row, 6)),
                cu=to_si(num(self.table.item(row, 7)), "pressure", self._system),
                n_raw=num(self.table.item(row, 8)),
                n60=num(self.table.item(row, 9)),
                qc=to_si(num(self.table.item(row, 10)), "stress", self._system),
                cpt_fs=to_si(num(self.table.item(row, 11)), "pressure", self._system),
                cc=num(self.table.item(row, 12)),
                e0=num(self.table.item(row, 13)),
                ocr=num(self.table.item(row, 14), 1.0),
                ll=num(self.table.item(row, 15)),
                pl=num(self.table.item(row, 16)),
                fines=num(self.table.item(row, 17)),
                es=to_si(num(self.table.item(row, 18)), "pressure", self._system),
                k_subgrade=to_si(num(self.table.item(row, 19)), "subgrade", self._system),
                allowable_bearing=self._opt(row, 20),
                pile_skin=self._opt(row, 21),
                pile_end=self._opt(row, 22),
                pile_skin_driven=self._opt(row, 23),
                pile_end_driven=self._opt(row, 24),
                pile_skin_bored=self._opt(row, 25),
                pile_end_bored=self._opt(row, 26),
            )
            layers.append(layer)
        layers.sort(key=lambda l: l.bottom_depth)
        bh.layers = layers

    def _opt(self, row: int, col: int):
        cell = self.table.item(row, col)
        if cell is None or not cell.text().strip():
            return None
        try:
            return to_si(float(cell.text().strip()), "pressure", self._system)
        except ValueError:
            return None

    def _load_layers(self, bh: Borehole) -> None:
        self.table.setRowCount(0)
        self._loading = True
        for layer in bh.sorted_layers():
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                layer.bottom_depth, layer.soil_type, layer.description,
                layer.gamma, layer.gamma_sat, layer.cohesion, layer.friction_angle,
                layer.cu, layer.n_raw, layer.n60, layer.qc, layer.cpt_fs,
                layer.cc, layer.e0, layer.ocr,
                layer.ll, layer.pl, layer.fines, layer.es, layer.k_subgrade,
                "" if layer.allowable_bearing is None else layer.allowable_bearing,
                "" if layer.pile_skin is None else layer.pile_skin,
                "" if layer.pile_end is None else layer.pile_end,
                "" if layer.pile_skin_driven is None else layer.pile_skin_driven,
                "" if layer.pile_end_driven is None else layer.pile_end_driven,
                "" if layer.pile_skin_bored is None else layer.pile_skin_bored,
                "" if layer.pile_end_bored is None else layer.pile_end_bored,
            ]
            for col, value in enumerate(values):
                if col in self._COLUMN_QUANTITY and value != "":
                    value = convert(float(value), self._COLUMN_QUANTITY[col], self._system)
                self.table.setItem(row, col, item(value))
        self._loading = False

    def _on_borehole_changed(self, index: int) -> None:
        if self._loading:
            return
        self._flush_borehole()
        self._flush_layers()
        self._load_borehole(index)
        self._plot()

    def _add_borehole(self) -> None:
        self._flush_borehole()
        self._flush_layers()
        index = len(self._boreholes) + 1
        bh = Borehole(id=f"BH-{index}", layers=[
            SoilLayer(bottom_depth=3.0, soil_type="Fill", n_raw=5, n60=5),
            SoilLayer(bottom_depth=10.0, soil_type="CL", cu=30, n_raw=8, n60=7),
        ])
        self._boreholes.append(bh)
        self.combo.blockSignals(True)
        self.combo.addItem(bh.id)
        self.combo.setCurrentIndex(len(self._boreholes) - 1)
        self.combo.blockSignals(False)
        self._load_borehole(self.combo.currentIndex())
        self._plot()

    def _remove_borehole(self) -> None:
        if len(self._boreholes) <= 1:
            QMessageBox.information(self, "Borehole", "At least one borehole is required.")
            return
        index = self.combo.currentIndex()
        del self._boreholes[index]
        self.combo.blockSignals(True)
        self.combo.removeItem(index)
        self.combo.setCurrentIndex(max(0, index - 1))
        self.combo.blockSignals(False)
        self._load_borehole(self.combo.currentIndex())
        self._plot()

    # ------------------------------------------------------------------
    # Layers and plot
    # ------------------------------------------------------------------

    def _add_layer(self) -> None:
        self._flush_layers()
        bh = self._current()
        depth = 1.0
        if bh and bh.layers:
            depth = max(l.bottom_depth for l in bh.layers) + 2.0
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [depth, "CL", "New layer", 18.0, 19.0, 0, 0, 25, 8, 7,
                  0.0, 0.0, 0.15, 0.8, 1.0, 40, 20, 50, 8000, 0,
                  "", "", "", "", "", "", ""]
        for col, value in enumerate(values):
            if col in self._COLUMN_QUANTITY and value != "":
                value = convert(float(value), self._COLUMN_QUANTITY[col], self._system)
            self.table.setItem(row, col, item(value))
        self.table.selectRow(row)

    def _remove_layer(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def _plot(self) -> None:
        if self.canvas is None:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        try:
            f = convert(1.0, "length", self._system)
            for bh in self._boreholes:
                depths, nvals = [], []
                top = 0.0
                for layer in sorted(bh.layers, key=lambda l: l.bottom_depth):
                    depths.append(0.5 * (top + layer.bottom_depth) * f)
                    nvals.append(layer.effective_n60())
                    top = layer.bottom_depth
                ax.plot(nvals, depths, marker="o", linewidth=1.2, label=bh.id)
            ax.invert_yaxis()
            ax.set_xlabel("N60")
            ax.set_ylabel(f"Depth below ground ({label('length', self._system)})")
            ax.set_title("SPT profile")
            ax.grid(True, linestyle=":", linewidth=0.4)
            if len(self._boreholes) > 1:
                ax.legend(fontsize=7)
            self.figure.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import soil data", "", "Excel/CSV (*.xlsx *.xlsm *.csv)"
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                boreholes = import_soil_csv(path)
            else:
                boreholes = import_soil_excel(path)
            if not boreholes:
                raise ValueError("No valid soil rows were found.")
            self._boreholes = boreholes
            self.combo.blockSignals(True)
            self.combo.clear()
            self.combo.addItems([b.id for b in boreholes])
            self.combo.setCurrentIndex(0)
            self.combo.blockSignals(False)
            self._load_borehole(0)
            self._plot()
            QMessageBox.information(
                self, "Import complete",
                f"Imported {len(boreholes)} borehole(s) and "
                f"{sum(len(b.layers) for b in boreholes)} layer(s).",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
