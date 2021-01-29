import enum
import re
from pathlib import Path
from typing import (Any, Dict, FrozenSet, ItemsView, Iterable, Mapping,
                    NamedTuple, Optional, Tuple, Union, ValuesView)

from .tagsystem import compile_tag_filter, match_tag_filter


class AttrParseError(Exception):
    pass


class Entry:
    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        self._data: Dict[str, Any] = data.copy() if data is not None else {}

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Entry) and self._data == other._data

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def as_dict(self) -> Dict[str, Any]:
        return self._data.copy()

    def replace(self, **kwargs: Any) -> 'Entry':
        new_data = self._data.copy()
        new_data.update(**kwargs)
        return Entry(new_data)


Entries = Tuple[Entry, ...]


class AttrType(enum.Enum):
    TEXT = enum.auto()
    INT = enum.auto()
    FLOAT = enum.auto()
    TAGS = enum.auto()
    PATH = enum.auto()


class Attr(NamedTuple):
    name: str
    type_: AttrType
    abbrev: str = ''
    editable: bool = False
    filter_help: str = ''
    sort_help: str = ''

    @property
    def _is_sortable(self) -> bool:
        return len(self.sort_help) > 0

    @property
    def _is_filterable(self) -> bool:
        return len(self.filter_help) > 0

    def _load_value(self, raw_value: Any) -> Any:
        if self.type_ in {AttrType.TEXT, AttrType.INT}:
            return raw_value
        elif self.type_ == AttrType.TAGS:
            return frozenset(raw_value)
        else:
            raise NotImplementedError(f"Can't load attribute of type {self.type_}")

    def _encode_value(self, entry: Entry) -> Any:
        assert self.editable
        if self.type_ == AttrType.TEXT:
            return entry[self.name] if self.name in entry else ''
        elif self.type_ == AttrType.INT:
            return entry[self.name] if self.name in entry else 0
        elif self.type_ == AttrType.FLOAT:
            return entry[self.name] if self.name in entry else 0.0
        elif self.type_ == AttrType.TAGS:
            return list(entry[self.name]) if self.name in entry else []
        else:
            raise NotImplementedError(f"Can't encode attribute of type {self.type_}")

    def _run_parser(self, rawtext: str) -> Any:
        # TODO: better typing?
        assert self.editable
        if self.type_ == AttrType.TEXT:
            return rawtext
        elif self.type_ == AttrType.INT:
            try:
                return int(rawtext)
            except ValueError:
                raise AttrParseError()
        elif self.type_ == AttrType.TAGS:
            return frozenset(re.split(r'\s*,\s*', rawtext)) - frozenset([''])
        else:
            raise NotImplementedError(f"Can't parse attribute of type {self.type_}")

    def _run_filter(self, payload: str, entries: Entries,
                    tagmacros: Dict[str, str]) -> bool:
        if self.type_ == AttrType.TEXT:
            return any(_filter_text(self.name, payload, entries))
        elif self.type_ == AttrType.INT:
            return any(_filter_number(self.name, payload, entries))
        elif self.type_ == AttrType.TAGS:
            return any(_filter_tags(self.name, payload, entries, tagmacros))
        else:
            raise NotImplementedError(f"Can't filter attribute of type {self.type_}")


AttributeData = Dict[str, Attr]


def _filter_text(attribute: str, payload: str, entries: Entries
                 ) -> Iterable[Entry]:
    """
    Return a tuple with the entries that include the specified text
    in the payload variable. The filtering in case-insensitive.
    """
    if not payload:
        return (entry for entry in entries if not entry[attribute])
    elif payload == NONEMPTY_SEARCH:
        return (entry for entry in entries if entry[attribute])
    else:
        return (entry for entry in entries
                if payload.lower() in entry[attribute].lower())


def _filter_number(attribute: str, payload: str, entries: Entries
                   ) -> Iterable[Entry]:
    from operator import ge, gt, le, lt
    compfuncs = {'<': lt, '>': gt, '<=': le, '>=': ge}
    expressions = [(compfuncs[m.group(1)], int(m.group(2).replace('k', '000')))
                   for m in re.finditer(r'([<>][=]?)(\d+k?)', payload)]

    def matches(entry: Entry) -> bool:
        return all(fn(entry[attribute], num)
                   for fn, num in expressions)
    return filter(matches, entries)


