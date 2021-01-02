from collections import Counter
import json
from operator import itemgetter
import os.path
from pathlib import Path
import pickle
import re
import subprocess
from typing import Any, Callable, Dict, List, Match, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets
from PyQt5.QtCore import pyqtProperty, pyqtSignal, Qt
from PyQt5.QtGui import QColor

from libsyntyche.cli import ArgumentRules, AutocompletionPattern, Command
from libsyntyche.terminal import MessageTray

from . import tagsystem
from .common import (ActiveFilters, LOCAL_DIR, Settings, SortBy,
                     STATE_FILTER_KEY, STATE_SORT_KEY)
from .declarative import hbox, label, Stretch, vbox
from .index.entrylist import EntryList, index_stories
from .index.taginfolist import TagInfoList
from .index.terminal import Terminal
from .taggedlist import AttrNames, make_abbrev_dict, NONEMPTY_SEARCH


class IconWidget(QtSvg.QSvgWidget):
    def __init__(self, name: str, resolution: int,
                 parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(QtCore.QSize(resolution, resolution))
        path = LOCAL_DIR / 'data' / f'{name}.svg'
        with open(path, 'rb') as f:
            self.base_data = f.read()
        self._color: QColor = QColor()
        self.color = QColor(Qt.white)

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, color: QColor) -> None:
        if self._color == color:
            return
        r = color.red()
        g = color.green()
        b = color.blue()
        hex_color = f'#{r:0>2x}{g:0>2x}{b:0>2x}'.encode()
        base = self.base_data.replace(b'stroke="currentColor"',
                                      b'stroke="' + hex_color + b'"')
        self._color = color
        self.load(base)


class StatusBar(QtWidgets.QFrame):
    moved = pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.filter_icon = IconWidget('filter', 13, self)
        self.filter_icon.setObjectName('status_filter_icon')
        self.sort_label = label('', 'status_sort_label', parent=self)
        self.filter_label = label('', 'status_filter_label', parent=self)
        self.count_label = label('', 'status_count_label', parent=self)
        self.setLayout(hbox(Stretch,
                            self.sort_label,
                            label('•', 'status_separator'),
                            self.filter_icon,
                            self.filter_label,
                            label('•', 'status_separator'),
                            self.count_label,
                            Stretch))

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        self.moved.emit()

    @pyqtProperty(int)
    def icon_size(self) -> int:
        return self.filter_icon.width()

    @icon_size.setter  # type: ignore
    def icon_size(self, size: int) -> None:
        self.filter_icon.setFixedSize(QtCore.QSize(size, size))

    @pyqtProperty(QColor)
    def icon_color(self) -> QColor:
        return self.filter_icon.color

    @icon_color.setter  # type: ignore
    def icon_color(self, color: QColor) -> None:
        self.filter_icon.color = color

    def update_counts(self, visible_count: int, count: int) -> None:
        self.count_label.setText(f'{visible_count}/{count} entries visible')

    def set_filter_info(self, filters: ActiveFilters) -> None:
        active_filters = []
        for cmd, payload in filters._asdict().items():
            if payload is None:
                continue
            if cmd in {AttrNames.DESCRIPTION.name,
                       AttrNames.TITLE.name,
                       AttrNames.RECAP.name}:
                if payload == '':
                    payload = '<empty>'
                elif payload == NONEMPTY_SEARCH:
                    payload = '<nonempty>'
            active_filters.append(f'{cmd}: {payload}')
        if active_filters:
            text = ' | '.join(active_filters)
        else:
            text = '-'
        self.filter_label.setText(text)

    def set_sort_info(self, sorted_by: SortBy) -> None:
        self.sort_label.setText(f'sorted by <b>{sorted_by.key}</b> '
                                f'({sorted_by._order_name()})')


