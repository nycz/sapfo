from pathlib import Path
import re
from typing import (Any, Callable, Dict, FrozenSet, Iterable, NamedTuple,
                    Tuple)

from .tagsystem import compile_tag_filter, match_tag_filter


class Attr(NamedTuple):
    name: str
    abbrev: str


class HiddenAttr(NamedTuple):
    name: str


class AttrNames:
    INDEX = HiddenAttr('index_')
    TITLE = Attr('title', 'n')
    TAGS = Attr('tags', 't')
    DESCRIPTION = Attr('description', 'd')
    WORDCOUNT = Attr('wordcount', 'c')
    BACKSTORY_WORDCOUNT = Attr('backstorywordcount', 'b')
    BACKSTORY_PAGES = Attr('backstorypages', 'p')
    FILE = HiddenAttr('file')
    LAST_MODIFIED = Attr('lastmodified', 'm')
    METADATA_FILE = HiddenAttr('metadatafile')
    RECAP = Attr('recap', 'r')


def make_abbrev_dict(*attrs: Attr) -> Dict[str, str]:
    return {a.abbrev: a.name for a in attrs}


class Entry(NamedTuple):
    index_: int
    title: str
    tags: FrozenSet[str]
    description: str
    wordcount: int
    backstorywordcount: int
    backstorypages: int
    file: Path
    lastmodified: float
    metadatafile: Path
    recap: str


assert {v.name for k, v in AttrNames.__dict__.items()
        if not k.startswith('_')} == set(Entry._fields)


Entries = Tuple[Entry, ...]

AttributeData = Dict[str, Dict[str, Callable[..., Any]]]

# A gloriously ugly hack to pass a Special Text into filter_text
NONEMPTY_SEARCH = '!)(__**??**__)(!'


def parse_text(rawtext: str) -> str:
    return rawtext


def parse_tags(rawtext: str) -> FrozenSet[str]:
    return frozenset(re.split(r'\s*,\s*', rawtext)) - frozenset([''])


def edit_entry(entry: Entry, attribute: str, rawnewvalue: str,
               attributedata: AttributeData) -> Entry:
    """
    Edit a single entry and return the updated tuple of entries.
    """
    if attributedata[attribute]['parser'] is None:
        raise AttributeError('Attribute is read-only')
    newvalue = attributedata[attribute]['parser'](rawnewvalue)
    return entry._replace(**{attribute: newvalue})


def filter_text(attribute: str, payload: str, entries: Entries
                ) -> Iterable[Entry]:
    """
    Return a tuple with the entries that include the specified text
    in the payload variable. The filtering in case-insensitive.
    """
    if not payload:
        return (entry for entry in entries
                if not getattr(entry, attribute))
    elif payload == NONEMPTY_SEARCH:
        return (entry for entry in entries
                if getattr(entry, attribute))
    else:
        return (entry for entry in entries
                if payload.lower() in getattr(entry, attribute).lower())


def filter_number(attribute: str, payload: str, entries: Entries
                  ) -> Iterable[Entry]:
    from operator import lt, gt, le, ge
    compfuncs = {'<': lt, '>': gt, '<=': le, '>=': ge}
    expressions = [(compfuncs[m.group(1)], int(m.group(2).replace('k', '000')))
                   for m in re.finditer(r'([<>][=]?)(\d+k?)', payload)]

    def matches(entry: Entry) -> bool:
        return all(fn(getattr(entry, attribute), num)
                   for fn, num in expressions)
    return filter(matches, entries)


def filter_tags(attribute: str, payload: str, entries: Entries,
                tagmacros: Dict[str, str]) -> Iterable[Entry]:
    if not payload:
        return (entry for entry in entries
                if not getattr(entry, attribute))
    elif payload == NONEMPTY_SEARCH:
        return (entry for entry in entries
                if getattr(entry, attribute))
    else:
        tag_filter = compile_tag_filter(payload, tagmacros)
        return (entry for entry in entries
                if match_tag_filter(tag_filter, getattr(entry, attribute)))


def filter_entry(entry: Entry, filters: Iterable[Tuple[str, str]],
                 attributedata: AttributeData,
                 tagmacros: Dict[str, str]) -> bool:
    entries = [entry]
    for attribute, payload in filters:
        func = attributedata[attribute]['filter']
        if func == filter_tags:
            result = func(attribute, payload, entries, tagmacros)
        else:
            result = func(attribute, payload, entries)
        if not list(result):
            return False
    return True


class ParseFuncs:
    text = parse_text
    tags = parse_tags


class FilterFuncs:
    text = filter_text
    number = filter_number
    tags = filter_tags
