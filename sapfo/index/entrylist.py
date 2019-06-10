from datetime import datetime
import json
import os
from pathlib import Path
import pickle
import re
from typing import (Callable, cast, Dict, FrozenSet, Iterable,
                    List, Optional, Tuple)

from PyQt5 import QtCore, QtGui, QtWidgets

from ..common import ActiveFilters, CACHE_DIR, SortBy
from ..declarative import grid, hflow, label
from ..listlayout import ListLayout
from ..taggedlist import (AttributeData, edit_entry, Entries, Entry,
                          FilterFuncs, ParseFuncs)


class EntryWidget(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget, number: int,
                 total_count: int, entry: Entry, length_template: str,
                 tag_colors: Dict[str, str]) -> None:
        super().__init__(parent)
        self.entry = entry
        self.number = number
        self.numlen = len(str(total_count - 1))
        self.length_template = length_template
        self.number_widget = label(f'{number:>{self.numlen}}',
                                   'number', parent=self)
        self.title_widget = label(entry.title, 'title', parent=self)
        self.last_modified_widget = label(
            datetime.fromtimestamp(entry.lastmodified).strftime('%Y-%m-%d'),
            'last_modified', parent=self)
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
        self.recap_widget = label(entry.recap, 'recap', word_wrap=True,
                                  parent=self)
        if not entry.recap:
            self.recap_widget.hide()
        self.tag_widgets: List[QtWidgets.QLabel] = []
        self._tag_colors = tag_colors
        for tag in sorted(entry.tags):
            widget = label(tag, 'tag', parent=self)
            if tag in tag_colors:
                widget.setStyleSheet(f'background: {tag_colors[tag]};')
            self.tag_widgets.append(widget)
        self.top_row = hflow(self.title_widget,
                             self.word_count_widget,
                             self.last_modified_widget,
                             *self.tag_widgets)
        self.setLayout(grid({
            (0, 0): self.number_widget,
            (0, 1): self.top_row,
            (1, (0, 1)): self.desc_widget,
            (2, (0, 1)): self.recap_widget,
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

    def update_number(self) -> None:
        self.number_widget.setText(f'{self.number:>{self.numlen}}')

    def update_data(self, entry: Entry,
                    total_count: Optional[int] = None) -> None:
        self.entry = entry
        if total_count is not None:
            self.numlen = len(str(total_count - 1))
            self.update_number()
        self.title_widget.setText(entry.title)
        self.word_count_widget.setText(
            self.length_template.format(
                wordcount=entry.wordcount,
                backstorypages=entry.backstorypages,
                backstorywordcount=entry.backstorywordcount
            ))
        self.last_modified_widget.setText(
            datetime.fromtimestamp(entry.lastmodified).strftime('%Y-%m-%d'))
        self.desc_widget.setText(entry.description or '[no desc]')
        desc_class = ('description' if entry.description
                      else 'empty_description')
        if desc_class != self.desc_widget.objectName():
            self.desc_widget.setObjectName(desc_class)
            # Force the style to update
            self.desc_widget.style().polish(self.desc_widget)
        self.recap_widget.setText(entry.recap)
        if entry.recap and not self.recap_widget.isVisible():
            self.recap_widget.show()
        elif not entry.recap and self.recap_widget.isVisible():
            self.recap_widget.hide()
        tags = sorted(entry.tags)
        for tag_widget, tag in zip(self.tag_widgets, tags):
            tag_widget.setText(tag)
        old_tag_count = len(self.tag_widgets)
        new_tag_count = len(tags)
        if old_tag_count > new_tag_count:
            for tag_widget in self.tag_widgets[new_tag_count:]:
                self.top_row.removeWidget(tag_widget)
                tag_widget.deleteLater()
            self.tag_widgets = self.tag_widgets[:new_tag_count]
        elif old_tag_count < new_tag_count:
            for tag in tags[old_tag_count:]:
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

    visible_count_changed = QtCore.pyqtSignal(int, int)

    def __init__(self, parent: QtWidgets.QWidget, length_template: str,
                 dry_run: bool, sorted_by: SortBy,
                 active_filters: ActiveFilters,
                 attributedata: AttributeData) -> None:
        super().__init__(parent)
        self.dry_run = dry_run
        # Model values
        self.active_filters = active_filters
        self.attributedata = attributedata
        self.sorted_by = sorted_by
        self.tag_macros: Dict[str, str] = {}
        self.undostack: List[Entries] = []
        # View values
        self._spacing: int = 0
        self._separator_color: QtGui.QColor = QtGui.QColor('black')
        self._separator_h_margin = 0
        self._separator_height = 1
        self.length_template = length_template
        self.entry_class = EntryWidget
        self.entry_widgets: List[EntryWidget] = []
        self._tag_colors: Dict[str, str] = {}
        layout = ListLayout(self)
        layout.setObjectName('entry_list_layout')
        self.layout_ = layout

    @property
    def entries(self) -> Iterable[Entry]:
        return [w.entry for w in self.entry_widgets]

    @property
    def visible_entries(self) -> Iterable[Entry]:
        return [w.entry for w in self.entry_widgets if w.isVisible()]

    def visible_entry(self, pos: int) -> Entry:
        item = self.layout_.visibleItemAt(pos)
        if item is None:
            raise IndexError
        else:
            entry: Entry = cast(EntryWidget, item.widget()).entry
            return entry

    def visible_count(self) -> int:
        return self.layout_.visible_count()

    def count(self) -> int:
        return self.layout_.count()

    def sort(self) -> None:
        self.layout_.sort(self.sorted_by.key, self.sorted_by.descending)

    def filter_(self) -> None:
        filter_list = [(k, v) for k, v
                       in self.active_filters._asdict().items()
                       if v is not None]
        self.layout_.filter_(filter_list, self.attributedata, self.tag_macros)
        count = self.count()
        visible_count = self.visible_count()
        self.visible_count_changed.emit(visible_count, count)

    def undo(self) -> int:
        if not self.undostack:
            return 0
        items = {i.entry.index_: i for i in self.entry_widgets}
        undo_batch = self.undostack.pop()
        for entry in undo_batch:
            items[entry.index_].update_data(entry)
        if not self.dry_run:
            write_metadata(undo_batch)
        return len(undo_batch)

    def edit(self, pos: int, attribute: str, new_value: str) -> bool:
        item = self.layout_.visibleItemAt(pos)
        if item is None:
            raise IndexError
        widget = cast(EntryWidget, item.widget())
        old_entry = widget.entry
        new_entry = edit_entry(old_entry, attribute, new_value,
                               self.attributedata)
        if new_entry != old_entry:
            self.undostack.append((old_entry,))
            widget.update_data(new_entry)
            if not self.dry_run:
                write_metadata([new_entry])
            self.filter_()
            return True
        return False

    def replace_tags(self, oldtagstr: str, newtagstr: str,
                     attribute: str) -> int:
        """
        Return a tuple where all instances of one tag is replaced by a new tag or
        where a tag has been either added to or removed from all visible entries.

        If oldtagstr isn't specified (eg. empty), add the new tag
        to all visible entries.

        If newtagstr isn't specified, remove the old tag from all visible entries.

        If both are specified, replace the old tag with the new tag, but only in
        the (visible) entries where old tag exists.
        """
        def makeset(x: str) -> FrozenSet[str]:
            return frozenset([x] if x else [])
        # Failsafe!
        if not oldtagstr and not newtagstr:
            raise AssertionError('No tags specified, nothing to do')
        oldtag, newtag = makeset(oldtagstr), makeset(newtagstr)

        def replace_tag(entry: Entry) -> Entry:
            # Only replace in visible entries
            # and in entries where the old tag exists, if it's specified
            if oldtagstr and oldtagstr not in getattr(entry, attribute):
                return entry
            tags = (getattr(entry, attribute) - oldtag) | newtag
            return entry._replace(**{attribute: tags})

        old_entries = []
        new_entries = []
        for item in self.entry_widgets:
            if item.isHidden():
                continue
            new_entry = replace_tag(item.entry)
            if new_entry != item.entry:
                old_entries.append(item.entry)
                new_entries.append(new_entry)
                item.update_data(new_entry)
        if old_entries:
            self.undostack.append(tuple(old_entries))
        if not self.dry_run:
            write_metadata(tuple(new_entries))
        self.filter_()
        return len(old_entries)

    @property
    def tag_colors(self) -> Dict[str, str]:
        return self._tag_colors

    @tag_colors.setter
    def tag_colors(self, new_colors: Dict[str, str]) -> None:
        if self._tag_colors != new_colors:
            self._tag_colors = new_colors
            for entry in self.entry_widgets:
                entry.tag_colors = new_colors

    def set_entries(self, new_entries: Entries,
                    progress: QtWidgets.QProgressDialog) -> None:
        total_count = len(new_entries)
        if self.entry_widgets:
            progress.setLabelText('Clearing old widgets...')
            progress.setMaximum(len(self.entry_widgets))
            progress.setValue(0)
            self.entry_widgets.clear()
            n = 0
            while self.layout_.count() > 0:
                item = self.layout_.takeAt(0)
                if item is None:
                    break
                item.widget().deleteLater()
                del item
                n += 1
                progress.setValue(1)
        progress.setLabelText('Positioning widgets...')
        progress.setValue(0)
        progress.setMaximum(total_count)
        for n, entry in enumerate(new_entries):
            entry_widget = self.entry_class(self, n, total_count, entry,
                                            self.length_template,
                                            self.tag_colors)
            entry_widget.hide()
            self.entry_widgets.append(entry_widget)
            self.layout_.addWidget(entry_widget)
            progress.setValue(n + 1)
        progress.setLabelText('Sorting...')
        self.sort()
        progress.setLabelText('Filtering...')
        self.filter_()

    def update_spacing(self) -> None:
        self.layout_.setSpacing(self._spacing + self._separator_height)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        # minus one here to skip the line below the bottom item
        for n in range(self.layout_.count() - 1):
            item = self.layout_.itemAt(n)
            if not item or isinstance(item, QtWidgets.QSpacerItem):
                continue
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


def index_stories(root: Path, progress: QtWidgets.QProgressDialog
                  ) -> Entries:
    progress.setLabelText('Loading cache...')
    cache_file = CACHE_DIR / 'index.pickle'
    if cache_file.exists():
        cached_data = pickle.loads(cache_file.read_bytes())
    else:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cached_data = {}
    entries = []
    i = 0
    progress.setLabelText('Indexing files...')
    hits = list(os.walk(root))
    progress.setLabelText('Reading file data...')
    progress.setMaximum(sum(len(fnames) for _, _, fnames in hits))
    n = 0
    for dirpath, _, filenames in hits:
        dir_root = Path(dirpath)
        for fname in filenames:
            progress.setValue(n)
            metafile = dir_root / f'.{fname}.metadata'
            if not metafile.exists():
                n += 1
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
                index_=i,
                title=metadata['title'],
                tags=frozenset(metadata['tags']),
                description=metadata['description'],
                wordcount=wordcount,
                backstorywordcount=backstory_wordcount,
                backstorypages=backstory_pages,
                file=file,
                lastmodified=stat.st_mtime,
                metadatafile=metafile,
                recap=metadata.get('recap', ''),
            )
            entries.append(entry)
            i += 1
            n += 1
    progress.setMaximum(0)
    progress.setValue(0)
    progress.setLabelText('Saving cache...')
    cache_file.write_bytes(pickle.dumps(cached_data))
    return tuple(entries)


def entry_attributes() -> AttributeData:
    # Keep this down here only to make it easier to see if we're missing
    # something in index_stories
    f = FilterFuncs
    p = ParseFuncs
    attributes: Dict[str, Dict[str, Callable]] = {
        'title': {'filter': f.text, 'parser': p.text},
        'tags': {'filter': f.tags, 'parser': p.tags},
        'description': {'filter': f.text, 'parser': p.text},
        'wordcount': {'filter': f.number},
        'backstorywordcount': {'filter': f.number},
        'backstorypages': {'filter': f.number},
        'file': {},
        'lastmodified': {},
        'metadatafile': {},
        'recap': {'filter': f.text, 'parser': p.text},
    }
    return attributes


def write_metadata(entries: Iterable[Entry]) -> None:
    for entry in entries:
        metadata = {
            'title': entry.title,
            'description': entry.description,
            'tags': list(entry.tags),
            'recap': entry.recap,
        }
        entry.metadatafile.write_text(json.dumps(metadata), encoding='utf-8')