class IndexView(QtWidgets.QWidget):
    view_meta = pyqtSignal(tuple)
    quit = pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget, dry_run: bool,
                 settings: Settings, statepath: Path, history_file: Path,
                 base_gui: str, user_gui: str
                 ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.statepath = statepath
        # Main view
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.entry_view = EntryList(self, settings, dry_run,
                                    statepath, base_gui, user_gui)
        self.scroll_area.setWidget(self.entry_view)
        self.scroll_area.setFocusPolicy(Qt.NoFocus)
        self.scroll_area.setAlignment(Qt.AlignHCenter)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # Status bar
        self.status_bar = StatusBar(self)
        self.entry_view.visible_count_changed.connect(
            self.status_bar.update_counts)
        self.status_bar.set_filter_info(self.entry_view.active_filters)
        self.status_bar.set_sort_info(self.entry_view.sorted_by)
        # Tag info list
        self.tag_info = TagInfoList(self, settings)
        # Terminal
        self.terminal = Terminal(self, history_file)
        # Layout
        self.setLayout(vbox(Stretch(self.scroll_area),
                            self.status_bar,
                            self.tag_info,
                            self.terminal))
        self.connect_signals()
        # Misc shizzle
        self.rootpath = settings.path
        self.print_ = self.terminal.print_
        self.error = self.terminal.error
        self.set_terminal_text = self.terminal.prompt
        self.dry_run = dry_run
        self.progress = QtWidgets.QProgressDialog(self)
        self.progress.setModal(True)
        self.progress.setAutoReset(False)
        # Hotkeys
        hotkeypairs = (
            ('reload', self.reload_view),
            ('zoom in', self.zoom_in),
            ('zoom out', self.zoom_out),
            ('reset zoom', self.zoom_reset)
        )
        self.hotkeys = {
            key: QtWidgets.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }
        self.update_hotkeys(settings.hotkeys)
        # Message tray
        self.message_tray = MessageTray(self)
        self.terminal.show_message.connect(self.message_tray.add_message)
        self.status_bar.moved.connect(self.adjust_tray)

    def setStyleSheet(self, css: str) -> None:
        super().setStyleSheet(css)
        self.terminal.setStyleSheet(css)

    def save_state(self) -> None:
        state = {
            STATE_FILTER_KEY: self.entry_view.active_filters._asdict(),
            STATE_SORT_KEY: list(self.entry_view.sorted_by)
        }
        self.statepath.write_bytes(pickle.dumps(state))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.adjust_tray()

    def adjust_tray(self) -> None:
        rect = self.geometry()
        rect.setBottom(self.status_bar.geometry().bottom())
        self.message_tray.setGeometry(rect)

    def on_external_key_event(self, ev: QtGui.QKeyEvent, press: bool) -> None:
        target = None
        if ev.modifiers() == Qt.NoModifier:
            target = self.scroll_area
        elif ev.modifiers() & Qt.ShiftModifier and self.tag_info.isVisible():
            target = self.tag_info
            ev = QtGui.QKeyEvent(ev.type(), ev.key(), Qt.NoModifier,
                                 autorep=ev.isAutoRepeat(), count=ev.count())
        if target:
            if press:
                target.keyPressEvent(ev)
            else:
                target.keyReleaseEvent(ev)

    def connect_signals(self) -> None:
        t = self.terminal
        s = self.settings
        # TODO: maybe better typing with Signal0, Signal1 etc here?
        connects: Tuple[Tuple[pyqtSignal, Callable[..., Any]], ...] = (
            # (t.input_term.scroll_index, self.entry_view.event),
            (self.tag_info.print_,      t.print_),
            (self.tag_info.error,       t.error),
            # Settings
            (s.hotkeys_changed, self.update_hotkeys),
        )
        for signal, slot in connects:
            signal.connect(slot)

        self.terminal.add_command(Command(
            'filter', 'Filter entries (aka show only entries matching the filter)',
            self.filter_entries,
            short_name='f',
            arg_help=(('', 'List the active filters.'),
                      ('-', 'Reset all filters.'),
                      ('[ndrtcbp]-', 'Reset the specified filter.'),
                      ('[ndrtcbp]', 'Don\'t apply any filter, instead set the '
                                    'terminal\'s input text to the specified '
                                    'filter\'s current value.'),
                      (AttrNames.TITLE.abbrev,
                       'Filter on titles (case insensitive).'),
                      (AttrNames.DESCRIPTION.abbrev,
                       'Filter on descriptions (case insensitive).'),
                      (AttrNames.RECAP.abbrev,
                       'Filter on recaps (case insensitive).'),
                      (AttrNames.TAGS.abbrev,
                       'Filter on tags. Supports AND (comma , ), '
                       'OR (vertical bar | ), NOT prefix (dash - ), and '
                       'tag macros (use @ as prefix) specified in the '
                       'config. AND and OR can\'t be used mixed without '
                       'explicit parentheses to specify precedence. '
                       'Spaces are allowed in tag names, but not (),| . '
                       'Tags are case sensitive.'),
                      ('[ndrt]_', 'Show only entries with this '
                                  'attribute empty.'),
                      ('[ndrt]*', 'Show no entries with this '
                                  'attribute empty.'),
                      (AttrNames.WORDCOUNT.abbrev,
                       'Filter on wordcount. Supports the operators '
                       '> < >= <= followed by the target number. A "k" '
                       'suffix in the number is replaced by 000. '
                       'Operator expressions can be combined without any '
                       'delimiters. Eg.: >900<=50k'),
                      (AttrNames.BACKSTORY_WORDCOUNT.abbrev,
                       'Filter on backstory wordcount. This uses '
                       'the same syntax as the wordcount filter.'),
                      (AttrNames.BACKSTORY_PAGES.abbrev,
                       'Filter on number of backstory pages. This uses '
                       'the same syntax as the wordcount filter.')),
        ))

        def complete_tag_filter(name: str, match_text: str) -> List[str]:
            if match_text.startswith('@'):
                return [f'@{m}' for m in sorted(self.settings.tag_macros.keys())
                        if m.startswith(match_text[1:])]
            else:
                return [t for t, count in sorted(self.get_tags(),
                                                 key=itemgetter(1),
                                                 reverse=True)
                        if t.startswith(match_text)]

        # TODO: insert an extra space before the first tag maybe
        self.terminal.add_autocompletion_pattern(AutocompletionPattern(
            'filter-entries-tags',
            prefix=rf'f{AttrNames.TAGS.abbrev}\s*',
            start=r'(^|[(,|])\s*',
            end=r'([),|]|$)',
            illegal_chars='()|,',
            get_suggestions=complete_tag_filter,
        ))

        self.terminal.add_command(Command(
            'sort', 'Sort entries',
            self.sort_entries,
            short_name='s',
            arg_help=(('[ncbpm][!<>]', 'Sort using the specified '
                                       'key and order.'),
                      (AttrNames.TITLE.abbrev,
                       'Sort by title.'),
                      (AttrNames.WORDCOUNT.abbrev,
                       'Sort by wordcount.'),
                      (AttrNames.BACKSTORY_WORDCOUNT.abbrev,
                       'Sort by backstory wordcount.'),
                      (AttrNames.BACKSTORY_PAGES.abbrev,
                       'Sort by number of backstory pages.'),
                      (AttrNames.LAST_MODIFIED.abbrev,
                       'Sort by last modified date.'),
                      ('!', 'Reverse sort order.'),
                      ('<', 'Sort ascending.'),
                      ('>', 'Sort descending.')),
        ))
        self.terminal.add_command(Command(
            'edit', 'Edit entry',
            self.edit_entry,
            short_name='e',
            args=ArgumentRules.REQUIRED,
            arg_help=(('u', 'Undo last edit.'),
                      ('[ndrt]123', "Don't edit anything, instead set the "
                                    "terminal's input text to the current "
                                    "value of the specified attribute in "
                                    "entry 123."),
                      ('[ndr]123 text', 'Set the value of the specified '
                                        'attribute in entry 123 to "text".'),
                      ('r123-', 'Clear the recap in entry 123.'),
                      ('t123 tag1, tag2',
                       'Set the tags of entry 123 to tag1 and tag2. The list '
                       'is comma separated and all tags are stripped of '
                       'surrounding whitespace before saved.'),
                      ('t* tag1, tag2', 'Replace all instances of tag1 with '
                                        'tag2 in all visible entries.'),
                      ('t* tag1,', 'Remove all instances of tag1 '
                                   'from all visible entries.'),
                      ('t* ,tag2', 'Add tag2 to all visible entries.')),
        ))

        self.terminal.add_autocompletion_pattern(AutocompletionPattern(
            'edit-entries-tags',
            prefix=rf'e{AttrNames.TAGS.abbrev}[*0-9]\s*',
            start=r'(^|,)\s*',
            end=r'(,|$)',
            illegal_chars='()|,',
            get_suggestions=complete_tag_filter,
        ))

        self.terminal.add_command(Command(
            'new_entry', 'Create new entry',
            self.new_entry,
            short_name='n',
            args=ArgumentRules.REQUIRED,
            arg_help=(('(tag1, tag2, ..) path',
                       ('Create a new entry with the tags at the path. '
                        'The title is generate automatically from '
                        'the path.')),),
        ))

        def complete_tags(name: str, match_text: str) -> List[str]:
            return [tag for num, tag in
                    sorted(((num, t) for t, num in self.get_tags()
                            if t.startswith(match_text)), reverse=True)]

        self.terminal.add_autocompletion_pattern(AutocompletionPattern(
            'new-entry-tags',
            prefix=r'n\s*[(]\s*',
            start=r'(^|,)\s*',
            end=r'\s*($|,|[)])',
            illegal_chars=')',
            get_suggestions=complete_tags,
        ))

        def complete_filename(name: str, match_text: str) -> List[str]:
            # TODO: handle directories maybe?
            root = self.rootpath
            if not root.is_dir():
                return []
            suggestions = [root / p
                           for p in sorted(root.iterdir())
                           if p.name.lower().startswith(match_text.rstrip().lower())]
            return [p.name + (os.path.sep * p.is_dir())
                    for p in suggestions]

        self.terminal.add_autocompletion_pattern(AutocompletionPattern(
            'new-entry-path',
            prefix=r'n\s*[(][^)]*[)]\s*',
            get_suggestions=complete_filename,
        ))

        self.terminal.add_command(Command(
            'manage_tags', 'Manage tags.',
            self.manage_tags,
            short_name='t',
            arg_help=(('', 'Hide tag list if visible, otherwise show '
                           'tag list in default order, sorted by '
                           'usage count.'),
                      ('[ac]-[/tagname]', 'Show tags in reverse order.'),
                      ('a[-][/tagname]', 'Show tags alphabetically sorted.'),
                      ('c[-][/tagname]', 'Show tags sorted by usage count.'),
                      ('[ac][-]/tagname', 'Show tags that includes '
                                          '"tagname".'),
                      ('@', 'List tag macros.')),
        ))
        self.terminal.add_command(Command(
            'count_length', 'Show combined size of wordcount and more',
            self.count_length,
            short_name='c',
            args=ArgumentRules.REQUIRED,
            arg_help=((AttrNames.WORDCOUNT.abbrev,
                       'Show combined wordcount for all visible entries.'),
                      (AttrNames.BACKSTORY_WORDCOUNT.abbrev,
                       'Show combined backstory wordcount '
                       'for all visible entries.'),
                      (AttrNames.BACKSTORY_PAGES.abbrev,
                       'Show combined number of backstory pages '
                       'for all visible entries.')),
        ))
        self.terminal.add_command(Command(
            'external_edit', 'Open entry file in external editor',
            self.external_run_entry,
            short_name='x',
            args=ArgumentRules.REQUIRED,
            arg_help=(('123', "Open entry 123's file (note: not sapfo's json "
                              "metadata file) in an external editor. "
                              "This is the same as entering 123 without any "
                              "command at all."),
                      ('foobar', "If there is only one entry with a name "
                                 "\"foobar\", open that entry in an external "
                                 "editor.")),
        ))
        self.terminal.add_command(Command(
            'open_meta', 'Open entry in backstory (meta) editor',
            self.open_meta,
            short_name='m',
            args=ArgumentRules.REQUIRED,
            arg_help=(('123', 'Open the backstory/meta editor '
                              'for entry 123.'),),
        ))

    def update_hotkeys(self, hotkeys: Dict[str, str]) -> None:
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(hotkeys[key]))

    def zoom_in(self) -> None:
        pass

    def zoom_out(self) -> None:
        pass

    def zoom_reset(self) -> None:
        pass

    def reload_view(self) -> None:
        """
        Reload the entrylist by scanning the metadata files and then refresh
        the view with the updated entrylist.

        Is also the method that generates the entrylist the first time.
        So don't look for a init_everything method/function or anything, kay?
        """
        self.progress.setLabelText('Loading index...')
        self.progress.setMaximum(0)
        self.progress.setMinimumDuration(0)
        self.progress.setValue(0)
        raw_entries = index_stories(self.rootpath, self.progress)
        try:
            self.entry_view.set_entries(raw_entries, self.progress)
        except tagsystem.ParsingError as e:
            self.error(f'Failed to reload active tag filter, resetting')
            self.error(f'[Tag parsing] {e}')
            self.entry_view.active_filters = \
                self.entry_view.active_filters._replace(tags=None)
            self.status_bar.set_filter_info(self.entry_view.active_filters)
            self.entry_view.set_entries(raw_entries, self.progress)
            self.save_state()
        self.progress.reset()

    def get_tags(self) -> List[Tuple[str, int]]:
        """
        Return all tags and how many times they appear among the entries.
        Called by the terminal for the tab completion.
        """
        return Counter(tag for entry in self.entry_view.entries
                       for tag in entry.tags).most_common()

    def manage_tags(self, arg: Optional[str]) -> None:
        # self.tag_info.view_tags(self.get_tags())
        """
        t - (when visible) hide
        t[ac][-][/tagname]
            a - sort alphabetically
            - - reverse order
            / - show/search for tags
        t@ - list macros
        """
        arg = arg or ''
        if not arg and self.tag_info.isVisible():
            self.tag_info.hide()
            return
        if arg == '@':
            self.tag_info.view_macros()
            return
        rx = re.fullmatch(r'(?P<alpha>[ac])?(?P<reverse>-)?(?P<search>/.*)?',
                          arg)
        if rx is None:
            self.error('invalid arg')
            return
        match = rx.groupdict()
        sort_alphabetically = match.get('alpha', 'c') == 'a'
        search = match['search'][1:] if match['search'] else None
        self.tag_info.view_tags(self.get_tags(), sort_alphabetically,
                                bool(match['reverse']), search)

    def filter_entries(self, arg: Optional[str]) -> None:
        """
        The main filter method, called by terminal command.

        If arg is not present, print active filters.
        If arg is -, reset all filters.
        If arg is a category followed by -, reset that filter.
        If arg is a category (t or d) followed by _, show all entries with
        nothing in that particular category (eg. empty description).
        If arg is a category, prompt with the active filter (if any).
        """
        filters = make_abbrev_dict(AttrNames.TITLE,
                                   AttrNames.DESCRIPTION,
                                   AttrNames.RECAP,
                                   AttrNames.TAGS,
                                   AttrNames.WORDCOUNT,
                                   AttrNames.BACKSTORY_WORDCOUNT,
                                   AttrNames.BACKSTORY_PAGES)
        filterchars = ''.join(filters)
        # Print active filters
        if not arg:
            active_filters = [f'{cmd}: {payload}'
                              for cmd, payload
                              in self.entry_view.active_filters._asdict().items()
                              if payload is not None]
            if active_filters:
                self.print_('; '.join(active_filters))
            else:
                self.error('No active filters')
            return
        # Reset all filters
        elif arg.strip() == '-':
            kwargs = dict(zip(filters.values(), len(filters)*(None,)))
            self.entry_view.active_filters = self.entry_view.active_filters._replace(**kwargs)
            self.entry_view.filter_()
            resultstr = 'Filters reset'
        # Reset specified filter
        elif re.fullmatch(rf'[{filterchars}]-\s*', arg):
            self.entry_view.active_filters = self.entry_view.active_filters._replace(
                **{filters[arg[0]]: None})
            self.entry_view.filter_()
            resultstr = f'Filter on {filters[arg[0]]} reset'
        else:
            # Prompt active filter
            if arg.strip() in filters.keys():
                payload = getattr(self.entry_view.active_filters, filters[arg])
                if payload is None:
                    payload = ''
                self.set_terminal_text('f' + arg.strip() + ' ' + payload)
                return
            # Filter empty entries
            if re.fullmatch(r'[nrdt]_\s*', arg):
                cmd = arg[0]
                payload = ''
            # Filter nonempty entries
            elif re.fullmatch(r'[nrdt]\*\s*', arg):
                cmd = arg[0]
                payload = NONEMPTY_SEARCH
            # Regular filter command
            elif re.fullmatch(rf'[{filterchars}] +\S.*', arg):
                cmd = arg[0]
                payload = arg.split(None, 1)[1].strip()
            # Invalid filter command
            else:
                self.error('Invalid filter command')
                return
            # Do the filtering
            self.entry_view.active_filters = self.entry_view.active_filters._replace(**{filters[cmd]: payload})
            try:
                self.entry_view.filter_()
            except tagsystem.ParsingError as e:
                self.error(f'[Tag parsing] {e}')
                return
            resultstr = 'Filter applied'
        self.status_bar.set_filter_info(self.entry_view.active_filters)
        self.print_(resultstr.format(self.entry_view.visible_count(),
                                     self.entry_view.count()))
        self.save_state()

    def sort_entries(self, arg: Optional[str]) -> None:
        """
        The main sort method, called by terminal command.

        If arg is not specified, print the current sort order.
        """
        acronyms = make_abbrev_dict(AttrNames.TITLE,
                                    AttrNames.WORDCOUNT,
                                    AttrNames.BACKSTORY_WORDCOUNT,
                                    AttrNames.BACKSTORY_PAGES,
                                    AttrNames.LAST_MODIFIED)
        if not arg:
            self.error('Nothing to sort by')
            return
        rx = re.fullmatch(r'(\w?)([><!]?)', arg)
        if not rx:
            self.error('Invalid sort command')
            return
        descending = self.entry_view.sorted_by.descending
        sort_key = self.entry_view.sorted_by.key
        if rx[2] == '!':
            descending = not descending
        elif rx[2] == '>':
            if descending:
                self.print_('Already sorting in descending order')
            else:
                descending = True
        elif rx[2] == '<':
            if not descending:
                self.print_('Already sorting in ascending order')
            else:
                descending = False
        if rx[1]:
            if rx[1] not in acronyms:
                self.error(f'Unknown attribute to sort by: "{rx[1]}"')
                return
            else:
                sort_key = acronyms[rx[1]]
        updated_sorting = self.entry_view.sorted_by._replace(
            descending=descending,
            key=sort_key)
        if updated_sorting != self.entry_view.sorted_by:
            self.entry_view.sorted_by = updated_sorting
            self.entry_view.sort()
            self.status_bar.set_sort_info(self.entry_view.sorted_by)
            self.save_state()

    def edit_entry(self, arg: str) -> None:
        """
        The main edit method, called by terminal command.

        If arg is "u", undo the last edit.
        Otherwise, either replace/add/remove tags from the visible entries
        or edit attributes of a single entry.
        """
        if arg.strip() == 'u':
            edits = self.entry_view.undo()
            if edits == 0:
                self.error('Nothing to undo')
            else:
                self.print_(f'{edits} edits reverted')
            return
        replace_tags = re.fullmatch(AttrNames.TAGS.abbrev
                                    + r'\*\s*(.*?)\s*,\s*(.*?)\s*', arg)
        abbrevs = ''.join(x.abbrev for x in [AttrNames.RECAP,
                                             AttrNames.DESCRIPTION,
                                             AttrNames.TAGS,
                                             AttrNames.TITLE])
        main_data = re.fullmatch(rf'[{abbrevs}](\d+)(.*)', arg)
        # Replace/add/remove a bunch of tags
        if replace_tags:
            oldtag, newtag = replace_tags.groups()
            if not oldtag and not newtag:
                self.error('No tags specified, nothing to do')
                return
            count = self.entry_view.replace_tags(oldtag, newtag,
                                                 AttrNames.TAGS.name)
            if count > 0:
                self.print_(f'Edited tags in {count} entries')
            else:
                self.error('No tags edited')
        # Edit a single entry
        elif main_data:
            entry_id = int(main_data.group(1))
            if entry_id >= self.entry_view.visible_count():
                self.error('Index out of range')
                return
            payload = main_data.group(2).strip()
            category = make_abbrev_dict(AttrNames.DESCRIPTION,
                                        AttrNames.TITLE,
                                        AttrNames.RECAP,
                                        AttrNames.TAGS)[arg[0]]
            # category = {'d': AttrNames.DESCRIPTION,
                        # 'n': AttrNames.TITLE,
                        # 'r': AttrNames.RECAP,
                        # 't': AttrNames.TAGS}[arg[0]]
            # No data specified, so the current is provided instead
            if not payload:
                data = getattr(self.entry_view.visible_entry(entry_id),
                               category)
                new = (', '.join(sorted(data))
                       if arg[0] == AttrNames.TAGS.abbrev else data)
                self.set_terminal_text('e' + arg.strip() + ' ' + new)
            else:
                if arg[0] == AttrNames.RECAP.abbrev and payload == '-':
                    # Clear recap if the arg is -
                    payload = ''
                edited = self.entry_view.edit_(entry_id, category, payload)
                if edited:
                    self.print_('Entry edited')
                else:
                    self.print_('Same data as before, nothing edited')
        else:
            self.error('Invalid edit command')

    def new_entry(self, arg: str) -> None:
        """
        Main new entry method, called by the terminal.
        """
        # def metadatafile(path: str) -> str:
        #     dirname, fname = os.path.split(path)
        #     return join(dirname, '.' + fname + '.metadata')
        file_exists = False
        tags: List[str] = []
        new_entry_rx = re.match(r'\s*\(([^\(]*?)\)\s*(.+)\s*', arg)
        if not new_entry_rx:
            self.error('Invalid new entry command')
            return
        tagstr, path = new_entry_rx.groups()
        fullpath = self.rootpath / path
        metadatafile = fullpath.with_name(f'.{fullpath.name}.metadata')
        if tagstr:
            tags = list({tag.strip() for tag in tagstr.split(',')})
        if metadatafile.exists():
            self.error('Metadata already exists for that file')
            return
        if fullpath.exists():
            file_exists = True

        title = fullpath.stem.replace('-', ' ')

        # Fix the capitalization
        def fix_capitalization(mo: Match[str]) -> str:
            return mo[0].capitalize()
        if self.settings.capitalize_all_words_in_title:
            title = re.sub(r"\w[\w']*", fix_capitalization, title)
        else:
            title = title.capitalize()
        try:
            fullpath.touch()
            metadatafile.write_text(json.dumps({'title': title,
                                                'description': '',
                                                'tags': tags}))
        except Exception as e:
            self.error(f'Couldn\'t create the files: {e}')
        else:
            self.reload_view()
            if file_exists:
                self.print_('New entry created, '
                            'metadatafile added to existing file')
            else:
                self.print_('New entry created')

    def open_meta(self, arg: str) -> None:
        """
        Main open meta method, called by the terminal.

        arg should be the index of the entry to be viewed in the meta viewer.
        """
        if not arg.isdigit():
            partialnames = [n for n, entry
                            in enumerate(self.entry_view.visible_entries)
                            if arg.lower() in entry.title.lower()]
            if not partialnames:
                self.error(f'Entry not found: "{arg}"')
                return
            elif len(partialnames) > 1:
                self.error(f'Ambiguous name, '
                           f'matches {len(partialnames)} entries')
                return
            elif len(partialnames) == 1:
                arg = str(partialnames[0])
        elif not int(arg) in range(self.entry_view.visible_count()):
            self.error('Index out of range')
            return
        self.view_meta.emit(self.entry_view.visible_entry(int(arg)))

    def count_length(self, arg: str) -> None:
        """
        Main count length method, called by terminal command.
        """
        def print_length(targetstr: str, targetattr: str) -> None:
            self.print_('Total {}: {}'.format(targetstr,
                        sum(getattr(x, targetattr)
                            for x in self.entry_view.visible_entries)))
        cmd = arg.strip()
        if cmd == 'c':
            print_length('wordcount', 'wordcount')
        elif cmd == 'b':
            print_length('backstory wordcount', 'backstorywordcount')
        elif cmd == 'p':
            print_length('backstory pages', 'backstorypages')
        else:
            self.error('Unknown argument')

    def external_run_entry(self, arg: str) -> None:
        """
        Main external run method, called by terminal command.
        """
        if not arg.isdigit():
            partialnames = [n for n, entry
                            in enumerate(self.entry_view.visible_entries)
                            if arg.lower() in entry.title.lower()]
            if not partialnames:
                self.error(f'Entry not found: "{arg}"')
                return
            elif len(partialnames) > 1:
                self.error(f'Ambiguous name, '
                           f'matches {len(partialnames)} entries')
                return
            elif len(partialnames) == 1:
                arg = str(partialnames[0])
        elif not int(arg) in range(self.entry_view.visible_count()):
            self.error('Index out of range')
            return
        if not self.settings.editor:
            self.error('No editor command defined')
            return
        subprocess.Popen([self.settings.editor,
                          self.entry_view.visible_entry(int(arg)).file])
        self.print_(f'Opening entry with {self.settings.editor}')
