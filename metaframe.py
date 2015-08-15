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



class MetaFrame(QtGui.QFrame):
    show_index = pyqtSignal()
    quit = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setDisabled(True)
        class MetaTitle(QtGui.QLabel):
            pass
        self.titlelabel = MetaTitle()
        self.tabbar = QtGui.QTabBar()
        self.tabbar.currentChanged.connect(self.tab_changed)
        class MetaTabCounter(QtGui.QLabel):
            pass
        self.tabcounter = MetaTabCounter(self)
        class MetaTextEdit(QtGui.QTextEdit):
            pass
        self.textarea = MetaTextEdit()
        self.textarea.setTabStopWidth(30)
        self.textarea.setAcceptRichText(False)
        self.terminal = MetaTerminal(self)
        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.textarea, self.terminal)
        self.connect_signals()

        self.formatter = Formatter(self.textarea)

        set_hotkey('Ctrl+PgUp', self, lambda: self.change_tab(-1))
        set_hotkey('Ctrl+PgDown', self, lambda: self.change_tab(+1))
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

    def change_tab(self, direction):
        currenttab = self.tabbar.currentIndex()
        if direction > 0 and currenttab == self.tabbar.count() - 1:
            newtab = 0
        elif direction < 0 and currenttab == 0:
            newtab = self.tabbar.count() - 1
        else:
            newtab = currenttab + direction
        self.tabbar.setCurrentIndex(newtab)

    def set_entry(self, entry):
        while self.tabbar.count() > 0:
            self.tabbar.removeTab(0)
        self.root = entry.file + '.metadir'
        self.make_sure_metadir_exists(self.root)
        self.files = sorted(os.listdir(self.root))
        for f in self.files:
            firstline, data = read_file(join(self.root, f)).split('\n', 1)
            try:
                jsondata = json.loads(firstline)
            except ValueError:
                self.terminal.print_('Bad/no properties found on page {}, fixing...'.format(f))
                jsondata = json.dumps({'title': f})
                write_file(join(self.root, f), jsondata + '\n' + firstline + '\n' + data)
                title = f
            else:
                title = jsondata['title']
            self.tabbar.addTab(title)
        self.update_tabcounter()
        self.titlelabel.setText(entry.title)
        self.setEnabled(True)
        self.textarea.setFocus()

    def update_tabcounter(self):
        self.tabcounter.setText('{}/{}'.format(self.tabbar.currentIndex()+1, self.tabbar.count()))

    def tab_changed(self, tabnum):
        self.tabbar.setCurrentIndex(tabnum)
        self.update_tabcounter()
        firstline, data = read_file(join(self.root, self.files[tabnum])).split('\n', 1)
        self.textarea.setPlainText(data)

    def make_sure_metadir_exists(self, root):
        if not os.path.exists(root):
            os.mkdir(root)
            data = json.dumps({'title': 'about.txt'})
            write_file(join(root, 'about.txt'), data + '\n')

    def new_page(self, fname):
        f = join(self.root, fname)
        if os.path.exists(f):
            self.terminal.error('File already exists: "{}"'.format(fname))
            return
        write_file(f, json.dumps({'title': fname}) + '\n')
        self.files = sorted(self.files + [fname])
        i = self.files.index(fname)
        self.tabbar.insertTab(i, fname)
        self.tabbar.setCurrentIndex(i)

    def delete_page(self, arg):
        if self.tabbar.count() <= 1:
            self.terminal.error('Can\'t remove the only page')
            return
        if arg != '!':
            self.terminal.error('Use d! to confirm deletion')
            return
        tabnum = self.tabbar.currentIndex()
        page = self.tabbar.tabText(tabnum)
        os.remove(join(self.root, self.files[tabnum]))
        self.files.pop(tabnum)
        self.tabbar.removeTab(tabnum)
        self.terminal.print_('Page "{}" deleted'.format(page))

    def rename_page(self, title):
        if title in (self.tabbar.tabText(n) for n in range(self.tabbar.count())):
            self.terminal.error('Page name already exists')
            return
        tabnum = self.tabbar.currentIndex()
        firstline, data = read_file(join(self.root, self.files[tabnum])).split('\n', 1)
        jsondata = json.loads(firstline)
        jsondata['title'] = title
        self.tabbar.setTabText(tabnum, title)
        write_file(join(self.root, self.files[tabnum]), json.dumps(jsondata) + '\n' + data)

    def save_page(self, _):
        tabnum = self.tabbar.currentIndex()
        firstline, _ = read_file(join(self.root, self.files[tabnum])).split('\n', 1)
        data = self.textarea.toPlainText()
        write_file(join(self.root, self.files[tabnum]), firstline + '\n' + data)

    def print_filename(self, _):
        tabnum = self.tabbar.currentIndex()
        self.terminal.print_(self.files[tabnum])

# Testing formatting yo

    # def set_header(self, header):
    #     print('header',header)
    #     cursor = self.textarea.textCursor()
    #     format = QtGui.QTextCharFormat()
    #     format.setFontPointSize(30)
    #     if not cursor.hasSelection():
    #         cursor.select(QtGui.QTextCursor.BlockUnderCursor)
    #     cursor.mergeCharFormat(format)
    #     self.textarea.mergeCurrentCharFormat(format)
    #     self.textarea.setPlainText(self.textarea.toHtml())



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
