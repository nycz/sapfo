from collections import namedtuple, defaultdict
from operator import itemgetter
import os
from os.path import exists, join
import re
import subprocess

from PyQt4 import QtWebKit
from PyQt4.QtCore import pyqtSignal, Qt

from libsyntyche.common import local_path, read_file, read_json, set_hotkey, write_json
from libsyntyche import taggedlist


class IndexFrame(QtWebKit.QWebView):

    view_entry = pyqtSignal(tuple)
    view_meta = pyqtSignal(tuple)
    error = pyqtSignal(str)
    print_ = pyqtSignal(str)
    set_terminal_text = pyqtSignal(str)
    show_popup = pyqtSignal(str, str, str, str)

    def __init__(self, parent, dry_run):
        super().__init__(parent)
        self.setDisabled(True)
        self.dry_run = dry_run
        self.htmltemplates = load_html_templates()
        self.css = None # Is set every time the config is reloaded

        set_hotkey("Ctrl+R", parent, self.reload_view)
        set_hotkey("F5", parent, self.reload_view)

        self.entries = ()
        self.visible_entries = ()
        activefilters = namedtuple('activefilters', 'title description tags wordcount backstorywordcount backstorypages')
        self.active_filters = activefilters(* 6 * (None,))
        self.sorted_by = ('title', False)
        self.undostack = ()

    def update_settings(self, new_settings):
        self.settings = new_settings
        self.reload_view()

    def zoom(self, arg):
        if arg == 'in':
            self.setZoomFactor(self.zoomFactor()+0.1)
        elif arg == 'out':
            self.setZoomFactor(self.zoomFactor()-0.1)
        elif arg == 'reset':
            self.setZoomFactor(1)


    def reload_view(self):
        """
        Reload the entrylist by scanning the metadata files and then refresh
        the view with the updated entrylist.

        Is also the method that generates the entrylist the first time.
        So don't look for a init_everything method/function or anything, kay?
        """
        self.attributedata, self.entries = index_stories(self.settings['path'])
        self.visible_entries = self.regenerate_visible_entries()
        print('reloaded')
        self.refresh_view(keep_position=True)

    def refresh_view(self, keep_position=False):
        """
        Refresh the view with the filtered entries and the current css.
        The full entrylist is not touched by this.
        """
        frame = self.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        body = generate_html_body(self.visible_entries,
                                  self.htmltemplates.tags,
                                  self.htmltemplates.entry,
                                  self.settings['entry length template'],
                                  self.settings['tag colors'])
        self.setHtml(self.htmltemplates.index_page.format(body=body, css=self.css))
        if keep_position:
            frame.setScrollBarValue(Qt.Vertical, pos)
        print('refreshed')

    def get_tags(self):
        """
        Return all tags and how many times they appear among the entries.
        Called by the terminal for the tab completion.
        """
        tags = defaultdict(int)
        for e in self.entries:
            for t in e.tags:
                tags[t] += 1
        return list(tags.items())

    def list_(self, arg):
        if arg.startswith('f'):
            filters = ('{} {}'.format(cmd, payload) for cmd, payload in self.active_filters)
            if self.active_filters:
                self.print_.emit(', '.join(filters))
            else:
                self.error.emit('No active filters')
        elif arg.startswith('t'):
            # Sort alphabetically or after uses
            sortarg = 1
            if len(arg) == 2 and arg[1] == 'a':
                sortarg = 0
            self.old_pos = self.page().mainFrame().scrollBarValue(Qt.Vertical)
            entry_template = '<div class="list_entry"><span class="tag" style="background-color:{color};">{tagname}</span><span class="length">({count:,})</span></div>'
            t_entries = (entry_template.format(color=self.settings['tag colors'].get(tag, '#677'),
                                               tagname=tag, count=num)
                         for tag, num in sorted(self.get_tags(), key=itemgetter(sortarg), reverse=sortarg))
            body = '<br>'.join(t_entries)
            html = '<style type="text/css">{css}</style>\
                    <body><div id="taglist">{body}</div></body>'.format(body=body, css=self.css)
            self.show_popup.emit(html, '', '', 'html')

    def regenerate_visible_entries(self, entries=None, active_filters=None,
                                   attributedata=None, sort_by=None, reverse=None,
                                   tagmacros=None):
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
        raw_active_filters = self.active_filters if active_filters is None else active_filters
        filters = [(k,v) for k,v in raw_active_filters._asdict().items() if v is not None]
        return taggedlist.generate_visible_entries(
            self.entries if entries is None else entries,
            filters,
            self.attributedata if attributedata is None else attributedata,
            self.sorted_by[0] if sort_by is None else sort_by,
            self.sorted_by[1] if reverse is None else reverse,
            self.settings['tag macros'] if tagmacros is None else tagmacros,
        )

    def filter_entries(self, arg):
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
            active_filters = ['{}: {}'.format(cmd, payload)
                             for cmd, payload in self.active_filters._asdict().items()
                             if payload is not None]
            if active_filters:
                self.print_.emit('; '.join(active_filters))
            else:
                self.error.emit('No active filters')
            return
        # Reset all filters
        elif arg.strip() == '-':
            kwargs = dict(zip(filters.values(), len(filters)*(None,)))
            self.active_filters = self.active_filters._replace(**kwargs)
            visible_entries = self.regenerate_visible_entries()
            resultstr = 'Filters reset: {}/{} entries visible'
        # Reset specified filter
        elif re.fullmatch(r'[{}]-\s*'.format(filterchars), arg):
            self.active_filters = self.active_filters._replace(**{filters[arg[0]]:None})
            visible_entries = self.regenerate_visible_entries()
            resultstr = 'Filter on {} reset: {{}}/{{}} entries visible'.format(filters[arg[0]])
        else:
            # Prompt active filter
            if arg.strip() in filters.keys():
                payload = getattr(self.active_filters, filters[arg])
                if payload is None:
                    payload = ''
                self.set_terminal_text.emit('f' + arg.strip() + ' ' + payload)
                return
            # Filter empty entries
            if re.fullmatch(r'[dt]_\s*'.format(filterchars), arg):
                cmd = arg[0]
                payload = ''
            # Regular filter command
            elif re.fullmatch(r'[{}] +\S.*'.format(filterchars), arg):
                cmd = arg[0]
                payload = arg.split(None,1)[1].strip()
            # Invalid filter command
            else:
                self.error.emit('Invalid filter command')
                return
            # Do the filtering
            self.active_filters = self.active_filters._replace(**{filters[cmd]: payload})
            try:
                visible_entries = self.regenerate_visible_entries()
            except SyntaxError as e:
                # This should be an error from the tag parser
                self.error.emit('[Tag parsing] {}'.format(e))
                return
            resultstr = 'Filtered: {}/{} entries visible'
        # Only actually update stuff if the entries have changed
        if visible_entries != self.visible_entries:
            self.visible_entries = visible_entries
            self.refresh_view()
        # Print the output
        filtered, total = len(self.visible_entries), len(self.entries)
        self.print_.emit(resultstr.format(filtered, total))

    def sort_entries(self, arg):
        """
        The main sort method, called by terminal command.

        If arg is not specified, print the current sort order.
        """
        acronyms = {'n': 'title', 'c': 'wordcount', 'b': 'backstorywordcount', 'p': 'backstorypages'}
        if not arg:
            attr = self.sorted_by[0]
            order = ('ascending', 'descending')[self.sorted_by[1]]
            self.print_.emit('Sorted by {}, {}'.format(attr, order))
            return
        if arg[0] not in acronyms:
            self.error.emit('Unknown attribute to sort by: "{}"'.format(arg[0]))
            return
        if not re.fullmatch(r'\w-?\s*', arg):
            self.error.emit('Incorrect sort command')
            return
        reverse = arg.strip().endswith('-')
        self.sorted_by = (acronyms[arg[0]], reverse)
        sorted_entries = taggedlist.sort_entries(self.visible_entries,
                                                 acronyms[arg[0]],
                                                 reverse)
        if sorted_entries != self.visible_entries:
            self.visible_entries = sorted_entries
            self.refresh_view()

    def edit_entry(self, arg):
        """
        The main edit method, called by terminal command.

        If arg is "u", undo the last edit.
        Otherwise, either replace/add/remove tags from the visible entries
        or edit attributes of a single entry.
        """
        if arg.strip() == 'u':
            if not self.undostack:
                self.error.emit('Nothing to undo')
                return
            undoitem = self.undostack[-1]
            self.undostack = self.undostack[:-1]
            self.entries = taggedlist.undo(self.entries, undoitem)
            self.visible_entries = self.regenerate_visible_entries()
            self.refresh_view(keep_position=True)
            if not self.dry_run:
                write_metadata(undoitem)
            self.print_.emit('{} edits reverted'.format(len(undoitem)))
            return
        replace_tags = re.fullmatch(r't\*\s*(.*?)\s*,\s*(.*?)\s*', arg)
        main_data = re.fullmatch(r'[dtn](\d+)(.*)', arg)
        # Replace/add/remove a bunch of tags
        if replace_tags:
            oldtag, newtag = replace_tags.groups()
            if not oldtag and not newtag:
                self.error.emit('No tags specified, nothing to do')
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
                self.print_.emit('Edited tags in {} entries'.format(len(changed)))
            else:
                self.error.emit('No tags edited')
        # Edit a single entry
        elif main_data:
            entry_id = int(main_data.group(1))
            if entry_id >= len(self.visible_entries):
                self.error.emit('Index out of range')
                return
            payload = main_data.group(2).strip()
            category = {'d': 'description', 'n': 'title', 't': 'tags'}[arg[0]]
            # No data specified, so the current is provided instead
            if not payload:
                data = getattr(self.visible_entries[entry_id], category)
                new = ', '.join(sorted(data)) if arg[0] == 't' else data
                self.set_terminal_text.emit('e' + arg.strip() + ' ' + new)
            else:
                index = self.visible_entries[entry_id][0]
                entries = taggedlist.edit_entry(index,
                                                self.entries,
                                                category,
                                                payload,
                                                self.attributedata)
                if entries != self.entries:
                    self.undostack = self.undostack + ((self.visible_entries[entry_id],),)
                    self.entries = entries
                    self.visible_entries = self.regenerate_visible_entries()
                    self.refresh_view(keep_position=True)
                    if not self.dry_run:
                        write_metadata((self.entries[index],))
                    self.print_.emit('Entry edited')
        else:
            self.error.emit('Invalid edit command')


    def open_entry(self, arg):
        """
        Main open entry method, called by the terminal.

        arg should be the index of the entry to be viewed.
        """
        if not isinstance(arg, int):
            raise AssertionError('BAD CODE: the open entry arg should be an int')
        if arg not in range(len(self.visible_entries)):
            self.error.emit('Index out of range')
            return
        self.view_entry.emit(self.visible_entries[arg])


    def open_meta(self, arg):
        """
        Main open meta method, called by the terminal.

        arg should be the index of the entry to be viewed in the meta viewer.
        """
        if not arg.isdigit():
            partialnames = [n for n, entry in enumerate(self.visible_entries)
                            if arg.lower() in entry.title.lower()]
            if not partialnames:
                self.error.emit('Entry not found: "{}"'.format(arg))
                return
            elif len(partialnames) > 1:
                self.error.emit('Ambiguous name, matches {} entries'.format(len(partialnames)))
                return
            elif len(partialnames) == 1:
                arg = partialnames[0]
        elif not int(arg) in range(len(self.visible_entries)):
            self.error.emit('Index out of range')
            return
        self.view_meta.emit(self.visible_entries[int(arg)])


    def count_length(self, arg):
        """
        Main count length method, called by terminal command.
        """
        def print_length(targetstr, targetattr):
            self.print_.emit('Total {}: {}'.format(targetstr,
                    sum(getattr(x, targetattr) for x in self.visible_entries)))
        cmd = arg.strip()
        if cmd == 'c':
            print_length('wordcount', 'wordcount')
        elif cmd == 'b':
            print_length('backstory wordcount', 'backstorywordcount')
        elif cmd == 'p':
            print_length('backstory pages', 'backstorypages')
        else:
            self.error.emit('Unknown argument')


    def external_run_entry(self, arg):
        """
        Main external run method, called by terminal command.
        """
        if not arg.isdigit():
            partialnames = [n for n, entry in enumerate(self.visible_entries)
                            if arg.lower() in entry.title.lower()]
            if not partialnames:
                self.error.emit('Entry not found: "{}"'.format(arg))
                return
            elif len(partialnames) > 1:
                self.error.emit('Ambiguous name, matches {} entries'.format(len(partialnames)))
                return
            elif len(partialnames) == 1:
                arg = partialnames[0]
        elif not int(arg) in range(len(self.visible_entries)):
            self.error.emit('Index out of range')
            return
        if not self.settings.get('editor', None):
            self.error.emit('No editor command defined')
            return
        subprocess.Popen([self.settings['editor'],
                          self.visible_entries[int(arg)].file])
        self.print_.emit('Opening entry with {}'.format(self.settings['editor']))


