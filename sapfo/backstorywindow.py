from datetime import datetime
import enum
from itertools import chain
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import (Any, Callable, cast, Dict, Iterable, List,
                    NamedTuple, Optional, Set, Tuple, Union)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, Qt, QRect
from PyQt5.QtGui import QTextCharFormat

from libsyntyche import terminal
from libsyntyche.cli import ArgumentRules, Command
from libsyntyche.texteditor import SearchAndReplaceable
from libsyntyche.widgets import Signal0

from .common import Settings
from .declarative import hbox, vbox, Stretch
from .taggedlist import Entry


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


def _text_char_format(foreground: Optional[Union[str, Color]] = None,
                      background: Optional[Union[str, Color]] = None,
                      bold: bool = False,
                      italic: bool = False,
                      underline: bool = False,
                      underline_style: Optional[QTextCharFormat.UnderlineStyle] = None,
                      underline_color: Optional[Union[str, Color]] = None,
                      point_size: Optional[int] = None
                      ) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setFontFamily('monospace')
    if foreground:
        if isinstance(foreground, str):
            foreground = QtGui.QColor(foreground)
        fmt.setForeground(foreground)
    if background:
        if isinstance(background, str):
            background = QtGui.QColor(background)
        fmt.setBackground(background)
    if bold:
        fmt.setFontWeight(QtGui.QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    if underline:
        fmt.setFontUnderline(True)
    if underline_style is not None:
        fmt.setUnderlineStyle(underline_style)
    if underline_color is not None:
        if isinstance(underline_color, str):
            underline_color = QtGui.QColor(underline_color)
        fmt.setUnderlineColor(underline_color)
    if point_size is not None:
        fmt.setFontPointSize(point_size)
    return fmt


class ChunkType(enum.IntFlag):
    ATOM = 0
    STRING = 0b00000001
    BROKEN_STRING = 0b10000001
    NUMBER = 0b00000010
    TAG = 0b00000100
    COLOR = 0b00001000
    BACKGROUND = 0b00011000
    FOREGROUND = 0b00101000


class Chunk(NamedTuple):
    start: int
    text: str
    type_: ChunkType

    def _format(self, highlighter: QtGui.QSyntaxHighlighter,
                fmt: QTextCharFormat) -> None:
        highlighter.setFormat(self.start, len(self.text), fmt)


def _parse_timeline_command(line: str) -> List[Chunk]:
    chunks = []
    buf = ''
    buf_start = -1
    in_string = False
    for n, char in enumerate(chain(line, [None])):
        if in_string:
            if char == '"' and not buf.endswith('\\'):
                chunks.append(Chunk(buf_start, buf + '"', ChunkType.STRING))
                buf_start = -1
                buf = ''
                in_string = False
            elif char is None:
                chunks.append(Chunk(buf_start, buf, ChunkType.BROKEN_STRING))
            else:
                buf += char
        elif buf_start >= 0:
            if char is None or char in {' ', '\t'}:
                if buf.startswith('#'):
                    type_ = ChunkType.TAG
                elif buf.isdigit():
                    type_ = ChunkType.NUMBER
                elif buf.startswith('fg:'):
                    type_ = ChunkType.FOREGROUND
                elif buf.startswith('bg:'):
                    type_ = ChunkType.BACKGROUND
                else:
                    type_ = ChunkType.ATOM
                chunks.append(Chunk(buf_start, buf, type_))
                buf_start = -1
                buf = ''
            else:
                buf += char
        elif char is not None and char not in {' ', '\t'}:
            in_string = (char == '"')
            buf_start = n
            buf += char
    return chunks


class Formatter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent: QtCore.QObject, settings: Settings) -> None:
        super().__init__(parent)
        self._timeline_mode = False
        self.formats: List[Tuple[str, QTextCharFormat]] = []
        self.update_formats(settings.backstory_viewer_formats)

    @property
    def timeline_mode(self) -> bool:
        return self._timeline_mode

    @timeline_mode.setter
    def timeline_mode(self, new_mode: bool) -> None:
        if new_mode != self._timeline_mode:
            self._timeline_mode = new_mode
            self.rehighlight()

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
        if self._timeline_mode:
            self.highlight_timeline(text)
        else:
            for rx, fmt in self.formats:
                for chunk in re.finditer(rx, text):
                    self.setFormat(chunk.start(),
                                   chunk.end() - chunk.start(), fmt)

    def highlight_timeline(self, text: str) -> None:
        # Monokai
        c_background = QtGui.QColor('#272822')
        c_foreground = QtGui.QColor('#F8F8F2')
        c_comment = QtGui.QColor('#75715E')
        c_red = QtGui.QColor('#F92672')
        c_orange = QtGui.QColor('#FD971F')
        c_light_orange = QtGui.QColor('#E69F66')
        c_yellow = QtGui.QColor('#E6DB74')
        c_green = QtGui.QColor('#A6E22E')
        c_blue = QtGui.QColor('#66D9EF')
        c_purple = QtGui.QColor('#AE81FF')
        # Formats
        cmd_fmt = _text_char_format(bold=True, foreground=c_red)
        tag_fmt = _text_char_format(foreground=c_green, italic=True)
        keyword_fmt = _text_char_format(foreground=c_light_orange,
                                        bold=True)
        error_fmt = _text_char_format(background=Qt.darkRed)
        chunks = _parse_timeline_command(text)
        # Trailing whitespace
        ws = re.search(r'\s+$', text)
        if ws:
            self.setFormat(ws.start(), ws.end() - ws.start(), error_fmt)
        # Comments
        if text.startswith('//'):
            comment_fmt = _text_char_format(italic=True, foreground=c_comment)
            self.setFormat(0, len(text), comment_fmt)
            return
        # Format def command
        formatdef_rx = re.match(r'(format) +(#\S+)', text)
        if formatdef_rx is not None:
            self.setFormat(0, len(formatdef_rx[1]), cmd_fmt)
            self.setFormat(formatdef_rx.start(2), len(formatdef_rx[2]),
                           tag_fmt)
            bg: Union[QtGui.QColor, QtCore.Qt.GlobalColor]
            fg: Union[QtGui.QColor, QtCore.Qt.GlobalColor]
            for n, match in enumerate(re.finditer(r'\S+', text.lower())):
                # Skip the first two
                if n < 2:
                    continue
                if match[0] in {'italic', 'bold'}:
                    fmt = keyword_fmt
                elif re.fullmatch(r'[fb]g:#([0-9a-f]+)', match[0]) is not None \
                        and len(match[0]) - 4 in {3, 6, 8}:
                    fg = QtGui.QColor(match[0][3:])
                    bg = Qt.black if fg.lightnessF() > 0.5 else Qt.white
                    if match[0].startswith('bg'):
                        fg, bg = bg, fg
                    fmt = _text_char_format(bold=True, background=bg,
                                            foreground=fg)
                else:
                    fmt = error_fmt
                self.setFormat(match.start(0), len(match[0]), fmt)
            return
        if not chunks:
            return
        elif chunks[0].text == 'chapter':
            chunks[0]._format(self, _text_char_format(bold=True,
                                                      foreground=c_red))
            formats = {
                ChunkType.NUMBER: _text_char_format(bold=True,
                                                    foreground=c_orange),
                ChunkType.TAG: tag_fmt,
                ChunkType.STRING: _text_char_format(bold=True,
                                                    foreground=c_foreground),
            }
            max_allowed = {ChunkType.NUMBER: 1, ChunkType.STRING: 1}
            for chunk in chunks[1:]:
                if chunk.type_ in formats \
                        and max_allowed.get(chunk.type_, 1) > 0:
                    fmt = formats[chunk.type_]
                    if chunk.type_ in max_allowed:
                        max_allowed[chunk.type_] -= 1
                else:
                    fmt = error_fmt
                chunk._format(self, fmt)
        elif chunks[0].text == 'event':
            chunks[0]._format(self, _text_char_format(bold=True,
                                                      foreground=c_blue))#'#74e0af'))
            formats = {
                ChunkType.TAG: tag_fmt,
                ChunkType.STRING: _text_char_format(foreground=c_foreground)#'#eaedc0')
            }
            max_allowed = {ChunkType.STRING: 1}
            for chunk in chunks[1:]:
                if chunk.type_ in formats \
                        and max_allowed.get(chunk.type_, 1) > 0:
                    fmt = formats[chunk.type_]
                    if chunk.type_ in max_allowed:
                        max_allowed[chunk.type_] -= 1
                else:
                    fmt = error_fmt
                chunk._format(self, fmt)
        elif chunks[0].text == 'time':
            chunks[0]._format(self, _text_char_format(bold=True,
                                                      foreground=c_purple))
            if len(chunks) > 1:
                chunks[1]._format(self, _text_char_format(foreground=c_foreground))
                if len(chunks) > 2:
                    self.setFormat(chunks[2].start, len(text) - chunks[2].start,
                                   error_fmt)
        elif self.currentBlock().blockNumber() == 0 \
                and text == '!!timeline':
            meta_fmt = _text_char_format(bold=True, italic=True,
                                         foreground=Qt.darkGray)
            self.setFormat(0, len(text), meta_fmt)
        else:
            self.setFormat(0, len(text), error_fmt)


