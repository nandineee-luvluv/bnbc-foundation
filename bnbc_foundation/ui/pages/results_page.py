"""Results, schedule, detail and site-plan page."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..common import Card, SectionTitle, error_color, make_table
from ...core.models import Project
from ...core.report import SCHEDULE_HEADERS, plan_shape, schedule_headers, selected_results
from ...core.units import convert, convert_text, label, system_of

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Circle, Polygon as MplPolygon, Rectangle
except Exception:  # pragma: no cover
    FigureCanvasQTAgg = None
    Figure = None
    Rectangle = None
    MplPolygon = None
    Circle = None


class ResultsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._results = []
        self._system = "SI"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(SectionTitle("Design results"))

        cards = QHBoxLayout()
        self.card_ok = self._summary_card("OK", "0", "#C6EFCE")
        self.card_check = self._summary_card("CHECK", "0", "#FFEB9C")
        self.card_fail = self._summary_card("FAIL", "0", "#FFC7CE")
        self.card_count = self._summary_card("Foundations", "0", "#DDEBF7")
        self.card_concrete = self._summary_card("Concrete, m3", "0", "#E2EFDA")
        self.card_steel = self._summary_card("Steel, kg", "0", "#FFF2CC")
        self.card_pile = self._summary_card("Piles, m", "0", "#E4DFEC")
        for card in (self.card_ok, self.card_check, self.card_fail, self.card_count,
                     self.card_concrete, self.card_steel, self.card_pile):
            cards.addWidget(card)
        layout.addLayout(cards)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        schedule_tab = QWidget()
        sl = QVBoxLayout(schedule_tab)
        sl.setContentsMargins(0, 6, 0, 0)
        splitter = QSplitter(Qt.Vertical)
        self.table = make_table(SCHEDULE_HEADERS)
        for i, width in enumerate([70, 60, 120, 240, 45, 240, 80, 70, 70, 55,
                                   150, 65, 65, 65, 85, 160, 65, 240]):
            self.table.setColumnWidth(i, width)
        self.table.setMinimumHeight(230)
        splitter.addWidget(self.table)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        sl.addWidget(splitter)
        self.tabs.addTab(schedule_tab, "Foundation schedule")

        plan_tab = QWidget()
        pl = QVBoxLayout(plan_tab)
        pl.setContentsMargins(0, 6, 0, 0)
        if FigureCanvasQTAgg is not None:
            self.figure = Figure(figsize=(8.0, 5.0))
            self.canvas = FigureCanvasQTAgg(self.figure)
            pl.addWidget(self.canvas)
        else:
            self.canvas = None
            pl.addWidget(QLabel("matplotlib is not available"))
        self.tabs.addTab(plan_tab, "Site plan")

        warnings_tab = QWidget()
        wl = QVBoxLayout(warnings_tab)
        wl.setContentsMargins(0, 6, 0, 0)
        self.warnings = QTextEdit()
        self.warnings.setReadOnly(True)
        wl.addWidget(self.warnings)
        self.tabs.addTab(warnings_tab, "Warnings")

        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.cellDoubleClicked.connect(lambda *_: self._show_detail())

    @staticmethod
    def _summary_card(title: str, value: str, color: str) -> Card:
        card = Card()
        card.setStyleSheet(f"QFrame#Card {{ background: {color}; border: none; border-radius: 8px; }}")
        label = QLabel(title.upper())
        label.setStyleSheet("font-size: 9px; color: #44546A; font-weight: bold;")
        number = QLabel(value)
        number.setStyleSheet("font-size: 20px; color: #1F4E79; font-weight: bold;")
        card.add(label)
        card.add(number)
        card.title_label = label
        card.number_label = number
        return card

    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._results = []
        self.table.setRowCount(0)
        self.detail.clear()
        self.warnings.clear()
        for card in (self.card_ok, self.card_check, self.card_fail, self.card_count,
                     self.card_concrete, self.card_steel, self.card_pile):
            card.number_label.setText("0")
        if self.canvas is not None:
            self.figure.clear()
            self.canvas.draw_idle()

    def show_results(self, project: Project) -> None:
        self._results = selected_results(project)
        self._system = system_of(project)
        s = self._system
        results = self._results
        ok = sum(1 for r in results if r.status == "OK")
        check = sum(1 for r in results if r.status == "CHECK")
        fail = sum(1 for r in results if r.status == "FAIL")
        self.card_ok.number_label.setText(str(ok))
        self.card_check.number_label.setText(str(check))
        self.card_fail.number_label.setText(str(fail))
        self.card_count.number_label.setText(str(len(results)))
        self.card_concrete.title_label.setText(f"CONCRETE, {label('volume', s)}")
        self.card_concrete.number_label.setText(
            f"{convert(sum(r.concrete_volume for r in results), 'volume', s):.1f}"
        )
        self.card_steel.title_label.setText(f"STEEL, {label('mass', s)}")
        self.card_steel.number_label.setText(
            f"{convert(sum(r.steel_weight for r in results), 'mass', s):.0f}"
        )
        self.card_pile.title_label.setText(f"PILES, {label('length', s)}")
        self.card_pile.number_label.setText(
            f"{convert(sum(r.pile_length_total for r in results), 'length', s):.0f}"
        )

        for col, header in enumerate(schedule_headers(project)):
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(header))
        self.table.setRowCount(0)
        for result in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(result.schedule_row(s)):
                cell = QTableWidgetItem("" if value is None else str(value))
                cell.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                cell.setToolTip(cell.text())
                self.table.setItem(row, col, cell)
            self.table.item(row, 16).setBackground(error_color(result.status))
            self.table.item(row, 0).setBackground(QColor("#DDEBF7"))
            self.table.setRowHeight(row, 36)
        self.warnings.setPlainText(
            "\n".join(f"- {w}" for w in (project.warnings or []))
            or "No warnings."
        )
        if results:
            self.table.selectRow(0)
            self._show_detail()
        self._plot(project)

    def _show_detail(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows or rows[0] >= len(self._results):
            return
        r = self._results[rows[0]]
        s = self._system
        checks = r.details.get("checks", {}) or {}
        rows_html = "".join(
            f"<tr><td style='padding:3px 8px;color:#667085'>{escape(str(k))}</td>"
            f"<td style='padding:3px 8px'>{escape(str(v))}</td></tr>"
            for k, v in checks.items()
        )
        alternatives = "".join(f"<li>{escape(a)}</li>" for a in r.alternatives)
        html = f"""
        <h2 style="color:#1F4E79;margin-bottom:2px">{escape(r.element_id)} &mdash; {escape(r.foundation_type)}</h2>
        <p style="color:#667085">{escape(convert_text(r.size, s))}</p>
        <table cellspacing="0" style="border-collapse:collapse">
          <tr><td style="padding:3px 8px;color:#667085">Status</td><td style="padding:3px 8px"><b>{escape(r.status)}</b></td></tr>
          <tr><td style="padding:3px 8px;color:#667085">Service load</td><td style="padding:3px 8px">{convert(r.service_load, 'force', s):.1f} {label('force', s)}</td></tr>
          <tr><td style="padding:3px 8px;color:#667085">Factored load</td><td style="padding:3px 8px">{convert(r.factored_load, 'force', s):.1f} {label('force', s)}</td></tr>
          <tr><td style="padding:3px 8px;color:#667085">q max / allow</td><td style="padding:3px 8px">{convert(r.q_service_max, 'pressure', s):.1f} / {convert(r.q_allow, 'pressure', s):.1f} {label('pressure', s)}</td></tr>
          <tr><td style="padding:3px 8px;color:#667085">Utilization</td><td style="padding:3px 8px">{r.utilization:.3f}</td></tr>
          <tr><td style="padding:3px 8px;color:#667085">Settlement</td><td style="padding:3px 8px">{convert(r.settlement, 'settlement', s):.1f} / {convert(r.settlement_limit, 'settlement', s):.1f} {label('settlement', s)}</td></tr>
          <tr><td style="padding:3px 8px;color:#667085">Governing</td><td style="padding:3px 8px">{escape(r.governing)}</td></tr>
        </table>
        <h3 style="color:#1F4E79;margin-bottom:2px">Requirement</h3>
        <p>{escape(convert_text(r.requirement, s))}</p>
        <h3 style="color:#1F4E79;margin-bottom:2px">Checks</h3>
        <table cellspacing="0" style="border-collapse:collapse">{rows_html}</table>
        <h3 style="color:#1F4E79;margin-bottom:2px">Remarks</h3>
        <p>{escape(convert_text(r.remarks, s) or "-")}</p>
        <h3 style="color:#1F4E79;margin-bottom:2px">Alternatives</h3>
        <ul>{alternatives or "<li>None</li>"}</ul>
        """
        self.detail.setHtml(html)

    def _plot(self, project: Project) -> None:
        if self.canvas is None:
            return
        s = self._system
        f = convert(1.0, "length", s)
        unit = label("length", s)
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        try:
            for e in project.elements:
                cx, cy = (v * f for v in e.center)
                shape, data = plan_shape(e)
                if shape == "circle":
                    ax.add_patch(Circle(
                        (data[0] * f, data[1] * f), data[2] * f, facecolor="#9DC3E6",
                        edgecolor="#1F4E79", alpha=0.75,
                    ))
                else:
                    ax.add_patch(MplPolygon(
                        [(p[0] * f, p[1] * f) for p in data], closed=True,
                        facecolor="#9DC3E6", edgecolor="#1F4E79", alpha=0.8,
                    ))
                if abs(e.x - e.center[0]) > 1e-9 or abs(e.y - e.center[1]) > 1e-9:
                    ax.plot(e.x * f, e.y * f, marker="+", color="#C00000", markersize=6)
                ax.text(cx, cy + 0.35 * f, e.id, ha="center", va="bottom", fontsize=7)
            for r in self._results:
                footprint = r.details.get("footprint")
                rect = r.details.get("rect")
                if r.element_kind == "raft":
                    continue
                if footprint:
                    ax.add_patch(MplPolygon(
                        [(p[0] * f, p[1] * f) for p in footprint], closed=True, fill=False,
                        linestyle="--", linewidth=0.8, edgecolor="#C00000",
                    ))
                elif rect:
                    x0, y0, x1, y1 = rect
                    ax.add_patch(Rectangle((x0 * f, y0 * f), (x1 - x0) * f, (y1 - y0) * f,
                                           fill=False, linestyle="--", linewidth=0.8,
                                           edgecolor="#C00000"))
            o = project.options
            if o.site_xmax - o.site_xmin < 5000 and o.site_ymax - o.site_ymin < 5000:
                ax.add_patch(Rectangle((o.site_xmin * f, o.site_ymin * f),
                                       (o.site_xmax - o.site_xmin) * f,
                                       (o.site_ymax - o.site_ymin) * f,
                                       fill=False, linestyle=":", linewidth=1.3,
                                       edgecolor="#548235"))
            for bh in project.boreholes:
                ax.plot(bh.x * f, bh.y * f, marker="v", color="#7030A0", markersize=7)
                ax.text(bh.x * f, (bh.y - 0.5) * f, bh.id, ha="center", fontsize=7,
                        color="#7030A0")
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xlabel(f"x ({unit})")
            ax.set_ylabel(f"y ({unit})")
            ax.set_title("Site plan and selected foundation outlines")
            ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.6)
            self.figure.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()
