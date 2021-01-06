import enum
from pathlib import Path
import re
from typing import (Any, Dict, FrozenSet, ItemsView, Iterable, Mapping, NamedTuple,
                    Optional, Tuple, Union, ValuesView)

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


class NewAttrType(enum.Enum):
    TEXT = enum.auto()
    INT = enum.auto()
    FLOAT = enum.auto()
    TAGS = enum.auto()
    PATH = enum.auto()


class NewAttr(NamedTuple):
    name: str
    type_: NewAttrType
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
        if self.type_ in {NewAttrType.TEXT, NewAttrType.INT}:
            return raw_value
        elif self.type_ == NewAttrType.TAGS:
            return frozenset(raw_value)
        else:
            raise NotImplementedError(f"Can't load attribute of type {self.type_}")

    def _encode_value(self, entry: Entry) -> Any:
        assert self.editable
        if self.type_ == NewAttrType.TEXT:
            return entry[self.name] if self.name in entry else ''
        elif self.type_ == NewAttrType.INT:
            return entry[self.name] if self.name in entry else 0
        elif self.type_ == NewAttrType.FLOAT:
            return entry[self.name] if self.name in entry else 0.0
        elif self.type_ == NewAttrType.TAGS:
            return list(entry[self.name]) if self.name in entry else []
        else:
            raise NotImplementedError(f"Can't encode attribute of type {self.type_}")

    def _run_parser(self, rawtext: str) -> Any:
        # TODO: better typing?
        assert self.editable
        if self.type_ == NewAttrType.TEXT:
            return rawtext
        elif self.type_ == NewAttrType.INT:
            try:
                return int(rawtext)
            except ValueError:
                raise AttrParseError()
        elif self.type_ == NewAttrType.TAGS:
            return frozenset(re.split(r'\s*,\s*', rawtext)) - frozenset([''])
        else:
            raise NotImplementedError(f"Can't parse attribute of type {self.type_}")

    def _run_filter(self, payload: str, entries: Entries,
                    tagmacros: Dict[str, str]) -> bool:
        if self.type_ == NewAttrType.TEXT:
            return any(_filter_text(self.name, payload, entries))
        elif self.type_ == NewAttrType.INT:
            return any(_filter_number(self.name, payload, entries))
        elif self.type_ == NewAttrType.TAGS:
            return any(_filter_tags(self.name, payload, entries, tagmacros))
        else:
            raise NotImplementedError(f"Can't filter attribute of type {self.type_}")


AttributeData = Dict[str, NewAttr]


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
    from operator import lt, gt, le, ge
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
    ATTR_INDEX: NewAttr(
        name=ATTR_INDEX,
        type_=NewAttrType.INT,
    ),
    ATTR_TITLE: NewAttr(
        name=ATTR_TITLE,
        type_=NewAttrType.TEXT,
        abbrev='n',
        editable=True,
        filter_help='titles',
        sort_help='title',
    ),
    ATTR_TAGS: NewAttr(
        name=ATTR_TAGS,
        type_=NewAttrType.TAGS,
        abbrev='t',
        editable=True,
        filter_help='tags',
    ),
    ATTR_DESCRIPTION: NewAttr(
        name=ATTR_DESCRIPTION,
        type_=NewAttrType.TEXT,
        abbrev='d',
        editable=True,
        filter_help='descriptions',
    ),
    ATTR_WORDCOUNT: NewAttr(
        name=ATTR_WORDCOUNT,
        type_=NewAttrType.INT,
        abbrev='c',
        filter_help='wordcount',
        sort_help='wordcount',
    ),
    ATTR_BACKSTORY_WORDCOUNT: NewAttr(
        name=ATTR_BACKSTORY_WORDCOUNT,
        type_=NewAttrType.INT,
        abbrev='b',
        filter_help='backstory wordcount',
        sort_help='backstory wordcount',
    ),
    ATTR_BACKSTORY_PAGES: NewAttr(
        name=ATTR_BACKSTORY_PAGES,
        type_=NewAttrType.INT,
        abbrev='p',
        editable=True,
        filter_help='number of backstory pages',
        sort_help='number of backstory pages',
    ),
    ATTR_FILE: NewAttr(
        name=ATTR_FILE,
        type_=NewAttrType.PATH,
    ),
    ATTR_LAST_MODIFIED: NewAttr(
        name=ATTR_LAST_MODIFIED,
        type_=NewAttrType.FLOAT,
        abbrev='m',
        sort_help='last modified date',
    ),
    ATTR_METADATA_FILE: NewAttr(
        name=ATTR_METADATA_FILE,
        type_=NewAttrType.PATH,
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
