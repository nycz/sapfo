#!/usr/bin/env python3

import collections
from operator import itemgetter
import os
import os.path
from os.path import join
import re
import shutil
import sys

from PyQt4 import QtGui, QtWebKit

from libsyntyche import common
from terminal import Terminal


class MainWindow(QtGui.QFrame):
    def __init__(self, profile):
        super().__init__()
        self.setWindowTitle('Sapfo')

        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.main_widget = QtWebKit.QWebView(self)
        layout.addWidget(self.main_widget, stretch=1)

        self.terminal = Terminal(self)
        layout.addWidget(self.terminal)

        # Load profile
        settings = read_config()
        if not profile:
            profile = settings['default profile']
        if profile not in settings['profiles']:
            raise NameError('Profile not found')

        self.data = index_stories(settings['profiles'][profile])
        self.entries = self.data['entries'].copy()
        self.entries_sortkey = 'title'
        self.entries_sort_reverse = False
        self.update_view()

        self.connect_signals()

        self.set_stylesheet()
        self.show()

    def update_view(self):
        self.main_widget.setHtml(generate_index(self.entries, \
                            self.entries_sortkey, self.entries_sort_reverse))

    def connect_signals(self):
        self.terminal.filter_.connect(self.filter_entries)
        self.terminal.sort.connect(self.sort_entries)

    def filter_entries(self, arg):
        # Reset filter if no argument
        if not arg:
            self.entries = self.data['entries'].copy()
            self.update_view()
            return
        if len(arg) == 1:
            return #TODO

        def testfilter(acronym, fullname, filtered=lambda x: x.lower()):
            if arg[0] == acronym:
                name = arg[1:].strip().lower()
                self.entries = {n:e for n,e in self.data['entries'].items()
                            if name in filtered(e[fullname])}
                self.update_view()
                return

        # Filter on title (name)
        testfilter('n', 'title')
        # Filter on description
        testfilter('d', 'description')
        # Filter on tags
        if arg[0] == 't':
            tags = set(re.split(r'\s*,\s*', arg[1:].strip().lower()))
            self.entries = {n:e for n,e in self.entries.items()
                             if tags <= set(map(str.lower, e['tags']))}
            self.update_view()
            return
        # Filter on length
        if arg[0] == 'l':
            from operator import lt,gt,le,ge
            def tonum(num):
                if num.endswith('k'):
                    return int(num[:-1])*1000
                else:
                    return int(num)
            compfuncs = {'<': lt, '>': gt, '<=': le, '>=': ge}
            expressions = [
                (compfuncs[match.group(1)], tonum(match.group(2))) for match
                in re.finditer(r'([<>][=]?)(\d+k?)', arg[1:].strip().lower())
            ]
            def matches(wordcount):
                for f, num in expressions:
                    if not f(wordcount, num):
                        return False
                return True
            self.entries = {n:e for n,e in self.entries.items()
                        if matches(e['wordcount'])}
            self.update_view()

    def sort_entries(self, arg):
        acronyms = {'n': 'title', 'l': 'wordcount'}
        if not arg or arg[0] not in acronyms:
            return #TODO
        reverse = False
        if len(arg) > 1 and arg[1] == '-':
            reverse = True
        self.entries_sortkey = acronyms[arg[0]]
        self.entries_sort_reverse = reverse
        self.update_view()

    def set_stylesheet(self):
        self.setStyleSheet(common.parse_stylesheet(\
                           common.read_file(common.local_path('qt.css'))))


def generate_index(raw_entries, key, reverse):
    def format_tags(tags):
        tag_template = '<span class="tag">{tag}</span>'
        return ''.join([tag_template.format(tag=x)
                          for x in sorted(tags)])
    def format_desc(desc):
        return desc if desc else '<span class="empty_desc">[no desc]</span>'

    entrystr = common.read_file(common.local_path('entry_template.html'))
    entries = [entrystr.format(title=s['title'],
                               tags=format_tags(s['tags']),
                               desc=format_desc(s['description']),
                               wc=s['wordcount'])
               for s in sorted(raw_entries.values(), reverse=reverse, key=itemgetter(key))]
    body = '<hr />'.join(entries)
    boilerplate = """
        <style type="text/css">{css}</style>
        <body>{body}</body>
    """
    return boilerplate.format(body=body,
                css=common.read_file(common.local_path('index_page.css')))


def generate_word_count(path, files):
    wordcount_rx = re.compile(r'\S+')
    def count_words(fpath):
        with open(join(path,fpath)) as f:
            return len(wordcount_rx.findall(f.read()))
    return sum(map(count_words, files))


def index_stories(data):
    path = data['path']
    dirs = [d for d in os.listdir(path)
            if os.path.isdir(join(path, d))]
    fname_rx = re.compile(data['name_filter'], re.IGNORECASE)
    entries = []
    for d in dirs:
        metadata = common.read_json(join(path, d, 'metadata.json'))
        wordcount = generate_word_count(join(path,d), filter(fname_rx.search, os.listdir(join(path,d))))
        metadata.update({'wordcount': wordcount})
        entries.append(metadata)
    entries.sort(key=itemgetter('title'))
    return {'dirs': dirs, 'entries': {n:e for n,e in enumerate(entries)}}


def read_config():
    config_dir = os.path.join(os.getenv('HOME'), '.config', 'sapfo')
    config_file = os.path.join(config_dir, 'settings.json')
    if not os.path.exists(config_file):
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, mode=0o755, exist_ok=True)
        shutil.copyfile(common.local_path('default_settings.json'), config_file)
        print("No config found, copied the default to {}. Edit it at once.".format(config_dir))
    return common.read_json(config_file)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', nargs='?')
    args = parser.parse_args()

    app = QtGui.QApplication(sys.argv)
    window = MainWindow(args.profile)
    app.setActiveWindow(window)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
