"""MAKEMAP — Entry point."""

import sys
import os
from pathlib import Path

os.environ["QT_LOGGING_RULES"] = "*.warning=false;*.debug=false"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import qInstallMessageHandler  # noqa: E402

qInstallMessageHandler(lambda *_: None)

from src.app.application import Application  # noqa: E402


def main():
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
