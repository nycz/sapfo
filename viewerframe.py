import os
import os.path
from os.path import join
import re

from PyQt4 import QtCore, QtGui, QtWebKit

from libsyntyche import common
import infopanel


class ViewerFrame(QtGui.QFrame):

    class WebView(QtWebKit.QWebView):
        previous = QtCore.pyqtSignal()
        next = QtCore.pyqtSignal()
        wheel_event = QtCore.pyqtSignal(int)
        # Overrides
        def mouseReleaseEvent(self, ev):
            if ev.button() == QtCore.Qt.XButton1:
                self.previous.emit()
            elif ev.button() == QtCore.Qt.XButton2:
                self.next.emit()
            else:
                super().mouseReleaseEvent(ev)

        def wheelEvent(self, ev):
            viewport_size = self.page().viewportSize()
            true_size = self.page().currentFrame().contentsSize()
            # If there are scrollbars, do the regular thing
            if true_size.width() > viewport_size.width() \
                    or true_size.height() > viewport_size.height():
                super().wheelEvent(ev)
            else:
                self.wheel_event.emit(ev.delta())

    set_fullscreen = QtCore.pyqtSignal(bool)
    show_index = QtCore.pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.pages = []
        self.page = 0
        self.fullscreen = False
        self.setDisabled(True)

        # Layout
        layout = QtGui.QVBoxLayout(self)
        common.kill_theming(layout)

        self.webview = self.WebView(self)
        layout.addWidget(self.webview)
        layout.setStretchFactor(self.webview, 1)

        self.info_panel = infopanel.InfoPanel(self)
        layout.addWidget(self.info_panel)
        layout.setStretchFactor(self.info_panel, 0)

        # Signals
        self.webview.next.connect(self.next)
        self.webview.previous.connect(self.previous)
        self.webview.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.webview.linkClicked.connect(self.link_clicked)
        self.webview.wheel_event.connect(self.wheel_event)

    def set_hotkeys(self, hotkeys):
        for key in hotkeys['next']:
            common.set_hotkey(key, self, self.next)
        for key in hotkeys['previous']:
            common.set_hotkey(key, self, self.previous)
        for key in hotkeys['home']:
            common.set_hotkey(key, self, self.goto_index)
        for key in hotkeys['toggle fullscreen']:
            common.set_hotkey(key, self, self.toggle_fullscreen)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.info_panel.set_fullscreen(self.fullscreen)

    def wheel_event(self, delta):
        # Negative delta means scrolling towards you
        if delta < 0:
            self.next()
        elif delta > 0:
            self.previous()

    def link_clicked(self, url):
        if not url.isLocalFile():
            import webbrowser
            webbrowser.open_new_tab(url.toString())

    def start(self, data):
        self.info_panel.set_data(data)
        self.setEnabled(True)
        self.pages = data['pages']
        self.page = 0
        self.set_page()

    def set_page(self):
        self.webview.load(QtCore.QUrl.fromLocalFile(self.pages[self.page]))
        self.info_panel.set_data(pagenr=self.page)

    def next(self):
        if self.page < len(self.pages)-1:
            self.page += 1
            self.set_page()

    def previous(self):
        if self.page > 0:
            self.page -= 1
            self.set_page()

    def goto_index(self):
        self.setDisabled(True)
        self.show_index.emit()
