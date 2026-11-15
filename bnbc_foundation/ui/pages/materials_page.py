"""Materials and design-factor page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QWidget,
)

from ..common import Card, SectionTitle, dspin, format_list, get_spin, parse_list, set_spin
from ...core.models import Project
from ...core.units import label, system_of


class MaterialsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._system = "SI"
        self.setObjectName("Page")
        layout = QGridLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addWidget(SectionTitle("Materials and resistance factors"), 0, 0, 1, 2)

        concrete = Card("Concrete and reinforcement")
        form = QFormLayout()
        self.f_c = dspin(15, 100, 30, 1, 1, "MPa")
        self.f_y = dspin(250, 700, 420, 0, 10, "MPa")
        self.gamma = dspin(18, 28, 24, 1, 0.5, "kN/m3")
        self.cover = dspin(20, 150, 75, 0, 5, "mm")
        self.bars = QLineEdit("12, 16, 20, 25")
        self.max_spacing = dspin(100, 600, 300, 0, 10, "mm")
        self.min_spacing = dspin(50, 300, 100, 0, 5, "mm")
        form.addRow("f'c", self.f_c)
        form.addRow("fy", self.f_y)
        form.addRow("Concrete unit weight", self.gamma)
        form.addRow("Bottom cover", self.cover)
        form.addRow("Bar diameters", self.bars)
        self.bar_label = form.labelForField(self.bars)
        form.addRow("Maximum bar spacing", self.max_spacing)
        form.addRow("Minimum bar spacing", self.min_spacing)
        concrete.add_layout(form)
        layout.addWidget(concrete, 1, 0)

        factors = Card("Strength reduction factors")
        fform = QFormLayout()
        self.phi_flexure = dspin(0.5, 1.0, 0.90, 2, 0.05)
        self.phi_shear = dspin(0.5, 1.0, 0.75, 2, 0.05)
        self.phi_bearing = dspin(0.4, 1.0, 0.65, 2, 0.05)
        fform.addRow("Flexure phi", self.phi_flexure)
        fform.addRow("Shear phi", self.phi_shear)
        fform.addRow("Bearing phi", self.phi_bearing)
        factors.add_layout(fform)
        factors.add(QLineEdit("BNBC 2020 Part 6, Clause 6.2.3.2: 0.90 flexure, "
                              "0.75 shear, 0.65 bearing."))
        layout.addWidget(factors, 1, 1)
        layout.setRowStretch(2, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

    def load_project(self, project: Project) -> None:
        m = project.materials
        self._system = system_of(project)
        s = self._system
        set_spin(self.f_c, m.f_c, "stress", s)
        set_spin(self.f_y, m.f_y, "stress", s)
        set_spin(self.gamma, m.gamma_concrete, "unit_weight", s)
        set_spin(self.cover, m.cover, "length_mm", s)
        self.bar_label.setText(f"Bar diameters ({label('length_mm', s)})")
        self.bars.setText(format_list(m.bar_diameters, "length_mm", s))
        set_spin(self.max_spacing, m.max_bar_spacing, "length_mm", s)
        set_spin(self.min_spacing, m.min_bar_spacing, "length_mm", s)
        self.phi_flexure.setValue(m.phi_flexure)
        self.phi_shear.setValue(m.phi_shear)
        self.phi_bearing.setValue(m.phi_bearing)

    def apply_to_project(self, project: Project) -> None:
        m = project.materials
        s = self._system
        m.f_c = get_spin(self.f_c, "stress", s)
        m.f_y = get_spin(self.f_y, "stress", s)
        m.gamma_concrete = get_spin(self.gamma, "unit_weight", s)
        m.concrete_unit_weight = m.gamma_concrete
        m.cover = get_spin(self.cover, "length_mm", s)
        diameters = parse_list(self.bars.text(), "length_mm", s)
        m.bar_diameters = diameters or [12.0, 16.0, 20.0, 25.0]
        m.max_bar_spacing = get_spin(self.max_spacing, "length_mm", s)
        m.min_bar_spacing = get_spin(self.min_spacing, "length_mm", s)
        m.phi_flexure = self.phi_flexure.value()
        m.phi_shear = self.phi_shear.value()
        m.phi_bearing = self.phi_bearing.value()
