from os.path import join
import re

from PyQt4.QtCore import pyqtSignal, Qt, QUrl
from PyQt4 import QtGui, QtWebKit

from libsyntyche.common import kill_theming, read_file, local_path


class InfoPanel(QtGui.QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QtGui.QGridLayout(self)
        kill_theming(layout)
        class InfoPanelLabel(QtGui.QLabel): pass
        self.label = InfoPanelLabel()
        layout.addWidget(self.label, 1, 0, Qt.AlignHCenter)
        self.show()

    def set_data(self, data):
        s = "<strong>{fname}</strong>\t&nbsp;\t{wordcount}"
        self.label.setText(s.format(
            fname=data.title,
            wordcount="<em>({:,})</em>".format(data.wordcount)
        ))


class ViewerFrame(QtGui.QFrame):

    set_fullscreen = pyqtSignal(bool)
    show_index = pyqtSignal()

    def __init__(self, parent):
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
            key: QtGui.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }

        self.template = read_file(local_path(join('templates', 'viewer_page_template.html')))
        self.css = "" # Is set every time the config is reloaded
        self.rawtext = ""
        self.formatconverters = []
        self.chapterstrings = []

        # Layout
        layout = QtGui.QVBoxLayout(self)
        kill_theming(layout)

        self.webview = QtWebKit.QWebView(self)
        layout.addWidget(self.webview)
        layout.setStretchFactor(self.webview, 1)
        self.webview.settings().setDefaultTextEncoding('utf-8')

        self.info_panel = InfoPanel(self)
        layout.addWidget(self.info_panel, 0)

    def update_settings(self, settings):
        self.formatconverters = settings['formatting converters']
        self.chapterstrings = settings['chapter strings']
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.info_panel.setHidden(self.fullscreen)

    def zoom_in(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()+0.1)

    def zoom_out(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()-0.1)

    def zoom_reset(self):
        self.webview.setZoomFactor(1)

    def goto_index(self):
        self.setDisabled(True)
        self.show_index.emit()

    def view_page(self, data):
        self.setEnabled(True)
        self.data = data
        self.info_panel.set_data(data)
        self.rawtext = format_rawtext(read_file(data.file), self.formatconverters,
                                      self.chapterstrings)
        self.set_html()

    def update_css(self):
        frame = self.webview.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        self.set_html()
        frame.setScrollBarValue(Qt.Vertical, pos)

    def set_html(self):
        html = self.template.format(title=self.data.title, body=self.rawtext, css=self.css)
        self.webview.setHtml(html)


def format_rawtext(text, formatconverters, chapterstrings):
    """
    Format the text according to the format and chapter regexes.
    Make sure that the chapter lines aren't touched by the generic formatting.
    """
    def format_chunk(chunklines):
        """ Apply the formatting regexes on a chunk of the text. """
        chunk = '\n'.join(chunklines)
        for x in formatconverters:
            if len(x) == 2:
                chunk = re.sub(x[0], x[1], chunk)
            elif len(x) == 3:
                chunk = replace_in_selection(x[0], x[1], x[2], chunk)
        return chunk
    lines = text.splitlines()
    def get_parts():
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
                    yield '<h2>'+template.format(**match.groupdict()).strip()+'</h2>'
                    oldn = n+1
                    break
        # If there's any text left, format and yield it
        if oldn < len(lines)-1:
            yield format_chunk(lines[oldn:])
    return '\n'.join(get_parts())

def replace_in_selection(rx, rep, selrx, text):
    chunks = []
    selections = re.finditer(selrx, text)
    for sel in selections:
        x = re.sub(rx, rep, sel.group(0))
        chunks.append((sel.start(), sel.end(), x))
    # Do this backwards to avoid messing up the positions of the chunks
    for start, end, payload in chunks[::-1]:
        text = text[:start] + payload + text[end:]
    return text
