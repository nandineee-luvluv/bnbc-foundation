"""Columns, shear walls and reaction page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..common import Card, SectionTitle, item, make_table, num, text
from ...core.models import Element, Project, Reaction
from ...core.units import convert, label, system_of, to_si
from ...core.report import (
    import_elements_csv,
    import_elements_excel,
    import_reactions_csv,
)


def loads_headers(system: str = "SI") -> list[str]:
    length = label("length", system)
    force = label("force", system)
    moment = label("moment", system)
    return [
        "ID", "Kind", f"X ({length})", f"Y ({length})", f"dx ({length})", f"dy ({length})", "Shape",
        f"L ({length})", f"W ({length})", f"Dia. ({length})", "Rot. (deg)",
        f"Wall x1 ({length})", f"Wall y1 ({length})",
        f"Wall x2 ({length})", f"Wall y2 ({length})",
        f"Wall t ({length})", f"Base elev. ({length})", "Preferred", "Lateral",
        f"Service P ({force})", f"Service Mx ({moment})",
        f"Service My ({moment})", f"Service Vx ({force})", f"Service Vy ({force})",
        f"Factored P ({force})", f"Factored Mx ({moment})",
        f"Factored My ({moment})", f"Factored Vx ({force})", f"Factored Vy ({force})",
        "Notes",
    ]


HEADERS = loads_headers("SI")

# Column indexes used by the table <-> Element conversion.
ID_COL = 0
KIND_COL = 1
X_COL = 2
Y_COL = 3
DX_COL = 4
DY_COL = 5
SHAPE_COL = 6
LENGTH_COL = 7
WIDTH_COL = 8
DIAMETER_COL = 9
ROTATION_COL = 10
X1_COL = 11
Y1_COL = 12
X2_COL = 13
Y2_COL = 14
WALL_T_COL = 15
BASE_COL = 16
PREFERRED_COL = 17
LATERAL_COL = 18
SERVICE_P_COL = 19
SERVICE_MX_COL = 20
SERVICE_MY_COL = 21
SERVICE_VX_COL = 22
SERVICE_VY_COL = 23
FACTORED_P_COL = 24
FACTORED_MX_COL = 25
FACTORED_MY_COL = 26
FACTORED_VX_COL = 27
FACTORED_VY_COL = 28
NOTES_COL = 29


class LoadCaseDialog(QDialog):
    """Edit raw DL/LL/WL/EQ or other load cases for one element."""

    def __init__(self, element: Element, parent=None, system: str = "SI"):
        super().__init__(parent)
        self.setWindowTitle(f"Load cases - {element.id}")
        self.resize(760, 420)
        self.element = element
        self._system = system
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Enter separate load cases (DL, LL, WL, EQ, ...). The engine will generate "
            "BNBC service and strength combinations. Leave the table empty to use the "
            "combined service/factored values on the main page."
        ))
        self.table = make_table(
            ["Case", f"P ({label('force', system)})",
             f"Mx ({label('moment', system)})", f"My ({label('moment', system)})",
             f"Vx ({label('force', system)})", f"Vy ({label('force', system)})",
             "Factored", "Includes lateral"]
        )
        self.table.setMinimumHeight(240)
        for r in element.reactions:
            self._add_row(r)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        add = QPushButton("Add case")
        template = QPushButton("Add DL/LL/WL/EQ")
        remove = QPushButton("Remove")
        add.setObjectName("Secondary")
        template.setObjectName("Secondary")
        remove.setObjectName("Secondary")
        buttons.addWidget(add)
        buttons.addWidget(template)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        add.clicked.connect(lambda: self._add_row(Reaction("D")))
        template.clicked.connect(self._add_template)
        remove.clicked.connect(self._remove)

    def _add_row(self, r: Reaction) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            r.case,
            convert(r.P, "force", self._system),
            convert(r.Mx, "moment", self._system),
            convert(r.My, "moment", self._system),
            convert(r.Vx, "force", self._system),
            convert(r.Vy, "force", self._system),
            "Yes" if r.factored else "No",
            "Yes" if r.includes_lateral else "No",
        ]
        for col, value in enumerate(values):
            self.table.setItem(row, col, item(value))

    def _add_template(self) -> None:
        for name in ("DL", "LL", "WL", "EQ"):
            self._add_row(Reaction(name, 0.0, 0.0, 0.0, 0.0, 0.0))

    def _remove(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def reactions(self) -> list[Reaction]:
        out: list[Reaction] = []
        for row in range(self.table.rowCount()):
            case = text(self.table.item(row, 0), "Service")
            p = to_si(num(self.table.item(row, 1)), "force", self._system)
            mx = to_si(num(self.table.item(row, 2)), "moment", self._system)
            my = to_si(num(self.table.item(row, 3)), "moment", self._system)
            vx = to_si(num(self.table.item(row, 4)), "force", self._system)
            vy = to_si(num(self.table.item(row, 5)), "force", self._system)
            factored = text(self.table.item(row, 6), "No").lower() in ("yes", "y", "true", "1")
            lateral = text(self.table.item(row, 7), "No").lower() in ("yes", "y", "true", "1")
            out.append(Reaction(case, p, mx, my, vx, vy,
                                factored=factored, includes_lateral=lateral))
        return out


class LoadsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._custom_reactions: dict[str, list[Reaction]] = {}
        self._project: Project | None = None
        self._system = "SI"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(SectionTitle("Columns, shear walls and base reactions"))

        toolbar = Card("Elements")
        row = QHBoxLayout()
        self.btn_add_col = QPushButton("Add column")
        self.btn_add_wall = QPushButton("Add shear wall")
        self.btn_del = QPushButton("Remove selected")
        self.btn_del.setObjectName("Danger")
        self.btn_cases = QPushButton("Edit load cases...")
        self.btn_cases.setObjectName("Secondary")
        self.btn_import = QPushButton("Import Excel/CSV...")
        self.btn_import.setObjectName("Secondary")
        self.btn_reactions = QPushButton("Import ETABS/SAFE reactions...")
        self.btn_reactions.setObjectName("Secondary")
        for b in (self.btn_add_col, self.btn_add_wall, self.btn_del,
                  self.btn_cases, self.btn_import, self.btn_reactions):
            row.addWidget(b)
        row.addStretch(1)
        toolbar.add_layout(row)
        layout.addWidget(toolbar)

        self.table = make_table(HEADERS, stretch_last=True)
        self.table.setMinimumHeight(420)
        layout.addWidget(self.table, 1)
        hint = QLabel(
            "X/Y is the column reaction or insertion point; dx/dy offset it to the "
            "column centre. Rectangular columns use L x W; circular columns set "
            "Shape = Circular and use Diameter. Walls use the Wall x1/y1-x2/y2 "
            "centreline endpoints and Wall t (blank endpoints fall back to X/Y, "
            "Length and Wall t). Service/factored columns accept pre-combined "
            "envelopes; use 'Edit load cases...' for separate DL/LL/WL/EQ reactions. "
            "Positive P is compression; values use the selected display units."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.btn_add_col.clicked.connect(lambda: self._add_element("column"))
        self.btn_add_wall.clicked.connect(lambda: self._add_element("wall"))
        self.btn_del.clicked.connect(self._remove_selected)
        self.btn_cases.clicked.connect(self._edit_cases)
        self.btn_import.clicked.connect(self._import)
        self.btn_reactions.clicked.connect(self._import_reactions)

    def load_project(self, project: Project) -> None:
        self._project = project
        self._system = system_of(project)
        self.table.setHorizontalHeaderLabels(loads_headers(self._system))
        self.table.setRowCount(0)
        self._custom_reactions = {}
        for element in project.elements:
            self._add_row(element)
            if any(r.case not in ("Service", "Factored") for r in element.reactions):
                self._custom_reactions[element.id] = list(element.reactions)

    def _add_row(self, element: Element | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        # Display the raw (insertion-point) reactions.  The offset-to-centre
        # transformation is applied by the design engine, not by the editor.
        raw = list(element.reactions) if element else []
        service = max(
            (r for r in raw if not r.factored),
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
            default=Reaction(),
        )
        factored_candidates = [r for r in raw if r.factored]
        factored = max(
            factored_candidates,
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
            default=Reaction(),
        )
        has_factored = bool(factored_candidates)
        s = self._system
        values = [
            element.id if element else f"C{row + 1}",
            element.kind if element else "column",
            convert(element.x, "length", s) if element else 0.0,
            convert(element.y, "length", s) if element else 0.0,
            convert(element.dx, "length", s) if element else 0.0,
            convert(element.dy, "length", s) if element else 0.0,
            element.shape if element else "Rectangular",
            convert(element.length, "length", s) if element else convert(0.45, "length", s),
            convert(element.width, "length", s) if element else convert(0.45, "length", s),
            convert(element.diameter, "length", s) if element else 0.0,
            element.rotation if element else 0.0,
            "" if element is None or element.x1 is None else convert(element.x1, "length", s),
            "" if element is None or element.y1 is None else convert(element.y1, "length", s),
            "" if element is None or element.x2 is None else convert(element.x2, "length", s),
            "" if element is None or element.y2 is None else convert(element.y2, "length", s),
            convert(element.wall_thickness, "length", s) if element else convert(0.25, "length", s),
            convert(element.base_elev, "length", s) if element else 0.0,
            element.preferred if element else "Auto",
            "Yes" if service.includes_lateral else "No",
            convert(service.P, "force", s), convert(service.Mx, "moment", s),
            convert(service.My, "moment", s), convert(service.Vx, "force", s),
            convert(service.Vy, "force", s),
            convert(factored.P, "force", s) if has_factored else 0.0,
            convert(factored.Mx, "moment", s) if has_factored else 0.0,
            convert(factored.My, "moment", s) if has_factored else 0.0,
            convert(factored.Vx, "force", s) if has_factored else 0.0,
            convert(factored.Vy, "force", s) if has_factored else 0.0,
            element.notes if element else "",
        ]
        for col, value in enumerate(values):
            self.table.setItem(row, col, item(value))

    def _add_element(self, kind: str) -> None:
        row = self.table.rowCount()
        s = self._system
        if kind == "column":
            values = [
                f"C{row + 1}", "column", 0.0, 0.0, 0.0, 0.0,
                "Rectangular", convert(0.45, "length", s), convert(0.45, "length", s),
                0.0, 0.0, "", "", "", "", convert(0.25, "length", s),
                0.0, "Auto", "No",
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, "",
            ]
        else:
            values = [
                f"W{row + 1}", "wall", 0.0, 0.0, 0.0, 0.0,
                "Rectangular", convert(3.0, "length", s), convert(0.25, "length", s),
                0.0, 0.0, "", "", "", "", convert(0.25, "length", s),
                0.0, "Auto", "No",
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, "",
            ]
        self.table.insertRow(row)
        for col, value in enumerate(values):
            self.table.setItem(row, col, item(value))
        self.table.selectRow(row)

    def _remove_selected(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            element_id = text(self.table.item(row, ID_COL))
            self._custom_reactions.pop(element_id, None)
            self.table.removeRow(row)

    def _edit_cases(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if len(rows) != 1:
            QMessageBox.information(self, "Load cases", "Select exactly one element first.")
            return
        row = rows[0]
        element = self._element_from_row(row)
        dialog = LoadCaseDialog(element, self, self._system)
        if dialog.exec() == QDialog.Accepted:
            reactions = dialog.reactions()
            if reactions:
                self._custom_reactions[element.id] = reactions
                service = max(
                    (r for r in reactions if not r.factored),
                    key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
                    default=Reaction(),
                )
                for col, value_ in zip(
                    range(SERVICE_P_COL, SERVICE_VY_COL + 1),
                    (service.P, service.Mx, service.My, service.Vx, service.Vy),
                ):
                    quantity = "force" if col in (SERVICE_P_COL, SERVICE_VX_COL, SERVICE_VY_COL) else "moment"
                    self.table.item(row, col).setText(
                        str(round(convert(value_, quantity, self._system), 4))
                    )
                self.table.item(row, LATERAL_COL).setText(
                    "Yes" if service.includes_lateral else "No"
                )
                factored_candidates = [r for r in reactions if r.factored]
                if factored_candidates:
                    factored = max(
                        factored_candidates,
                        key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
                    )
                    for col, value_ in zip(
                        range(FACTORED_P_COL, FACTORED_VY_COL + 1),
                        (factored.P, factored.Mx, factored.My, factored.Vx, factored.Vy),
                    ):
                        quantity = "force" if col in (FACTORED_P_COL, FACTORED_VX_COL, FACTORED_VY_COL) else "moment"
                        self.table.item(row, col).setText(
                            str(round(convert(value_, quantity, self._system), 4))
                        )
                else:
                    for col in range(FACTORED_P_COL, FACTORED_VY_COL + 1):
                        self.table.item(row, col).setText("0.0")
            else:
                self._custom_reactions.pop(element.id, None)

    def _optional_num_cell(self, row: int, col: int) -> float | None:
        value = text(self.table.item(row, col))
        return (
            to_si(num(self.table.item(row, col)), "length", self._system)
            if value else None
        )

    def _element_from_row(self, row: int) -> Element:
        element_id = text(self.table.item(row, ID_COL), f"C{row + 1}")
        kind = text(self.table.item(row, KIND_COL), "column").lower()
        if kind not in ("column", "wall"):
            kind = "wall" if "wall" in kind else "column"
        lateral = text(self.table.item(row, LATERAL_COL), "No").lower() in (
            "yes", "y", "true", "1"
        )
        s = self._system
        service = Reaction(
            "Service",
            to_si(num(self.table.item(row, SERVICE_P_COL)), "force", s),
            to_si(num(self.table.item(row, SERVICE_MX_COL)), "moment", s),
            to_si(num(self.table.item(row, SERVICE_MY_COL)), "moment", s),
            to_si(num(self.table.item(row, SERVICE_VX_COL)), "force", s),
            to_si(num(self.table.item(row, SERVICE_VY_COL)), "force", s),
            includes_lateral=lateral,
        )
        fp = to_si(num(self.table.item(row, FACTORED_P_COL)), "force", s)
        fmx = to_si(num(self.table.item(row, FACTORED_MX_COL)), "moment", s)
        fmy = to_si(num(self.table.item(row, FACTORED_MY_COL)), "moment", s)
        fvx = to_si(num(self.table.item(row, FACTORED_VX_COL)), "force", s)
        fvy = to_si(num(self.table.item(row, FACTORED_VY_COL)), "force", s)
        reactions = list(self._custom_reactions.get(element_id, []))
        if not reactions:
            reactions = [service]
            if any(abs(v) > 1e-9 for v in (fp, fmx, fmy, fvx, fvy)):
                reactions.append(Reaction(
                    "Factored", fp, fmx, fmy, fvx, fvy,
                    factored=True, includes_lateral=lateral,
                ))
        shape = text(self.table.item(row, SHAPE_COL), "Rectangular")
        if "circ" in shape.lower() or "round" in shape.lower():
            shape = "Circular"
        else:
            shape = "Rectangular"
        return Element(
            id=element_id,
            kind=kind,
            x=to_si(num(self.table.item(row, X_COL)), "length", s),
            y=to_si(num(self.table.item(row, Y_COL)), "length", s),
            base_elev=to_si(num(self.table.item(row, BASE_COL)), "length", s),
            length=to_si(
                num(
                    self.table.item(row, LENGTH_COL),
                    0.45 if kind == "column" else 3.0,
                ),
                "length",
                s,
            ),
            width=to_si(
                num(
                    self.table.item(row, WIDTH_COL),
                    0.45 if kind == "column" else 0.25,
                ),
                "length",
                s,
            ),
            wall_thickness=to_si(
                num(self.table.item(row, WALL_T_COL), 0.25), "length", s
            ),
            preferred=text(self.table.item(row, PREFERRED_COL), "Auto"),
            reactions=reactions,
            notes=text(self.table.item(row, NOTES_COL)),
            dx=to_si(num(self.table.item(row, DX_COL)), "length", s),
            dy=to_si(num(self.table.item(row, DY_COL)), "length", s),
            shape=shape,
            diameter=to_si(num(self.table.item(row, DIAMETER_COL)), "length", s),
            rotation=num(self.table.item(row, ROTATION_COL)),
            x1=self._optional_num_cell(row, X1_COL),
            y1=self._optional_num_cell(row, Y1_COL),
            x2=self._optional_num_cell(row, X2_COL),
            y2=self._optional_num_cell(row, Y2_COL),
        )

    def apply_to_project(self, project: Project) -> None:
        elements: list[Element] = []
        for row in range(self.table.rowCount()):
            element = self._element_from_row(row)
            if not element.id:
                continue
            if any(e.id == element.id for e in elements):
                raise ValueError(f"Duplicate element ID: {element.id}")
            elements.append(element)
        project.elements = elements

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import columns and walls", "",
            "Excel/CSV (*.xlsx *.xlsm *.csv)"
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                elements = import_elements_csv(path)
            else:
                elements = import_elements_excel(path)
            if not elements:
                raise ValueError("No valid element rows were found.")
            self.table.setRowCount(0)
            self._custom_reactions = {}
            for e in elements:
                self._add_row(e)
                if any(r.case not in ("Service", "Factored") for r in e.reactions):
                    self._custom_reactions[e.id] = list(e.reactions)
            QMessageBox.information(self, "Import complete",
                                    f"Imported {len(elements)} elements.")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def _import_reactions(self) -> None:
        if self._project is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import ETABS/SAFE base reactions", "", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            self.apply_to_project(self._project)
            report = import_reactions_csv(self._project, path)
            by_id = {e.id: e for e in self._project.elements}
            for row in range(self.table.rowCount()):
                element_id = text(self.table.item(row, ID_COL), "")
                element = by_id.get(element_id)
                if element is None:
                    continue
                if element_id in report["matched"]:
                    self._custom_reactions[element_id] = list(element.reactions)
                    service = max(
                        (r for r in element.reactions if not r.factored),
                        key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
                        default=Reaction(),
                    )
                    for col, value in zip(
                        range(SERVICE_P_COL, SERVICE_VY_COL + 1),
                        (service.P, service.Mx, service.My, service.Vx, service.Vy),
                    ):
                        quantity = "force" if col in (SERVICE_P_COL, SERVICE_VX_COL, SERVICE_VY_COL) else "moment"
                        self.table.item(row, col).setText(
                            str(round(convert(value, quantity, self._system), 4))
                        )
                    self.table.item(row, LATERAL_COL).setText(
                        "Yes" if service.includes_lateral else "No"
                    )
                    factored_rows = [r for r in element.reactions if r.factored]
                    if factored_rows:
                        factored = max(
                            factored_rows,
                            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
                        )
                        for col, value in zip(
                            range(FACTORED_P_COL, FACTORED_VY_COL + 1),
                            (factored.P, factored.Mx, factored.My,
                             factored.Vx, factored.Vy),
                        ):
                            quantity = "force" if col in (FACTORED_P_COL, FACTORED_VX_COL, FACTORED_VY_COL) else "moment"
                            self.table.item(row, col).setText(
                                str(round(convert(value, quantity, self._system), 4))
                            )
            message = (
                f"Read {report['rows']} reaction rows for "
                f"{report['elements']} elements.\n"
                f"Load cases: {', '.join(report['cases']) or '-'}"
            )
            if report["unmatched"]:
                message += (
                    "\nUnmatched IDs: " + ", ".join(report["unmatched"][:20])
                )
            QMessageBox.information(self, "Reaction import complete", message)
        except Exception as exc:
            QMessageBox.critical(self, "Reaction import failed", str(exc))
