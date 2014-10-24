from operator import itemgetter
import re

from PyQt4 import QtGui
from PyQt4.QtCore import pyqtSignal, Qt, QEvent

from libsyntyche.terminal import GenericTerminalInputBox, GenericTerminalOutputBox, GenericTerminal


class TerminalInputBox(GenericTerminalInputBox):
    scroll_index = pyqtSignal(QtGui.QKeyEvent)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
            nev = QtGui.QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
            self.scroll_index.emit(nev)
        else:
            return super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
            nev = QtGui.QKeyEvent(QEvent.KeyRelease, event.key(), Qt.NoModifier)
            self.scroll_index.emit(nev)
        else:
            return super().keyReleaseEvent(event)


class Terminal(GenericTerminal):
    filter_ = pyqtSignal(str)
    sort = pyqtSignal(str)
    open_ = pyqtSignal(int)
    quit = pyqtSignal(str)
    edit = pyqtSignal(str)
    external_edit = pyqtSignal(str)
    list_ = pyqtSignal(str)
    count_length = pyqtSignal(str)

    def __init__(self, parent, get_tags):
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox)
        self.get_tags = get_tags
        self.autocomplete_type = '' # 'path' or 'tag'

        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'x': (self.external_edit, 'Open in external program/editor'),
            'l': (self.list_, 'List'),
            'c': (self.count_length, 'Count total length')
        }

    def command_parsing_injection(self, arg):
        if arg.isdigit():
            self.open_.emit(int(arg))
            return True

    def autocomplete(self):

        def get_interval(t, pos, separators):
            """ Return the interval of the string that is going to be autocompleted """
            start, end = 0, len(t)
            for n,i in enumerate(t):
                if n < pos and i in separators:
                    start = n + 1
                if n >= pos and i in separators:
                    end = n
                    break
            return start, end

        def autocomplete_tags(text, pos, separators, prefix=''):
            self.autocomplete_type = 'tag'
            start, end = get_interval(text, pos, separators)
            ws_prefix, dash, target_text = re.match(r'(\s*)(-?)(.*)',text[start:end]).groups()
            new_text = self.run_autocompletion(target_text)
            output = prefix + text[:start] + ws_prefix + dash + new_text + text[end:]
            self.prompt(output)
            self.input_term.setCursorPosition(len(output) - len(text[end:]))

        text = self.input_term.text()
        pos = self.input_term.cursorPosition()

        # Auto complete the ft and the et command
        tabsep_rx = re.match(r'(ft|et\*|et\d+\s*)(.*)', text)
        if tabsep_rx:
            prefix, payload = tabsep_rx.groups()
            if pos < len(prefix):
                return
            separators = {'f': '(),|', 'e': ','}
            autocomplete_tags(payload, pos - len(prefix), separators[prefix[0]], prefix=prefix)


    def get_ac_suggestions(self, prefix):
        if self.autocomplete_type == 'tag':
            tags = list(zip(*sorted(self.get_tags(), key=itemgetter(1), reverse=True)))[0]
            return [x for x in tags if x.startswith(prefix)]
