from datetime import datetime
import json
import os
import os.path
from os.path import join
import re
import shutil
import subprocess
from typing import (overload, Any, Callable, Dict, Iterable, List,
                    NamedTuple, Optional, Tuple, Union)

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5 import QtGui, QtWidgets

from libsyntyche.common import kill_theming, read_file, write_file
from libsyntyche.oldterminal import (GenericTerminalInputBox,
                                     GenericTerminalOutputBox, GenericTerminal)
from libsyntyche.texteditor import SearchAndReplaceable

from sapfo.taggedlist import Entry


class Page(NamedTuple):
    title: str
    fname: str
    cursorpos: int = 0
    scrollpos: int = 0


def fixtitle(fname: str) -> str:
    return re.sub(r"\w[\w']*",
                  lambda mo: mo.group(0)[0].upper() + mo.group(0)[1:].lower(),
                  os.path.splitext(fname)[0].replace('-', ' '))


@overload
def generate_page_metadata(title: str, created: Optional[datetime] = None,
                           revision: Optional[int] = None,
                           revcreated: Optional[datetime] = None,
                           asdict: bool = True) -> Dict[str, Any]:
    pass


@overload  # noqa: F811
def generate_page_metadata(title: str, created: Optional[datetime] = None,
                           revision: Optional[int] = None,
                           revcreated: Optional[datetime] = None,
                           asdict: bool = False) -> str:
    pass


def generate_page_metadata(title: str,  # noqa: F811
                           created: Optional[datetime] = None,
                           revision: Optional[int] = None,
                           revcreated: Optional[datetime] = None,
                           asdict: bool = False) -> Union[str, Dict[str, Any]]:
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


def check_and_fix_page_metadata(jsondata: Dict[str, Any], payload: str,
                                fname: str) -> Dict[str, Any]:
    """
    Make sure that the page's metadata has all required keys. Fix and add
    them if some of them are missing.
    """
    fixed = False
    defaultvalues = generate_page_metadata(fixtitle(os.path.basename(fname)),
                                           asdict=True)
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
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.formats: Optional[List] = None

    def update_formats(self, formatstrings: Dict) -> None:
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

    def highlightBlock(self, text: str) -> None:
        if self.formats is None:
            return
        for rx, fmt in self.formats:
            for chunk in re.finditer(rx, text):
                self.setFormat(chunk.start(), chunk.end() - chunk.start(), fmt)


class TabBar(QtWidgets.QTabBar):
    set_tab_index = pyqtSignal(int)

    def __init__(self, parent: QtWidgets.QWidget, print_: Callable) -> None:
        super().__init__(parent)
        self.print_ = print_
        self.pages: List[Page] = []

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton:
            tab = self.tabAt(ev.pos())
            if tab != -1:
                self.set_tab_index.emit(tab)

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        self.change_tab(-ev.angleDelta().y())

    def next_tab(self) -> None:
            self.change_tab(1)

    def prev_tab(self) -> None:
        self.change_tab(-1)

    def change_tab(self, direction: int) -> None:
        currenttab = self.currentIndex()
        if direction > 0 and currenttab == self.count() - 1:
            newtab = 0
        elif direction < 0 and currenttab == 0:
            newtab = self.count() - 1
        else:
            newtab = currenttab + int(direction/abs(direction))
        self.set_tab_index.emit(newtab)

    def clear(self) -> None:
        while self.count() > 1:
            if self.currentIndex() == 0:
                self.removeTab(1)
            else:
                self.removeTab(0)
        self.removeTab(0)

    def current_page_fname(self) -> str:
        i: int = self.currentIndex()
        return self.pages[i].fname

    def get_page_fname(self, i: int) -> str:
        return self.pages[i].fname

    def set_page_position(self, i: int, cursorpos: int,
                          scrollpos: int) -> None:
        self.pages[i] = self.pages[i]._replace(cursorpos=cursorpos,
                                               scrollpos=scrollpos)

    def get_page_position(self, i: int) -> Tuple[int, int]:
        return self.pages[i][2:4]

    def load_pages(self, root: str) -> Iterable[Page]:
        """
        Read all pages from the specified directory and build a list of them.
        """
        for fname in os.listdir(root):
            if re.search(r'\.rev\d+$', fname) is not None:
                continue
            if os.path.isdir(join(root, fname)):
                continue
            firstline, data = read_file(join(root, fname)).split('\n', 1)
            try:
                jsondata = json.loads(firstline)
            except ValueError:
                self.print_(f'Bad/no properties found on page {fname}, '
                            f'fixing...')
                title = fixtitle(fname)
                jsondata = generate_page_metadata(title)
                write_file(join(root, fname),
                           '\n'.join([jsondata, firstline, data]))
                yield Page(title, fname)
            else:
                fixedjsondata = check_and_fix_page_metadata(jsondata, data,
                                                            join(root, fname))
                yield Page(fixedjsondata['title'], fname)

    def open_entry(self, root: str) -> None:
        """
        Ready the tab bar for a new entry.
        """
        self.clear()
        # fnames = os.listdir(root)
        self.pages = sorted(self.load_pages(root))
        for title, _, _, _ in self.pages:
            self.addTab(title)

    def add_page(self, title: str, fname: str) -> int:
        """
        Add a new page to and then sort the tab bar. Return the index of the
        new tab.
        """
        self.pages.append(Page(title, fname))
        self.pages.sort()
        i = next(pos for pos, page in enumerate(self.pages)
                 if page.fname == fname)
        self.insertTab(i, title)
        return i

    def remove_page(self) -> str:
        """
        Remove the active page from the tab bar and return the page's file name

        Note that the actual file on the disk is not removed by this.
        Raise IndexError if there is only one tab left.
        """
        if self.count() <= 1:
            raise IndexError('Can\'t remove the only page')
        i: int = self.currentIndex()
        page = self.pages.pop(i)
        self.removeTab(i)
        self.print_(f'Page "{page.title}" deleted')
        return page.fname

    def rename_page(self, newtitle: str) -> None:
        """
        Rename the active page and update the tab bar.
        """
        i = self.currentIndex()
        self.pages[i] = self.pages[i]._replace(title=newtitle)
        self.pages.sort()
        self.setTabText(i, newtitle)
        new_i = next(pos for pos, page in enumerate(self.pages)
                     if page.title == newtitle)
        self.moveTab(i, new_i)


