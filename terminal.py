from itertools import chain
from operator import itemgetter
import os.path
import re

from PyQt4 import QtGui
from PyQt4.QtCore import pyqtSignal, Qt, QEvent

from libsyntyche.common import read_file, local_path
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
    open_meta = pyqtSignal(str)
    list_ = pyqtSignal(str)
    new_entry = pyqtSignal(str)
    count_length = pyqtSignal(str)
    zoom = pyqtSignal(str)
    show_readme = pyqtSignal(str, str, str, str)

    def __init__(self, parent, get_tags):
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox)
        self.get_tags = get_tags
        self.autocomplete_type = '' # 'path' or 'tag'
        # These two are set in reload_settings() in sapfo.py
        self.rootpath = ''
        self.tagmacros = {}
        hotkeypairs = (
            ('zoom in', lambda: self.zoom.emit('in')),
            ('zoom out', lambda: self.zoom.emit('out')),
            ('reset zoom', lambda: self.zoom.emit('reset'))
        )
        self.hotkeys = {
            key: QtGui.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }

        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'x': (self.external_edit, 'Open in external program/editor'),
            'm': (self.open_meta, 'Open in meta viewer'),
            'l': (self.list_, 'List'),
            'n': (self.new_entry, 'New entry'),
            'c': (self.count_length, 'Count total length'),
            'h': (self.cmd_show_readme, 'Show readme')
        }

    def cmd_show_readme(self, arg):
        self.show_readme.emit('', local_path('README.md'), None, 'markdown')

    def update_settings(self, settings):
        self.rootpath = settings['path']
        self.tagmacros = settings['tag macros']
        # Terminal animation settings
        self.output_term.animate = settings['animate terminal output']
        interval = settings['terminal animation interval']
        if interval < 1:
            self.error('Too low animation interval')
        self.output_term.set_timer_interval(max(1, interval))
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))

    def command_parsing_injection(self, arg):
        if arg.isdigit():
            self.open_.emit(int(arg))
            return True

    def autocomplete(self, reverse):

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
            new_text = self.run_autocompletion(target_text, reverse)
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
                new_text = self.run_autocompletion(text[start:].lstrip(), reverse)
                self.prompt(text[:start] + ' ' + new_text)
            # If the cursor is within the tags' parentheses, autocomplete it as a tag
            else:
                autocomplete_tags(text, pos, '(),')


    def get_ac_suggestions(self, prefix):
        if self.autocomplete_type == 'tag':
            tags = next(zip(*sorted(self.get_tags(), key=itemgetter(1), reverse=True)))
            macros = ('@' + x for x in sorted(self.tagmacros.keys()))
            return [x for x in chain(tags, macros) if x.startswith(prefix)]
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