def _filter_tags(attribute: str, payload: str, entries: Entries,
                 tagmacros: Dict[str, str]) -> Iterable[Entry]:
    if not payload:
        return (entry for entry in entries if not entry[attribute])
    elif payload == NONEMPTY_SEARCH:
        return (entry for entry in entries if entry[attribute])
    else:
        tag_filter = compile_tag_filter(payload, tagmacros)
        return (entry for entry in entries
                if match_tag_filter(tag_filter, entry[attribute]))


def filter_entry(entry: Entry, filters: Iterable[Tuple[str, str]],
                 attributedata: AttributeData,
                 tagmacros: Dict[str, str]) -> bool:
    for attribute, payload in filters:
        attr = attributedata[attribute]
        if not attr._run_filter(payload, tuple([entry]), tagmacros):
            return False
    return True


ATTR_INDEX = 'index_'
ATTR_TITLE = 'title'
ATTR_TAGS = 'tags'
ATTR_DESCRIPTION = 'description'
ATTR_WORDCOUNT = 'wordcount'
ATTR_BACKSTORY_WORDCOUNT = 'backstorywordcount'
ATTR_BACKSTORY_PAGES = 'backstorypages'
ATTR_FILE = 'file'
ATTR_LAST_MODIFIED = 'lastmodified'
ATTR_METADATA_FILE = 'metadatafile'


builtin_attrs = {
    ATTR_INDEX: Attr(
        name=ATTR_INDEX,
        type_=AttrType.INT,
    ),
    ATTR_TITLE: Attr(
        name=ATTR_TITLE,
        type_=AttrType.TEXT,
        abbrev='n',
        editable=True,
        filter_help='titles',
        sort_help='title',
    ),
    ATTR_TAGS: Attr(
        name=ATTR_TAGS,
        type_=AttrType.TAGS,
        abbrev='t',
        editable=True,
        filter_help='tags',
    ),
    ATTR_DESCRIPTION: Attr(
        name=ATTR_DESCRIPTION,
        type_=AttrType.TEXT,
        abbrev='d',
        editable=True,
        filter_help='descriptions',
    ),
    ATTR_WORDCOUNT: Attr(
        name=ATTR_WORDCOUNT,
        type_=AttrType.INT,
        abbrev='c',
        filter_help='wordcount',
        sort_help='wordcount',
    ),
    ATTR_BACKSTORY_WORDCOUNT: Attr(
        name=ATTR_BACKSTORY_WORDCOUNT,
        type_=AttrType.INT,
        abbrev='b',
        filter_help='backstory wordcount',
        sort_help='backstory wordcount',
    ),
    ATTR_BACKSTORY_PAGES: Attr(
        name=ATTR_BACKSTORY_PAGES,
        type_=AttrType.INT,
        abbrev='p',
        editable=True,
        filter_help='number of backstory pages',
        sort_help='number of backstory pages',
    ),
    ATTR_FILE: Attr(
        name=ATTR_FILE,
        type_=AttrType.PATH,
    ),
    ATTR_LAST_MODIFIED: Attr(
        name=ATTR_LAST_MODIFIED,
        type_=AttrType.FLOAT,
        abbrev='m',
        sort_help='last modified date',
    ),
    ATTR_METADATA_FILE: Attr(
        name=ATTR_METADATA_FILE,
        type_=AttrType.PATH,
    ),
}


# A gloriously ugly hack to pass a Special Text into filter_text
NONEMPTY_SEARCH = '!)(__**??**__)(!'


def edit_entry(entry: Entry, attribute: str, rawnewvalue: str,
               attributedata: AttributeData) -> Entry:
    """
    Edit a single entry and return the updated tuple of entries.
    """
    if not attributedata[attribute].editable:
        raise AttributeError('Attribute is read-only')
    newvalue = attributedata[attribute]._run_parser(rawnewvalue)
    return entry.replace(**{attribute: newvalue})
