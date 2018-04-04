from collections import namedtuple, defaultdict
from functools import partial
from operator import attrgetter
import os
from os.path import exists, join
import re

from libsyntyche.common import read_json, read_file
from libsyntyche.tagsystem import compile_tag_filter, match_tag_filter


def parse_text(rawtext):
    return rawtext

def parse_tags(rawtext):
    return frozenset(re.split(r'\s*,\s*', rawtext)) - frozenset([''])


def edit_entry(index, entries, attribute, rawnewvalue, attributedata):
    """
    Edit a single entry and return the updated tuple of entries.
    """
    if attributedata[attribute]['parser'] is None:
        raise AttributeError('Attribute is read-only')
    newvalue = attributedata[attribute]['parser'](rawnewvalue)
    entry = entries[index]._replace(**{attribute: newvalue})
    return entries[:index] + (entry,) + entries[index+1:]
    # return update_entry(entries, index, attribute, newvalue)

def replace_tags(oldtagstr, newtagstr, entries, visible_entries, attribute):
    """
    Return a tuple where all instances of one tag is replaced by a new tag or
    where a tag has been either added to or removed from all visible entries.

    If oldtagstr isn't specified (eg. empty), add the new tag
    to all visible entries.

    If newtagstr isn't specified, remove the old tag from all visible entries.

    If both are specified, replace the old tag with the new tag, but only in
    the (visible) entries where old tag exists.
    """
    # Failsafe!
    if not oldtagstr and not newtagstr:
        raise AssertionError('No tags specified, nothing to do')
    visible_entry_ids = next(zip(*visible_entries))
    makeset = lambda x: frozenset([x] if x else [])
    oldtag, newtag = makeset(oldtagstr), makeset(newtagstr)
    def replace_tag(entry):
        # Only replace in visible entries
        # and in entries where the old tag exists, if it's specified
        if entry[0] not in visible_entry_ids \
                or (oldtagstr and oldtagstr not in getattr(entry, attribute)):
            return entry
        tags = (getattr(entry, attribute) - oldtag) | newtag
        return entry._replace(**{attribute: tags})
    return tuple(map(replace_tag, entries))

def undo(entries, undoitems):
    for item in undoitems:
        index = item[0]
        entries = entries[:index] + (item,) + entries[index+1:]
    return entries

def get_diff(oldentries, newentries):
    """
    Return a tuple of pairs (old, new) with entries that has been changed.
    """
    diffpairs = ((oldentry, newentry)\
                 for oldentry, newentry in zip(oldentries, newentries)\
                 if newentry != oldentry)
    return tuple(zip(*diffpairs))

def filter_text(attribute, payload, entries):
    """
    Return a tuple with the entries that include the specified text
    in the payload variable. The filtering in case-insensitive.
    """
    if not payload:
        return (entry for entry in entries\
                if not getattr(entry, attribute))
    else:
        return (entry for entry in entries\
                if payload.lower() in getattr(entry, attribute).lower())

def filter_number(attribute, payload, entries):
    from operator import lt,gt,le,ge
    compfuncs = {'<':lt, '>':gt, '<=':le, '>=':ge}
    expressions = [(compfuncs[m.group(1)], int(m.group(2).replace('k','000')))
                   for m in re.finditer(r'([<>][=]?)(\d+k?)', payload)]
    def matches(entry):
        return all(fn(getattr(entry, attribute), num) for fn, num in expressions)
    return filter(matches, entries)

def filter_tags(attribute, payload, entries, tagmacros):
    if not payload:
        return (entry for entry in entries \
                if not getattr(entry, attribute))
    else:
        tag_filter = compile_tag_filter(payload, tagmacros)
        return (entry for entry in entries \
                if match_tag_filter(tag_filter, getattr(entry, attribute)))

def filter_entries(entries, filters, attributedata, tagmacros):
    """
    Return a tuple with all entries that match the filters.

    filters is an iterable with (attribute, payload) pairs where payload is
    the string to be used with the attribute's specified filter function.
    """
    filtered_entries = entries
    for attribute, payload in filters:
        func = attributedata[attribute]['filter']
        if func == filter_tags:
            filtered_entries = func(attribute, payload, filtered_entries, tagmacros)
        else:
            filtered_entries = func(attribute, payload, filtered_entries)
    return tuple(filtered_entries)

def sort_entries(entries, attribute, reverse):
    return tuple(sorted(entries, key=attrgetter(attribute), reverse=reverse))

def generate_visible_entries(entries, filters, attributedata, sort_by, reverse, tagmacros):
    filtered_entries = filter_entries(entries, filters, attributedata, tagmacros)
    return sort_entries(filtered_entries, sort_by, reverse)


# Decoratorstuff

def generate_entrylist(fn):
    filterfuncs = {'text': filter_text, 'number': filter_number, 'tags': filter_tags}
    parserfuncs = {'text': parse_text, 'tags': parse_tags}
    def makedict(d):
        if 'filter' in d:
            d['filter'] = filterfuncs[d['filter']]
        if 'parser' in d:
            d['parser'] = parserfuncs[d['parser']]
        return {x:d.get(x, None) for x in ('filter', 'parser')}

    def entrywrapper(*args, **kwargs):
        attributes, entries = fn(*args, **kwargs)
        attributedata = {name:makedict(attr) for name, attr in attributes}
        Entry = namedtuple('Entry', ('index',) + next(zip(*attributes)))
        entrylist = (Entry(n, *args) for n, args in enumerate(entries))
        return attributedata, tuple(entrylist)
    return entrywrapper
