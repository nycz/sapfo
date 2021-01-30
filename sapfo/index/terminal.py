from pathlib import Path

from libsyntyche import terminal
from PyQt5 import QtWidgets


class Terminal(terminal.Terminal):

    def __init__(self, parent: QtWidgets.QWidget, history_file: Path) -> None:
        super().__init__(parent, history_file=history_file)
        self.output_field.hide()
