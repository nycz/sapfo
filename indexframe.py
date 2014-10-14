from operator import itemgetter
import os
import os.path
from os.path import join
import re
import subprocess

from PyQt4 import QtCore, QtGui, QtWebKit
from PyQt4.QtCore import pyqtSignal, Qt

from libsyntyche.common import local_path, read_file, read_json, set_hotkey, write_json

from tagsystem import compile_tag_filter, parse_tag_filter

class IndexFrame(QtWebKit.QWebView):

    start_entry = pyqtSignal(dict)
    error = pyqtSignal(str)
    print_ = pyqtSignal(str)
    set_terminal_text = pyqtSignal(str)
    init_popup = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setDisabled(True)
        self.current_filters = []

        set_hotkey("Ctrl+R", parent, self.reload_view)
        set_hotkey("F5", parent, self.reload_view)

        self.undo_stack = []
        self.current_filters = []
        self.old_pos = None

    def reload_view(self):
        self.all_entries = index_stories(self.settings)
        self.entries = self.all_entries.copy()
        for x in self.current_filters:
            self.filter_entries(x, reapply=True)
        self.refresh_view(keep_position=True)
        self.print_.emit('Reloaded')

    def refresh_view(self, keep_position=False):
        frame = self.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        self.setHtml(generate_index(self.entries, self.settings['tag colors']))
        if keep_position:
            frame.setScrollBarValue(Qt.Vertical, pos)

    def update_settings(self, new_settings):
        self.settings = new_settings
        self.reload_view()

    def list_(self, arg):
        if arg.startswith('f'):
            if self.current_filters:
                self.print_.emit(', '.join(self.current_filters))
            else:
                self.error.emit('No active filters')
        elif arg.startswith('t'):
            # Sort alphabetically or after uses
            sortarg = 1
            if len(arg) == 2 and arg[1] == 'a':
                sortarg = 0
            self.old_pos = self.page().mainFrame().scrollBarValue(Qt.Vertical)
            entry_template = '<div class="list_entry"><span class="tag" style="background-color:{color};">{tagname}</span><span class="length">({count:,})</span></div>'
            t_entries = [entry_template.format(color=self.settings['tag colors'].get(tag, '#677'),
                                               tagname=tag, count=num)
                         for tag, num in sorted(self.get_tags(), key=itemgetter(sortarg), reverse=sortarg)]
            body = '<br>'.join(t_entries)
            css = read_file(local_path('index_page.css'))# + '#taglist {-webkit-column-width: 5-em}'
            self.setHtml('<style type="text/css">{css}</style>\
                          <body><div id="taglist">{body}</div></body>'.format(body=body, css=css))
            self.init_popup.emit()

    def close_popup(self):
        self.refresh_view()
        self.page().mainFrame().setScrollBarValue(Qt.Vertical, self.old_pos)

    def get_tags(self):
        tags = {}
        for e in self.all_entries:
            for t in e['tags']:
                tags[t] = tags.get(t, 0) + 1
        return list(tags.items())


    # ==== Manage entries ====================================================

    def filter_entries(self, arg, reapply=False):
        # Reset filter if no argument
        if not arg:
            self.current_filters = []
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
            try:
                tag_filter = compile_tag_filter(payload)
            except SyntaxError as e:
                self.error.emit(str(e))
                return
            try:
                entries = [x for x in self.entries
                           if parse_tag_filter(tag_filter, x['tags'])]
            except SyntaxError as e:
                self.error.emit(str(e))
                return
            else:
                self.entries = entries

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
                    if not f(x['length'], num):
                        return False
                return True
            self.entries = list(filter(matches, self.entries))

        if cmd in 'ndtl' and not reapply:
            self.current_filters.append(cmd + ' ' + payload)
            self.refresh_view()
            self.print_.emit('Filter applied')


    def sort_entries(self, arg):
        acronyms = {'n': 'title', 'l': 'length'}
        if not arg or arg[0] not in acronyms:
            return #TODO
        reverse = False
        if len(arg) > 1 and arg[1] == '-':
            reverse = True
        self.entries.sort(key=itemgetter(acronyms[arg[0]]), reverse=reverse)
        self.refresh_view()


    def open_entry(self, num):
        if not isinstance(num, int):
            return
        if num not in range(len(self.entries)) or not self.entries[num]['pages']:
            return
        self.start_entry.emit(self.entries[num])


    def edit_entry(self, arg):
        def find_entry_id(metadatafile, entries):
            for n,e in enumerate(entries):
                if metadatafile == e['metadatafile']:
                    return n

        def set_data(metadatafile, category, payload):
            metadata = read_json(metadatafile)
            metadata[category] = payload
            write_json(metadatafile, metadata)
            entry_id = find_entry_id(metadatafile, self.entries)
            if entry_id is not None:
                self.entries[entry_id][category] = payload
            self.all_entries[find_entry_id(metadatafile, self.all_entries)][category] = payload
            self.refresh_view(keep_position=True)

        def update_entry_list(selected_entries, entries, revert):
            for n,entry in enumerate(entries):
                if entry['metadatafile'] in selected_entries:
                    entries[n]['tags'] = selected_entries[entry['metadatafile']][revert]

        if arg.strip().lower() == 'u':
            if not self.undo_stack:
                self.error.emit('Nothing to undo')
            else:
                if isinstance(self.undo_stack[-1], dict):
                    selected_entries = self.undo_stack.pop()
                    update_entry_list(selected_entries, self.all_entries, True)
                    update_entry_list(selected_entries, self.entries, True)
                    for metadatafile, entry in selected_entries.items():
                        metadata = read_json(metadatafile)
                        metadata['tags'] = entry[1]
                        write_json(metadatafile, metadata)
                    self.refresh_view(keep_position=True)
                else:
                    set_data(*self.undo_stack.pop())
            return

        replace_tags = re.match(r't\*\s*(.*?)\s*,\s*(.*?)\s*$', arg)
        if replace_tags:
            oldtag, newtag = replace_tags.groups()
            if not oldtag and not newtag:
                return
            selected_entries = {}
            for n,x in enumerate(self.entries):
                if oldtag in x['tags'] or not oldtag:
                    metadata = read_json(x['metadatafile'])
                    oldtags = metadata['tags'].copy()
                    if oldtag:
                        metadata['tags'].remove(oldtag)
                    if newtag:
                        metadata['tags'] = list(set(metadata['tags'] + [newtag]))
                    write_json(x['metadatafile'], metadata)
                    self.entries[n]['tags'] = metadata['tags']
                    selected_entries[x['metadatafile']] = (metadata['tags'], oldtags)
            self.undo_stack.append(selected_entries)
            update_entry_list(selected_entries, self.all_entries, False)
            self.refresh_view(keep_position=True)


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
            # Convert the string to a list if tags
            if arg[0] == 't':
                payload = list(set(re.split(r'\s*,\s*', payload)))
            metadatafile = self.entries[entry_id]['metadatafile']
            self.undo_stack.append((metadatafile, category, self.entries[entry_id][category]))
            set_data(metadatafile, category, payload)


    def count_length(self, arg):
        total_length = sum(x['length'] for x in self.entries)
        self.print_.emit(str(total_length))


    def external_run_entry(self, arg):
        if not arg.isdigit():
            return
        if not int(arg) in range(len(self.entries)):
            self.error.emit('Index out of range')
            return
        if not self.settings.get('editor', None):
            self.error.emit('No editor command defined')
            return
        subprocess.Popen([self.settings['editor'], self.entries[int(arg)]['pages'][0]])



