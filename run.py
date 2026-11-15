#!/usr/bin/env python3
"""Launch the BNBC 2020 foundation design desktop application."""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BNBC 2020 foundation designer")
    parser.add_argument("--project", help="JSON project file to open at start-up")
    parser.add_argument("--smoke", action="store_true", help="start, process events and quit")
    args = parser.parse_args(argv)

    # Allow running from a headless terminal/test harness.
    if args.smoke and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtWidgets import QApplication

    from bnbc_foundation.core.models import sample_project
    from bnbc_foundation.core.report import load_project
    from bnbc_foundation.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv if argv is None else ["bnbc-foundation"])
    project = load_project(args.project) if args.project else sample_project()
    window = MainWindow(project)
    window.show()
    if args.smoke:
        app.processEvents()
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
