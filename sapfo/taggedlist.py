from operator import attrgetter
from pathlib import Path
import re
from typing import (Any, Callable, Dict, FrozenSet, Iterable, NamedTuple,
                    Optional, Tuple)

from libsyntyche.oldtagsystem import compile_tag_filter, match_tag_filter


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


Entries = Tuple[Entry, ...]

AttributeData = Dict[str, Dict[str, Callable]]


def parse_text(rawtext: str) -> str:
    return rawtext


def parse_tags(rawtext: str) -> FrozenSet[str]:
    return frozenset(re.split(r'\s*,\s*', rawtext)) - frozenset([''])


def edit_entry(index: int, entries: Entries,
               attribute: str, rawnewvalue: str,
               attributedata: AttributeData) -> Entries:
    """
    Edit a single entry and return the updated tuple of entries.
    """
    if attributedata[attribute]['parser'] is None:
        raise AttributeError('Attribute is read-only')
    newvalue = attributedata[attribute]['parser'](rawnewvalue)
    entry = entries[index]._replace(**{attribute: newvalue})
    return entries[:index] + (entry,) + entries[index+1:]
    # return update_entry(entries, index, attribute, newvalue)


def replace_tags(oldtagstr: str, newtagstr: str, entries: Entries,
                 visible_entries: Entries, attribute: str) -> Entries:
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
    visible_entry_ids = next(zip(*visible_entries))
    oldtag, newtag = makeset(oldtagstr), makeset(newtagstr)

    def replace_tag(entry: Entry) -> Entry:
        # Only replace in visible entries
        # and in entries where the old tag exists, if it's specified
        if entry[0] not in visible_entry_ids \
                or (oldtagstr and oldtagstr not in getattr(entry, attribute)):
            return entry
        tags = (getattr(entry, attribute) - oldtag) | newtag
        return entry._replace(**{attribute: tags})
    return tuple(map(replace_tag, entries))


def undo(entries: Entries, undoitems: Entries) -> Entries:
    for item in undoitems:
        entries = entries[:item.index_] + (item,) + entries[item.index_+1:]
    return entries


def get_diff(oldentries: Entries, newentries: Entries
             ) -> Tuple[Entries, Entries]:
    """
    Return a tuple of pairs (old, new) with entries that has been changed.
    """
    diffpairs: Iterable[Tuple[Entry, Entry]] = (
            (oldentry, newentry)
            for oldentry, newentry in zip(oldentries, newentries)
            if newentry != oldentry)
    return tuple(zip(*diffpairs))


def filter_text(attribute: str, payload: str, entries: Entries
                ) -> Iterable[Entry]:
    """
    Return a tuple with the entries that include the specified text
    in the payload variable. The filtering in case-insensitive.
    """
    if not payload:
        return (entry for entry in entries
                if not getattr(entry, attribute))
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
    else:
        tag_filter = compile_tag_filter(payload, tagmacros)
        return (entry for entry in entries
                if match_tag_filter(tag_filter, getattr(entry, attribute)))


def filter_entries(entries: Entries, filters: Iterable[Tuple[str, str]],
                   attributedata: AttributeData,
                   tagmacros: Dict[str, str]) -> Entries:
    """
    Return a tuple with all entries that match the filters.

    filters is an iterable with (attribute, payload) pairs where payload is
    the string to be used with the attribute's specified filter function.
    """
    filtered_entries = entries
    for attribute, payload in filters:
        func = attributedata[attribute]['filter']
        if func == filter_tags:
            filtered_entries = func(attribute, payload, filtered_entries,
                                    tagmacros)
        else:
            filtered_entries = func(attribute, payload, filtered_entries)
    return tuple(filtered_entries)


def sort_entries(entries: Entries, attribute: str, reverse: bool) -> Entries:
    return tuple(sorted(entries, key=attrgetter(attribute), reverse=reverse))


def generate_visible_entries(entries: Entries,
                             filters: Iterable[Tuple[str, str]],
                             attributedata: AttributeData,
                             sort_by: str,
                             reverse: bool,
                             tagmacros: Dict[str, str]) -> Entries:
    filtered_entries = filter_entries(entries, filters, attributedata,
                                      tagmacros)
    return sort_entries(filtered_entries, sort_by, reverse)


class ParseFuncs:
    text = parse_text
    tags = parse_tags


class FilterFuncs:
    text = filter_text
    number = filter_number
    tags = filter_tags
