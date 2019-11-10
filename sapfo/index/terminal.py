from pathlib import Path

from PyQt5 import QtWidgets

from libsyntyche import terminal


class Terminal(terminal.Terminal):

    def __init__(self, parent: QtWidgets.QWidget, history_file: Path) -> None:
        super().__init__(parent, short_mode=True,
                         history_file=history_file)
        self.output_field.hide()
