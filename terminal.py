

from PyQt4 import QtGui
from PyQt4.QtCore import pyqtSignal, Qt, QEvent

from libsyntyche import common

class Terminal(QtGui.QWidget):
    class TerminalInputBox(QtGui.QLineEdit):
        tab_pressed = pyqtSignal()
        reset_ac_suggestions = pyqtSignal()
        reset_history_travel = pyqtSignal()
        history_up = pyqtSignal()
        history_down = pyqtSignal()

        scroll_index = pyqtSignal(QtGui.QKeyEvent)

        # This has to be here, keyPressEvent does not capture tab press
        def event(self, event):
            if event.type() == QEvent.KeyPress and\
                        event.modifiers() == Qt.NoModifier:
                if event.key() == Qt.Key_Tab:
                    self.tab_pressed.emit()
                    return True
            return super().event(event)

        def keyPressEvent(self, event):
            if event.text() or event.key() in (Qt.Key_Left, Qt.Key_Right):
                QtGui.QLineEdit.keyPressEvent(self, event)
                self.reset_ac_suggestions.emit()
                self.reset_history_travel.emit()
            elif event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
                nev = QtGui.QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
                self.scroll_index.emit(nev)
            elif event.key() == Qt.Key_Up:
                self.history_up.emit()
            elif event.key() == Qt.Key_Down:
                self.history_down.emit()
            else:
                return super().keyPressEvent(event)

        def keyReleaseEvent(self, event):
            if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
                nev = QtGui.QKeyEvent(QEvent.KeyRelease, event.key(), Qt.NoModifier)
                self.scroll_index.emit(nev)
            else:
                return super().keyReleaseEvent(event)

    # This needs to be here for the stylesheet
    class TerminalOutputBox(QtGui.QLineEdit):
        pass

    filter_ = pyqtSignal(str)
    sort = pyqtSignal(str)
    open_ = pyqtSignal(str)
    edit = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.input_term = self.TerminalInputBox()
        self.output_term = self.TerminalOutputBox()
        self.output_term.setDisabled(True)

        layout.addWidget(self.input_term)
        layout.addWidget(self.output_term)

        self.input_term.setFocus()

        self.input_term.returnPressed.connect(self.parse_command)

    def setFocus(self):
        self.input_term.setFocus()

    def print_(self, msg):
        self.output_term.setText(str(msg))

    def error(self, msg):
        self.output_term.setText('Error: ' + msg)


    def parse_command(self):
        text = self.input_term.text().strip()
        if not text:
            return
        self.input_term.setText('')
        self.output_term.setText('')

        if text.isdigit():
            self.open_.emit(text)
            return

        command = text[0].lower()
        if command in self.commands:
            # Run command
            self.commands[command][0](self, text[1:].strip())
        else:
            self.error('No such command (? for help)')


    # ==== Commands ============================== #

    def cmd_filter(self, arg):
        self.filter_.emit(arg)

    def cmd_open(self, arg):
        self.open_.emit(arg)

    def cmd_edit(self, arg):
        self.edit.emit(arg)

    def cmd_sort(self, arg):
        self.sort.emit(arg)

    def cmd_help(self, arg):
        if not arg:
            self.print_(' '.join(sorted(self.commands)))
        elif arg in self.commands:
            self.print_(self.commands[arg][1])
        else:
            self.error('No such command')


    commands = {
        'f': (cmd_filter, 'Filter'),
        'o': (cmd_open, 'Open'),
        'e': (cmd_edit, 'Edit'),
        's': (cmd_sort, 'Sort'),
        '?': (cmd_help, 'Help')
    }

#   f - filter entries (filter on: tags, desc, name, author, length)
#   o - open entry
#   e - edit entry
#   s - sort entries
#
#   t - tags
#   n - name
#   d - description
#   a - author?
#
#   reset filter?
#   filter on no tags?