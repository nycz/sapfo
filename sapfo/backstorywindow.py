from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import (Any, Callable, Dict, Iterable, List,
                    NamedTuple, Optional, Tuple)

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5 import QtGui, QtWidgets

from libsyntyche.texteditor import SearchAndReplaceable

from .common import Settings
from .declarative import hbox, vbox, Stretch
from .taggedlist import Entry
from .terminal import (GenericTerminalInputBox,
                       GenericTerminalOutputBox, GenericTerminal)


class Page(NamedTuple):
    title: str
    file: Path
    cursorpos: int = 0
    scrollpos: int = 0


def fixtitle(file: Path) -> str:
    return re.sub(r"\w[\w']*",
                  lambda mo: mo.group(0)[0].upper() + mo.group(0)[1:].lower(),
                  file.stem.replace('-', ' '))


def read_metadata(file: Path) -> Tuple[str, str]:
    return tuple(file.read_text(encoding='utf-8').split('\n', 1))  # type: ignore


def generate_page_metadata(title: str,  # noqa: F811
                           created: Optional[datetime] = None,
                           revision: Optional[int] = None,
                           revcreated: Optional[datetime] = None
                           ) -> Dict[str, Any]:
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
    return d


def check_and_fix_page_metadata(jsondata: Dict[str, Any], payload: str,
                                file: Path) -> Dict[str, Any]:
    """
    Make sure that the page's metadata has all required keys. Fix and add
    them if some of them are missing.
    """
    fixed = False
    defaultvalues = generate_page_metadata(fixtitle(file))
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
        file.write_text(json.dumps(jsondata) + '\n' + payload)
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

    def current_page_file(self) -> Path:
        i: int = self.currentIndex()
        return self.pages[i].file

    def get_page_file(self, i: int) -> Path:
        return self.pages[i].file

    def set_page_position(self, i: int, cursorpos: int,
                          scrollpos: int) -> None:
        self.pages[i] = self.pages[i]._replace(cursorpos=cursorpos,
                                               scrollpos=scrollpos)

    def get_page_position(self, i: int) -> Tuple[int, int]:
        return self.pages[i][2:4]

    def load_pages(self, root: Path) -> Iterable[Page]:
        """
        Read all pages from the specified directory and build a list of them.
        """
        for file in root.iterdir():
            if re.search(r'\.rev\d+$', file.name) is not None:
                continue
            if file.is_dir():
                continue
            firstline, data = file.read_text().split('\n', 1)
            try:
                jsondata = json.loads(firstline)
            except ValueError:
                self.print_(f'Bad/no properties found on page {file.name}, '
                            f'fixing...')
                title = fixtitle(file)
                jsondata = json.dumps(generate_page_metadata(title))
                file.write_text('\n'.join([jsondata, firstline, data]))
                yield Page(title, file)
            else:
                fixedjsondata = check_and_fix_page_metadata(jsondata, data,
                                                            file)
                yield Page(fixedjsondata['title'], file)

    def open_entry(self, root: Path) -> None:
        """
        Ready the tab bar for a new entry.
        """
        self.clear()
        # fnames = os.listdir(root)
        self.pages = sorted(self.load_pages(root))
        for title, _, _, _ in self.pages:
            self.addTab(title)

    def add_page(self, title: str, file: Path) -> int:
        """
        Add a new page to and then sort the tab bar. Return the index of the
        new tab.
        """
        self.pages.append(Page(title, file))
        self.pages.sort()
        i = next(pos for pos, page in enumerate(self.pages)
                 if page.file == file)
        self.insertTab(i, title)
        return i

    def remove_page(self) -> Path:
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
        return page.file

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
    closed = pyqtSignal(Path)

    def __init__(self, entry: Entry, settings: Settings,
                 history_path: Path) -> None:
        super().__init__()
        self.settings = settings

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
        history_file = history_path / (entry.file.name + '.history')
        self.terminal = BackstoryTerminal(self, settings, history_file)
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
        self.update_hotkeys(settings.hotkeys)
        self.ignorewheelevent = False
        self.entryfile = entry.file
        self.root = entry.file.with_name(entry.file.name + '.metadir')
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
            self.closed.emit(self.entryfile)
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
        titlelabel.setAlignment(Qt.AlignCenter)
        tabbar.setDrawBase(False)
        revisionnotice.setAlignment(Qt.AlignCenter)
        revisionnotice.hide()
        self.setLayout(vbox(titlelabel,
                            hbox(Stretch(tabbar), tabcounter),
                            revisionnotice,
                            hbox(Stretch, Stretch(textarea), Stretch),
                            self.terminal))

    def cmd_quit(self, arg: str) -> None:
        self.forcequitflag = arg == '!'
        self.close()

    def connect_signals(self) -> None:
        t = self.terminal
        s = self.settings
        connects = (
            # Terminal stuff
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
            # Misc
            (self.tabbar.set_tab_index, self.set_tab_index),
            # Settings
            (s.backstory_viewer_formats_changed,
             self.formatter.update_formats),
            (s.hotkeys_changed, self.update_hotkeys),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_hotkeys(self, hotkeys: Dict) -> None:
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(hotkeys[key]))

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
                file = self.tabbar.current_page_file()
                firstline = read_metadata(file)[0]
                data = self.textarea.toPlainText()
                file.write_text(firstline + '\n' + data)
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
        data = read_metadata(self.current_page_path())[1]
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

    def make_sure_metadir_exists(self, root: Path) -> None:
        """
        Create a directory with a stub page if none exist.
        """
        if not root.exists():
            root.mkdir()
            for fname, title in self.settings.backstory_default_pages.items():
                jsondata = json.dumps(generate_page_metadata(title))
                (root / fname).write_text(jsondata + '\n', encoding='utf-8')

    def current_page_path(self) -> Path:
        """ Return the current page's full path, including root dir """
        return self.tabbar.current_page_file()

    # ======= COMMANDS ========================================================

    def cmd_new_page(self, fname: str) -> None:
        file = self.root / fname
        if file.exists():
            self.terminal.error('File already exists')
            return
        title = fixtitle(file)
        try:
            newtab = self.tabbar.add_page(title, file)
        except KeyError as e:
            self.terminal.error(e.args[0])
        else:
            file.write_text(json.dumps(generate_page_metadata(title)) + '\n')
            # Do this afterwards to have something to load into textarea
            self.set_tab_index(newtab)

    def cmd_delete_current_page(self, arg: str) -> None:
        if arg != '!':
            self.terminal.error('Use d! to confirm deletion')
            return
        try:
            file = self.tabbar.remove_page()
        except IndexError as e:
            self.terminal.error(e.args[0])
        else:
            self.load_tab(self.tabbar.currentIndex())
            file.unlink()

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
            file = self.current_page_path()
            firstline, data = read_metadata(file)
            jsondata = json.loads(firstline)
            jsondata['title'] = title
            file.write_text(json.dumps(jsondata) + '\n' + data)

    def cmd_save_current_page(self, _: str) -> None:
        self.save_tab()

    def cmd_print_filename(self, arg: str) -> None:
        file = self.current_page_path()
        if arg == 'c':
            date = json.loads(read_metadata(file)[0])['created']
            self.terminal.print_('File created at ' + date)
        else:
            self.terminal.print_(self.tabbar.current_page_file().name)

    def cmd_count_words(self, arg: str) -> None:
        wc = len(re.findall(r'\S+', self.textarea.document().toPlainText()))
        self.terminal.print_(f'Words: {wc}')

    def cmd_revision_control(self, arg: str) -> None:
        file = self.current_page_path()
        jsondata = json.loads(read_metadata(file)[0])
        if arg == '+':
            if self.revisionactive:
                self.terminal.error('Can\'t create new revision '
                                    'when viewing an old one')
                return
            saved = self.save_tab()
            if saved:
                # Do this again in case something got saved before
                data = read_metadata(file)[1]
                rev = jsondata['revision']
                shutil.copy2(file, file.with_name(file.name + f'.rev{rev}'))
                jsondata['revision'] += 1
                jsondata['revision created'] = datetime.now().isoformat()
                file.write_text(json.dumps(jsondata) + '\n' + data)
                self.terminal.print_(f'Revision increased to {rev + 1}')
        # Show a certain revision
        elif arg.isdigit():
            revfname = file.with_name(file.name + f'.rev{arg}')
            if not revfname.exists():
                self.terminal.error(f'Revision {arg} not found')
                return
            saved = self.save_tab()
            if not saved:
                return
            try:
                data = read_metadata(file)[1]
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
        if not self.settings.editor:
            self.terminal.error('No editor command defined')
            return
        subprocess.Popen([self.settings.editor, str(self.entryfile)])
        self.terminal.print_(f'Opening entry with {self.settings.editor}')


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

    def __init__(self, parent: QtWidgets.QWidget, settings: Settings,
                 history_file: Path) -> None:
        super().__init__(parent, settings, GenericTerminalInputBox,
                         GenericTerminalOutputBox, history_file=history_file)
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
