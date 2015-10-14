from datetime import datetime
import json
import os
import os.path
from os.path import join
import re
import shutil

from PyQt4.QtCore import pyqtSignal, Qt
from PyQt4 import QtGui, QtCore

from libsyntyche.common import kill_theming, set_hotkey, read_file, write_file, local_path
from libsyntyche.terminal import GenericTerminalInputBox, GenericTerminalOutputBox, GenericTerminal

def generate_page_metadata(title, created=None, revision=None, revcreated=None, asdict=False):
    """
    Return a JSON string with the default metadata for a single backstory page.
    """
    now = datetime.now().isoformat()
    d = {
        'title': title,
        'created': now if created is None else created,
        'revision': 0 if revision is None else revision,
        'revision created': now if revcreated is None else revcreated,
    }
    if asdict:
        return d
    else:
        return json.dumps(d)

def check_and_fix_page_metadata(jsondata, payload, fname):
    """
    Make sure that the page's metadata has all required keys. Fix and add
    them if some of them are missing.
    """
    fixed = False
    defaultvalues = generate_page_metadata(os.path.basename(fname), asdict=True)
    # Special case if date exists and revision date doesn't:
    if 'revision created' not in jsondata and 'date' in jsondata:
        jsondata['revision created'] = jsondata['date']
        fixed = True
    # Generic fix
    for key, value in defaultvalues.items():
        if key not in jsondata:
            jsondata[key] = value
            fixed = True
    if fixed:
        write_file(fname, json.dumps(jsondata) + '\n' + payload)
    return jsondata

class Formatter(QtGui.QSyntaxHighlighter):
    def __init__(self, *args):
        super().__init__(*args)
        self.formats = None

    def update_formats(self, formatstrings):
        self.formats = []
        font = QtGui.QFont
        for s, items in formatstrings.items():
            f = QtGui.QTextCharFormat()
            if 'bold' in items:
                f.setFontWeight(font.Bold)
            if 'italic' in items:
                f.setFontItalic(True)
            if 'underline' in items:
                f.setFontUnderline(True)
            if 'strikethrough' in items:
                f.setFontStrikeOut(True)
            for x in items:
                if isinstance(x, int):
                    f.setFontPointSize(x)
                elif re.fullmatch(r'#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?', x):
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
    def __init__(self, parent, print_, set_tab_index):
        super().__init__(parent)
        self.print_ = print_
        self.pages = []
        self.set_tab_index = set_tab_index

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            tab = self.tabAt(ev.pos())
            if tab != -1:
                self.set_tab_index(tab)

    def wheelEvent(self, ev):
        self.change_tab(-ev.delta())

    def change_tab(self, direction):
        currenttab = self.currentIndex()
        if direction > 0 and currenttab == self.count() - 1:
            newtab = 0
        elif direction < 0 and currenttab == 0:
            newtab = self.count() - 1
        else:
            newtab = currenttab + int(direction/abs(direction))
        self.set_tab_index(newtab)

    def clear(self):
        while self.count() > 1:
            if self.currentIndex() == 0:
                self.removeTab(1)
            else:
                self.removeTab(0)
        self.removeTab(0)

    def current_page_fname(self):
        i = self.currentIndex()
        return self.pages[i][1]

    def get_page_fname(self, i):
        return self.pages[i][1]

    def set_page_position(self, page, cursorpos, scrollpos):
        self.pages[page][2] = cursorpos
        self.pages[page][3] = scrollpos

    def get_page_position(self, page):
        return self.pages[page][2:4]

    def load_pages(self, root):
        """
        Read all pages from the specified directory and build a list of them.
        """
        fnames = os.listdir(root)
        for f in fnames:
            if re.search(r'\.rev\d+$', f) is not None:
                continue
            firstline, data = read_file(join(root, f)).split('\n', 1)
            try:
                jsondata = json.loads(firstline)
            except ValueError:
                self.print_('Bad/no properties found on page {}, fixing...'.format(f))
                jsondata = generate_page_metadata(f)
                write_file(join(root, f), '\n'.join(jsondata, firstline, data))
                yield [f, f, 0, 0]
            else:
                fixedjsondata = check_and_fix_page_metadata(jsondata, data, join(root, f))
                yield [fixedjsondata['title'], f, 0, 0]

    def open_entry(self, root):
        """
        Ready the tab bar for a new entry.
        """
        self.clear()
        fnames = os.listdir(root)
        self.pages = sorted(self.load_pages(root))
        for title, _, _, _ in self.pages:
            self.addTab(title)

    def add_page(self, fname):
        """
        Add a new page to and then sort the tab bar. Return the index of the
        new tab.

        Raise KeyError if the title already exists.
        """
        if fname in (title for title, fname, cursorpos, scrollpos in self.pages):
            raise KeyError('Page name already exists')
        self.pages.append([fname, fname, 0, 0])
        self.pages.sort()
        i = next(zip(*self.pages)).index(fname)
        self.insertTab(i, fname)
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
        if newtitle in (title for title, fname, cursorpos, scrollpos in self.pages):
            raise KeyError('Page name already exists')
        i = self.currentIndex()
        self.pages[i][0] = newtitle
        self.pages.sort()
        self.setTabText(i, newtitle)
        self.moveTab(i, next(zip(*self.pages)).index(newtitle))


