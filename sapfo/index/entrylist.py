import json
from operator import attrgetter
import os
from pathlib import Path
import pickle
import re
from typing import (Any, Callable, Dict, FrozenSet, Iterable,
                    List, Optional, Tuple)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from .. import declin, declin_qt
from ..common import ActiveFilters, CACHE_DIR, Settings, SortBy
from ..taggedlist import (AttributeData, edit_entry, Entries, Entry,
                          filter_entry, FilterFuncs, ParseFuncs)


def calc_entry_layout(entry: Entry, visible_pos: int,
                      m: declin_qt.Model, y: int, width: int,
                      ) -> declin_qt.DrawGroup:
    entry_dict = entry._asdict()
    entry_dict['pos'] = visible_pos
    rect = declin_qt.StretchableRect(0, y,
                                     width=width)
    return declin_qt.calc_size(entry_dict, m.sections[m.main],
                               m, rect, 0)


class EntryItem:
    def __init__(self, entry: Entry, group: declin_qt.DrawGroup,
                 real_pos: int) -> None:
        self._entry = entry
        self.group = group
        self.pos = real_pos
        self._visible_pos = real_pos
        self._hidden = False
        self.needs_refresh = False

    @property
    def entry(self) -> Entry:
        return self._entry

    @entry.setter
    def entry(self, new_entry: Entry) -> None:
        if self._entry != new_entry:
            self._entry = new_entry
            self.needs_refresh = True

    @property
    def visible_pos(self) -> int:
        return self._visible_pos

    @visible_pos.setter
    def visible_pos(self, new_pos: int) -> None:
        if self._visible_pos != new_pos:
            self._visible_pos = new_pos
            self.needs_refresh = True

    @property
    def hidden(self) -> bool:
        return self._hidden

    @hidden.setter
    def hidden(self, new_val: bool) -> None:
        if self._hidden != new_val:
            self._hidden = new_val
            self.needs_refresh = True