def load_html_templates():
    html = namedtuple('HTMLTemplates', 'entry index_page tags')
    path = lambda fname: local_path(join('templates', fname))
    return html(read_file(path('entry_template.html')),
                read_file(path('index_page_template.html')),
                read_file(path('tags_template.html')))

def get_backstory_data(fname):
    out = {'wordcount': 0, 'pages': 0}
    root = fname + '.metadir'
    if not os.path.isdir(root):
        return out
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            try:
                data = read_file(join(dirpath, f)).split('\n',1)[1]
                words = len(re.findall(r'\S+', data))
            except:
                # Just ignore the file if something went wrong
                # TODO: add something here if being verbose?
                pass
            else:
                out['wordcount'] += words
                out['pages'] += 1
    return out


@taggedlist.generate_entrylist
def index_stories(path):
    """
    Find all files that match the filter, and return a sorted list
    of them with wordcount, paths and all data from the metadata file.
    """
    attributes = (
        ('title', {'filter': 'text', 'parser': 'text'}),
        ('tags', {'filter': 'tags', 'parser': 'tags'}),
        ('description', {'filter': 'text', 'parser': 'text'}),
        ('wordcount', {'filter': 'number'}),
        ('backstorywordcount', {'filter': 'number'}),
        ('backstorypages', {'filter': 'number'}),
        ('file', {}),
        ('metadatafile', {}),
    )
    metafile = lambda dirpath, fname: join(dirpath, '.'+fname+'.metadata')
    metadir = lambda dirpath, fname: join(dirpath, fname+'.metadir')
    files = ((read_json(metafile(dirpath, fname)),
             join(dirpath, fname),
             metafile(dirpath, fname),
             get_backstory_data(join(dirpath, fname)))
             for dirpath, _, filenames in os.walk(path)
             for fname in filenames
             if exists(metafile(dirpath, fname)))
    entries = ((metadata['title'],
                frozenset(metadata['tags']),
                metadata['description'],
                len(re.findall(r'\S+', read_file(fname))),
                backstorydata['wordcount'],
                backstorydata['pages'],
                fname,
                metadatafile)
               for metadata, fname, metadatafile, backstorydata in files)
    return attributes, entries

def generate_html_body(visible_entries, tagstemplate, entrytemplate, entrylengthtemplate, tagcolors):
    """
    Return html generated from the visible entries.
    """
    def format_tags(tags):
        return '<wbr>'.join(
            tagstemplate.format(tag=t.replace(' ', '&nbsp;').replace('-', '&#8209;'),
                                color=tagcolors.get(t, '#677'))
            for t in sorted(tags))
    def format_desc(desc):
        return desc if desc else '<span class="empty_desc">[no desc]</span>'
    entrytemplate = entrytemplate.format(lengthformatstr=entrylengthtemplate)
    entries = (entrytemplate.format(title=entry.title, id=n,
                                    tags=format_tags(entry.tags),
                                    desc=format_desc(entry.description),
                                    wordcount=entry.wordcount,
                                    backstorywordcount=entry.backstorywordcount,
                                    backstorypages=entry.backstorypages)
               for n,entry in enumerate(visible_entries))
    return '<hr />'.join(entries)

def write_metadata(entries):
    for entry in entries:
        metadata = {
            'title': entry.title,
            'description': entry.description,
            'tags': list(entry.tags)
        }
        write_json(entry.metadatafile, metadata)
