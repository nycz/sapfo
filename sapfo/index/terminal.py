from itertools import chain
from operator import itemgetter
import os
from pathlib import Path
import re
from typing import cast, Any, Callable, Dict, List, Optional, Tuple

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, Qt

from ..common import Settings
from ..terminal import (GenericTerminalInputBox,
                        GenericTerminalOutputBox, GenericTerminal)


class TerminalInputBox(GenericTerminalInputBox):
    scroll_index = pyqtSignal(str)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> Any:
        if event.modifiers() == Qt.ControlModifier \
                and event.key() in (Qt.Key_Up, Qt.Key_Down):
            # nev = QtGui.QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
            self.scroll_index.emit('up' if event.key() == Qt.Key_Up
                                   else 'down')
        else:
            return super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> Any:
        if event.modifiers() == Qt.ControlModifier \
                and event.key() in (Qt.Key_Up, Qt.Key_Down):
            pass
            # nev = QtGui.QKeyEvent(QEvent.KeyRelease, event.key(), Qt.NoModifier)
            # self.scroll_index.emit(nev)
        else:
            return super().keyReleaseEvent(event)


class HelpView(QtWidgets.QLabel):
    def __init__(self, parent: QtWidgets.QWidget,
                 commands: Dict[str, Tuple[Any, str]],
                 help_command: str) -> None:
        super().__init__(parent)
        self.command_help: Dict[str, Tuple[str, List[Tuple[str, str]]]] = {
            'f': ('Filter entries (aka show only entries matching the filter)',
                  [('', 'List the active filters.'),
                   ('-', 'Reset all filters.'),
                   ('[ndrtcbp]-', 'Reset the specified filter.'),
                   ('[ndrtcbp]', 'Don\'t apply any filter, instead set the '
                                 'terminal\'s input text to the specified '
                                 'filter\'s current value.'),
                   ('n', 'Filter on titles (case insensitive).'),
                   ('d', 'Filter on descriptions (case insensitive).'),
                   ('r', 'Filter on recaps (case insensitive).'),
                   ('t', 'Filter on tags. Supports AND (comma , ), '
                         'OR (vertical bar | ), NOT prefix (dash - ), and tag '
                         'macros (use @ as prefix) specified in the config. '
                         'AND and OR can\'t be used mixed without explicit '
                         'parentheses to specify precedence. Spaces are '
                         'allowed in tag names, but not (),| . Tags are case '
                         'sensitive.'),
                   ('[ndrt]_', 'Show only entries with this attribute empty.'),
                   ('[ndrt]*', 'Show no entries with this attribute empty.'),
                   ('c', 'Filter on wordcount. Supports the operators '
                         '> < >= <= followed by the target number. A "k" '
                         'suffix in the number is replaced by 000. Operator '
                         'expressions can be combined without any delimiters. '
                         'Eg.: >900<=50k'),
                   ('b', 'Filter on backstory wordcount. This uses '
                         'the same syntax as the wordcount filter.'),
                   ('p', 'Filter on number of backstory pages. This uses '
                         'the same syntax as the wordcount filter.')]),
            'e': ('Edit entry',
                  [('u', 'Undo last edit.'),
                   ('[ndrt]123', "Don't edit anything, instead set the "
                                 "terminal's input text to the current value "
                                 "of the specified attribute in entry 123."),
                   ('[ndr]123 text', 'Set the value of the specified '
                                     'attribute in entry 123 to "text".'),
                   ('r123-', 'Clear the recap in entry 123.'),
                   ('t123 tag1, tag2',
                    'Set the tags of entry 123 to tag1 and tag2. The list is '
                    'comma separated and all tags are stripped of '
                    'surrounding whitespace before saved.'),
                   ('t* tag1, tag2', 'Replace all instances of tag1 with '
                                     'tag2 in all visible entries.'),
                   ('t* tag1,', 'Remove all instances of tag1 '
                                'from all visible entries.'),
                   ('t* ,tag2', 'Add tag2 to all visible entries.')]),
            's': ('Sort entries',
                  [('[ncbpm][!<>]', 'Sort using the specified key and order.'),
                   ('n', 'Sort by title.'),
                   ('c', 'Sort by wordcount.'),
                   ('b', 'Sort by backstory wordcount.'),
                   ('p', 'Sort by number of backstory pages.'),
                   ('m', 'Sort by last modified date.'),
                   ('!', 'Reverse sort order.'),
                   ('<', 'Sort ascending.'),
                   ('>', 'Sort descending.')]),
            'q': ('Quit sapfo', []),
            'x': ('Open entry file in external editor.',
                  [('123', "Open entry 123's file (note: not sapfo's json "
                           "metadata file) in an external editor. "
                           "This is the same as entering 123 without any "
                           "command at all."),
                   ('foobar', "If there is only one entry with a name "
                              "\"foobar\", open that entry in an external "
                              "editor.")]),
            'm': ('Open backstory (meta) editor',
                  [('123', 'Open the backstory/meta editor for entry 123.')]),
            't': ('Manage tags',
                  [('', 'Hide tag list if visible, otherwise show '
                        'tag list in default order, sorted by usage count.'),
                   ('[ac]-[/tagname]', 'Show tags in reverse order.'),
                   ('a[-][/tagname]', 'Show tags alphabetically sorted.'),
                   ('c[-][/tagname]', 'Show tags sorted by usage count.'),
                   ('[ac][-]/tagname', 'Show tags that includes "tagname".'),
                   ('@', 'List tag macros.')]),
            'n': ('Create new entry',
                  [('(tag1, tag2, ..) path',
                    ('Create a new entry with the tags at the path. '
                     'The title is generate automatically from the path.'))]),
            'c': ('Show combined size of wordcount and more',
                  [('c', 'Show combined wordcount for all visible entries.'),
                   ('b', 'Show combined backstory wordcount '
                         'for all visible entries.'),
                   ('p', 'Show combined number of backstory pages '
                         'for all visible entries.')]),
            help_command: ('Show extended help',
                           [('', 'Toggle extended help view.'),
                            ('X', 'Show help for command X, which should be '
                             'one from the list below.')]),
            'l': ('Show terminal log',
                  [('', 'Toggle terminal log.')]),
        }

        def escape(s: str) -> str:
            return s.replace('<', '&lt;').replace('>', '&gt;')
        # TODO: make this into labels and widgets instead maybe?
        main_template = ('<h2 style="margin:0">{command}: {desc}</h2>'
                         '<hr><table>{rows}</table>')
        row_template = ('<tr><td><b>{command}{arg}</b></td>'
                        '<td style="padding-left:10px">{subdesc}</td></tr>')
        self.help_html = {
            command: main_template.format(
                command=command,
                desc=desc,
                rows=''.join(row_template.format(command=command,
                                                 arg=escape(arg),
                                                 subdesc=escape(subdesc))
                             for arg, subdesc in args)
            )
            for command, (desc, args) in self.command_help.items()
        }
        command_template = ('<div style="margin-left:5px">'
                            '<h3>List of commands</h3>'
                            '<table style="margin-top:2px">{}</table></div>')
        command_rows = (row_template.format(command=cmd, arg='', subdesc=desc)
                        for cmd, (_, desc) in sorted(commands.items()))
        self.help_html[help_command] += command_template.format(
            ''.join(command_rows))

        assert sorted(commands.keys()) == sorted(self.command_help.keys())
        self.setWordWrap(True)
        self.hide()

    def show_help(self, arg: str) -> bool:
        if arg not in self.help_html:
            return False
        self.setText(self.help_html[arg])
        return True