class EntryList(QtWidgets.QWidget):

    visible_count_changed = QtCore.pyqtSignal(int, int)

    def __init__(self, parent: QtWidgets.QWidget, settings: Settings,
                 dry_run: bool, sorted_by: SortBy,
                 active_filters: ActiveFilters,
                 attributedata: AttributeData,
                 base_gui: str, user_gui: str) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self._visible_to_real_pos: Dict[int, int] = {}
        self._minimum_height = 0
        self.dry_run = dry_run
        self.settings = settings
        # Model values
        self._entries: Entries = tuple()
        self.active_filters = active_filters
        self.attributedata = attributedata
        self.sorted_by = sorted_by
        self.raw_tag_colors: Dict[str, str] = settings.tag_colors
        self.tag_colors: Dict[str, declin.types.Color] = {}
        self.update_tag_colors(self.raw_tag_colors)
        settings.tag_colors_changed.connect(self.set_tag_colors)
        self.undostack: List[Entries] = []
        self.entry_items: List[EntryItem] = []
        self.base_gui = base_gui
        self.user_gui = user_gui
        self.gui_model: declin_qt.Model
        self.update_gui()

    def count(self) -> int:
        return len(self.entry_items)

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        if self.width() != ev.oldSize().width():
            self.update_gui()

    def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, on=True)
        min_y = ev.rect().y()
        max_y = ev.rect().y() + ev.rect().height()
        for n, real_pos in sorted(self._visible_to_real_pos.items()):
            item = self.entry_items[real_pos]
            r = item.group.drawable.rect
            if r.bottom() < min_y or r.top() > max_y:
                continue
            for drawitem in sorted(item.group.flatten(),
                                   key=attrgetter('depth'), reverse=True):
                r = drawitem.rect
                if r.bottom() < min_y or r.top() > max_y:
                    continue
                drawitem.draw(painter)

    def recalc_sizes(self) -> None:
        y = 0
        width = self.width()
        for n, real_pos in sorted(self._visible_to_real_pos.items()):
            item = self.entry_items[real_pos]
            group = calc_entry_layout(item.entry, real_pos, self.gui_model,
                                      y, width)
            item.group = group
            y += group.size().height()
        self._minimum_height = y
        self.updateGeometry()

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, self._minimum_height)

    def update_gui(self, user_gui: Optional[str] = None) -> None:
        if user_gui is None:
            user_gui = self.user_gui
        else:
            self.user_gui = user_gui
        try:
            gui_model = declin.parse(self.base_gui, user_gui)
        except declin.common.ParsingError as e:
            print('GUI PARSING ERROR', e)
        else:
            self.gui_model = declin_qt.Model(main=gui_model.main,
                                             sections=gui_model.sections,
                                             tag_colors=self.tag_colors)
        self.recalc_sizes()
        self.update()

    def update_tag_colors(self, tag_colors: Dict[str, str]) -> None:
        self.tag_colors = {}
        for tag, raw_color in tag_colors.items():
            try:
                color = declin.types.Color.parse(raw_color)
            except declin.common.ParsingError as e:
                print('BROKEN COLOR', tag, raw_color, e)
            else:
                self.tag_colors[tag] = color

    def set_tag_colors(self, new_colors: Dict[str, str]) -> None:
        if self.raw_tag_colors != new_colors:
            self.raw_tag_colors = new_colors
            self.update_tag_colors(new_colors)

    @property
    def entries(self) -> Iterable[Entry]:
        return self._entries

    @property
    def visible_entries(self) -> Iterable[Entry]:
        entries = []
        for n in self._visible_to_real_pos.values():
            entries.append(self.entry_items[n].entry)
        return entries

    def set_entries(self, new_entries: Entries,
                    progress: QtWidgets.QProgressDialog) -> None:
        self._entries = new_entries
        self.entry_items.clear()
        y = 0
        width = self.width()
        for n, entry in enumerate(new_entries):
            group = calc_entry_layout(entry, n, self.gui_model, y, width)
            self.entry_items.append(EntryItem(entry, group, n))
            y += group.size().height()
        self.filter_()
        self.sort()

    def visible_entry(self, pos: int) -> Entry:
        return self.entry_items[self._visible_to_real_pos[pos]].entry

    def visible_count(self) -> int:
        return len(self._visible_to_real_pos)

    def sort(self) -> None:
        self.entry_items.sort(
            key=lambda e: getattr(e.entry, self.sorted_by.key),
            reverse=self.sorted_by.descending
        )
        self._visible_to_real_pos.clear()
        pos = 0
        y = 0
        width = self.width()
        for n, item in enumerate(self.entry_items):
            if not item.hidden:
                self._visible_to_real_pos[pos] = n
                item.visible_pos = pos
                item.group = calc_entry_layout(item.entry, pos, self.gui_model,
                                               y, width)
                y += item.group.size().height()
                pos += 1
        self.update()

    def filter_(self) -> None:
        filter_list = [(k, v) for k, v
                       in self.active_filters._asdict().items()
                       if v is not None]
        self._visible_to_real_pos.clear()
        pos = 0
        y = 0
        width = self.width()
        for n, item in enumerate(self.entry_items):
            if filter_entry(item.entry, filter_list,
                            self.attributedata, self.settings.tag_macros):
                item.visible_pos = pos
                item.hidden = False
                item.group = calc_entry_layout(item.entry, pos,
                                               self.gui_model, y, width)
                y += item.group.size().height()
                self._visible_to_real_pos[pos] = n
                pos += 1
            else:
                item.hidden = True
        self._minimum_height = y
        self.updateGeometry()
        self.visible_count_changed.emit(pos, len(self.entry_items))
        self.update()

    def undo(self) -> int:
        if not self.undostack:
            return 0
        items = {item.entry.index_: item for item in self.entry_items}
        undo_batch = self.undostack.pop()
        for entry in undo_batch:
            item = items[entry.index_]
            item.entry = entry
        if not self.dry_run:
            write_metadata(undo_batch)
        self.sort()
        self.filter_()
        return len(undo_batch)

    def edit_(self, pos: int, attribute: str, new_value: str) -> bool:
        real_pos = self._visible_to_real_pos[pos]
        item = self.entry_items[real_pos]
        old_entry = item.entry
        new_entry = edit_entry(old_entry, attribute, new_value,
                               self.attributedata)
        if new_entry != old_entry:
            self.undostack.append((old_entry,))
            item.entry = new_entry
            if not self.dry_run:
                write_metadata([new_entry])
            self.sort()
            self.filter_()
            return True
        return False

    def replace_tags(self, oldtagstr: str, newtagstr: str,
                     attribute: str) -> int:
        """
        Return a tuple where all instances of one tag is replaced by a new tag
        or where a tag has been added to or removed from all visible entries.

        If oldtagstr isn't specified (eg. empty), add the new tag to all
        visible entries.

        If newtagstr isn't specified, remove the old tag from all visible
        entries.

        If both are specified, replace the old tag with the new tag, but only
        in the (visible) entries where old tag exists.
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
        for n, item in enumerate(self.entry_items):
            if item.hidden:
                continue
            entry = item.entry
            new_entry = replace_tag(entry)
            if new_entry != entry:
                old_entries.append(entry)
                new_entries.append(new_entry)
                item.entry = new_entry

        if old_entries:
            self.undostack.append(tuple(old_entries))
        if not self.dry_run:
            write_metadata(tuple(new_entries))
        self.sort()
        self.filter_()
        return len(old_entries)


def get_backstory_data(file: Path, cached_data: Dict[str, Any]
                       ) -> Tuple[int, int]:
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
            backstory_wordcount, backstory_pages = \
                get_backstory_data(file, cached_data)
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
    # TODO: type this better
    attributes: Dict[str, Dict[str, Callable[..., Any]]] = {
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
