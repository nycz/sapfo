from datetime import datetime
import json
import os
import os.path
from os.path import join
import re

from PyQt4.QtCore import pyqtSignal, Qt
from PyQt4 import QtGui, QtCore

from libsyntyche.common import kill_theming, set_hotkey, read_file, write_file, local_path
from libsyntyche.terminal import GenericTerminalInputBox, GenericTerminalOutputBox, GenericTerminal

class Formatter(QtGui.QSyntaxHighlighter):
    def __init__(self, *args):
        super().__init__(*args)
        self.formats = None

    def update_formats(self, formatstrings):
        self.formats = []
        font = QtGui.QFont
        for s, items in formatstrings.items():
            items = items.split(',')
            f = QtGui.QTextCharFormat()
            if 'bold' in items:
                f.setFontWeight(font.Bold)
            if 'italic' in items:
                f.setFontItalic(True)
            if 'strikethrough' in items:
                f.setFontStrikeOut(True)
            for x in items:
                if x.isdigit():
                    f.setFontPointSize(int(x))
                if re.fullmatch(r'#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?', x):
                    f.setForeground(QtGui.QColor(x))
            self.formats.append((s, f))
        self.rehighlight()

    def highlightBlock(self, text):
        if self.formats is None:
            return
        for rx, format in self.formats:
            for chunk in re.finditer(rx, text):
                self.setFormat(chunk.start(), chunk.end()-chunk.start(), format)


class TabBar(QtGui.QTabBar):
    def __init__(self, parent, print_):
        super().__init__(parent)
        self.print_ = print_
        self.pages = []

    def change_tab(self, direction):
        currenttab = self.currentIndex()
        if direction > 0 and currenttab == self.count() - 1:
            newtab = 0
        elif direction < 0 and currenttab == 0:
            newtab = self.count() - 1
        else:
            newtab = currenttab + direction
        self.setCurrentIndex(newtab)

    def clear(self):
        while self.count() > 0:
            self.removeTab(0)

    def current_page_fname(self):
        i = self.currentIndex()
        return self.pages[i][1]

    def get_page_fname(self, i):
        return self.pages[i][1]

    def load_pages(self, root):
        """
        Read all pages from the specified directory and build a list of them.
        """
        fnames = os.listdir(root)
        for f in fnames:
            firstline, data = read_file(join(root, f)).split('\n', 1)
            try:
                jsondata = json.loads(firstline)
            except ValueError:
                self.print_('Bad/no properties found on page {}, fixing...'.format(f))
                jsondata = json.dumps({'title': f, 'created': datetime.now().isoformat()})
                write_file(join(root, f), '\n'.join(jsondata, firstline, data))
                yield [f, f]
            else:
                yield [jsondata['title'], f]

    def open_entry(self, root):
        """
        Ready the tab bar for a new entry.
        """
        self.pages = []
        self.clear()
        fnames = os.listdir(root)
        self.pages = sorted(self.load_pages(root))
        for title, _ in self.pages:
            self.addTab(title)

    def add_page(self, fname):
        """
        Add a new page to and then sort the tab bar. Return the index of the
        new tab.

        Raise KeyError if the title already exists.
        """
        if fname in (title for title, fname in self.pages):
            raise KeyError('Page name already exists')
        self.pages.append([fname, fname])
        self.pages.sort()
        i = next(zip(*self.pages)).index(fname)
        self.insertTab(i, fname)
        # self.setCurrentIndex(i)
        return i

    def remove_page(self):
        """
        Remove the active page from the tab bar and return the page's file name.
        Note that the actual file on the disk is not removed by this.

        Raise IndexError if there is only one tab left.
        """
        if self.count() <= 1:
            raise IndexError('Can\'t remove the only page')
        i = self.currentIndex()
        page = self.pages.pop(i)
        self.removeTab(i)
        self.print_('Page "{}" deleted'.format(page[0]))
        return page[1]

    def rename_page(self, newtitle):
        """
        Rename the active page and update the tab bar.

        Raise KeyError if the title already exists.
        """
        if newtitle in (title for title, fname in self.pages):
            raise KeyError('Page name already exists')
        i = self.currentIndex()
        self.pages[i][0] = newtitle
        self.pages.sort()
        self.setTabText(i, newtitle)
        self.moveTab(i, next(zip(*self.pages)).index(newtitle))