class BackstoryWindow(QtWidgets.QFrame):
    closed = pyqtSignal(str)

    def __init__(self, entry: Entry, settings: Dict) -> None:
        super().__init__()

        class BackstoryTextEdit(QtWidgets.QTextEdit, SearchAndReplaceable):
            pass
        self.textarea = BackstoryTextEdit()
        self.textarea.setTabStopWidth(30)
        self.textarea.setAcceptRichText(False)

        class BackstoryTitle(QtWidgets.QLabel):
            pass
        self.titlelabel = BackstoryTitle(self)

        class BackstoryTabCounter(QtWidgets.QLabel):
            pass
        self.tabcounter = BackstoryTabCounter(self)

        class BackstoryRevisionNotice(QtWidgets.QLabel):
            pass
        self.revisionnotice = BackstoryRevisionNotice(self)
        self.terminal = BackstoryTerminal(self)
        self.textarea.initialize_search_and_replace(self.terminal.error,
                                                    self.terminal.print_)
        self.tabbar = TabBar(self, self.terminal.print_)
        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.revisionnotice, self.textarea, self.terminal)
        self.connect_signals()
        self.formatter = Formatter(self.textarea)
        self.revisionactive = False
        self.forcequitflag = False
        hotkeypairs = (
            ('next tab', self.tabbar.next_tab),
            ('prev tab', self.tabbar.prev_tab),
            ('save', self.save_tab),
            ('toggle terminal', self.toggle_terminal),
        )
        self.hotkeys = {
            key: QtWidgets.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }
        self.ignorewheelevent = False
        self.update_settings(settings)
        self.entryfilename = entry.file
        self.root = entry.file + '.metadir'
        self.make_sure_metadir_exists(self.root)
        self.tabbar.open_entry(self.root)
        self.load_tab(0)
        self.titlelabel.setText(entry.title)
        self.setWindowTitle(entry.title)
        self.textarea.setFocus()
        self.show()

    def closeEvent(self, ev: QtGui.QCloseEvent) -> None:
        success = self.save_tab()
        if success or self.forcequitflag:
            self.closed.emit(self.entryfilename)
            ev.accept()
        else:
            ev.ignore()

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        # If this isn't here textarea will call this method later
        # and we'll get an infinite loop
        if self.ignorewheelevent:
            self.ignorewheelevent = False
            return
        self.ignorewheelevent = True
        self.textarea.wheelEvent(ev)
        ev.ignore()

    def create_layout(self,
                      titlelabel: QtWidgets.QLabel,
                      tabbar: 'TabBar',
                      tabcounter: QtWidgets.QLabel,
                      revisionnotice: QtWidgets.QLabel,
                      textarea: QtWidgets.QTextEdit,
                      terminal: 'BackstoryTerminal') -> None:
        layout = QtWidgets.QVBoxLayout(self)
        kill_theming(layout)
        # Title label
        titlelabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titlelabel)
        # Tab bar and tab counter
        tab_layout = QtWidgets.QHBoxLayout()
        tabbar.setDrawBase(False)
        tab_layout.addWidget(tabbar, stretch=1)
        tab_layout.addWidget(tabcounter, stretch=0)
        layout.addLayout(tab_layout)
        # Revision notice label
        revisionnotice.setAlignment(Qt.AlignCenter)
        layout.addWidget(revisionnotice)
        revisionnotice.hide()
        # Textarea
        textarea_layout = QtWidgets.QHBoxLayout()
        textarea_layout.addStretch()
        textarea_layout.addWidget(textarea, stretch=1)
        textarea_layout.addStretch()
        layout.addLayout(textarea_layout)
        # Terminal
        layout.addWidget(self.terminal)

    def cmd_quit(self, arg: str) -> None:
        self.forcequitflag = arg == '!'
        self.close()

    def connect_signals(self) -> None:
        t = self.terminal
        connects = (
            (t.quit,                    self.cmd_quit),
            (t.new_page,                self.cmd_new_page),
            (t.delete_page,             self.cmd_delete_current_page),
            (t.rename_page,             self.cmd_rename_current_page),
            (t.save_page,               self.cmd_save_current_page),
            (t.print_filename,          self.cmd_print_filename),
            (t.count_words,             self.cmd_count_words),
            (t.revision_control,        self.cmd_revision_control),
            (t.external_edit,           self.cmd_external_edit),
            (t.search_and_replace,      self.textarea.search_and_replace),
            (self.tabbar.set_tab_index, self.set_tab_index),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings: Dict) -> None:
        self.formatter.update_formats(settings['backstory viewer formats'])
        self.formatconverters = settings['formatting converters']
        self.chapterstrings = settings['chapter strings']
        self.defaultpages = settings['backstory default pages']
        self.externaleditor = settings['editor']
        # Terminal animation settings
        self.terminal.output_term.animate = settings['animate terminal output']
        interval = settings['terminal animation interval']
        if interval < 1:
            self.terminal.error('Too low animation interval')
        self.terminal.output_term.set_timer_interval(max(1, interval))
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))

    def toggle_terminal(self) -> None:
        if self.textarea.hasFocus():
            self.terminal.show()
            self.terminal.setFocus()
        else:
            self.terminal.hide()
            self.textarea.setFocus()

    def update_tabcounter(self) -> None:
        self.tabcounter.setText(f'{self.tabbar.currentIndex()+1}'
                                f'/{self.tabbar.count()}')

    def save_tab(self) -> bool:
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
                self.terminal.error('Something went wrong when saving! '
                                    '(Use q! to force)')
                return False
        cursorpos = self.textarea.textCursor().position()
        scrollpos = self.textarea.verticalScrollBar().sliderPosition()
        self.tabbar.set_page_position(currenttab, cursorpos, scrollpos)
        self.textarea.document().setModified(False)
        return True

    def load_tab(self, newtab: int) -> None:
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
        tc.setPosition(min(cursorpos,
                           self.textarea.document().characterCount() - 1))
        self.textarea.setTextCursor(tc)
        self.textarea.verticalScrollBar().setSliderPosition(scrollpos)

    def set_tab_index(self, newtab: int) -> None:
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

    def make_sure_metadir_exists(self, root: str) -> None:
        """
        Create a directory with a stub page if none exist.
        """
        if not os.path.exists(root):
            os.mkdir(root)
            for fname, title in self.defaultpages.items():
                jsondata = generate_page_metadata(title)
                write_file(join(root, fname), jsondata + '\n')

    def current_page_path(self) -> str:
        """ Return the current page's full path, including root dir """
        return join(self.root, self.tabbar.current_page_fname())

    # ======= COMMANDS ========================================================

    def cmd_new_page(self, fname: str) -> None:
        f = join(self.root, fname)
        if os.path.exists(f):
            self.terminal.error('File already exists')
            return
        title = fixtitle(fname)
        try:
            newtab = self.tabbar.add_page(title, fname)
        except KeyError as e:
            self.terminal.error(e.args[0])
        else:
            write_file(f, generate_page_metadata(title) + '\n')
            # Do this afterwards to have something to load into textarea
            self.set_tab_index(newtab)

    def cmd_delete_current_page(self, arg: str) -> None:
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

    def cmd_rename_current_page(self, title: str) -> None:
        if not title.strip():
            oldtitle = self.tabbar.pages[self.tabbar.currentIndex()][0]
            self.terminal.prompt(f'r {oldtitle}')
            return
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

    def cmd_save_current_page(self, _: str) -> None:
        self.save_tab()

    def cmd_print_filename(self, arg: str) -> None:
        fname = self.current_page_path()
        if arg == 'c':
            firstline, _ = read_file(fname).split('\n', 1)
            date = json.loads(firstline)['created']
            self.terminal.print_('File created at ' + date)
        else:
            self.terminal.print_(self.tabbar.current_page_fname())

    def cmd_count_words(self, arg: str) -> None:
        wc = len(re.findall(r'\S+', self.textarea.document().toPlainText()))
        self.terminal.print_(f'Words: {wc}')

    def cmd_revision_control(self, arg: str) -> None:
        fname = self.current_page_path()
        firstline, _ = read_file(fname).split('\n', 1)
        jsondata = json.loads(firstline)
        if arg == '+':
            if self.revisionactive:
                self.terminal.error('Can\'t create new revision '
                                    'when viewing an old one')
                return
            saved = self.save_tab()
            if saved:
                # Do this again in case something got saved before
                _, data = read_file(fname).split('\n', 1)
                f = join(self.root, fname)
                rev = jsondata['revision']
                shutil.copy2(f, f'{f}.rev{rev}')
                jsondata['revision'] += 1
                jsondata['revision created'] = datetime.now().isoformat()
                write_file(f, json.dumps(jsondata) + '\n' + data)
                self.terminal.print_(f'Revision increased to {rev + 1}')
        # Show a certain revision
        elif arg.isdigit():
            revfname = join(self.root, f'{fname}.rev{arg}')
            if not os.path.exists(revfname):
                self.terminal.error(f'Revision {arg} not found')
                return
            saved = self.save_tab()
            if not saved:
                return
            try:
                _, data = read_file(revfname).split('\n', 1)
            except Exception as e:
                print(str(e))
                self.terminal.error('Something went wrong when loading the revision')
            else:
                self.textarea.setPlainText(data)
                self.textarea.document().setModified(False)
                self.revisionactive = True
                self.revisionnotice.setText(f'Showing revision {arg}. '
                                            f'Changes will not be saved.')
                self.revisionnotice.show()
        elif arg == '#':
            self.terminal.print_(f'Current revision: {jsondata["revision"]}')
        elif not arg:
            if not self.revisionactive:
                self.terminal.error('Already showing latest revision')
            else:
                currenttab = self.tabbar.currentIndex()
                self.set_tab_index(currenttab)
        else:
            self.terminal.error(f'Unknown argument: "{arg}"')

    def cmd_external_edit(self, arg: str) -> None:
        if not self.externaleditor:
            self.terminal.error('No editor command defined')
            return
        subprocess.Popen([self.externaleditor, self.entryfilename])
        self.terminal.print_(f'Opening entry with {self.externaleditor}')


