import re
from typing import Dict, Iterable, List, Tuple, Union

from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtGui, QtWidgets

from .common import LOCAL_DIR
from .declarative import hbox, Stretch, vbox
from .taggedlist import Entry


FormatConverters = List[Union[Tuple[str, str, str], Tuple[str, str]]]
ChapterStrings = List[Tuple[str, str]]


class InfoPanel(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)

        class InfoPanelLabel(QtWidgets.QLabel):
            pass
        self.label = InfoPanelLabel()
        self.setLayout(hbox(Stretch, self.label, Stretch))
        self.show()

    def set_data(self, data: Entry) -> None:
        self.label.setText(f'<strong>{data.title}</strong>\t&nbsp;\t'
                           f'<em>({data.wordcount:,})</em>')


class StoryView(QtWidgets.QFrame):
    set_fullscreen = pyqtSignal(bool)
    show_index = pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.fullscreen = False
        self.setDisabled(True)
        hotkeypairs = (
            ('home', self.goto_index),
            ('toggle fullscreen', self.toggle_fullscreen),
            ('zoom in', self.zoom_in),
            ('zoom out', self.zoom_out),
            ('reset zoom', self.zoom_reset)
        )
        self.hotkeys = {
            key: QtWidgets.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }
        self.template = (LOCAL_DIR / 'data' / 'templates'
                         / 'viewer_page_template.html'
                         ).read_text(encoding='utf-8')
        self.css = ''  # Is set every time the config is reloaded
        self.rawtext = ''
        self.formatconverters: FormatConverters = []
        self.chapterstrings: ChapterStrings = []

        self.textview = QtWidgets.QTextEdit(self)
        self.textview.setReadOnly(True)
        self.info_panel = InfoPanel(self)
        self.setLayout(vbox(Stretch(self.textview), self.info_panel))

    def update_settings(self, settings: Dict) -> None:
        self.formatconverters = settings['formatting converters']
        self.chapterstrings = settings['chapter strings']
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.info_panel.setHidden(self.fullscreen)

    def zoom_in(self) -> None:
        self.textview.zoomIn()

    def zoom_out(self) -> None:
        self.textview.zoomOut()

    def zoom_reset(self) -> None:
        pass

    def goto_index(self) -> None:
        self.setDisabled(True)
        self.show_index.emit()

    def view_page(self, entry: Entry) -> None:
        self.setEnabled(True)
        self.data = entry
        self.info_panel.set_data(entry)
        self.rawtext = format_rawtext(entry.file.read_text(encoding='utf-8'),
                                      self.formatconverters,
                                      self.chapterstrings)
        self.set_html()

    def update_css(self) -> None:
        pos = self.textview.verticalScrollBar().value()
        self.set_html()
        self.textview.verticalScrollBar().setValue(pos)

    def set_html(self) -> None:
        html = self.template.format(title=self.data.title, body=self.rawtext,
                                    css=self.css)
        self.textview.setHtml(html)


def format_rawtext(text: str,
                   formatconverters: FormatConverters,
                   chapterstrings: ChapterStrings) -> str:
    """
    Format the text according to the format and chapter regexes.
    Make sure that the chapter lines aren't touched by the generic formatting.
    """
    def format_chunk(chunklines: Iterable[str]) -> str:
        """ Apply the formatting regexes on a chunk of the text. """
        chunk = '\n'.join(chunklines)
        for x in formatconverters:
            if len(x) == 2:
                chunk = re.sub(x[0], x[1], chunk)
            elif len(x) == 3:
                chunk = replace_in_selection(x[0], x[1], x[2], chunk)
        return chunk
    lines = text.splitlines()

    def get_parts() -> Iterable[str]:
        """
        Return an iterator that yields each relevant chunk, either a chapter
        line or a chunk of formatted text, in the correct order.
        """
        oldn = 0
        for n, line in enumerate(lines):
            for rx_str, template in chapterstrings:
                match = re.match(rx_str, line)
                if match:
                    # If there's any text to format, yield it
                    if n > oldn:
                        yield format_chunk(lines[oldn:n])
                    # Yield the formatted chapter line
                    yield f'<h2>{template.format(**match.groupdict()).strip()}</h2>'
                    oldn = n+1
                    break
        # If there's any text left, format and yield it
        if oldn < len(lines)-1:
            yield format_chunk(lines[oldn:])
    return '\n'.join(get_parts())


def replace_in_selection(rx: str, rep: str, selrx: str, text: str) -> str:
    chunks: List[Tuple[int, int, str]] = []
    selections = re.finditer(selrx, text)
    for sel in selections:
        x = re.sub(rx, rep, sel.group(0))
        chunks.append((sel.start(), sel.end(), x))
    # Do this backwards to avoid messing up the positions of the chunks
    for start, end, payload in chunks[::-1]:
        text = text[:start] + payload + text[end:]
    return text