class TabBar(QtWidgets.QTabBar):
    set_tab_index = pyqtSignal(int)

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


def _make_font(family: Optional[str] = None,
               point_size: Optional[int] = None,
               pixel_size: Optional[int] = None,
               bold: Optional[bool] = None,
               italic: Optional[bool] = None,
               base_font: Optional[QtGui.QFont] = None) -> QtGui.QFont:
    font = base_font or QtGui.QFont()
    if family:
        font.setFamily(family)
    if point_size is not None:
        font.setPointSize(point_size)
    if pixel_size is not None:
        font.setPixelSize(pixel_size)
    if bold is not None:
        font.setBold(bold)
    if italic is not None:
        font.setItalic(italic)
    return font


class TLFormat(NamedTuple):
    foreground: Optional[Color] = None
    background: Optional[Color] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None

    def _get_foreground(self) -> Color:
        return Qt.white if self.foreground is None else self.foreground

    def _get_bold(self) -> bool:
        return False if self.bold is None else self.bold

    def _get_italic(self) -> bool:
        return False if self.italic is None else self.italic

    def activate(self, painter: QtGui.QPainter) -> None:
        painter.setPen(self._get_foreground())
        font = painter.font()
        font.setBold(self._get_bold())
        font.setItalic(self._get_italic())
        painter.setFont(font)