# ==== Generating functions =======================================

def index_stories(data):
    """
    Find all files that match the filter, and return a sorted list
    of them with wordcount, paths and all data from the metadata file.
    """
    path = data['path']
    count_words = data.get('count words', True)
    fname_rx = re.compile(data['name filter'], re.IGNORECASE)
    entries = []
    def blacklisted(fname):
        for r in data.get('blacklist', []):
            if re.search(r, fname, re.IGNORECASE):
                return True
        return False

    def add_entry(metadatafile, files):
        metadata = read_json(metadatafile)
        length = generate_word_count(files) if count_words else len(files)
        metadata.update({'length': length,
                         'count words': count_words,
                         'pages': files,
                         'raw text': data.get('raw text', False),
                         'metadatafile': metadatafile})
        entries.append(metadata)

    if data.get('loose files', False):
        md = lambda x: '.'+x+'.metadata'
        files = [(join(p,f), join(p,md(f)))
                 for p,_,fs in os.walk(path) for f in fs
                 if fname_rx.search(f) and os.path.exists(join(p, md(f)))
                 and not blacklisted(f)]
        for fpath, metadatafile in files:
            add_entry(metadatafile, [fpath])
    else:
        dirs = [d for d in os.listdir(path)
                if os.path.isdir(join(path, d))]
        for d in dirs:
            metadatafile = join(path, d, 'metadata.json')
            files = [join(path,d,f) for f in os.listdir(join(path,d))
                     if fname_rx.search(f) and not blacklisted(f)]
            add_entry(metadatafile, sorted(files))
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
                               length=s['length'])
               for n,s in enumerate(raw_entries)]
    body = '<hr />'.join(entries)
    css = read_file(local_path('index_page.css'))
    return '<style type="text/css">{css}</style>\
            <body>{body}</body>'.format(body=body, css=css)
