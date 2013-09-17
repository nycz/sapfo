from operator import itemgetter
import os
import os.path
from os.path import join
import re

from PyQt4 import QtCore, QtGui, QtWebKit
from PyQt4.QtCore import pyqtSignal, Qt

from libsyntyche.common import local_path, read_file, read_json, set_hotkey, write_json

class IndexFrame(QtWebKit.QWebView):

    start_entry = pyqtSignal(dict)
    error = pyqtSignal(str)
    set_terminal_text = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setDisabled(True)

        set_hotkey("Ctrl+R", self, self.reload_view)
        set_hotkey("F5", self, self.reload_view)

        self.undo_stack = []

    def reload_view(self):
        self.all_entries = index_stories(self.settings)
        self.entries = self.all_entries.copy()
        self.refresh_view(keep_position=True)

    def refresh_view(self, keep_position=False):
        frame = self.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        self.setHtml(generate_index(self.entries, self.settings['tag colors']))
        if keep_position:
            frame.setScrollBarValue(Qt.Vertical, pos)

    def update_settings(self, new_settings):
        self.settings = new_settings
        self.reload_view()


    # ==== Manage entries ====================================================

    def filter_entries(self, arg):
        # Reset filter if no argument
        if not arg:
            self.entries = self.all_entries.copy()
            self.refresh_view()
            return
        if len(arg) == 1:
            return #TODO

        cmd, payload = arg[0].lower(), arg[1:].strip().lower()
        def generic_filter(key):
            self.entries = [x for x in self.entries if payload in x[key].lower()]

        # Filter on title (name)
        if cmd == 'n':
            generic_filter('title')

        # Filter on description
        elif cmd == 'd':
            generic_filter('description')

        # Filter on tags
        elif cmd == 't':
            tags = set(re.split(r'\s*,\s*', payload))
            self.entries = [x for x in self.entries
                            if tags <= set(map(str.lower, x['tags']))]
        # Filter on length
        elif cmd == 'l':
            from operator import lt,gt,le,ge
            def tonum(num):
                return int(num[:-1])*1000 if num.endswith('k') else int(num)
            compfuncs = {'<':lt, '>':gt, '<=':le, '>=':ge}
            rx = re.compile(r'([<>][=]?)(\d+k?)')
            expressions = [(compfuncs[match.group(1)], tonum(match.group(2)))
                           for match in rx.finditer(payload)]
            def matches(x):
                for f, num in expressions:
                    if not f(x['wordcount'], num):
                        return False
                return True
            self.entries = list(filter(matches, self.entries))

        if cmd in 'ndtl':
            self.refresh_view()


    def sort_entries(self, arg):
        acronyms = {'n': 'title', 'l': 'wordcount'}
        if not arg or arg[0] not in acronyms:
            return #TODO
        reverse = False
        if len(arg) > 1 and arg[1] == '-':
            reverse = True
        self.entries.sort(key=itemgetter(acronyms[arg[0]]), reverse=reverse)
        self.refresh_view()


    def find_entry(self, arg):
        #TODO: better acronyms than s/g
        if len(arg) < 2 or arg[0] not in 'sg':
            return
        if arg[0] == 's':
            f = lambda x: x[1]['title'].lower().startswith(arg[1:].lower())
        else:
            f = lambda x: arg[1:].lower() in x[1]['title'].lower()
        candidates = list(filter(f, enumerate(self.entries)))
        if len(candidates) == 1:
            self.open_entry(candidates[0][0])


    def open_entry(self, num):
        if not isinstance(num, int):
            return
        if num not in range(len(self.entries)) or not self.entries[num]['pages']:
            return
        self.start_entry.emit(self.entries[num])


    def edit_entry(self, arg):
        def set_data(entry_id, category, payload):
            metadatafile = self.entries[entry_id]['metadatafile']
            metadata = read_json(metadatafile)
            metadata[category] = payload
            write_json(metadatafile, metadata)
            self.entries[entry_id][category] = payload
            self.refresh_view(keep_position=True)

        if arg.strip().lower() == 'u':
            if not self.undo_stack:
                self.error.emit('Nothing to undo')
            else:
                set_data(*self.undo_stack.pop())
            return

        main_data = re.match(r'[dtn](\d+)(.*)$', arg)
        if not main_data:
            return
        entry_id, payload = main_data.groups()
        entry_id = int(entry_id)
        if entry_id >= len(self.entries):
            self.error.emit('Index out of range')
            return
        payload = payload.strip()
        category = {'d': 'description', 'n': 'title', 't': 'tags'}[arg[0]]

        # No data specified, so the current is provided instead
        if not payload:
            data = self.entries[entry_id][category]
            new = ', '.join(data) if arg[0] == 't' else data
            self.set_terminal_text.emit('e' + arg + ' ' + new)
        # Update the chosen data with new stuff
        else:
            self.undo_stack.append((entry_id, category, self.entries[entry_id][category]))
            # Convert the string to a list if tags
            if arg[0] == 't':
                payload = list(set(re.split(r'\s*,\s*', payload)))
            set_data(entry_id, category, payload)


# ==== Generating functions =======================================

def index_stories(data):
    """
    Find all files that match the filter, and return a sorted list
    of them with wordcount, paths and all data from the metadata file.
    """
    path = data['path']
    dirs = [d for d in os.listdir(path)
            if os.path.isdir(join(path, d))]
    fname_rx = re.compile(data['name filter'], re.IGNORECASE)
    entries = []
    for d in dirs:
        metadatafile = join(path, d, 'metadata.json')
        metadata = read_json(metadatafile)
        files = [join(path,d,f) for f in os.listdir(join(path,d))
                 if fname_rx.search(f)]
        wordcount = generate_word_count(files)
        metadata.update({'wordcount': wordcount,
                         'pages': sorted(files),
                         'metadatafile': metadatafile})
        entries.append(metadata)
    return sorted(entries, key=itemgetter('title'))


def generate_word_count(files):
    """ Return the total wordcount for all pages in the entry. """
    wordcount_rx = re.compile(r'\S+')
    def count_words(fpath):
        with open(fpath) as f:
            return len(wordcount_rx.findall(f.read()))
    return sum(map(count_words, files))


def generate_index(raw_entries, tagcolors):
    """
    Return a generated html index page from the list of entries
    provided in raw_entries.
    """
    def format_tags(tags):
        tag_template = '<span class="tag" style="background-color:{color};">{tag}</span>'
        return '<wbr>'.join([
            tag_template.format(tag=x.replace(' ', '&nbsp;').replace('-', '&#8209;'),
                                color=tagcolors.get(x, '#677'))
            for x in sorted(tags)
        ])
    def format_desc(desc):
        return desc if desc else '<span class="empty_desc">[no desc]</span>'

    entrystr = read_file(local_path('entry_template.html'))
    entries = [entrystr.format(title=s['title'], id=n,
                               tags=format_tags(s['tags']),
                               desc=format_desc(s['description']),
                               wc=s['wordcount'])
               for n,s in enumerate(raw_entries)]
    body = '<hr />'.join(entries)
    css = read_file(local_path('index_page.css'))
    return '<style type="text/css">{css}</style>\
            <body>{body}</body>'.format(body=body, css=css)
