from collections import Counter
from itertools import chain, zip_longest
import json
from operator import itemgetter
import os
from pathlib import Path
import pickle
import re
import subprocess
from typing import (cast, Any, Callable, Dict, Iterable, List, Match,
                    Optional, Tuple)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, Qt

from . import taggedlist
from .common import CACHE_DIR, ActiveFilters
from .declarative import fix_layout, grid, hflow, label, Stretch, vbox
from .taggedlist import Entries, Entry
from .terminal import (GenericTerminalInputBox,
                       GenericTerminalOutputBox, GenericTerminal)


SortBy = Tuple[str, bool]


class IndexView(QtWidgets.QWidget):
    view_entry = pyqtSignal(tuple)
    view_meta = pyqtSignal(tuple)
    show_popup = pyqtSignal(str, str, str, str)
    quit = pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget, dry_run: bool,
                 statepath: Path, history_file: Path) -> None:
        super().__init__(parent)
        # Main view
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.entry_view = EntryList(self, '({wordcount})', ())
        self.scroll_area.setWidget(self.entry_view)
        self.scroll_area.setFocusPolicy(Qt.NoFocus)
        # Tag info list
        self.tag_info = TagInfoList(self)
        # Terminal
        self.terminal = Terminal(self, self.get_tags, history_file)
        # Layout
        self.setLayout(vbox(Stretch(self.scroll_area), self.tag_info,
                            self.terminal))
        self.connect_signals()
        # Misc shizzle
        self.rootpath = Path()
        self.print_ = self.terminal.print_
        self.error = self.terminal.error
        self.set_terminal_text = self.terminal.prompt
        self.dry_run = dry_run
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
        # State
        self.statepath = statepath
        state = self.load_state()
        # Entries and stuff
        self.entries: Entries = ()
        self.visible_entries: Entries = ()
        self.active_filters: ActiveFilters = ActiveFilters(**state['active filters'])
        self.sorted_by: SortBy = state['sorted by']
        self.undostack: Tuple[Entries, ...] = ()

    def load_state(self) -> Dict[str, Any]:
        try:
            state: Dict[str, Any] = pickle.loads(self.statepath.read_bytes())
            return state
        except FileNotFoundError:
            return {
                'active filters': {k: None for k in 'title description tags wordcount backstorywordcount backstorypages'.split()},
                'sorted by': ('title', False)
            }

    def save_state(self) -> None:
        state = {
            'active filters': self.active_filters._asdict(),
            'sorted by': self.sorted_by
        }
        self.statepath.write_bytes(pickle.dumps(state))

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
        connects = (
            (t.filter_,                 self.filter_entries),
            (t.sort,                    self.sort_entries),
            (t.open_,                   self.open_entry),
            (t.edit,                    self.edit_entry),
            (t.new_entry,               self.new_entry),
            # (t.input_term.scroll_index, self.entry_view.event),
            (t.manage_tags,             self.manage_tags),
            (t.count_length,            self.count_length),
            (t.external_edit,           self.external_run_entry),
            (t.open_meta,               self.open_meta),
            (t.quit,                    self.quit.emit),
            (self.tag_info.print_,      t.print_),
            (self.tag_info.error,       t.error),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings: Dict) -> None:
        self.settings = settings
        self.rootpath = Path(settings['path']).expanduser().resolve()
        self.terminal.update_settings(settings)
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))
        self.entry_view.tag_colors = settings['tag colors']
        self.entry_view.length_template = settings['entry length template']
        self.tag_info.tag_colors = settings['tag colors']
        self.tag_info.tag_macros = settings['tag macros']
        self.reload_view()

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
        self.attributedata, self.entries = index_stories(self.rootpath)
        self.visible_entries = self.regenerate_visible_entries()
        self.refresh_view(keep_position=True)

    def refresh_view(self, keep_position: bool = False) -> None:
        """
        Refresh the view with the filtered entries and the current css.
        The full entrylist is not touched by this.
        """
        # TODO: keep position?
        self.entry_view.set_entries(self.visible_entries)

    def get_tags(self) -> List[Tuple[str, int]]:
        """
        Return all tags and how many times they appear among the entries.
        Called by the terminal for the tab completion.
        """
        return Counter(tag for entry in self.entries
                       for tag in entry.tags).most_common()

    def manage_tags(self, arg: str) -> None:
        # self.tag_info.view_tags(self.get_tags())
        """
        t - (when visible) hide
        t[ac][-][/tagname]
            a - sort alphabetically
            - - reverse order
            / - show/search for tags
        t@ - list macros
        """
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

    def regenerate_visible_entries(self,
                                   entries: Optional[Entries] = None,
                                   active_filters: Optional[ActiveFilters] = None,
                                   attributedata: Optional[taggedlist.AttributeData] = None,
                                   sort_by: Optional[str] = None,
                                   reverse: Optional[bool] = None,
                                   tagmacros: Optional[Dict[str, str]] = None
                                   ) -> Entries:
        """
        Convenience method to regenerate all the visible entries from scratch
        using the active filters, the full entries list (not the
        visible_entries) and the sort order.

        Each of the variables can be overriden by their appropriate keyword
        argument if needed.

        NOTE: This should return stuff b/c of clarity, despite the fact that
        it should always return it into the self.visible_entries variable.
        """
        # Drop the empty posts in the active_filters named tuple
        raw_active_filters = (self.active_filters if active_filters is None
                              else active_filters)
        filters = [(k, v) for k, v in raw_active_filters._asdict().items()
                   if v is not None]
        return taggedlist.generate_visible_entries(
            self.entries if entries is None else entries,
            filters,
            self.attributedata if attributedata is None else attributedata,
            self.sorted_by[0] if sort_by is None else sort_by,
            self.sorted_by[1] if reverse is None else reverse,
            self.settings['tag macros'] if tagmacros is None else tagmacros,
        )

    def filter_entries(self, arg: str) -> None:
        """
        The main filter method, called by terminal command.

        If arg is not present, print active filters.
        If arg is -, reset all filters.
        If arg is a category followed by -, reset that filter.
        If arg is a category (t or d) followed by _, show all entries with
        nothing in that particular category (eg. empty description).
        If arg is a category, prompt with the active filter (if any).
        """
        filters = {'n': 'title',
                   'd': 'description',
                   't': 'tags',
                   'c': 'wordcount',
                   'b': 'backstorywordcount',
                   'p': 'backstorypages'}
        filterchars = ''.join(filters)
        # Print active filters
        if not arg:
            active_filters = [f'{cmd}: {payload}'
                              for cmd, payload in self.active_filters._asdict().items()
                              if payload is not None]
            if active_filters:
                self.print_('; '.join(active_filters))
            else:
                self.error('No active filters')
            return
        # Reset all filters
        elif arg.strip() == '-':
            kwargs = dict(zip(filters.values(), len(filters)*(None,)))
            self.active_filters = self.active_filters._replace(**kwargs)
            visible_entries = self.regenerate_visible_entries()
            resultstr = 'Filters reset: {}/{} entries visible'
        # Reset specified filter
        elif re.fullmatch(rf'[{filterchars}]-\s*', arg):
            self.active_filters = self.active_filters._replace(**{filters[arg[0]]: None})
            visible_entries = self.regenerate_visible_entries()
            resultstr = (f'Filter on {filters[arg[0]]} reset: '
                         f'{{}}/{{}} entries visible')
        else:
            # Prompt active filter
            if arg.strip() in filters.keys():
                payload = getattr(self.active_filters, filters[arg])
                if payload is None:
                    payload = ''
                self.set_terminal_text('f' + arg.strip() + ' ' + payload)
                return
            # Filter empty entries
            if re.fullmatch(r'[dt]_\s*', arg):
                cmd = arg[0]
                payload = ''
            # Regular filter command
            elif re.fullmatch(rf'[{filterchars}] +\S.*', arg):
                cmd = arg[0]
                payload = arg.split(None, 1)[1].strip()
            # Invalid filter command
            else:
                self.error('Invalid filter command')
                return
            # Do the filtering
            self.active_filters = self.active_filters._replace(**{filters[cmd]: payload})
            try:
                visible_entries = self.regenerate_visible_entries()
            except SyntaxError as e:
                # This should be an error from the tag parser
                self.error(f'[Tag parsing] {e}')
                return
            resultstr = 'Filtered: {}/{} entries visible'
        # Only actually update stuff if the entries have changed
        if visible_entries != self.visible_entries:
            self.visible_entries = visible_entries
            self.refresh_view()
        # Print the output
        filtered, total = len(self.visible_entries), len(self.entries)
        self.print_(resultstr.format(filtered, total))
        self.save_state()

    def sort_entries(self, arg: str) -> None:
        """
        The main sort method, called by terminal command.

        If arg is not specified, print the current sort order.
        """
        acronyms = {'n': 'title',
                    'c': 'wordcount',
                    'b': 'backstorywordcount',
                    'p': 'backstorypages',
                    'm': 'lastmodified'}
        if not arg:
            attr = self.sorted_by[0]
            order = ('ascending', 'descending')[self.sorted_by[1]]
            self.print_(f'Sorted by {attr}, {order}')
            return
        if arg[0] not in acronyms:
            self.error(f'Unknown attribute to sort by: "{arg[0]}"')
            return
        if not re.fullmatch(r'\w-?\s*', arg):
            self.error('Incorrect sort command')
            return
        reverse = arg.strip().endswith('-')
        self.sorted_by = (acronyms[arg[0]], reverse)
        sorted_entries = taggedlist.sort_entries(self.visible_entries,
                                                 acronyms[arg[0]],
                                                 reverse)
        if sorted_entries != self.visible_entries:
            self.visible_entries = sorted_entries
            self.refresh_view()
        self.save_state()

    def edit_entry(self, arg: str) -> None:
        """
        The main edit method, called by terminal command.

        If arg is "u", undo the last edit.
        Otherwise, either replace/add/remove tags from the visible entries
        or edit attributes of a single entry.
        """
        if arg.strip() == 'u':
            if not self.undostack:
                self.error('Nothing to undo')
                return
            undoitem = self.undostack[-1]
            self.undostack = self.undostack[:-1]
            self.entries = taggedlist.undo(self.entries, undoitem)
            self.visible_entries = self.regenerate_visible_entries()
            self.refresh_view(keep_position=True)
            if not self.dry_run:
                write_metadata(undoitem)
            self.print_(f'{len(undoitem)} edits reverted')
            return
        replace_tags = re.fullmatch(r't\*\s*(.*?)\s*,\s*(.*?)\s*', arg)
        main_data = re.fullmatch(r'[dtn](\d+)(.*)', arg)
        # Replace/add/remove a bunch of tags
        if replace_tags:
            oldtag, newtag = replace_tags.groups()
            if not oldtag and not newtag:
                self.error('No tags specified, nothing to do')
                return
            entries = taggedlist.replace_tags(oldtag,
                                              newtag,
                                              self.entries,
                                              self.visible_entries,
                                              'tags')
            if entries != self.entries:
                old, changed = taggedlist.get_diff(self.entries, entries)
                self.undostack = self.undostack + (old,)
                self.entries = entries
                self.visible_entries = self.regenerate_visible_entries()
                self.refresh_view(keep_position=True)
                if not self.dry_run:
                    write_metadata(changed)
                self.print_(f'Edited tags in {len(changed)} entries')
            else:
                self.error('No tags edited')
        # Edit a single entry
        elif main_data:
            entry_id = int(main_data.group(1))
            if entry_id >= len(self.visible_entries):
                self.error('Index out of range')
                return
            payload = main_data.group(2).strip()
            category = {'d': 'description', 'n': 'title', 't': 'tags'}[arg[0]]
            # No data specified, so the current is provided instead
            if not payload:
                data = getattr(self.visible_entries[entry_id], category)
                new = ', '.join(sorted(data)) if arg[0] == 't' else data
                self.set_terminal_text('e' + arg.strip() + ' ' + new)
            else:
                index = self.visible_entries[entry_id][0]
                entries = taggedlist.edit_entry(index,
                                                self.entries,
                                                category,
                                                payload,
                                                self.attributedata)
                if entries != self.entries:
                    self.undostack = self.undostack \
                            + ((self.visible_entries[entry_id],),)
                    self.entries = entries
                    self.visible_entries = self.regenerate_visible_entries()
                    self.refresh_view(keep_position=True)
                    if not self.dry_run:
                        write_metadata((self.entries[index],))
                    self.print_('Entry edited')
        else:
            self.error('Invalid edit command')

    def open_entry(self, arg: int) -> None:
        """
        Main open entry method, called by the terminal.

        arg should be the index of the entry to be viewed.
        """
        if not isinstance(arg, int):
            raise AssertionError('BAD CODE: the open entry arg '
                                 'should be an int')
        if arg not in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        self.view_entry.emit(self.visible_entries[arg])

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

        # Fix the capitalization
        def fix_capitalization(mo: Match[str]) -> str:
            return mo[0].capitalize()
        title = re.sub(r"\w[\w']*",
                       fix_capitalization,
                       fullpath.stem.replace('-', ' '))
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
            partialnames = [n for n, entry in enumerate(self.visible_entries)
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
        elif not int(arg) in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        self.view_meta.emit(self.visible_entries[int(arg)])

    def count_length(self, arg: str) -> None:
        """
        Main count length method, called by terminal command.
        """
        def print_length(targetstr: str, targetattr: str) -> None:
            self.print_('Total {}: {}'.format(targetstr,
                        sum(getattr(x, targetattr)
                            for x in self.visible_entries)))
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
            partialnames = [n for n, entry in enumerate(self.visible_entries)
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
        elif not int(arg) in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        if not self.settings.get('editor', None):
            self.error('No editor command defined')
            return
        subprocess.Popen([self.settings['editor'],
                          self.visible_entries[int(arg)].file])
        self.print_(f'Opening entry with {self.settings["editor"]}')


class TagInfoList(QtWidgets.QScrollArea):
    error = pyqtSignal(str)
    print_ = pyqtSignal(str)

    class TagCountBar(QtWidgets.QWidget):
        def __init__(self, parent: QtWidgets.QWidget,
                     percentage: float) -> None:
            super().__init__(parent)
            self.percentage = percentage

        def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
            right_offset = (1 - self.percentage) * ev.rect().width()
            painter = QtGui.QPainter(self)
            painter.fillRect(ev.rect().adjusted(0, 0, -int(right_offset), 0),
                             painter.background())
            painter.end()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setSizeAdjustPolicy(self.AdjustToContents)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.tag_colors: Dict[str, str] = {}
        self.tag_macros: Dict[str, str] = {}
        self.panel = QtWidgets.QWidget(self)
        self.panel.setObjectName('tag_info_list_panel')
        self.panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Maximum)
        layout = QtWidgets.QGridLayout(self.panel)
        layout.setColumnStretch(2, 1)
        layout.setHorizontalSpacing(10)
        # layout.setSizeConstraint(layout.SetMinAndMaxSize)
        # TODO: something less ugly than this
        self.setFixedHeight(200)
        self.panel.setLayout(layout)
        self.setWidget(self.panel)
        self.setWidgetResizable(True)
        self.hide()

    def clear(self) -> None:
        layout = self.panel.layout()
        while not layout.isEmpty():
            item = layout.takeAt(0)
            if item and item.widget() is not None:
                item.widget().deleteLater()

    def _make_tag(self, tag: str) -> QtWidgets.QWidget:
        tag_label_wrapper = QtWidgets.QWidget(self)
        tag_label = label(tag, 'tag', parent=tag_label_wrapper)
        if tag in self.tag_colors:
            tag_label.setStyleSheet(f'background: {self.tag_colors[tag]};')
        else:
            tag_label.setStyleSheet('background: #667;')
        sub_layout = QtWidgets.QHBoxLayout(tag_label_wrapper)
        fix_layout(sub_layout)
        sub_layout.addWidget(tag_label)
        sub_layout.addStretch()
        return tag_label_wrapper

    def view_tags(self, tags: List[Tuple[str, int]], sort_alphabetically: bool,
                  reverse: bool, name_filter: Optional[str]) -> None:
        self.clear()
        max_count = max(t[1] for t in tags)
        if sort_alphabetically:
            tags.sort(key=itemgetter(0))
        else:
            tags.sort(key=itemgetter(0), reverse=True)
            tags.sort(key=itemgetter(1))
        # If alphabetically, we want to default to ascending,
        # but if we're sorting by usage count, we want it descending.
        if reverse or (not sort_alphabetically and not reverse):
            tags.reverse()
        if name_filter:
            tags = [t for t in tags if name_filter in t[0]]
        layout = cast(QtWidgets.QGridLayout, self.panel.layout())
        for n, (tag, count) in enumerate(tags):
            # Tag name
            layout.addWidget(self._make_tag(tag), n, 0)
            # Tag count
            layout.addWidget(label(str(count), 'tag_info_count', parent=self),
                             n, 1, alignment=Qt.AlignBottom)
            # Tag bar
            count_bar = self.TagCountBar(self, count / max_count)
            layout.addWidget(count_bar, n, 2)
        self.show()

    def view_macros(self) -> None:
        # TODO: better view of this
        self.clear()
        layout = cast(QtWidgets.QGridLayout, self.panel.layout())
        for n, (tag, macro) in enumerate(sorted(self.tag_macros.items())):
            # Tag macro name
            layout.addWidget(self._make_tag('@' + tag), n, 0)
            # Tag macro expression
            layout.addWidget(label(macro, 'tag_info_macro_expression',
                                   parent=self, word_wrap=True), n, 1)
        self.show()


class EntryWidget(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget, number: int,
                 entry: Entry, length_template: str,
                 tag_colors: Dict[str, str]) -> None:
        super().__init__(parent)
        self.length_template = length_template
        self.number_widget = label(number, 'number', parent=self)
        self.title_widget = label(entry.title, 'title', parent=self)
        self.word_count_widget = label(
            self.length_template.format(
                wordcount=entry.wordcount,
                backstorypages=entry.backstorypages,
                backstorywordcount=entry.backstorywordcount
            ), 'wordcount', parent=self)
        self.desc_widget = label(entry.description or '[no desc]',
                                 ('description' if entry.description
                                  else 'empty_description'),
                                 word_wrap=True, parent=self)
        self.tag_widgets: List[QtWidgets.QLabel] = []
        self._tag_colors = tag_colors
        for tag in entry.tags:
            widget = label(tag, 'tag', parent=self)
            if tag in tag_colors:
                widget.setStyleSheet(f'background: {tag_colors[tag]};')
            self.tag_widgets.append(widget)
        self.top_row = hflow(self.title_widget,
                             self.word_count_widget,
                             *self.tag_widgets)
        self.setLayout(grid({
            (0, 0): self.number_widget,
            (0, 1): self.top_row,
            (1, (0, 1)): self.desc_widget
        }, col_stretch={1: 1}))

    @property
    def tag_colors(self) -> Dict[str, str]:
        return self._tag_colors

    @tag_colors.setter
    def tag_colors(self, new_colors: Dict[str, str]) -> None:
        self._tag_colors = new_colors
        self.refresh_tag_colors()

    def refresh_tag_colors(self) -> None:
        for tag_widget in self.tag_widgets:
            tag = tag_widget.text()
            # TODO: centralize default tag color
            if tag in self.tag_colors:
                tag_widget.setStyleSheet(f'background: {self.tag_colors[tag]};')
            else:
                tag_widget.setStyleSheet('background: #667;')

    def update_data(self, entry: Entry) -> None:
        self.title_widget.setText(entry.title)
        self.word_count_widget.setText(
            self.length_template.format(
                wordcount=entry.wordcount,
                backstorypages=entry.backstorypages,
                backstorywordcount=entry.backstorywordcount
            ))
        self.desc_widget.setText(entry.description or '[no desc]')
        desc_class = ('description' if entry.description
                      else 'empty_description')
        if desc_class != self.desc_widget.objectName():
            self.desc_widget.setObjectName(desc_class)
            # Force the style to update
            self.desc_widget.style().polish(self.desc_widget)
        for tag_widget, tag in zip(self.tag_widgets, entry.tags):
            tag_widget.setText(tag)
        old_tag_count = len(self.tag_widgets)
        new_tag_count = len(entry.tags)
        if old_tag_count > new_tag_count:
            for tag_widget in self.tag_widgets[new_tag_count:]:
                self.top_row.removeWidget(tag_widget)
                tag_widget.deleteLater()
            self.tag_widgets = self.tag_widgets[:new_tag_count]
        elif old_tag_count < new_tag_count:
            for tag in list(entry.tags)[old_tag_count:]:
                tag_widget = label(tag, 'tag', parent=self)
                self.tag_widgets.append(tag_widget)
                self.top_row.addWidget(tag_widget)
        self.refresh_tag_colors()


class EntryList(QtWidgets.QFrame):

    def get_spacing(self) -> int:
        return self.layout().spacing()

    def set_spacing(self, value: int) -> None:
        self._spacing = value
        self.update_spacing()

    spacing = QtCore.pyqtProperty(int, get_spacing, set_spacing)

    def get_separator_color(self) -> QtGui.QColor:
        return self._separator_color

    def set_separator_color(self, value: QtGui.QColor) -> None:
        self._separator_color = value

    separator_color = QtCore.pyqtProperty(QtGui.QColor, get_separator_color,
                                          set_separator_color)

    def get_separator_h_margin(self) -> int:
        return self._separator_h_margin

    def set_separator_h_margin(self, value: int) -> None:
        self._separator_h_margin = value

    separator_h_margin = QtCore.pyqtProperty(int, get_separator_h_margin,
                                             set_separator_h_margin)

    def get_separator_height(self) -> int:
        return self._separator_height

    def set_separator_height(self, value: int) -> None:
        self._separator_height = value
        self.update_spacing()

    separator_height = QtCore.pyqtProperty(int, get_separator_height,
                                           set_separator_height)

    def __init__(self, parent: QtWidgets.QWidget, length_template: str,
                 entries: Entries) -> None:
        super().__init__(parent)
        self._spacing: int = 0
        self._separator_color: QtGui.QColor = QtGui.QColor('black')
        self._separator_h_margin = 0
        self._separator_height = 1
        self.length_template = length_template
        self.entry_class = EntryWidget
        self.entry_widgets: List[EntryWidget] = []
        self._tag_colors: Dict[str, str] = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setObjectName('entry_list_layout')
        layout.setContentsMargins(0, 0, 0, 0)
        self.add_entries(entries)

    @property
    def tag_colors(self) -> Dict[str, str]:
        return self._tag_colors

    @tag_colors.setter
    def tag_colors(self, new_colors: Dict[str, str]) -> None:
        if self._tag_colors != new_colors:
            self._tag_colors = new_colors
            for entry in self.entry_widgets:
                entry.tag_colors = new_colors

    def add_entries(self, entries: Entries) -> None:
        self.entry_widgets = []
        for n, entry in enumerate(entries):
            entry_widget = self.entry_class(self, n, entry,
                                            self.length_template,
                                            self.tag_colors)
            self.entry_widgets.append(entry_widget)
            self.layout().addWidget(entry_widget)
        cast(QtWidgets.QVBoxLayout, self.layout()).addStretch(1)

    def update_entries(self, new_entries: Entries) -> None:
        for widget, entry in zip(self.entry_widgets, new_entries):
            widget.update_data(entry)

    def set_entries(self, new_entries: Entries) -> None:
        # Get rid of the extra stretch
        self.layout().takeAt(self.layout().count() - 1)
        for n, (widget, entry) in enumerate(zip_longest(self.entry_widgets,
                                                        new_entries)):
            if widget is None:
                entry_widget = self.entry_class(self, n, entry,
                                                self.length_template,
                                                self.tag_colors)
                self.entry_widgets.append(entry_widget)
                self.layout().addWidget(entry_widget)
            elif entry is None:
                self.layout().removeWidget(widget)
                widget.deleteLater()
            else:
                widget.update_data(entry)
        # print(len(new_entries), len(self.entry_widgets))
        if len(new_entries) < len(self.entry_widgets):
            self.entry_widgets = self.entry_widgets[:len(new_entries)]
        # print(len(new_entries), len(self.entry_widgets))
        # print(self.entry_widgets)
        cast(QtWidgets.QVBoxLayout, self.layout()).addStretch(1)


        # for widget in self.entry_widgets:
            # self.layout().removeWidget(widget)
            # widget.deleteLater()
        # print('10. removed all entries')
        # self.layout().takeAt(0)
        # self.add_entries(new_entries)

    def update_spacing(self) -> None:
        self.layout().setSpacing(self._spacing + self._separator_height)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        # minus two here to skip the stretch at the end and the line below
        # the bottom item
        for n in range(self.layout().count() - 2):
            item = self.layout().itemAt(n)
            if not item or isinstance(item, QtWidgets.QSpacerItem):
                continue
            # print(item)
            bottom: int = item.widget().geometry().bottom()
            y: int = bottom + self._spacing // 2
            painter.fillRect(self._separator_h_margin, y,
                             self.width() - self._separator_h_margin * 2,
                             self._separator_height,
                             self._separator_color)


def get_backstory_data(file: Path, cached_data: Dict) -> Tuple[int, int]:
    root = file.with_name(file.name + '.metadir')
    if not root.is_dir():
        return 0, 0
    wordcount = 0
    pages = 0
    for dirpath, _, filenames in os.walk(root):
        dir_root = Path(dirpath)
        for fname in filenames:
            # Skip old revision files
            if re.search(r'\.rev\d+$', fname) is not None:
                continue
            try:
                words = len((dir_root / fname)
                            .read_text().split('\n', 1)[1].split())
            except Exception:
                # Just ignore the file if something went wrong
                # TODO: add something here if being verbose?
                pass
            else:
                wordcount += words
                pages += 1
    return wordcount, pages


def index_stories(root: Path) -> Tuple[taggedlist.AttributeData, Entries]:
    cache_file = CACHE_DIR / 'index.pickle'
    if cache_file.exists():
        cached_data = pickle.loads(cache_file.read_bytes())
    else:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cached_data = {}
    entries = []
    i = 0
    for dirpath, _, filenames in os.walk(root):
        dir_root = Path(dirpath)
        for fname in filenames:
            metafile = dir_root / f'.{fname}.metadata'
            if not metafile.exists():
                continue
            metadata = json.loads(metafile.read_text(encoding='utf-8'))
            file = dir_root / fname
            stat = file.stat()
            if file in cached_data \
                    and cached_data[file]['modified'] == stat.st_mtime:
                wordcount = cached_data[file]['wordcount']
            else:
                wordcount = len(file.read_text().split())
                cached_data[file] = {'modified': stat.st_mtime,
                                     'wordcount': wordcount}
            backstory_wordcount, backstory_pages = get_backstory_data(file, cached_data)
            entry = Entry(
                i,
                metadata['title'],
                frozenset(metadata['tags']),
                metadata['description'],
                wordcount,
                backstory_wordcount,
                backstory_pages,
                file,
                stat.st_mtime,
                metafile
            )
            entries.append(entry)
            i += 1
    cache_file.write_bytes(pickle.dumps(cached_data))
    f = taggedlist.FilterFuncs
    p = taggedlist.ParseFuncs
    attributes: Dict[str, Dict[str, Callable]] = {
        'title': {'filter': f.text, 'parser': p.text},
        'tags': {'filter': f.tags, 'parser': p.tags},
        'description': {'filter': f.text, 'parser': p.text},
        'wordcount': {'filter': f.number},
        'backstorywordcount': {'filter': f.number},
        'backstorypages': {'filter': f.number},
        'file': {},
        'lastmodified': {'filter': f.number},
        'metadatafile': {},
    }
    return attributes, tuple(entries)


def write_metadata(entries: Entries) -> None:
    for entry in entries:
        metadata = {
            'title': entry.title,
            'description': entry.description,
            'tags': list(entry.tags)
        }
        entry.metadatafile.write_text(json.dumps(metadata), encoding='utf-8')


# TERMINAL

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
                 commands: Dict[str, Tuple[Any, str]]) -> None:
        super().__init__(parent)
        self.command_help: Dict[str, Tuple[str, List[Tuple[str, str]]]] = {
            'f': ('Filter entries (aka show only entries matching the filter)',
                  [('', 'List the active filters.'),
                   ('-', 'Reset all filters.'),
                   ('[ndtcbp]-', 'Reset the specified filter.'),
                   ('[ndtcbp]', 'Don\'t apply any filter, instead set the '
                                'terminal\'s input text to the specified '
                                'filter\'s current value.'),
                   ('n', 'Filter on titles (case insensitive).'),
                   ('n_', 'Show only entries with empty titles.'),
                   ('d', 'Filter on descriptions (case insensitive).'),
                   ('d_', 'Show only entries with empty descriptions.'),
                   ('t', 'Filter on tags. Supports AND (comma , ), '
                         'OR (vertical bar | ), NOT prefix (dash - ), and tag '
                         'macros (use @ as prefix) specified in the config. '
                         'AND and OR can\'t be used mixed without explicit '
                         'parentheses to specify precedence. Spaces are '
                         'allowed in tag names, but not (),| . Tags are case '
                         'sensitive.'),
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
                   ('[ndt]123', "Don't edit anything, instead set the "
                                "terminal's input text to the current value "
                                "of the specified attribute in entry 123."),
                   ('[nd]123 text', 'Set the value of the specified '
                                    'attribute in entry 123 to "text".'),
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
                  [('', 'Show current sort key and order.'),
                   ('[ncbpm]-', 'Sort descending instead of ascending.'),
                   ('n', 'Sort by title.'),
                   ('c', 'Sort by wordcount.'),
                   ('b', 'Sort by backstory wordcount.'),
                   ('p', 'Sort by number of backstory pages.'),
                   ('m', 'Sort by last modified date.')]),
            'q': ('Quit sapfo', []),
            '?': ('Print simple help',
                  [('', 'Print list of all commands.'),
                   ('<any valid command>',
                    'Print short description of this command.')]),
            'x': ('Open entry file in external editor.',
                  [('123', "Open entry 123's file (note: not sapfo's json "
                           "metadata file) in an external editor.")]),
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
            'h': ('Show extended help',
                  ([('', 'Toggle extended help view.')]
                   + [(cmd, f'Show help for {desc!r}')
                      for cmd, (_, desc) in sorted(commands.items())]))
        }

        def escape(s: str) -> str:
            return s.replace('<', '&lt;').replace('>', '&gt;')

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
    open_ = pyqtSignal(int)
    quit = pyqtSignal(str)
    edit = pyqtSignal(str)
    external_edit = pyqtSignal(str)
    open_meta = pyqtSignal(str)
    manage_tags = pyqtSignal(str)
    new_entry = pyqtSignal(str)
    count_length = pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget, get_tags: Callable,
                 history_file: Path) -> None:
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox,
                         history_file=history_file)
        self.get_tags = get_tags
        self.autocomplete_type = ''  # 'path' or 'tag'
        # These two are set in reload_settings() in sapfo.py
        self.rootpath = Path()
        self.tagmacros: Dict[str, str] = {}
        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'x': (self.external_edit, 'Open in external program/editor'),
            'm': (self.open_meta, 'Open in meta viewer'),
            't': (self.manage_tags, 'Manage tags'),
            'n': (self.new_entry, 'New entry'),
            'c': (self.count_length, 'Count total length'),
            'h': (self.cmd_show_extended_help, 'Show extended help')
        }
        self.help_view = HelpView(self, self.commands)
        # Default to show help about itself
        self.help_view.show_help('h')
        cast(QtWidgets.QBoxLayout,
             self.layout()).insertWidget(0, self.help_view)

    def cmd_show_extended_help(self, arg: str) -> None:
        if not arg and self.help_view.isVisible():
            self.help_view.hide()
        else:
            success = self.help_view.show_help(arg or 'h')
            if success:
                self.help_view.show()
            else:
                self.error('Unknown command')
                self.help_view.hide()

    def update_settings(self, settings: Dict) -> None:
        self.rootpath = Path(settings['path']).expanduser()
        self.tagmacros = settings['tag macros']
        # Terminal animation settings
        self.output_term.animate = settings['animate terminal output']
        interval = settings['terminal animation interval']
        if interval < 1:
            self.error('Too low animation interval')
        self.output_term.set_timer_interval(max(1, interval))

    def command_parsing_injection(self, arg: str) -> Optional[bool]:
        if arg.isdigit():
            self.open_.emit(int(arg))
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
            macros = ('@' + x for x in sorted(self.tagmacros.keys()))
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
