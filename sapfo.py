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
from viewerframe import ViewerFrame


class MainWindow(QtGui.QFrame):
    def __init__(self, profile):
        super().__init__()
        self.setWindowTitle('Sapfo')

        # Load profile
        settings = read_config()
        if not profile:
            profile = settings['default profile']
        if profile not in settings['profiles']:
            raise NameError('Profile not found')
        profile_settings = settings['profiles'][profile]

        # Generate hotkeys
        hotkeys = update_dict(settings['default settings']['hotkeys'],
                              profile_settings.get('hotkeys', {}))

        # Create stuff
        self.stack = QtGui.QStackedLayout(self)
        common.kill_theming(self.stack)

        index_widget = QtGui.QWidget(self)
        layout = QtGui.QVBoxLayout(index_widget)
        common.kill_theming(layout)

        self.index_viewer = QtWebKit.QWebView(index_widget)
        layout.addWidget(self.index_viewer, stretch=1)
        self.index_viewer.setDisabled(True)

        self.terminal = Terminal(index_widget)
        layout.addWidget(self.terminal)

        self.stack.addWidget(index_widget)

        # Story viewer
        self.story_viewer = ViewerFrame(self, hotkeys)
        self.stack.addWidget(self.story_viewer)


        self.tagcolors = profile_settings['tag colors']
        self.all_entries = index_stories(profile_settings)
        self.entries = self.all_entries.copy()
        self.entries_sortkey = 'title'
        self.entries_sort_reverse = False
        self.update_view()

        self.connect_signals()

        self.set_stylesheet()
        self.show()

    def wheelEvent(self, ev):
        self.index_viewer.wheelEvent(ev)

    def update_view(self):
        self.index_viewer.setHtml(generate_index(self.entries,
                                                self.entries_sortkey,
                                                self.entries_sort_reverse,
                                                self.tagcolors))

    def connect_signals(self):
        self.terminal.filter_.connect(self.filter_entries)
        self.terminal.sort.connect(self.sort_entries)
        self.terminal.open_.connect(self.open_entry)
        self.story_viewer.show_index.connect(self.show_index)

    def filter_entries(self, arg):
        # Reset filter if no argument
        if not arg:
            self.entries = self.all_entries.copy()
            self.update_view()
            return
        if len(arg) == 1:
            return #TODO

        def testfilter(acronym, fullname, filtered=lambda x: x.lower()):
            if arg[0] == acronym:
                name = arg[1:].strip().lower()
                self.entries = [x for x in self.all_entries
                            if name in filtered(x[fullname])]
                self.update_view()
                return

        # Filter on title (name)
        testfilter('n', 'title')
        # Filter on description
        testfilter('d', 'description')
        # Filter on tags
        if arg[0] == 't':
            tags = set(re.split(r'\s*,\s*', arg[1:].strip().lower()))
            self.entries = [x for x in self.entries
                            if tags <= set(map(str.lower, x['tags']))]
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
            self.entries = [x for x in self.entries
                            if matches(x['wordcount'])]
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

    def open_entry(self, arg):
        if not arg.isdigit():
            return
        if not self.entries[int(arg)]['pages']:
            return
        self.story_viewer.start(self.entries[int(arg)])
        self.stack.setCurrentIndex(1)

    def show_index(self):
        self.stack.setCurrentIndex(0)
        self.terminal.setFocus()


    def set_stylesheet(self):
        self.setStyleSheet(common.parse_stylesheet(\
                           common.read_file(common.local_path('qt.css'))))


def generate_index(raw_entries, key, reverse, tagcolors):
    def format_tags(tags):
        tag_template = '<span class="tag" style="background-color:{color};">{tag}</span>'
        return '<wbr>'.join([
            tag_template.format(tag=x.replace(' ', '&nbsp;').replace('-', '&#8209;'),
                                color=tagcolors.get(x, '#677'))
            for x in sorted(tags)
        ])
    def format_desc(desc):
        return desc if desc else '<span class="empty_desc">[no desc]</span>'

    entrystr = common.read_file(common.local_path('entry_template.html'))
    entries = [entrystr.format(title=s['title'], id=n,
                               tags=format_tags(s['tags']),
                               desc=format_desc(s['description']),
                               wc=s['wordcount'])
               for n,s in enumerate(sorted(raw_entries, reverse=reverse, key=itemgetter(key)))]
    body = '<hr />'.join(entries)
    boilerplate = """
        <style type="text/css">{css}</style>
        <body>{body}</body>
    """
    return boilerplate.format(body=body,
                css=common.read_file(common.local_path('index_page.css')))


def generate_word_count(files):
    wordcount_rx = re.compile(r'\S+')
    def count_words(fpath):
        with open(fpath) as f:
            return len(wordcount_rx.findall(f.read()))
    return sum(map(count_words, files))


def index_stories(data):
    path = data['path']
    dirs = [d for d in os.listdir(path)
            if os.path.isdir(join(path, d))]
    fname_rx = re.compile(data['name filter'], re.IGNORECASE)
    entries = []
    for d in dirs:
        metadata = common.read_json(join(path, d, 'metadata.json'))
        files = [join(path,d,f) for f in os.listdir(join(path,d))
                 if fname_rx.search(f)]
        wordcount = generate_word_count(files)
        metadata.update({'wordcount': wordcount,
                         'pages': sorted(files)})
        entries.append(metadata)
    return sorted(entries, key=itemgetter('title'))


def read_config():
    config_dir = os.path.join(os.getenv('HOME'), '.config', 'sapfo')
    config_file = os.path.join(config_dir, 'settings.json')
    if not os.path.exists(config_file):
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, mode=0o755, exist_ok=True)
        shutil.copyfile(common.local_path('default_settings.json'), config_file)
        print("No config found, copied the default to {}. Edit it at once.".format(config_dir))
    return common.read_json(config_file)


def update_dict(basedict, newdict):
    for key, value in newdict.items():
        if isinstance(value, collections.Mapping):
            subdict = update_dict(basedict.get(key, {}), value)
            basedict[key] = subdict
        elif isinstance(value, type([])):
            basedict[key] = list(set(value + basedict.get(key, [])))
        else:
            basedict[key] = value
    return basedict


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