class MetaFrame(QtGui.QFrame):
    show_index = pyqtSignal()
    quit = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)

        class MetaTextEdit(QtGui.QTextEdit):
            pass
        self.textarea = MetaTextEdit()
        self.textarea.setTabStopWidth(30)
        self.textarea.setAcceptRichText(False)
        class MetaTitle(QtGui.QLabel):
            pass
        self.titlelabel = MetaTitle()
        class MetaTabCounter(QtGui.QLabel):
            pass
        self.tabcounter = MetaTabCounter(self)
        self.terminal = MetaTerminal(self)
        self.tabbar = TabBar(self, self.terminal.print_)
        self.tabbar.currentChanged.connect(self.tab_changed)

        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.textarea, self.terminal)
        self.connect_signals()

        self.formatter = Formatter(self.textarea)

        set_hotkey('Ctrl+PgUp', self, lambda: self.tabbar.change_tab(-1))
        set_hotkey('Ctrl+PgDown', self, lambda: self.tabbar.change_tab(+1))
        set_hotkey('Ctrl+S', self, self.save_page)
        set_hotkey('Escape', self, self.toggle_terminal)


    def create_layout(self, titlelabel, tabbar, tabcounter, textarea, terminal):
        layout = QtGui.QVBoxLayout(self)
        kill_theming(layout)
        # Title label
        titlelabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titlelabel)
        # Tab bar and tab counter
        tab_layout = QtGui.QHBoxLayout()
        tabbar.setDrawBase(False)
        tab_layout.addWidget(tabbar, stretch=1)
        tab_layout.addWidget(tabcounter, stretch=0)
        layout.addLayout(tab_layout)
        # Textarea
        textarea_layout = QtGui.QHBoxLayout()
        textarea_layout.addStretch()
        textarea_layout.addWidget(textarea, stretch=1)
        textarea_layout.addStretch()
        layout.addLayout(textarea_layout)
        # Terminal
        layout.addWidget(self.terminal)

    def connect_signals(self):
        t = self.terminal
        connects = (
            (t.go_back,         self.show_index.emit),
            (t.quit,            self.quit.emit),
            (t.new_page,        self.new_page),
            (t.delete_page,     self.delete_page),
            (t.rename_page,     self.rename_page),
            (t.save_page,       self.save_page),
            (t.print_filename,  self.print_filename),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings):
        self.formatter.update_formats(settings['meta editor formats'])
        self.formatconverters = settings['formatting converters']
        self.chapterstrings = settings['chapter strings']

    def toggle_terminal(self):
        if self.textarea.hasFocus():
            self.terminal.show()
            self.terminal.setFocus()
        else:
            self.terminal.hide()
            self.textarea.setFocus()

    def update_tabcounter(self):
        self.tabcounter.setText('{}/{}'.format(self.tabbar.currentIndex()+1, self.tabbar.count()))

    def tab_changed(self, tabnum):
        """
        This is called every time the tab is changed, either "automatically"
        (eg. by mousewheel over the tab bar) or programmatically whenever the
        next/prev tab hotkeys are pressed.
        """
        self.update_tabcounter()
        fname = self.current_page_path()
        firstline, data = read_file(fname).split('\n', 1)
        self.textarea.setPlainText(data)

    def set_entry(self, entry):
        """
        Load an entry, filling the tab bar with all pages etc.

        This is the first thing that's called whenever the metaviewer is booted up.
        """
        self.root = entry.file + '.metadir'
        self.make_sure_metadir_exists(self.root)
        self.tabbar.open_entry(self.root)
        self.update_tabcounter()
        self.titlelabel.setText(entry.title)
        self.textarea.setFocus()

    def make_sure_metadir_exists(self, root):
        """
        Create a directory with a stub page if none exist.
        """
        if not os.path.exists(root):
            os.mkdir(root)
            data = json.dumps({'title': 'about.txt', 'created': datetime.now().isoformat()})
            write_file(join(root, 'about.txt'), data + '\n')

    def current_page_path(self):
        """ Return the current page's full path, including root dir """
        return join(self.root, self.tabbar.current_page_fname())

    # ======= COMMANDS ========================================================

    def new_page(self, fname):
        f = join(self.root, fname)
        if os.path.exists(f):
            self.terminal.error('File already exists')
            return
        try:
            newtab = self.tabbar.add_page(fname)
        except KeyError as e:
            self.terminal.error(e.args[0])
        else:
            write_file(f, json.dumps({'title': fname, 'created': datetime.now().isoformat()}) + '\n')
            # Do this afterwards to have something to load into textarea
            self.tabbar.setCurrentIndex(newtab)

    def delete_page(self, arg):
        if arg != '!':
            self.terminal.error('Use d! to confirm deletion')
            return
        try:
            fname = self.tabbar.remove_page()
        except IndexError as e:
            self.terminal.error(e.args[0])
        else:
            os.remove(join(self.root, fname))

    def rename_page(self, title):
        try:
            self.tabbar.rename_page(title)
        except KeyError as e:
            self.terminal.error(e.args[0])
        else:
            fname = self.current_page_path()
            firstline, data = read_file(fname).split('\n', 1)
            jsondata = json.loads(firstline)
            jsondata['title'] = title
            write_file(fname, json.dumps(jsondata) + '\n' + data)

    def save_page(self, _):
        fname = self.current_page_path()
        firstline, _ = read_file(fname).split('\n', 1)
        data = self.textarea.toPlainText()
        write_file(fname, firstline + '\n' + data)

    def print_filename(self, arg):
        fname = self.current_page_path()
        if arg == 'c':
            firstline, _ = read_file(fname).split('\n', 1)
            date = json.loads(firstline)['created']
            self.terminal.print_('File created at ' + date)
        else:
            self.terminal.print_(self.tabbar.current_page_fname())



class MetaTerminal(GenericTerminal):
    new_page = pyqtSignal(str)
    delete_page = pyqtSignal(str)
    rename_page = pyqtSignal(str)
    save_page = pyqtSignal(str)
    print_filename = pyqtSignal(str)
    quit = pyqtSignal(str)
    go_back = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent, GenericTerminalInputBox, GenericTerminalOutputBox)

        self.commands = {
            'n': (self.new_page, 'New page'),
            'd': (self.delete_page, 'Delete page'),
            'r': (self.rename_page, 'Rename page'),
            's': (self.save_page, 'Save page'),
            'f': (self.print_filename, 'Print name of the active file'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'q': (self.quit, 'Quit'),
            'b': (self.go_back, 'Go back to index')
        }

        self.hide()
