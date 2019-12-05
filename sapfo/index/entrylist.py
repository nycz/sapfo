import json
from operator import attrgetter
import os
from pathlib import Path
import pickle
import re
from typing import (Any, Callable, cast, Dict, FrozenSet, Iterable,
                    List, Optional, Tuple)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from libsyntyche.widgets import Signal0, Signal1

from .. import declin, declin_qt
from ..common import ActiveFilters, CACHE_DIR, Settings, SortBy
from ..taggedlist import (AttributeData, edit_entry, Entries, Entry,
                          filter_entry, FilterFuncs, ParseFuncs)


class EntryList(QtWidgets.QListWidget):

    ENTRY_ROLE = QtCore.Qt.UserRole
    POS_ROLE = QtCore.Qt.UserRole + 1

    class SortInfo:
        def __init__(self, key: str, reverse: bool) -> None:
            self.key = key
            self.reverse = reverse

    class EntryItem(QtWidgets.QListWidgetItem):
        def __init__(self, entry: Entry, relative_pos: int,
                     sort_info: 'EntryList.SortInfo',
                     parent: Optional[QtWidgets.QListWidget] = None
                     ) -> None:
            super().__init__(parent)
            self._entry = entry
            self._relative_pos = relative_pos
            self._sort_info = sort_info

        def __lt__(self, other: QtWidgets.QListWidgetItem) -> bool:
            if not isinstance(other, EntryList.EntryItem):
                return False
            result: bool = (getattr(self._entry, self._sort_info.key)
                            < getattr(other._entry, self._sort_info.key))
            return result

        def data(self, role: int) -> Any:
            if role == EntryList.ENTRY_ROLE:
                return self._entry
            elif role == EntryList.POS_ROLE:
                return self._relative_pos
            else:
                return super().data(role)

        def setData(self, role: int, new_data: Any) -> None:
            if role == EntryList.ENTRY_ROLE:
                self._entry = new_data
            elif role == EntryList.POS_ROLE:
                self._relative_pos = new_data
            else:
                super().setData(role, new_data)

    class Delegate(QtWidgets.QStyledItemDelegate):
        def __init__(self, base_gui: str, override_gui: str,
                     tag_colors: Dict[str, str]) -> None:
            super().__init__()
            self.tag_colors: Dict[str, declin.types.Color] = {}
            self.update_tag_colors(tag_colors)
            self.base_gui = base_gui
            self.gui_model: Optional[declin_qt.Model] = None
            self.update_gui(override_gui)
            self.layouts: Dict[str, List[declin_qt.Drawable]] = {}

        def update_gui(self, user_gui: str) -> None:
            try:
                gui_model = declin.parse(self.base_gui, user_gui)
            except declin.common.ParsingError as e:
                print('GUI PARSING ERROR', e)
            else:
                self.gui_model = declin_qt.Model(main=gui_model.main,
                                                 sections=gui_model.sections,
                                                 tag_colors=self.tag_colors)

        def update_tag_colors(self, tag_colors: Dict[str, str]) -> None:
            self.tag_colors = {}
            for tag, raw_color in tag_colors.items():
                try:
                    color = declin.types.Color.parse(raw_color)
                except declin.common.ParsingError as e:
                    print('BROKEN COLOR', tag, raw_color, e)
                else:
                    self.tag_colors[tag] = color

        def sizeHint(self, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtCore.QSize:
            entry = index.data(EntryList.ENTRY_ROLE)
            m = self.gui_model
            if m is not None:
                start_point = m.sections[m.main]
                rect = declin_qt.StretchableRect(option.rect.x(),
                                                 option.rect.y(),
                                                 width=option.rect.width())
                entry_dict = entry._asdict()
                entry_dict['pos'] = index.data(EntryList.POS_ROLE)
                group = declin_qt.calc_size(entry_dict, start_point,
                                            m, rect, 0)
                self.layouts[entry.index_] = list(group.flatten())
                return group.size()
            else:
                return super().sizeHint(option, index)

        def paint(self, painter: QtGui.QPainter,
                  option: QtWidgets.QStyleOptionViewItem,
                  index: QtCore.QModelIndex) -> None:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, on=True)
            entry = index.data(EntryList.ENTRY_ROLE)
            for item in sorted(self.layouts[entry.index_],
                               key=attrgetter('depth'), reverse=True):
                item.draw(painter, y_offset=option.rect.y())
            painter.restore()

    visible_count_changed = QtCore.pyqtSignal(int, int)

    def __init__(self, parent: QtWidgets.QWidget, settings: Settings,
                 dry_run: bool, sorted_by: SortBy,
                 active_filters: ActiveFilters,
                 attributedata: AttributeData,
                 base_gui: str, override_gui: str) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.dry_run = dry_run
        self.settings = settings
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSpacing(0)  # spacing > 0 is just weird man
        # Model values
        self._entries: Entries = tuple()
        self._visible_to_real_pos: Dict[int, int] = {}
        self.active_filters = active_filters
        self.attributedata = attributedata
        self.sorted_by = sorted_by
        self.sort_info = self.SortInfo(self.sorted_by.key,
                                       self.sorted_by.descending)
        self.tag_colors: Dict[str, str] = settings.tag_colors
        settings.tag_colors_changed.connect(self.set_tag_colors)
        self.undostack: List[Entries] = []
        self.delegate = EntryList.Delegate(base_gui, override_gui,
                                           self.tag_colors)
        self.setItemDelegate(self.delegate)

    def update_gui(self, override: str) -> None:
        self.delegate.update_gui(override)

    def set_tag_colors(self, new_colors: Dict[str, str]) -> None:
        if self.tag_colors != new_colors:
            self.tag_colors = new_colors
            self.delegate.update_tag_colors(new_colors)

    @property
    def entries(self) -> Iterable[Entry]:
        return self._entries

    @property
    def visible_entries(self) -> Iterable[Entry]:
        entries = []
        for n in self._visible_to_real_pos.values():
            entry: Entry = self.item(n).data(self.ENTRY_ROLE)
            entries.append(entry)
        return entries

    def set_entries(self, new_entries: Entries,
                    progress: QtWidgets.QProgressDialog) -> None:
        self._entries = new_entries
        count = self.count()
        for _ in range(count):
            self.takeItem(0)
        for n, entry in enumerate(new_entries):
            self.addItem(self.EntryItem(entry, n, self.sort_info, self))
        self.sort()
        self.filter_()

    def visible_entry(self, pos: int) -> Entry:
        entry: Entry = self.item(self._visible_to_real_pos[pos]
                                 ).data(self.ENTRY_ROLE)
        return entry

    def visible_count(self) -> int:
        return sum(not self.isRowHidden(n) for n in range(self.count()))

    def sort(self) -> None:
        self.sort_info.key = self.sorted_by.key
        self.sortItems(Qt.DescendingOrder if self.sorted_by.descending
                       else Qt.AscendingOrder)
        self._visible_to_real_pos = {}
        pos = 0
        for n in range(self.count()):
            if not self.isRowHidden(n):
                self._visible_to_real_pos[pos] = n
                self.item(n).setData(self.POS_ROLE, pos)
                pos += 1

    def filter_(self) -> None:
        filter_list = [(k, v) for k, v
                       in self.active_filters._asdict().items()
                       if v is not None]
        self._visible_to_real_pos = {}
        pos = 0
        count = self.count()
        for n in range(count):
            item = self.item(n)
            if filter_entry(item.data(self.ENTRY_ROLE), filter_list,
                            self.attributedata, self.settings.tag_macros):
                item.setData(self.POS_ROLE, pos)
                self.setRowHidden(n, False)
                self._visible_to_real_pos[pos] = n
                pos += 1
            else:
                self.setRowHidden(n, True)
        self.visible_count_changed.emit(pos, count)

    def undo(self) -> int:
        if not self.undostack:
            return 0
        items = {item._entry.index_: item
                 for item in (cast(EntryList.EntryItem, self.item(i))
                              for i in range(self.count()))}
        undo_batch = self.undostack.pop()
        for entry in undo_batch:
            item = items[entry.index_]
            item.setData(self.ENTRY_ROLE, entry)
            index = self.indexFromItem(item)
            self.dataChanged(index, index)
        if not self.dry_run:
            write_metadata(undo_batch)
        return len(undo_batch)

    def edit_(self, pos: int, attribute: str, new_value: str) -> bool:
        real_pos = self._visible_to_real_pos[pos]
        item = cast(EntryList.EntryItem, self.item(real_pos))
        if item is None:
            raise IndexError
        old_entry = item._entry
        new_entry = edit_entry(old_entry, attribute, new_value,
                               self.attributedata)
        if new_entry != old_entry:
            self.undostack.append((old_entry,))
            item.setData(self.ENTRY_ROLE, new_entry)
            if not self.dry_run:
                write_metadata([new_entry])
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
        for n in range(self.count()):
            item = self.item(n)
            entry: Entry = item.data(self.ENTRY_ROLE)
            if self.isRowHidden(n):
                continue
            new_entry = replace_tag(entry)
            if new_entry != entry:
                old_entries.append(entry)
                new_entries.append(new_entry)
                item.setData(self.ENTRY_ROLE, new_entry)
        if old_entries:
            self.undostack.append(tuple(old_entries))
        if not self.dry_run:
            write_metadata(tuple(new_entries))
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