class MetaFrame(QtGui.QFrame):
    show_index = pyqtSignal()
    quit = pyqtSignal(bool)

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
        class MetaRevisionNotice(QtGui.QLabel):
            pass
        self.revisionnotice = MetaRevisionNotice(self)
        self.terminal = MetaTerminal(self)
        self.tabbar = TabBar(self, self.terminal.print_, self.set_tab_index)

        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.revisionnotice, self.textarea, self.terminal)
        self.connect_signals()

        self.formatter = Formatter(self.textarea)

        self.revisionactive = False
        self.hotkeys_set = False

        set_hotkey('Ctrl+PgUp', self, lambda: self.tabbar.change_tab(-1))
        set_hotkey('Ctrl+PgDown', self, lambda: self.tabbar.change_tab(+1))
        set_hotkey('Ctrl+S', self, self.save_tab)
        set_hotkey('Escape', self, self.toggle_terminal)


    def create_layout(self, titlelabel, tabbar, tabcounter, revisionnotice,
                      textarea, terminal):
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
        # Revision notice label
        revisionnotice.setAlignment(Qt.AlignCenter)
        layout.addWidget(revisionnotice)
        revisionnotice.hide()
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
            (t.go_back,         self.cmd_go_to_index),
            (t.quit,            lambda arg: self.quit.emit(arg == '!')),
            (t.new_page,        self.cmd_new_page),
            (t.delete_page,     self.cmd_delete_current_page),
            (t.rename_page,     self.cmd_rename_current_page),
            (t.save_page,       self.cmd_save_current_page),
            (t.print_filename,  self.cmd_print_filename),
            (t.count_words,     self.cmd_count_words),
            (t.revision_control,self.cmd_revision_control),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings):
        self.set_hotkeys(settings['hotkeys'])
        self.formatter.update_formats(settings['backstory viewer formats'])
        self.formatconverters = settings['formatting converters']
        self.chapterstrings = settings['chapter strings']

    def set_hotkeys(self, hotkeys):
        if self.hotkeys_set:
            return
        self.hotkeys_set = True
        for key in hotkeys['exit backstory']:
            set_hotkey(key, self, self.cmd_go_to_index)

    def toggle_terminal(self):
        if self.textarea.hasFocus():
            self.terminal.show()
            self.terminal.setFocus()
        else:
            self.terminal.hide()
            self.textarea.setFocus()

    def update_tabcounter(self):
        self.tabcounter.setText('{}/{}'.format(self.tabbar.currentIndex()+1, self.tabbar.count()))

    def save_tab(self):
        """
        Attempt to save the active tab, both the text and the scrollbar/cursor
        position.

        Return True if it succeeds, return False if it fails.
        """
        if self.revisionactive:
            return True
        currenttab = self.tabbar.currentIndex()
        if self.textarea.document().isModified():
            try:
                fname = join(self.root, self.tabbar.current_page_fname())
                firstline, _ = read_file(fname).split('\n', 1)
                data = self.textarea.toPlainText()
                write_file(fname, firstline + '\n' + data)
            except Exception as e:
                print(str(e))
                self.terminal.error('Something went wrong when saving! (Use q! or b! to force)')
                return False
        cursorpos = self.textarea.textCursor().position()
        scrollpos = self.textarea.verticalScrollBar().sliderPosition()
        self.tabbar.set_page_position(currenttab, cursorpos, scrollpos)
        self.textarea.document().setModified(False)
        return True

    def load_tab(self, newtab):
        """
        Load a new tab with the correct data and scrollbar/cursor position.

        Note that this does not in any way save existing data.
        """
        self.tabbar.setCurrentIndex(newtab)
        self.update_tabcounter()
        fname = self.current_page_path()
        _, data = read_file(fname).split('\n', 1)
        self.textarea.setPlainText(data)
        self.textarea.document().setModified(False)
        # Set the scrollbar/cursor positions
        cursorpos, scrollpos = self.tabbar.get_page_position(newtab)
        tc = self.textarea.textCursor()
        tc.setPosition(min(cursorpos, self.textarea.document().characterCount()-1))
        self.textarea.setTextCursor(tc)
        self.textarea.verticalScrollBar().setSliderPosition(scrollpos)

    def set_tab_index(self, newtab):
        """
        This is called whenever the tab is changed, i.e. when either of these
        things happen:
        * left mouse press on tab
        * mouse wheel scroll event on tab
        * ctrl pgup/pgdn
        """
        if self.revisionactive:
            self.revisionactive = False
            self.revisionnotice.hide()
            self.load_tab(newtab)
        else:
            # Save the old tab if needed
            success = self.save_tab()
            if success:
                # Load the new tab
                self.load_tab(newtab)


    def set_entry(self, entry):
        """
        Load an entry, filling the tab bar with all pages etc.

        This is the first thing that's called whenever the metaviewer is booted up.
        """
        self.revisionactive = False
        self.revisionnotice.hide()
        self.terminal.clear()
        self.root = entry.file + '.metadir'
        self.make_sure_metadir_exists(self.root)
        self.tabbar.open_entry(self.root)
        self.load_tab(0)
        self.titlelabel.setText(entry.title)
        self.textarea.setFocus()

    def make_sure_metadir_exists(self, root):
        """
        Create a directory with a stub page if none exist.
        """
        if not os.path.exists(root):
            os.mkdir(root)
            jsondata = generate_page_metadata('about.txt')
            write_file(join(root, 'about.txt'), jsondata + '\n')

    def current_page_path(self):
        """ Return the current page's full path, including root dir """
        return join(self.root, self.tabbar.current_page_fname())

    # ======= COMMANDS ========================================================

    def cmd_new_page(self, fname):
        f = join(self.root, fname)
        if os.path.exists(f):
            self.terminal.error('File already exists')
            return
        try:
            newtab = self.tabbar.add_page(fname)
        except KeyError as e:
            self.terminal.error(e.args[0])
        else:
            write_file(f, generate_page_metadata(fname) + '\n')
            # Do this afterwards to have something to load into textarea
            self.set_tab_index(newtab)

    def cmd_delete_current_page(self, arg):
        if arg != '!':
            self.terminal.error('Use d! to confirm deletion')
            return
        try:
            fname = self.tabbar.remove_page()
        except IndexError as e:
            self.terminal.error(e.args[0])
        else:
            self.load_tab(self.tabbar.currentIndex())
            os.remove(join(self.root, fname))

    def cmd_rename_current_page(self, title):
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

    def cmd_save_current_page(self, _):
        self.save_tab()

    def cmd_go_to_index(self, arg=''):
        success = self.save_tab()
        if success or arg == '!':
            self.show_index.emit()

    def cmd_print_filename(self, arg):
        fname = self.current_page_path()
        if arg == 'c':
            firstline, _ = read_file(fname).split('\n', 1)
            date = json.loads(firstline)['created']
            self.terminal.print_('File created at ' + date)
        else:
            self.terminal.print_(self.tabbar.current_page_fname())

    def cmd_count_words(self, arg):
        wc = len(re.findall(r'\S+', self.textarea.document().toPlainText()))
        self.terminal.print_('Words: {}'.format(wc))

    def cmd_revision_control(self, arg):
        fname = self.current_page_path()
        firstline, _ = read_file(fname).split('\n', 1)
        jsondata = json.loads(firstline)
        if arg == '+':
            if self.revisionactive:
                self.terminal.error('Can\'t create new revision when viewing an old one')
                return
            saved = self.save_tab()
            if saved:
                # Do this again in case something got saved before
                _, data = read_file(fname).split('\n', 1)
                f = join(self.root, fname)
                rev = jsondata['revision']
                shutil.copy2(f, f + '.rev{}'.format(rev))
                jsondata['revision'] += 1
                jsondata['revision created'] = datetime.now().isoformat()
                write_file(f, json.dumps(jsondata) + '\n' + data)
                self.terminal.print_('Revision increased to {}'.format(rev + 1))
        # Show a certain revision
        elif arg.isdigit():
            revfname = join(self.root, fname + '.rev{}'.format(arg))
            if not os.path.exists(revfname):
                self.terminal.error('Revision {} not found'.format(arg))
                return
            saved = self.save_tab()
            if not saved:
                return
            try:
                _, data = read_file(revfname).split('\n', 1)
            except Exception as e:
                print(str(e))
                self.error('Something went wrong when loading the revision')
            else:
                self.textarea.setPlainText(data)
                self.textarea.document().setModified(False)
                self.revisionactive = True
                self.revisionnotice.setText('Showing revision {}'.format(arg))
                self.revisionnotice.show()
        elif arg == '#':
            self.terminal.print_('Current revision: {}'.format(jsondata['revision']))
        elif not arg:
            if not self.revisionactive:
                self.terminal.error('Already showing latest revision')
            else:
                currenttab = self.tabbar.currentIndex()
                self.set_tab_index(currenttab)
        else:
            self.terminal.error('Unknown argument: "{}"'.format(arg))




class MetaTerminal(GenericTerminal):
    new_page = pyqtSignal(str)
    delete_page = pyqtSignal(str)
    rename_page = pyqtSignal(str)
    save_page = pyqtSignal(str)
    print_filename = pyqtSignal(str)
    count_words = pyqtSignal(str)
    quit = pyqtSignal(str)
    go_back = pyqtSignal(str)
    revision_control = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent, GenericTerminalInputBox, GenericTerminalOutputBox)

        self.commands = {
            'n': (self.new_page, 'New page'),
            'd': (self.delete_page, 'Delete page'),
            'r': (self.rename_page, 'Rename page'),
            's': (self.save_page, 'Save page'),
            'f': (self.print_filename, 'Print name of the active file'),
            'c': (self.count_words, 'Print the page\'s wordcount'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'q': (self.quit, 'Quit (q! to force)'),
            '#': (self.revision_control, 'Revision control'),
            'b': (self.go_back, 'Go back to index (b! to force)'),
        }

        self.hide()