class TLTimeChange:
    def __init__(self, days: Tuple[int, int], relative: bool) -> None:
        self.min_days, self.max_days = days
        self.relative = relative


class TLEvent:
    def __init__(self, text: str,
                 tags: Optional[Set[str]] = None,
                 time_change: Optional[TLTimeChange] = None) -> None:
        self.text = text
        self.tags = tags or set()
        self.time_change = time_change


class TLChapter:
    def __init__(self, number: int,
                 events: Optional[List[TLEvent]] = None,
                 tags: Optional[Set[str]] = None,
                 title: Optional[str] = None,
                 time_change: Optional[TLTimeChange] = None) -> None:
        self.number = number
        self.events = events or []
        self.tags = tags or set()
        self.title = title
        self.time_change = time_change


class TLTimeState:
    def __init__(self) -> None:
        self.min_day = 0
        self.max_day = 0

    def update(self, change: TLTimeChange) -> None:
        if not change.relative:
            self.min_day = 0
            self.max_day = 0
        self.min_day += change.min_days
        self.max_day += change.max_days

    def __str__(self) -> str:
        if self.min_day == self.max_day:
            return f'Day {self.min_day}'
        else:
            return f'Day {self.min_day} ~ {self.max_day}'


class Timeline(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        # self.setFixedSize(500, 500)
        self.lines: List[str] = []
        self.chapters: List[TLChapter] = []
        self.tag_formats: Dict[str, TLFormat] = {}

    def get_format(self, tags: Set[str],
                   default: Optional[TLFormat] = None) -> TLFormat:
        default_fmt = default or TLFormat()
        if not tags:
            return default_fmt
        fmt_dict = default_fmt._asdict()
        for tag, fmt in self.tag_formats.items():
            if tag in tags:
                for key, value in fmt._asdict().items():
                    if value is not None:
                        fmt_dict[key] = value
        return TLFormat(**fmt_dict)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        chapter_font = _make_font('sans-serif', pixel_size=20, bold=True)
        chapter_font_metrics = QtGui.QFontMetrics(chapter_font)
        chapter_line_height = chapter_font_metrics.lineSpacing()
        event_font = _make_font('serif', pixel_size=16)
        event_font_metrics = QtGui.QFontMetrics(event_font)
        event_line_height = event_font_metrics.lineSpacing()
        between_chapters = (event_line_height * 0.5
                            + chapter_line_height * 1.0) // 2
        between_events = (event_line_height * 0.5) // 2
        r = self.rect()
        p = QtGui.QPainter(self)
        p.fillRect(r, QtGui.QBrush(QtGui.QColor('#223')))
        p.setPen(Qt.white)
        x = 110
        y = 10
        time_state = TLTimeState()
        # min_day, max_day = 0, 0
        # last_date = None

        def draw_time_change(time_change: TLTimeChange, space: int) -> None:
            orig_font = p.font()
            p.setFont(event_font)
            time_state.update(time_change)
            time_text = str(time_state)
            xx = x - 100
            yy = int(y - space * 0.9)
            orig_pen = p.pen()
            p.setPen(QtGui.QColor('#33ffffff'))
            p.drawLine(xx + event_font_metrics.width(time_text) + 10, yy,
                       xx + 1000, yy)
            p.setPen(Qt.white)
            p.drawText(QRect(xx, yy - event_line_height,
                             r.width() - xx, event_line_height * 2),
                       Qt.AlignVCenter, time_text)
            p.setPen(orig_pen)
            p.setFont(orig_font)

        chapters = iter(self.chapters)
        n = 0
        while True:
            try:
                chapter = next(chapters)
            except StopIteration:
                break
            # Draw the chapter
            if n > 0:
                y += chapter_line_height
            if chapter.time_change is not None:
                if n == 0:
                    y += between_chapters * 2
                draw_time_change(chapter.time_change, between_chapters)
            p.setFont(chapter_font)
            chapter_text = f'Chapter {chapter.number}'
            if chapter.title:
                chapter_text += ' - ' + chapter.title
            fmt = self.get_format(chapter.tags)
            if fmt.background is not None:
                chapter_width = max([chapter_font_metrics.width(chapter_text)]
                                    + [event_font_metrics.width(e.text)
                                       for e in chapter.events])
                evs = len(chapter.events)
                padding = event_line_height / 2
                chapter_height = (chapter_line_height * 1.5
                                  + evs * event_line_height
                                  + (max(evs - 1, 0) * event_line_height / 2))
                bg_rect = QRect(x, y, chapter_width, chapter_height)
                p.fillRect(bg_rect.adjusted(-padding, -padding,
                                            padding, padding),
                           fmt.background)
            p.setPen(fmt._get_foreground())
            p.drawText(QRect(x, y, r.width() - x, chapter_line_height),
                       Qt.AlignBottom, chapter_text)
            y += chapter_line_height * 1.5
            # Draw the events
            p.setFont(event_font)
            for event in chapter.events:
                ev_fmt = self.get_format(event.tags,
                                         default=fmt._replace(background=None))
                ev_fmt.activate(p)
                if ev_fmt.background is not None:
                    bg_rect = QRect(x, y, event_font_metrics.width(event.text),
                                    event_line_height)
                    padding = between_events * 0.8
                    p.fillRect(bg_rect.adjusted(-padding, -padding,
                                                padding, padding),
                               ev_fmt.background)

                if event.time_change is not None:
                    draw_time_change(event.time_change, between_events)
                p.drawText(QRect(x, y, r.width() - x, event_line_height),
                           Qt.AlignBottom, event.text)
                y += event_line_height * 1.5

            n += 1
        self.setMinimumHeight(y + between_chapters)

    def update_data(self, text: str) -> None:
        lines = [t for t in (line.strip() for line in text.splitlines()) if t]
        if self.lines == lines:
            return
        self.lines = lines
        self.chapters = []
        self.tag_formats.clear()

        def parse_color(lower_attrs: Iterable[str], prefix: str,
                        name: str) -> Optional[QtGui.QColor]:
            color_attrs = [a for a in lower_attrs
                           if a.startswith(prefix + ':')]
            if len(color_attrs) == 1:
                try:
                    return QtGui.QColor(color_attrs[0].split(':', 1)[1])
                except Exception:
                    pass
            else:
                pass
            return None

        time_change: Optional[TLTimeChange] = None

        for line in lines:
            if line.startswith('!!'):
                continue
            cmd, *args = line.split(None, 1)
            if cmd == 'chapter':
                try:
                    match = re.fullmatch(r'(\d+)(?:\s+"([^"]*)")?(?:\s+(.*))?', args[0])
                    tags = set(match[3].split()) if match[3] else None
                    chapter = TLChapter(int(match[1]),
                                        title=match[2],
                                        tags=tags,
                                        time_change=time_change)
                    self.chapters.append(chapter)
                    time_change = None
                except Exception:
                    pass
            elif cmd == 'event':
                try:
                    match = re.fullmatch(r'"([^"]*)"\s*(.*)', args[0])
                    tags = set(match[2].split()) if match[2] else None
                    event = TLEvent(match[1], tags=tags,
                                    time_change=time_change)
                    self.chapters[-1].events.append(event)
                    time_change = None
                except Exception:
                    pass
            elif cmd == 'time':
                try:
                    match = re.fullmatch(r'\+?(\d+)(?:~(\d+))?', args[0])
                    if match:
                        min_ = match[1]
                        max_ = match[1] if match[2] is None else match[2]
                        # TODO: don't overwrite
                        time_change = TLTimeChange((int(min_), int(max_)),
                                                   relative=args[0].startswith('+'))
                except Exception:
                    pass
            elif cmd == 'format':
                try:
                    target, *attrs = args[0].split()
                    lower_attrs = {a.lower() for a in attrs}
                    fg = parse_color(lower_attrs, 'fg', 'foreground')
                    bg = parse_color(lower_attrs, 'bg', 'background')
                    self.tag_formats[target] = TLFormat(
                        bold='bold' in lower_attrs,
                        italic='italic' in lower_attrs,
                        foreground=fg,
                        background=bg)
                except Exception:
                    pass
        self.update()


class TimelineWindow(QtWidgets.QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.scene = Timeline(self)
        self.setWidget(self.scene)
        self.setWidgetResizable(True)
        self.show()


class BackstoryTextEdit(QtWidgets.QTextEdit, SearchAndReplaceable):
    resized = QtCore.pyqtSignal()

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self.resized.emit()


class BackstoryWindow(QtWidgets.QFrame):
    closed = pyqtSignal(Path)

    def __init__(self, entry: Entry, settings: Settings,
                 history_path: Path) -> None:
        super().__init__()
        self.settings = settings

        self.timeline = TimelineWindow()
        self.timeline.hide()

        self.textarea = BackstoryTextEdit()
        self.default_font = self.textarea.fontFamily()
        self.textarea.setTabStopWidth(30)
        self.textarea.setAcceptRichText(False)

        def update_timeline_maybe() -> None:
            if self.in_timeline_mode():
                self.timeline.scene.update_data(self.textarea.toPlainText())
                self.timeline.update()

        cast(Signal0, self.textarea.textChanged).connect(update_timeline_maybe)

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
        self.terminal = BackstoryTerminal(self, history_file)
        self.textarea.initialize_search_and_replace(self.terminal.error,
                                                    self.terminal.print_)
        self.tabbar = TabBar(self, self.terminal.print_)
        self.create_layout(self.titlelabel, self.tabbar, self.tabcounter,
                           self.revisionnotice, self.textarea, self.terminal)
        self.formatter = Formatter(self.textarea, settings)
        def set_formatter_mode() -> None:
            in_timeline_mode = self.in_timeline_mode()
            self.formatter.timeline_mode = in_timeline_mode
            # if in_timeline_mode:
                # self.textarea.setFontFamily('monospace')
            # else:
                # self.textarea.setFontFamily(self.default_font)

        cast(Signal0, self.textarea.textChanged).connect(set_formatter_mode)
        self.connect_signals()
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
        # Message tray
        self.message_tray = terminal.MessageTray(self)
        self.terminal.show_message.connect(self.message_tray.add_message)
        self.textarea.resized.connect(self.adjust_tray)
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

    def adjust_tray(self) -> None:
        rect = self.textarea.geometry()
        self.message_tray.setGeometry(rect)

    def in_timeline_mode(self) -> bool:
        text = self.textarea.document().firstBlock().text()
        return text.startswith('!!timeline')

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
        t = self.terminal
        s = self.settings
        connects: Tuple[Tuple[pyqtSignal, Callable[..., Any]], ...] = (
            # Misc
            (self.tabbar.set_tab_index, self.set_tab_index),
            # Settings
            (s.backstory_viewer_formats_changed,
             self.formatter.update_formats),
            (s.hotkeys_changed, self.update_hotkeys),
        )
        for signal, slot in connects:
            signal.connect(slot)

        t.add_command(Command(
            'new-page', 'New page',
            self.cmd_new_page,
            short_name='n',
            args=ArgumentRules.REQUIRED,
        ))
        t.add_command(Command(
            'delete-page', 'Delete page',
            self.cmd_delete_current_page,
            short_name='d',
        ))
        t.add_command(Command(
            'rename-page', 'Rename page',
            self.cmd_rename_current_page,
            short_name='r',
            args=ArgumentRules.REQUIRED,
        ))
        t.add_command(Command(
            'save-page', 'Save page',
            self.cmd_save_current_page,
            short_name='s',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'print-filename', 'Print name of the active file',
            self.cmd_print_filename,
            short_name='f',
        ))
        t.add_command(Command(
            'count-words', 'Print the page\'s wordcount',
            self.cmd_count_words,
            short_name='c',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'quit', 'Quit (q! to force)',
            self.cmd_quit,
            short_name='q',
        ))
        t.add_command(Command(
            'revision-control', 'Revision control',
            self.cmd_revision_control,
            short_name='#',
        ))
        t.add_command(Command(
            'external-edit', 'Open in external program/editor',
            self.cmd_external_edit,
            short_name='x',
            args=ArgumentRules.NONE,
        ))
        t.add_command(Command(
            'search-and-replace', 'Search/replace',
            self.textarea.search_and_replace,
            short_name='/',
            args=ArgumentRules.REQUIRED,
            strip_input=False,
        ))
        t.add_command(Command(
            'color-picker', 'Color picker',
            self.show_color_picker,
            short_name='p',
            args=ArgumentRules.NONE,
        ))

    def update_hotkeys(self, hotkeys: Dict[str, str]) -> None:
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(hotkeys[key]))

    def show_color_picker(self) -> None:
        if self.in_timeline_mode():
            cursor = self.textarea.textCursor()
            block = cursor.block()
            prefix = block.text()[:cursor.positionInBlock()].rsplit(' ', 1)[-1]
            suffix = block.text()[cursor.positionInBlock():].split(' ', 1)[0]
            text = prefix + suffix
            if text[:3] not in {'fg:', 'bg:'}:
                self.terminal.error('Cursor has to be in a fg/bg field')
                return
            start_color: Union[QtGui.QColor, Qt.GlobalColor]
            try:
                start_color = QtGui.QColor(text[3:])
            except Exception:
                start_color = Qt.white
            new_color = QtWidgets.QColorDialog.getColor(start_color, self)
            if not new_color.isValid():
                return
            cursor.setPosition(cursor.position() - len(prefix))
            cursor.setPosition(cursor.position() + len(text),
                               QtGui.QTextCursor.KeepAnchor)
            cursor.insertText(text[:3] + new_color.name(QtGui.QColor.HexRgb))
            self.textarea.setTextCursor(cursor)
        else:
            self.terminal.error('Color picker is only available '
                                'in timeline mode')

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
                data = read_metadata(file)[1]
            except Exception as e:
                print(str(e))
                self.terminal.error('Something went wrong '
                                    'when loading the revision')
            else:
                self.textarea.setPlainText(data)
                self.textarea.document().setModified(False)
                self.revisionactive = True
                self.revisionnotice.setText(f'Showing revision {arg}. '
                                            f'Changes will not be saved.')
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
        super().__init__(parent, history_file=history_file, short_mode=True)
        self.output_field.hide()
        self.hide()
