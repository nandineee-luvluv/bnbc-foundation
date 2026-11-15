"""Foundation options, limits, site constraints and cost rates page."""

from __future__ import annotations

import csv

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..common import SectionTitle, dspin, format_list, get_spin, parse_list, set_spin
from ...core.models import Project
from ...core.units import convert, label, system_of, to_si


class OptionsPage(QWidget):
    _UNIT_FIELDS = (
        ("min_dim", "min_footing_dim", "length"),
        ("max_dim", "max_footing_dim", "length"),
        ("dim_step", "footing_dim_step", "length"),
        ("min_soil_thickness", "min_thickness_soil", "length_mm"),
        ("min_pile_thickness", "min_thickness_pile", "length_mm"),
        ("min_depth_clay", "min_depth_cohesive", "length"),
        ("min_depth_sand", "min_depth_cohesionless", "length"),
        ("min_depth_general", "min_depth_general", "length"),
        ("raft_overhang", "raft_overhang", "length"),
        ("raft_min_thickness", "raft_min_thickness", "length_mm"),
        ("max_pile_length", "max_pile_length", "length"),
        ("min_pile_spacing", "min_pile_spacing", "length"),
        ("cap_edge_cover", "cap_edge_cover", "length"),
        ("cap_embedment", "cap_embedment", "length"),
        ("cap_min_thickness", "cap_min_thickness", "length_mm"),
        ("cap_cover", "cap_cover", "length_mm"),
        ("single_min_diameter", "single_pile_min_diameter", "length"),
        ("site_xmin", "site_xmin", "length"),
        ("site_xmax", "site_xmax", "length"),
        ("site_ymin", "site_ymin", "length"),
        ("site_ymax", "site_ymax", "length"),
        ("settlement_sand", "settlement_limit_sand", "settlement"),
        ("settlement_clay", "settlement_limit_clay", "settlement"),
        ("differential_limit", "differential_limit", "settlement"),
        ("crack_width_limit", "crack_width_limit", "settlement"),
    )

    _COST_FIELDS = (
        ("cost_concrete", "cost_concrete", "cost_per_volume"),
        ("cost_excavation", "cost_excavation", "cost_per_volume"),
        ("cost_pile", "cost_pile", "cost_per_length"),
        ("cost_steel", "cost_steel", "cost_per_mass"),
        ("cost_raft", "cost_raft", "cost_per_area"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._system = "SI"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(10)
        outer.addWidget(SectionTitle("Foundation options, limits and site constraints"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setSpacing(12)

        # Foundation types
        types = QGroupBox("Allowed foundation systems")
        tf = QFormLayout(types)
        self.allow_isolated = QCheckBox("Isolated footings")
        self.allow_combined = QCheckBox("Combined footings")
        self.allow_strip = QCheckBox("Strip / wall footings")
        self.allow_single_pile = QCheckBox("Single pile with cap")
        self.allow_pile_group = QCheckBox("Pile group with cap")
        self.allow_raft = QCheckBox("Raft / mat")
        self.prefer_shallow = QCheckBox("Prefer shallow foundations")
        self.optimize_cost = QCheckBox("Rank feasible options by cost")
        for w in (self.allow_isolated, self.allow_combined, self.allow_strip,
                  self.allow_single_pile, self.allow_pile_group, self.allow_raft,
                  self.prefer_shallow, self.optimize_cost):
            tf.addRow(w)
        self.raft_trigger = QComboBox()
        self.raft_trigger.addItems(["Auto", "Always", "Never"])
        self.raft_analysis = QComboBox()
        self.raft_analysis.addItems(["Auto", "Rigid", "Winkler strips", "Plate"])
        tf.addRow("Raft trigger", self.raft_trigger)
        tf.addRow("Raft analysis", self.raft_analysis)
        grid.addWidget(types, 0, 0)

        # Geometry and safety
        geometry = QGroupBox("Geometry and factors of safety")
        gf = QFormLayout(geometry)
        self.min_dim = dspin(0.5, 10, 0.8, 2, 0.05, "m")
        self.max_dim = dspin(1, 60, 8.0, 2, 0.25, "m")
        self.dim_step = dspin(0.01, 1, 0.05, 2, 0.01, "m")
        self.min_soil_thickness = dspin(100, 2000, 150, 0, 25, "mm")
        self.min_pile_thickness = dspin(200, 3000, 300, 0, 25, "mm")
        self.min_depth_clay = dspin(0.5, 20, 1.5, 2, 0.25, "m")
        self.min_depth_sand = dspin(0.5, 20, 2.0, 2, 0.25, "m")
        self.min_depth_general = dspin(0.0, 10, 0.5, 2, 0.25, "m")
        self.fs_shallow = dspin(1.0, 6.0, 2.5, 2, 0.1)
        self.fs_pile = dspin(1.0, 8.0, 3.0, 2, 0.1)
        self.raft_overhang = dspin(0.0, 10, 0.5, 2, 0.1, "m")
        self.raft_min_thickness = dspin(300, 3000, 500, 0, 25, "mm")
        for label, widget in (
            ("Minimum footing dimension", self.min_dim),
            ("Maximum footing dimension", self.max_dim),
            ("Dimension increment", self.dim_step),
            ("Minimum RC thickness on soil", self.min_soil_thickness),
            ("Minimum RC thickness on piles", self.min_pile_thickness),
            ("Minimum depth in clay", self.min_depth_clay),
            ("Minimum depth in sand", self.min_depth_sand),
            ("Minimum general depth", self.min_depth_general),
            ("FS shallow bearing", self.fs_shallow),
            ("FS pile", self.fs_pile),
            ("Raft overhang", self.raft_overhang),
            ("Raft minimum thickness", self.raft_min_thickness),
        ):
            gf.addRow(label, widget)
        self.raft_outline = QLineEdit()
        self.raft_outline.setPlaceholderText("x1,y1; x2,y2; ... (blank = automatic rectangle)")
        self.btn_raft_outline = QPushButton("Import CSV...")
        self.btn_raft_outline.setObjectName("Secondary")
        outline_row = QHBoxLayout()
        outline_row.addWidget(self.raft_outline, 1)
        outline_row.addWidget(self.btn_raft_outline)
        self.raft_outline_label = QLabel("Raft outline")
        gf.addRow(self.raft_outline_label, outline_row)
        self.geometry_form = gf
        self.btn_raft_outline.clicked.connect(self._import_raft_outline)
        grid.addWidget(geometry, 0, 1)

        # Piles
        piles = QGroupBox("Piles")
        pf = QFormLayout(piles)
        self.pile_type = QComboBox()
        self.pile_type.addItems(["Bored", "Driven", "Drilled shaft"])
        self.pile_method = QComboBox()
        self.pile_method.addItems(["SPT", "Static", "CPT", "Direct"])
        self.pile_control = QComboBox()
        self.pile_control.addItems(["Good", "Normal", "Poor", "Very Poor"])
        self.pile_diameters = QLineEdit("0.40, 0.50, 0.60, 0.75, 0.90, 1.20")
        self.pile_lengths = QLineEdit("10, 15, 20, 25, 30")
        self.max_pile_length = dspin(5, 100, 40, 1, 1, "m")
        self.min_pile_spacing = dspin(0.5, 5, 0.75, 2, 0.05, "m")
        self.end_spacing = dspin(1.5, 6, 2.5, 2, 0.1)
        self.friction_spacing = dspin(1.5, 6, 3.0, 2, 0.1)
        self.cap_edge_cover = dspin(0.05, 2, 0.10, 2, 0.05, "m")
        self.cap_embedment = dspin(0.0, 1, 0.075, 3, 0.025, "m")
        self.cap_min_thickness = dspin(200, 3000, 300, 0, 25, "mm")
        self.cap_cover = dspin(30, 150, 50, 0, 5, "mm")
        self.single_min_diameter = dspin(0.3, 3, 0.60, 2, 0.05, "m")
        for label_text, widget in (
            ("Pile type", self.pile_type),
            ("Design method", self.pile_method),
            ("Construction control", self.pile_control),
            ("Diameters", self.pile_diameters),
            ("Lengths", self.pile_lengths),
            ("Maximum length", self.max_pile_length),
            ("Minimum spacing", self.min_pile_spacing),
            ("End-bearing spacing (x D)", self.end_spacing),
            ("Friction spacing (x D)", self.friction_spacing),
            ("Cap edge cover", self.cap_edge_cover),
            ("Cap embedment", self.cap_embedment),
            ("Cap minimum thickness", self.cap_min_thickness),
            ("Cap cover", self.cap_cover),
            ("Single-pile minimum diameter", self.single_min_diameter),
        ):
            pf.addRow(label_text, widget)
        self.pile_form = pf
        grid.addWidget(piles, 1, 0)

        # Site and serviceability
        site = QGroupBox("Site and serviceability")
        sf = QFormLayout(site)
        self.site_xmin = dspin(-10000, 10000, -1000, 2, 1, "m")
        self.site_xmax = dspin(-10000, 10000, 1000, 2, 1, "m")
        self.site_ymin = dspin(-10000, 10000, -1000, 2, 1, "m")
        self.site_ymax = dspin(-10000, 10000, 1000, 2, 1, "m")
        self.settlement_sand = dspin(1, 200, 25, 1, 1, "mm")
        self.settlement_clay = dspin(1, 200, 40, 1, 1, "mm")
        self.differential_limit = dspin(1, 200, 20, 1, 1, "mm")
        self.angular_limit = dspin(0.0001, 0.05, 1 / 500, 5, 0.0001)
        self.area_ratio = dspin(0.1, 1, 0.5, 2, 0.05)
        self.pga_g = dspin(0.0, 2.0, 0.0, 2, 0.01, "g")
        for label, widget in (
            ("Site x minimum", self.site_xmin), ("Site x maximum", self.site_xmax),
            ("Site y minimum", self.site_ymin), ("Site y maximum", self.site_ymax),
            ("Settlement limit, sand", self.settlement_sand),
            ("Settlement limit, clay", self.settlement_clay),
            ("Differential limit", self.differential_limit),
            ("Angular distortion limit", self.angular_limit),
            ("Maximum footing area ratio", self.area_ratio),
            ("Peak ground acceleration", self.pga_g),
        ):
            sf.addRow(label, widget)
        grid.addWidget(site, 1, 1)

        # Costs
        costs = QGroupBox("Optional cost rates")
        cf = QFormLayout(costs)
        self.cost_concrete = dspin(0, 1e7, 0, 2, 100)
        self.cost_excavation = dspin(0, 1e7, 0, 2, 50)
        self.cost_pile = dspin(0, 1e7, 0, 2, 100)
        self.cost_steel = dspin(0, 1e7, 0, 2, 10)
        self.cost_raft = dspin(0, 1e7, 0, 2, 100)
        for label_text, widget in (
            ("Concrete rate", self.cost_concrete),
            ("Excavation rate", self.cost_excavation),
            ("Pile rate", self.cost_pile),
            ("Steel rate", self.cost_steel),
            ("Raft rate", self.cost_raft),
        ):
            cf.addRow(label_text, widget)
        grid.addWidget(costs, 3, 0, 1, 2)

        # Serviceability and supplementary pile checks
        checks = QGroupBox("Serviceability and supplementary checks")
        qf = QFormLayout(checks)
        self.crack_width_limit = dspin(0.05, 2.0, 0.30, 2, 0.05, "mm")
        self.crack_check = QCheckBox("Crack width check (service)")
        self.uplift_check = QCheckBox("Shallow footing buoyancy/uplift check")
        self.uplift_fs = dspin(1.0, 3.0, 1.10, 2, 0.05)
        self.pile_uplift_fs = dspin(1.0, 6.0, 2.00, 2, 0.25)
        self.pile_lateral_fs = dspin(1.0, 6.0, 2.50, 2, 0.25)
        self.pile_downdrag_check = QCheckBox("Pile downdrag / negative skin friction")
        self.pile_lateral_check = QCheckBox("Pile lateral capacity (Broms)")
        self.pile_pm_check = QCheckBox("Pile P-M interaction")
        qf.addRow("Crack width limit", self.crack_width_limit)
        for w in (self.crack_check, self.uplift_check):
            qf.addRow(w)
        qf.addRow("Uplift FS", self.uplift_fs)
        qf.addRow("Pile uplift FS", self.pile_uplift_fs)
        qf.addRow("Pile lateral FS", self.pile_lateral_fs)
        for w in (self.pile_downdrag_check, self.pile_lateral_check,
                  self.pile_pm_check):
            qf.addRow(w)
        grid.addWidget(checks, 2, 0, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def load_project(self, project: Project) -> None:
        o = project.options
        self._system = system_of(project)
        s = self._system
        self.allow_isolated.setChecked(o.allow_isolated)
        self.allow_combined.setChecked(o.allow_combined)
        self.allow_strip.setChecked(o.allow_strip)
        self.allow_single_pile.setChecked(o.allow_single_pile)
        self.allow_pile_group.setChecked(o.allow_pile_group)
        self.allow_raft.setChecked(o.allow_raft)
        self.prefer_shallow.setChecked(o.prefer_shallow)
        self.optimize_cost.setChecked(o.optimize_cost)
        self.raft_trigger.setCurrentText(o.raft_trigger)
        self.raft_analysis.setCurrentText(o.raft_analysis)
        for widget_name, attr, quantity in self._UNIT_FIELDS:
            set_spin(getattr(self, widget_name), getattr(o, attr), quantity, s)
        self.fs_shallow.setValue(o.fs_shallow)
        self.fs_pile.setValue(o.fs_pile)
        self.pile_type.setCurrentText(o.pile_type)
        self.pile_method.setCurrentText(o.pile_design_method)
        self.pile_control.setCurrentText(o.pile_control)
        self.pile_diameters.setText(
            format_list([d * 1000.0 for d in o.pile_diameters], "length_mm", s)
        )
        self.pile_lengths.setText(format_list(o.pile_lengths, "length", s))
        self.end_spacing.setValue(o.pile_spacing_end_bearing)
        self.friction_spacing.setValue(o.pile_spacing_friction)
        self.angular_limit.setValue(o.angular_limit)
        self.area_ratio.setValue(o.max_footing_area_ratio)
        self.pga_g.setValue(o.pga_g)
        self.raft_outline_label.setText(f"Raft outline ({label('length', s)})")
        diameters_label = self.pile_form.labelForField(self.pile_diameters)
        if diameters_label is not None:
            diameters_label.setText(f"Diameters ({label('length_mm', s)})")
        lengths_label = self.pile_form.labelForField(self.pile_lengths)
        if lengths_label is not None:
            lengths_label.setText(f"Lengths ({label('length', s)})")
        for widget_name, attr, quantity in self._COST_FIELDS:
            set_spin(getattr(self, widget_name), getattr(o, attr), quantity, s)
        self.crack_check.setChecked(o.crack_check)
        self.uplift_check.setChecked(o.uplift_check)
        self.uplift_fs.setValue(o.uplift_fs)
        self.pile_uplift_fs.setValue(o.pile_uplift_fs)
        self.pile_lateral_fs.setValue(o.pile_lateral_fs)
        self.pile_downdrag_check.setChecked(o.pile_downdrag_check)
        self.pile_lateral_check.setChecked(o.pile_lateral_check)
        self.pile_pm_check.setChecked(o.pile_pm_check)
        self.raft_outline.setText(
            "; ".join(
                f"{convert(p[0], 'length', s):g},{convert(p[1], 'length', s):g}"
                for p in o.raft_outline if len(p) >= 2
            )
        )

    @staticmethod
    def _values(text_value: str) -> list[float]:
        out = []
        for part in text_value.replace(";", ",").split(","):
            try:
                value = float(part.strip())
            except ValueError:
                continue
            if value > 0:
                out.append(value)
        return sorted(set(out))

    def apply_to_project(self, project: Project) -> None:
        o = project.options
        s = self._system
        o.allow_isolated = self.allow_isolated.isChecked()
        o.allow_combined = self.allow_combined.isChecked()
        o.allow_strip = self.allow_strip.isChecked()
        o.allow_single_pile = self.allow_single_pile.isChecked()
        o.allow_pile_group = self.allow_pile_group.isChecked()
        o.allow_raft = self.allow_raft.isChecked()
        o.prefer_shallow = self.prefer_shallow.isChecked()
        o.optimize_cost = self.optimize_cost.isChecked()
        o.raft_trigger = self.raft_trigger.currentText()
        o.raft_analysis = self.raft_analysis.currentText()
        for widget_name, attr, quantity in self._UNIT_FIELDS:
            setattr(o, attr, get_spin(getattr(self, widget_name), quantity, s))
        o.fs_shallow = self.fs_shallow.value()
        o.fs_pile = self.fs_pile.value()
        o.pile_type = self.pile_type.currentText()
        o.pile_design_method = self.pile_method.currentText()
        o.pile_control = self.pile_control.currentText()
        o.pile_diameters = [
            value / 1000.0
            for value in parse_list(self.pile_diameters.text(), "length_mm", s)
        ] or [0.4, 0.6, 0.9]
        o.pile_lengths = parse_list(self.pile_lengths.text(), "length", s) or [10, 15, 20, 25]
        o.pile_spacing_end_bearing = self.end_spacing.value()
        o.pile_spacing_friction = self.friction_spacing.value()
        o.angular_limit = self.angular_limit.value()
        o.max_footing_area_ratio = self.area_ratio.value()
        o.pga_g = self.pga_g.value()
        for widget_name, attr, quantity in self._COST_FIELDS:
            setattr(o, attr, get_spin(getattr(self, widget_name), quantity, s))
        o.crack_check = self.crack_check.isChecked()
        o.uplift_check = self.uplift_check.isChecked()
        o.uplift_fs = self.uplift_fs.value()
        o.pile_uplift_fs = self.pile_uplift_fs.value()
        o.pile_lateral_fs = self.pile_lateral_fs.value()
        o.pile_downdrag_check = self.pile_downdrag_check.isChecked()
        o.pile_lateral_check = self.pile_lateral_check.isChecked()
        o.pile_pm_check = self.pile_pm_check.isChecked()
        o.raft_outline = self._parse_outline(self.raft_outline.text(), s)

    def _import_raft_outline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import raft outline", "", "CSV (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            points: list[list[float]] = []
            with open(path, newline="", encoding="utf-8-sig") as fh:
                for row in csv.reader(fh):
                    values = [cell.strip() for cell in row if cell.strip()]
                    if len(values) < 2:
                        continue
                    try:
                        x, y = float(values[0]), float(values[1])
                    except ValueError:
                        continue
                    points.append([x, y])
            if len(points) < 3:
                raise ValueError("The outline needs at least three x,y points.")
            self.raft_outline.setText(
                "; ".join(
                    f"{convert(x, 'length', self._system):g},"
                    f"{convert(y, 'length', self._system):g}"
                    for x, y in points
                )
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    @staticmethod
    def _parse_outline(text_value: str, system: str = "SI") -> list[list[float]]:
        points: list[list[float]] = []
        for part in text_value.replace("\n", ";").split(";"):
            values = [v.strip() for v in part.split(",") if v.strip()]
            if len(values) < 2:
                continue
            try:
                points.append([
                    to_si(float(values[0]), "length", system),
                    to_si(float(values[1]), "length", system),
                ])
            except ValueError:
                continue
        return points if len(points) >= 3 else []