class Terminal(GenericTerminal):
    filter_ = pyqtSignal(str)
    sort = pyqtSignal(str)
    quit = pyqtSignal(str)
    edit = pyqtSignal(str)
    external_edit = pyqtSignal(str)
    open_meta = pyqtSignal(str)
    manage_tags = pyqtSignal(str)
    new_entry = pyqtSignal(str)
    count_length = pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget, settings: Settings,
                 get_tags: Callable, history_file: Path) -> None:
        super().__init__(parent, settings, TerminalInputBox,
                         GenericTerminalOutputBox, help_command='h',
                         history_file=history_file)
        self.output_term.hide()
        self.get_tags = get_tags
        self.autocomplete_type = ''  # 'path' or 'tag'
        self.rootpath = settings.path
        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            'x': (self.external_edit, 'Open in external program/editor'),
            'm': (self.open_meta, 'Open in meta viewer'),
            't': (self.manage_tags, 'Manage tags'),
            'n': (self.new_entry, 'New entry'),
            'c': (self.count_length, 'Count total length'),
            self.help_command: (self.cmd_show_extended_help, 'Show help'),
            'l': (self.cmd_toggle_log, 'Toggle terminal log'),
        }
        self.help_view = HelpView(self, self.commands, self.help_command)
        # Default to show help about itself
        self.help_view.show_help(self.help_command)
        cast(QtWidgets.QBoxLayout,
             self.layout()).insertWidget(0, self.help_view)

    def cmd_show_extended_help(self, arg: str) -> None:
        if not arg and self.help_view.isVisible():
            self.help_view.hide()
        else:
            success = self.help_view.show_help(arg or self.help_command)
            if success:
                self.help_view.show()
            else:
                self.error('Unknown command')
                self.help_view.hide()

    def command_parsing_injection(self, arg: str) -> Optional[bool]:
        if arg.isdigit():
            self.external_edit.emit(arg)
            return True
        return None

    def autocomplete(self, reverse: bool) -> None:
        def get_interval(t: str, pos: int, separators: str) -> Tuple[int, int]:
            """
            Return the interval of the string that is going to be autocompleted
            """
            start, end = 0, len(t)
            for n, i in enumerate(t):
                if n < pos and i in separators:
                    start = n + 1
                if n >= pos and i in separators:
                    end = n
                    break
            return start, end

        def autocomplete_tags(text: str, pos: int, separators: str,
                              prefix: str = '') -> None:
            self.autocomplete_type = 'tag'
            start, end = get_interval(text, pos, separators)

            ws_prefix, dash, target_text = re.match(r'(\s*)(-?)(.*)',  # type: ignore
                                                    text[start:end]).groups()
            new_text = self.run_autocompletion(target_text, reverse)
            output = (prefix + text[:start] + ws_prefix
                      + dash + new_text + text[end:])
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
            autocomplete_tags(payload, pos - len(prefix),
                              separators[prefix[0]], prefix=prefix)
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
                new_text = self.run_autocompletion(text[start:].lstrip(),
                                                   reverse)
                self.prompt(text[:start] + ' ' + new_text)
            # If the cursor is within the tags' parentheses,
            # then autocomplete it as a tag
            else:
                autocomplete_tags(text, pos, '(),')

    def get_ac_suggestions(self, prefix: str) -> List[str]:
        # TODO: tests, and then replace os.path with pathlib prolly
        if self.autocomplete_type == 'tag':
            tags = next(zip(*sorted(self.get_tags(),
                                    key=itemgetter(1), reverse=True)))
            macros = ('@' + x for x in sorted(self.settings.tag_macros.keys()))
            return [x for x in chain(tags, macros) if x.startswith(prefix)]
        elif self.autocomplete_type == 'path':
            root = self.rootpath / (prefix or ' ')
            if not root.parent.is_dir():
                return []
            suggestions = [root.parent / p
                           for p in sorted(os.listdir(root.parent))
                           if p.lower().startswith(root.name.rstrip().lower())]
            # Remove the root prefix and add a / at the end if it's a directory
            return [p.name + (os.sep * p.is_dir())
                    for p in suggestions]
        return []
