from PyQt4.QtCore import pyqtSignal, Qt, QUrl
from PyQt4 import QtGui, QtWebKit

from libsyntyche.common import kill_theming, set_hotkey, read_file, local_path
import infopanel


class ViewerFrame(QtGui.QFrame):

    set_fullscreen = pyqtSignal(bool)
    show_index = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.fullscreen = False
        self.setDisabled(True)

        self.hotkeys_set = False

        self.template = read_file(local_path('viewer_page_template.html'))
        self.css = "" # Is set every time the config is reloaded
        self.rawtext = ""

        # Layout
        layout = QtGui.QVBoxLayout(self)
        kill_theming(layout)

        self.webview = QtWebKit.QWebView(self)
        layout.addWidget(self.webview)
        layout.setStretchFactor(self.webview, 1)
        self.webview.settings().setDefaultTextEncoding('utf-8')

        self.info_panel = infopanel.InfoPanel(self)
        layout.addWidget(self.info_panel)
        layout.setStretchFactor(self.info_panel, 0)

    def set_hotkeys(self, hotkeys):
        if self.hotkeys_set:
            return
        self.hotkeys_set = True
        for key in hotkeys['home']:
            set_hotkey(key, self, self.goto_index)
        for key in hotkeys['toggle fullscreen']:
            set_hotkey(key, self, self.toggle_fullscreen)
        for key in hotkeys['zoom in']:
            set_hotkey(key, self, self.zoom_in)
        for key in hotkeys['zoom out']:
            set_hotkey(key, self, self.zoom_out)
        for key in hotkeys['reset zoom']:
            set_hotkey(key, self, self.zoom_reset)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.info_panel.set_fullscreen(self.fullscreen)

    def zoom_in(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()+0.1)

    def zoom_out(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()-0.1)

    def zoom_reset(self):
        self.webview.setZoomFactor(1)

    def view_page(self, data):
        self.setEnabled(True)
        self.data = data
        self.info_panel.set_data(data)
        self.rawtext = read_file(data['page']).replace('\n', '<br>')
        self.set_html()

    def update_css(self):
        frame = self.webview.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        self.set_html()
        frame.setScrollBarValue(Qt.Vertical, pos)

    def set_html(self):
        html = self.template.format(title=self.data['title'], body=self.rawtext, css=self.css)
        self.webview.setHtml(html)

    def goto_index(self):
        self.setDisabled(True)
        self.show_index.emit()