class BackstoryTerminal(GenericTerminal):
    new_page = pyqtSignal(str)
    delete_page = pyqtSignal(str)
    rename_page = pyqtSignal(str)
    save_page = pyqtSignal(str)
    print_filename = pyqtSignal(str)
    count_words = pyqtSignal(str)
    quit = pyqtSignal(str)
    revision_control = pyqtSignal(str)
    external_edit = pyqtSignal(str)
    search_and_replace = pyqtSignal(str)
    print_help = pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, GenericTerminalInputBox,
                         GenericTerminalOutputBox)
        self.commands = {
            'n': (self.new_page, 'New page'),
            'd': (self.delete_page, 'Delete page'),
            'r': (self.rename_page, 'Rename page'),
            's': (self.save_page, 'Save page'),
            'f': (self.print_filename, 'Print name of the active file'),
            'c': (self.count_words, 'Print the page\'s wordcount'),
            '?': (self.print_help, 'List commands or help for [command]'),
            'q': (self.quit, 'Quit (q! to force)'),
            '#': (self.revision_control, 'Revision control'),
            'x': (self.external_edit, 'Open in external program/editor'),
            '/': (self.search_and_replace, 'Search/replace',
                  {'keep whitespace': True}),
        }
        self.print_help.connect(self.cmd_help)
        self.hide()
