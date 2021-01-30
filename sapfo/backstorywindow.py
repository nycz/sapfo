import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, List, NamedTuple, Optional,
                    Tuple, Union)

from libsyntyche import terminal
from libsyntyche.cli import ArgumentRules, Command
from libsyntyche.texteditor import Searcher
from libsyntyche.widgets import mk_signal0, mk_signal1
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCharFormat

from .common import Settings
from .declarative import Stretch, hbox, vbox
from .taggedlist import ATTR_FILE, ATTR_TITLE, Entry

Color = Union[QtGui.QColor, Qt.GlobalColor]


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
    lines = file.read_text(encoding='utf-8').split('\n', 1)
    return lines[0], lines[1]


def generate_page_metadata(title: str,
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
    def __init__(self, parent: QtCore.QObject, settings: Settings) -> None:
        super().__init__(parent)
        self.formats: List[Tuple[str, QTextCharFormat]] = []
        self.update_formats(settings.backstory_viewer_formats)

    def update_formats(self, formatstrings: Dict[str, List[Union[str, int]]]
                       ) -> None:
        self.formats = []
        font = QtGui.QFont
        for s, items in formatstrings.items():
            f = QTextCharFormat()
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
                elif re.fullmatch(r'#(?:[0-9a-f]{2})?[0-9a-f]{6}|[0-9a-f]{3}',
                                  x.lower()):
                    f.setForeground(QtGui.QColor(x))
            self.formats.append((s, f))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for rx, fmt in self.formats:
            for chunk in re.finditer(rx, text):
                self.setFormat(chunk.start(),
                               chunk.end() - chunk.start(), fmt)


class TabBar(QtWidgets.QTabBar):
    set_tab_index = mk_signal1(int)

    def __init__(self, parent: QtWidgets.QWidget,
                 print_: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.print_ = print_
        self.pages: List[Page] = []

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton:
            tab = self.tabAt(ev.pos())
            if tab != -1:
                self.set_tab_index.emit(tab)

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        delta = ev.angleDelta().y() + ev.angleDelta().x()
        if delta != 0:
            self.change_tab(-delta)

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


class BackstoryTextEdit(QtWidgets.QTextEdit):
    resized = mk_signal0()

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self.resized.emit()


class BackstoryWindow(QtWidgets.QFrame):
    closed = mk_signal1(Path)

    def __init__(self, entry: Entry, settings: Settings,
                 history_path: Path) -> None:
        super().__init__()
        self.settings = settings

        self.textarea = BackstoryTextEdit()
        self.default_font = self.textarea.fontFamily()
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
        history_file = history_path / (entry[ATTR_FILE].name + '.history')
        self.terminal = BackstoryTerminal(self, history_file)
        self.searcher = Searcher(self.textarea, self.terminal.error,
                                 self.terminal.print_)
        self.tabbar = TabBar(self, self.terminal.print_)
        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.revisionnotice, self.textarea, self.terminal)
        self.formatter = Formatter(self.textarea, settings)
        self.connect_signals()
        self.revisionactive = False
        self.forcequitflag = False
        hotkeypairs: Dict[str, Callable[[], Any]] = {
            'next tab': self.tabbar.next_tab,
            'prev tab': self.tabbar.prev_tab,
            'save': self.save_tab,
            'toggle terminal': self.toggle_terminal,
        }
        self.hotkeys = {
            key: QtWidgets.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs.items()
        }
        self.update_hotkeys(settings.hotkeys)
        self.ignorewheelevent = False
        self.entryfile = entry[ATTR_FILE]
        self.root = entry[ATTR_FILE].with_name(entry[ATTR_FILE].name + '.metadir')
        self.make_sure_metadir_exists(self.root)
        self.tabbar.open_entry(self.root)
        self.load_tab(0)
        self.titlelabel.setText(entry[ATTR_TITLE])
        self.setWindowTitle(entry[ATTR_TITLE])
        self.textarea.setFocus()
        # Message tray
        self.message_tray = terminal.MessageTray(self)
        self.terminal.show_message.connect(self.message_tray.add_message)
        self.textarea.resized.connect(self.adjust_tray)
        self.show()

    def setStyleSheet(self, css: str) -> None:
        super().setStyleSheet(css)
        self.terminal.setStyleSheet(css)

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

    def adjust_tray(self) -> None:
        rect = self.textarea.geometry()
        self.message_tray.setGeometry(rect)

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
                            hbox(Stretch(value=0), Stretch(textarea),
                                 Stretch(value=0)),
                            self.terminal))

    def cmd_quit(self, arg: str) -> None:
        self.forcequitflag = arg == '!'
        self.close()

    def connect_signals(self) -> None:
        self.tabbar.set_tab_index.connect(self.set_tab_index)
        self.settings.backstory_viewer_formats_changed.connect(
            self.formatter.update_formats)
        self.settings.hotkeys_changed.connect(self.update_hotkeys)
        t = self.terminal
        t.add_command(Command(
            'new-page', 'New page',
            self.cmd_new_page,
            short_name='n',
            args=ArgumentRules.REQUIRED,
            arg_help=(('filename.txt',
                       'Create a new page with the specified filename.'),),
        ))
        t.add_command(Command(
            'delete-page', 'Delete page',
            self.cmd_delete_current_page,
            short_name='d',
            arg_help=(('', 'Delete the open page.'),
                      ('!', 'Confirm the deletion.')),
        ))
        t.add_command(Command(
            'rename-page', 'Rename page',
            self.cmd_rename_current_page,
            short_name='r',
            args=ArgumentRules.REQUIRED,
            arg_help=(('Foobar', 'Rename the page to "Foobar".'),),
        ))
        t.add_command(Command(
            'save-page', 'Save page',
            self.cmd_save_current_page,
            short_name='s',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'print-filename', 'Print info about the open file',
            self.cmd_print_filename,
            short_name='f',
            arg_help=(('', 'Print the name of the active file.'),
                      ('c', 'Print the last modified date '
                       'of the active file.')),
        ))
        t.add_command(Command(
            'count-words', 'Print the page\'s wordcount',
            self.cmd_count_words,
            short_name='c',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'quit', 'Quit',
            self.cmd_quit,
            short_name='q',
            arg_help=(('', 'Close the window.'),
                      ('!', 'Force close the window.')),
        ))
        t.add_command(Command(
            'revision-control', 'Revision control',
            self.cmd_revision_control,
            short_name='#',
            arg_help=(('', 'Show latest revision.'),
                      ('+', 'Add new revision.'),
                      ('2', 'Show revision 2 (works with any number).'),
                      ('#', 'Print current revision.')),
        ))
        t.add_command(Command(
            'external-edit', 'Open in external program/editor',
            self.cmd_external_edit,
            short_name='x',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'search-and-replace', 'Search/replace',
            self.searcher.search_or_replace,
            short_name='/',
            args=ArgumentRules.REQUIRED,
            strip_input=False,
            arg_help=(('foo', 'Search for "foo".'),
                      ('foo/b', 'Search backwards for "foo". '
                       '(Can be combined with the other flags '
                       'in any order.)'),
                      ('foo/i', 'Search case-insensitively for '
                       '"foo". (Can be combined with the other '
                       'flags in any order.)'),
                      ('foo/w', 'Search for "foo", only matching '
                       'whole words. (Can be combined with the '
                       'other flags in any order.)'),
                      ('foo/bar/', 'Replace the first instance '
                       'of "foo" with "bar", starting from the '
                       'cursor\'s position.'),
                      ('foo/bar/[biw]', 'The flags works just '
                       'like in the search action.'),
                      ('foo/bar/a', 'Replace all instances '
                       'of "foo" with "bar". (Can be combined '
                       'with the other flags in any order.)')),
        ))

    def update_hotkeys(self, hotkeys: Dict[str, str]) -> None:
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(hotkeys[key]))

    def toggle_terminal(self) -> None:
        if self.textarea.hasFocus():
            self.terminal.show()
            self.terminal.input_field.setFocus()
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

    def cmd_delete_current_page(self, arg: Optional[str]) -> None:
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

    def cmd_save_current_page(self) -> None:
        self.save_tab()

    def cmd_print_filename(self, arg: Optional[str]) -> None:
        file = self.current_page_path()
        if arg == 'c':
            date = json.loads(read_metadata(file)[0])['created']
            self.terminal.print_('File created at ' + date)
        else:
            self.terminal.print_(self.tabbar.current_page_file().name)

    def cmd_count_words(self) -> None:
        wc = len(re.findall(r'\S+', self.textarea.document().toPlainText()))
        self.terminal.print_(f'Words: {wc}')

    def cmd_revision_control(self, arg: Optional[str]) -> None:
        file = self.current_page_path()
        jsondata = json.loads(read_metadata(file)[0])
        if not arg:
            if not self.revisionactive:
                self.terminal.error('Already showing latest revision')
            else:
                currenttab = self.tabbar.currentIndex()
                self.set_tab_index(currenttab)
        elif arg == '+':
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
                data = read_metadata(revfname)[1]
            except Exception as e:
                print(str(e))
                self.terminal.error('Something went wrong '
                                    'when loading the revision')
            else:
                self.textarea.setPlainText(data)
                self.textarea.document().setModified(False)
                self.revisionactive = True
                changed_date = datetime.fromtimestamp(revfname.stat().st_mtime)
                self.revisionnotice.setText(f'Showing revision {arg}. '
                                            f'Changes will not be saved.\n'
                                            f'Last modified: {changed_date}')
                self.revisionnotice.show()
        elif arg == '#':
            self.terminal.print_(f'Current revision: {jsondata["revision"]}')
        else:
            self.terminal.error(f'Unknown argument: "{arg}"')

    def cmd_external_edit(self) -> None:
        if not self.settings.editor:
            self.terminal.error('No editor command defined')
            return
        subprocess.Popen([self.settings.editor, str(self.entryfile)])
        self.terminal.print_(f'Opening entry with {self.settings.editor}')


class BackstoryTerminal(terminal.Terminal):
    def __init__(self, parent: QtWidgets.QWidget, history_file: Path) -> None:
        super().__init__(parent, history_file=history_file)
        self.output_field.hide()
        self.hide()
