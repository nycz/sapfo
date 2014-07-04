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

        self.rawtext_wrapper = read_file(local_path('rawtext_wrapper.html'))

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

        # Signals
        self.webview.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.webview.linkClicked.connect(self.link_clicked)

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

    def wheel_event(self, delta):
        # Negative delta means scrolling towards you
        if delta < 0:
            self.next()
        elif delta > 0:
            self.previous()

    def zoom_in(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()+0.1)

    def zoom_out(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()-0.1)

    def zoom_reset(self):
        self.webview.setZoomFactor(1)

    def link_clicked(self, url):
        if not url.isLocalFile():
            import webbrowser
            webbrowser.open_new_tab(url.toString())

    def view_page(self, data):
        self.info_panel.set_data(data)
        self.setEnabled(True)
        rawtext = read_file(data['page']).replace('\n', '<br>')
        html = self.rawtext_wrapper.format(title=data['title'], body=rawtext)
        self.webview.setHtml(html)

    def goto_index(self):
        self.setDisabled(True)
        self.show_index.emit()
