from operator import itemgetter
import os.path
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
    new_entry = pyqtSignal(str)
    count_length = pyqtSignal(str)

    def __init__(self, parent, get_tags):
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox)
        self.get_tags = get_tags
        self.rootpath = ''
        self.autocomplete_type = '' # 'path' or 'tag'

        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'x': (self.external_edit, 'Open in external program/editor'),
            'l': (self.list_, 'List'),
            'n': (self.new_entry, 'New entry'),
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
        # Autocomplete the n command
        elif re.match(r'n\s*\([^\(]*?(\)\s*.*)?$', text):
            taggroup_pos_start = text.find('(') + 1
            taggroup_pos_end = text.find(')') if ')' in text else len(text)
            if pos < taggroup_pos_start:
                return
            # If the cursor is right of the ), autocomplete it as a path
            if pos > taggroup_pos_end:
                self.autocomplete_type = 'path'
                start = taggroup_pos_end + 1
                new_text = self.run_autocompletion(text[start:].lstrip())
                self.prompt(text[:start] + ' ' + new_text)
            # If the cursor is within the tags' parentheses, autocomplete it as a tag
            else:
                autocomplete_tags(text, pos, '(),')


    def get_ac_suggestions(self, prefix):
        if self.autocomplete_type == 'tag':
            tags = list(zip(*sorted(self.get_tags(), key=itemgetter(1), reverse=True)))[0]
            return [x for x in tags if x.startswith(prefix)]
        elif self.autocomplete_type == 'path':
            root = os.path.expanduser(self.rootpath)
            dirpath, namepart = os.path.split(os.path.join(root, prefix))
            if not os.path.isdir(dirpath):
                return []
            suggestions = [os.path.join(dirpath, p) for p in sorted(os.listdir(dirpath))
                           if p.lower().startswith(namepart.lower())]
            # Remove the root prefix and add a / at the end if it's a directory
            return [p.replace(root, '', 1).lstrip(os.path.sep) + (os.path.sep*os.path.isdir(p))
                    for p in suggestions]
